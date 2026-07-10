#!/usr/bin/env python3
"""Deploy entrypoint — Felix Truthful Reporting trust-scan timer (#683, WP04).

Mission: ``felix-truthful-reporting-01KX6MN5`` (WP04).

Installs the ``felix-trust-scan.{service,timer}`` systemd **user** units
under the ``claude`` account on office2, enables the timer, runs a preflight
self-test of the scan runner, and triggers a prompt-sync tick to verify the
fleet doctrine (WP01) landed in the deployed ``AGENTS.md`` files — all before
declaring success. Tier 3 (Logic/Workflow — installs a user timer; no Tier
0/1/2 action). Rebaseline is **not required** (gap `#621` — agent prompts are
an *unmonitored* audited surface; ``audit.sh`` does not hash deployed
``AGENTS.md``, and the detector/systemd code is not a hashed baseline
either).

Strict, halt-on-error order:

  1. **Install units** — copy ``felix-trust-scan.service`` +
     ``felix-trust-scan.timer`` into ``~/.config/systemd/user/``.
  2. **``daemon-reload`` + ``enable --now``** — a repo unit file does
     nothing until installed *and* daemon-reloaded (#701/#699/#706 deploy
     lessons).
  3. **Preflight self-test** — ``python3 -m scripts.trust.run_trust_scan
     --preflight --json`` (may exit 2 on a hard scan-inability fault; a
     non-zero self-test fails the deploy).
  4. **Prompt-sync verification (Codex finding 10)** — trigger
     ``systemctl --user start agent-prompt-sync.service`` and grep the
     deployed ``main`` ``AGENTS.md`` for the truthful-reporting doctrine
     marker (WP01), rather than waiting for the 5-minute prompt-sync timer.
  5. **Report via the ``#701`` bus** — outcome (success/failure) is emitted
     through ``scripts.common.alert_bus.emit``; no parallel channel.

No auto-rollback — on any failure the script prints recovery instructions
and exits non-zero.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects** on office2.
  Safe to run anywhere (off-office2 too).
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (install / enable / self-test / prompt-sync-verify).
  Nothing is rolled back; recovery instructions are printed to stderr.
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

# felix-deployer invokes the entrypoint by path (not via `python3 -m`), so the
# repo root is not on sys.path unless we put it there ourselves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.common.alert_bus import emit  # noqa: E402
from scripts.common.alert_bus.model import Alert, Severity  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants.
# --------------------------------------------------------------------------- #

_UNIT_SOURCE_DIR = _REPO_ROOT / "scripts" / "office2"
_UNIT_NAMES = ("felix-trust-scan.service", "felix-trust-scan.timer")
_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

_TIMER_UNIT = "felix-trust-scan.timer"

_PREFLIGHT_ARGV = [
    sys.executable,
    "-m",
    "scripts.trust.run_trust_scan",
    "--preflight",
    "--json",
]

# The deployed location of `main`'s AGENTS.md (per
# docs/design/architecture/data/service-inventory.json services.openclaw.
# agents.main.workspace) — the prompt-sync pipeline copies
# scripts/openclaw/agents/main/AGENTS.md here.
_MAIN_DEPLOYED_AGENTS_MD = Path("/data/services/openclaw/data/AGENTS.md")

# Stable substring of the WP01 truthful-reporting doctrine block. Kept
# loose (case-insensitive "truthful" anchor) rather than the full literal so
# this verification step does not become a second, drift-prone copy of
# WP01's exact wording — WP01's own fleet-guard test
# (scripts/openclaw/agents/tests/test_truthful_doctrine.py) is the source of
# truth for the literal; this is a deploy-time smoke check that *some*
# truthful-reporting doctrine landed in the synced prompt.
_DOCTRINE_MARKER = "truthful"


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit a summary line + a JSON detail line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _print_recovery(lines: list[str]) -> None:
    """Print manual-recovery guidance to stderr (no auto-rollback)."""
    sys.stderr.write("RECOVERY (manual — this deploy does not roll back):\n")
    for line in lines:
        sys.stderr.write(f"  - {line}\n")


def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Execute *argv* and return (returncode, stdout, stderr).

    A missing executable (``FileNotFoundError`` — e.g. ``systemctl`` absent
    from a non-office2 dry-run sandbox) is reported as rc=127 with the
    exception text on stderr rather than raising.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- #
# Step 1 — install the systemd user units.
# --------------------------------------------------------------------------- #


def _step_install_units() -> tuple[bool, dict]:
    details: dict = {"dest_dir": str(_SYSTEMD_USER_DIR)}
    try:
        _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        installed = []
        for unit_name in _UNIT_NAMES:
            src = _UNIT_SOURCE_DIR / unit_name
            dest = _SYSTEMD_USER_DIR / unit_name
            shutil.copyfile(src, dest)
            installed.append(str(dest))
        details["installed"] = installed
        return True, details
    except OSError as exc:
        details["error"] = str(exc)
        return False, details


# --------------------------------------------------------------------------- #
# Step 2 — daemon-reload + enable --now.
# --------------------------------------------------------------------------- #


def _step_enable_timer() -> tuple[bool, dict]:
    details: dict = {}

    rc, stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    details["daemon_reload_rc"] = rc
    if rc != 0:
        details["daemon_reload_stderr"] = stderr[:400]
        return False, details

    rc, stdout, stderr = _run(["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    details["enable_now_rc"] = rc
    if rc != 0:
        details["enable_now_stderr"] = stderr[:400]
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Step 3 — preflight self-test.
# --------------------------------------------------------------------------- #


def _step_preflight_self_test() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(_PREFLIGHT_ARGV, cwd=_REPO_ROOT)
    details = {
        "self_test_rc": rc,
        "self_test_stdout_excerpt": stdout[:400],
        "self_test_stderr_excerpt": stderr[:400],
    }
    return rc == 0, details


# --------------------------------------------------------------------------- #
# Step 4 — prompt-sync trigger + deployed AGENTS.md verification.
# --------------------------------------------------------------------------- #


def _step_prompt_sync_and_verify() -> tuple[bool, dict]:
    details: dict = {}

    rc, stdout, stderr = _run(
        ["systemctl", "--user", "start", "agent-prompt-sync.service"]
    )
    details["prompt_sync_start_rc"] = rc
    if rc != 0:
        details["prompt_sync_start_stderr"] = stderr[:400]
        return False, details

    try:
        content = _MAIN_DEPLOYED_AGENTS_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        details["read_error"] = str(exc)
        details["path"] = str(_MAIN_DEPLOYED_AGENTS_MD)
        return False, details

    marker_present = _DOCTRINE_MARKER.lower() in content.lower()
    details["path"] = str(_MAIN_DEPLOYED_AGENTS_MD)
    details["marker"] = _DOCTRINE_MARKER
    details["marker_present"] = marker_present
    return marker_present, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run() -> int:
    _print_line(
        "DRY-RUN",
        f"would install {', '.join(_UNIT_NAMES)} into {_SYSTEMD_USER_DIR}",
        {"units": list(_UNIT_NAMES)},
    )
    _print_line(
        "DRY-RUN",
        "would run `systemctl --user daemon-reload` then "
        f"`systemctl --user enable --now {_TIMER_UNIT}`",
        {},
    )
    _print_line(
        "DRY-RUN",
        "would run `python3 -m scripts.trust.run_trust_scan --preflight --json` "
        "as a self-test",
        {"argv": _PREFLIGHT_ARGV},
    )
    _print_line(
        "DRY-RUN",
        "would trigger `systemctl --user start agent-prompt-sync.service` and "
        f"verify the doctrine marker in {_MAIN_DEPLOYED_AGENTS_MD}",
        {"marker": _DOCTRINE_MARKER},
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-trust-scan deploy succeeded"
            if ok
            else f"felix-trust-scan deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-truthful-reporting",
                severity=severity,
                title=title,
                description=(
                    "Deployed the felix-trust-scan timer + preflight self-test "
                    "+ prompt-sync verification."
                    if ok
                    else f"Deploy halted at phase {phase!r}."
                ),
                details={key: str(value) for key, value in details.items()},
            )
        )
    except Exception:  # noqa: BLE001 - fail-safe: reporting must never break the deploy
        pass


def _apply() -> int:
    ok, details = _step_install_units()
    _print_line("APPLY", "install units " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Confirm {_UNIT_SOURCE_DIR} contains {', '.join(_UNIT_NAMES)}.",
                f"Confirm {_SYSTEMD_USER_DIR} is writable by the claude user.",
            ]
        )
        _report(ok=False, phase="install_units", details=details)
        return 1

    ok, details = _step_enable_timer()
    _print_line("APPLY", "enable timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Inspect the systemctl output above.",
                f"Manually: systemctl --user daemon-reload && "
                f"systemctl --user enable --now {_TIMER_UNIT}",
            ]
        )
        _report(ok=False, phase="enable_timer", details=details)
        return 1

    ok, details = _step_preflight_self_test()
    _print_line("APPLY", "preflight self-test " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The preflight self-test failed (scan-inability — e.g. an "
                "unreadable baseline).",
                "Inspect the self_test_stderr_excerpt above.",
                "Manually: python3 -m scripts.trust.run_trust_scan --preflight --json",
            ]
        )
        _report(ok=False, phase="preflight_self_test", details=details)
        return 1

    ok, details = _step_prompt_sync_and_verify()
    _print_line(
        "APPLY", "prompt-sync + AGENTS.md verify " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "Confirm agent-prompt-sync.service ran successfully:",
                "  systemctl --user status agent-prompt-sync.service",
                f"Confirm the doctrine block landed in {_MAIN_DEPLOYED_AGENTS_MD} "
                "(WP01 fleet doctrine).",
                "This may indicate WP01's doctrine commit has not reached main yet.",
            ]
        )
        _report(ok=False, phase="prompt_sync_verify", details=details)
        return 1

    _report(ok=True, phase="complete", details=details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: deploy-truthful-reporting.py --dry-run|--apply\n"
        )
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
