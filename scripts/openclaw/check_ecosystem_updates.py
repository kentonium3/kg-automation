"""OpenClaw ecosystem update-availability check (#628).

Weekly deterministic detection of available upgrades across the whole OpenClaw
ecosystem on office2 — the openclaw **core** package plus every installed
``@openclaw/*`` **channel plugin** — so a core-vs-plugin version gap (the
#588/#617 silent WhatsApp DM-reply break) or a missed core release is surfaced
*before* it bites, ecosystem-wide.

Output discipline (the Felix Output-Discipline pattern):

* **Silent no-op** when everything is current — exit 0, no alert. A weekly
  timer that pages only when there is something to do.
* **One ntfy digest** (via the #701 felix-alert bus) when >=1 update is
  available OR a component check failed — a single WARN listing each component
  ``name: current -> latest``, pointing at the upgrade runbook.

Detection is **read-only** (npm registry/global queries + reading plugin
``package.json`` files); the actual upgrade is performed **manually as an
attended Tier-0 change** per ``docs/runbooks/openclaw-ecosystem-upgrade.md`` —
this helper never mutates the runtime.

::

    python3 -m scripts.openclaw.check_ecosystem_updates [--once] [--dry-run] [--self-check]

Deterministic (Constitution Directive 6) — no LLM turn. **Fail-open** (a single
component's probe failure records an error line and the pass continues to the
next component). A completed pass **exits 0 even when updates are found**
(updates -> emit, not a process failure). A non-zero exit is reserved for a
**runner-level** fault (``npm`` absent, the plugin projects dir unreadable at
the top level) so the systemd ``OnFailure=`` shim pages the operator that the
check did not complete a pass.

Modeled on ``scripts/canary/run.py`` (injected runner, fail-open per component,
exit-code discipline, emit via the shared #701 bus).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from scripts.common.alert_bus import Alert, Severity, emit

__all__ = [
    "main",
    "run_pass",
    "CheckResult",
    "ComponentUpdate",
    "ComponentError",
    "PluginInstall",
]

# --------------------------------------------------------------------------- #
# Grounded constants.
# --------------------------------------------------------------------------- #

#: openclaw stores channel plugins under this openclaw-managed tree (NOT
#: npm-global). Each ``projects/<slug>/node_modules/@openclaw/<pkg>`` is one
#: installed plugin; its version lives in that package's ``package.json``. The
#: bundled ``@openclaw/proxyline`` / ``@openclaw/fs-safe`` under openclaw's OWN
#: node_modules are core deps, not channels, and never appear here.
_DEFAULT_PROJECTS_DIR = Path.home() / ".openclaw" / "npm" / "projects"

#: The core package name (npm-global).
_CORE_PACKAGE = "openclaw"

#: Wall-clock ceiling for any single npm call. A weekly check has no reason to
#: hang; a network stall on one component fails that component open, not the run.
_NPM_TIMEOUT = 60

_RUNBOOK = "docs/runbooks/openclaw-ecosystem-upgrade.md"

#: Self-observability tick-signal (mirrors the felix-canary / felix-trust-scan
#: last-tick.json pattern). A weekly check that is SILENT on success cannot be
#: told apart from a check that never ran — so every completed pass rewrites this
#: pointer atomically, and the felix-canary freshness probe (registered in
#: service-inventory.json) pages if it goes stale beyond the weekly window. A
#: runner-level fault raises before the tick is written, so a stalled/broken
#: timer surfaces (freshness) rather than going dark.
_STATE_DIR = Path("/data/services/felix-openclaw-updates/state")
_TICK_PATH = _STATE_DIR / "last-tick.json"


# --------------------------------------------------------------------------- #
# Value objects.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ComponentUpdate:
    """A component with a newer version available."""

    name: str  # "openclaw" or "@openclaw/whatsapp"
    kind: str  # "core" | "plugin"
    current: str
    latest: str


@dataclass(frozen=True)
class ComponentError:
    """A component whose probe failed (fail-open — recorded, pass continues)."""

    name: str
    kind: str
    error: str


@dataclass(frozen=True)
class PluginInstall:
    """One installed @openclaw/* plugin at one install site (project tree)."""

    name: str
    version: str
    project: str  # the projects/<slug> dir name, for reporting per-tree drift


@dataclass
class CheckResult:
    """Outcome of one pass."""

    checked: int = 0
    updates: list[ComponentUpdate] = field(default_factory=list)
    errors: list[ComponentError] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        """True when the pass has anything worth paging about."""
        return bool(self.updates) or bool(self.errors)


# The injectable command runner: (argv) -> CompletedProcess. Defaults to a real
# subprocess call; tests pass a fake so they never touch npm or the network.
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        timeout=_NPM_TIMEOUT,
    )


# --------------------------------------------------------------------------- #
# Detection.
# --------------------------------------------------------------------------- #


def check_core(runner: Runner) -> tuple[ComponentUpdate | None, ComponentError | None]:
    """Return an update (or error) for the openclaw **core** global package.

    Uses ``npm outdated -g --json openclaw``: npm prints ``{}`` (or nothing) and
    exits 0 when current, or a ``{"openclaw": {"current", "latest", ...}}`` map
    and exits **1** when an upgrade exists. Exit 1 is npm's normal
    "outdated found" signal, **not** a failure — we parse stdout regardless and
    only treat unparseable output as an error.
    """
    try:
        proc = runner(["npm", "outdated", "-g", "--json", _CORE_PACKAGE])
    except (subprocess.SubprocessError, OSError) as exc:
        return None, ComponentError(_CORE_PACKAGE, "core", f"npm outdated failed: {exc}")

    raw = (proc.stdout or "").strip()
    if not raw:
        # Empty output = nothing outdated (npm 0-exit, current).
        return None, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        detail = (proc.stderr or raw).strip()[:200]
        return None, ComponentError(_CORE_PACKAGE, "core", f"unparseable npm output: {detail}")

    entry = parsed.get(_CORE_PACKAGE)
    if not isinstance(entry, dict):
        return None, None  # openclaw not listed -> current
    current = str(entry.get("current", "") or "")
    latest = str(entry.get("latest", "") or "")
    if latest and current and latest != current:
        return ComponentUpdate(_CORE_PACKAGE, "core", current, latest), None
    return None, None


def discover_plugins(projects_dir: Path) -> list[PluginInstall]:
    """List **every** installed ``@openclaw/*`` plugin (one entry per install site).

    Enumerates ``projects/*/node_modules/@openclaw/*/package.json``. It does NOT
    dedup: a plugin installed under more than one project tree yields one entry
    per tree, so a stale copy in one tree is never masked by a current copy in
    another (this feature exists to catch exactly that silent drift). Version
    strings are carried verbatim and only ever compared for **equality** against
    the registry ``latest`` — never ordered — so date-tag strings like
    ``2026.7.2`` vs ``2026.7.11`` can't be mis-ranked. A malformed
    ``package.json`` is skipped silently; an unreadable *tree* is a runner-level
    fault handled by the caller.
    """
    installs: list[PluginInstall] = []
    for pkg_json in sorted(projects_dir.glob("*/node_modules/@openclaw/*/package.json")):
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("name")
        version = data.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if not name.startswith("@openclaw/"):
            continue
        # projects/<slug>/node_modules/@openclaw/<pkg>/package.json -> <slug>
        project = pkg_json.parents[3].name
        installs.append(PluginInstall(name, version, project))
    return installs


def npm_latest(runner: Runner, package: str) -> str:
    """Return the registry ``latest`` dist-tag version of *package* (stripped).

    Raises on a non-zero npm exit or empty output so the caller can record a
    per-component error and continue (fail-open).
    """
    proc = runner(["npm", "view", package, "version"])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        raise RuntimeError(f"npm view exit {proc.returncode}: {detail}")
    latest = (proc.stdout or "").strip()
    if not latest:
        raise RuntimeError("npm view returned no version")
    return latest


def check_plugins(
    runner: Runner, projects_dir: Path
) -> tuple[list[ComponentUpdate], list[ComponentError], int]:
    """Check every installed ``@openclaw/*`` plugin install-site against the registry.

    A plugin install is flagged when its installed version differs from the
    registry ``latest`` dist-tag (detection-only inequality — the operator judges
    the actual upgrade in the runbook; date-tag semver ordering is deliberately
    avoided as fragile). The registry is queried once per distinct plugin name;
    a lookup failure records one error for that name and skips its installs. Two
    installs of the same name at the same outdated version collapse to a single
    digest line, but two *different* installed versions are both reported.

    Returns ``(updates, errors, install_sites_checked)`` — the count is the
    number of install sites enumerated (for the tick's diagnostic field).
    """
    installs = discover_plugins(projects_dir)
    names = sorted({inst.name for inst in installs})

    latest_by_name: dict[str, str] = {}
    errors: list[ComponentError] = []
    for name in names:
        try:
            latest_by_name[name] = npm_latest(runner, name)
        except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
            errors.append(ComponentError(name, "plugin", str(exc)))

    updates: list[ComponentUpdate] = []
    seen: set[tuple[str, str, str]] = set()
    for inst in installs:
        latest = latest_by_name.get(inst.name)
        if latest is None:  # its registry lookup failed (already recorded)
            continue
        if latest != inst.version:
            key = (inst.name, inst.version, latest)
            if key not in seen:
                seen.add(key)
                updates.append(ComponentUpdate(inst.name, "plugin", inst.version, latest))
    return updates, errors, len(installs)


# --------------------------------------------------------------------------- #
# Digest.
# --------------------------------------------------------------------------- #


def _render_digest(result: CheckResult) -> tuple[str, str]:
    """Return (title, body) for the ntfy digest — only called when there are findings."""
    n = len(result.updates)
    if n and result.errors:
        title = f"OpenClaw: {n} update(s) available, {len(result.errors)} check error(s)"
    elif n:
        title = f"OpenClaw: {n} ecosystem update(s) available"
    else:
        title = f"OpenClaw update check: {len(result.errors)} check error(s)"

    lines: list[str] = []
    if result.updates:
        lines.append("Updates available:")
        for u in result.updates:
            lines.append(f"  - {u.name} ({u.kind}): {u.current} -> {u.latest}")
    if result.errors:
        lines.append("Check errors (component skipped, pass continued):")
        for e in result.errors:
            lines.append(f"  - {e.name} ({e.kind}): {e.error}")
    return title, "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tick-signal (self-observability).
# --------------------------------------------------------------------------- #


def _write_tick(tick_path: Path, result: CheckResult, now: datetime) -> None:
    """Atomically rewrite the last-tick.json freshness pointer for a completed pass.

    Raises ``OSError`` on a state-dir/write failure — the caller treats that as a
    runner-level fault (a completed check that cannot record it is not a healthy
    pass), consistent with the felix-canary "state dir unwritable" contract.
    """
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "success",
        "completed_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updates_available": len(result.updates),
        "check_errors": len(result.errors),
        "components_checked": result.checked,
    }
    fd, tmp_name = tempfile.mkstemp(dir=str(tick_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, tick_path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# Pass orchestration.
# --------------------------------------------------------------------------- #


def run_pass(
    *,
    runner: Runner | None = None,
    projects_dir: Path | None = None,
    emitter: Callable[[Alert], object] | None = None,
    tick_path: Path | None = None,
    now: Callable[[], datetime] | None = None,
    dry_run: bool = False,
) -> CheckResult:
    """Run one full ecosystem check; emit a digest iff there are findings.

    Fail-open across components. In ``dry_run`` the digest is composed and
    printed but **not** emitted and **no** tick is written. Raises
    ``RuntimeError`` only on a runner-level fault (npm absent / projects dir
    unreadable / tick unwritable) — the caller maps that to a non-zero exit so
    ``OnFailure=`` fires.
    """
    runner = runner or _default_runner
    projects_dir = projects_dir if projects_dir is not None else _DEFAULT_PROJECTS_DIR
    emitter = emitter or emit
    tick_path = tick_path if tick_path is not None else _TICK_PATH
    now = now or (lambda: datetime.now(timezone.utc))

    if shutil.which("npm") is None:
        raise RuntimeError("npm not found on PATH — cannot check for updates")
    if not projects_dir.is_dir():
        raise RuntimeError(f"openclaw plugin projects dir not readable: {projects_dir}")

    result = CheckResult()

    core_update, core_error = check_core(runner)
    result.checked += 1  # core
    if core_update:
        result.updates.append(core_update)
    if core_error:
        result.errors.append(core_error)

    plugin_updates, plugin_errors, plugin_sites = check_plugins(runner, projects_dir)
    result.checked += plugin_sites  # one per plugin install site
    result.updates.extend(plugin_updates)
    result.errors.extend(plugin_errors)

    if result.has_findings:
        title, body = _render_digest(result)
        severity = Severity.WARN
        action = f"Follow {_RUNBOOK} (attended Tier-0 upgrade)."
        if dry_run:
            sys.stdout.write(f"[dry-run] would emit ({severity.value}): {title}\n{body}\n")
        else:
            emitter(
                Alert(
                    source="felix-openclaw-updates/check",
                    severity=severity,
                    title=title,
                    description=body,
                    action=action,
                    details={"updates": str(len(result.updates)), "errors": str(len(result.errors))},
                )
            )
    else:
        sys.stdout.write("openclaw ecosystem current — no updates available (silent no-op)\n")

    # A completed pass records its own liveness (skip under dry-run — no side
    # effects). A tick-write failure is a runner-level fault (see _write_tick).
    if not dry_run:
        try:
            _write_tick(tick_path, result, now())
        except OSError as exc:
            raise RuntimeError(f"could not write tick-signal {tick_path}: {exc}") from exc

    return result


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #


def _self_check(projects_dir: Path, tick_path: Path) -> int:
    """Verify the runner can operate: npm present + projects dir readable + state writable."""
    problems: list[str] = []
    if shutil.which("npm") is None:
        problems.append("npm not on PATH")
    if not projects_dir.is_dir():
        problems.append(f"projects dir missing: {projects_dir}")
    try:
        tick_path.parent.mkdir(parents=True, exist_ok=True)
        probe = tick_path.parent / ".self-check-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        problems.append(f"state dir not writable ({tick_path.parent}): {exc}")
    if problems:
        sys.stdout.write("status=fail " + "; ".join(problems) + "\n")
        return 1
    sys.stdout.write("status=ok npm present, projects dir readable, state dir writable, alert-bus importable\n")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_ecosystem_updates",
        description="Detect available OpenClaw core + channel-plugin updates (silent unless found).",
    )
    parser.add_argument("--once", action="store_true", help="run a single check pass (the timer mode)")
    parser.add_argument("--dry-run", action="store_true", help="compose but do not emit the digest; no side effects")
    parser.add_argument("--self-check", action="store_true", help="verify prerequisites and exit")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_check:
        return _self_check(_DEFAULT_PROJECTS_DIR, _TICK_PATH)

    try:
        run_pass(dry_run=args.dry_run)
    except RuntimeError as exc:
        sys.stderr.write(f"felix-openclaw-updates: runner-level fault: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
