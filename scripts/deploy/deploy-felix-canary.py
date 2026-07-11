#!/usr/bin/env python3
"""Deploy entrypoint — Felix component-health canary timer (#327, WP06).

Mission: ``felix-canary-registry-01KX8T7B`` (WP06).

Installs the ``felix-canary.{service,timer}`` + ``felix-canary-onfailure.service``
systemd **user** units under the ``claude`` account on office2, **verifies the
deployed command can actually write state + a ledger line under systemd BEFORE
enabling the timer** (F9 — the #703 lesson), and only then enables the 15-min
timer. Tier 3 (Logic/Workflow — installs a user timer + runs a real unit once;
no Tier 0/1/2 action). ``audited_surface: true`` — systemd units are a hashed
audited surface, so felix-deployer auto-rebaselines on the happy path.

Strict, halt-on-error order:

  1. **Install units** — copy ``felix-canary.service``, ``felix-canary.timer``,
     and ``felix-canary-onfailure.service`` into ``~/.config/systemd/user/``.
  2. **``daemon-reload``** — install the unit definitions (a repo unit file does
     nothing until installed + daemon-reloaded — #701/#699/#706 deploy lessons).
  3. **Verify-before-enable gate (F9)** — three sub-steps, all BEFORE the timer
     is enabled so a fresh deploy never pages the operator on an unverified
     false-positive (#711):
       a. ``--self-check`` — inventory readable + alert-bus importable + state
          dir writable → must print ``status=ok``;
       b. **run the REAL unit once** (``systemctl --user start
          felix-canary.service`` — the exact ``ExecStart`` from the installed
          unit, under the unit's user + ``EnvironmentFile``), then assert
          ``last-tick.json`` has a fresh ``completed_at_utc`` AND a ledger line
          landed under ``ledger/<today>.jsonl``. This proves the deployed
          command writes state + ledger under systemd — which ``--dry-run``
          alone cannot (dry-run writes nothing).
  4. **``enable --now``** — start the 15-min timer, reached ONLY after the gate
     passes clean.
  5. **Report via the ``#701`` bus** — outcome (success/failure) is emitted
     through ``scripts.common.alert_bus.emit``; no parallel channel.

**Byte-identical ExecStart guard (#703):** the ``ExecStart`` the self-test path
exercises is derived by PARSING the installed ``felix-canary.service`` file — not
hand-typed — and asserted equal to the canonical expected form. ``systemctl start``
runs that exact same line, so the deploy verification and the live timer can
never diverge.

No auto-rollback — on any failure the script prints recovery instructions and
exits non-zero.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects** on office2.
  Safe to run anywhere (off-office2 too).
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (install / daemon-reload / self-check / real-unit
  verify / enable). Nothing is rolled back; recovery instructions to stderr.
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
_SERVICE_UNIT = "felix-canary.service"
_TIMER_UNIT = "felix-canary.timer"
_ONFAILURE_UNIT = "felix-canary-onfailure.service"
_UNIT_NAMES = (_SERVICE_UNIT, _TIMER_UNIT, _ONFAILURE_UNIT)
_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

# The canonical ExecStart the timer runs (§5 CLI + WP06). The deploy PARSES the
# installed .service and asserts it equals this exact string (#703 byte-identical
# guard) — the self-test then starts that same unit, so the verified command and
# the live timer command are provably identical.
_EXPECTED_EXECSTART = "/usr/bin/python3 -m scripts.canary.run --once"

# The runner's own state + ledger surface (data-model.md; scripts/canary/run.py
# DEFAULT_TICK_PATH / DEFAULT_LEDGER_DIR). The F9 real-unit verify asserts a
# fresh tick + a ledger line land here after `systemctl start`.
_STATE_DIR = Path("/data/services/felix-canary/state")
_TICK_PATH = _STATE_DIR / "last-tick.json"
_LEDGER_DIR = Path("/data/services/felix-canary/ledger")

# The self-check argv — the SAME module the ExecStart runs, in --self-check mode.
_SELF_CHECK_ARGV = [
    sys.executable,
    "-m",
    "scripts.canary.run",
    "--self-check",
]


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


def _parse_execstart(service_path: Path) -> str | None:
    """Return the ExecStart value from an installed .service file, or None.

    Parses the ``[Service]`` section's ``ExecStart=`` line and strips it. Only
    the first ExecStart is honored (a oneshot has exactly one). Returns None if
    no ExecStart line is present.
    """
    for raw in service_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("ExecStart="):
            return line[len("ExecStart="):].strip()
    return None


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
# Step 2 — daemon-reload (install the unit definitions; does NOT start anything).
# --------------------------------------------------------------------------- #


def _step_daemon_reload() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    details: dict = {"daemon_reload_rc": rc}
    if rc != 0:
        details["daemon_reload_stderr"] = stderr[:400]
        return False, details
    return True, details


# --------------------------------------------------------------------------- #
# Step 3 — verify-before-enable gate (F9). Runs BEFORE `enable --now` (#711).
# --------------------------------------------------------------------------- #


def _step_verify_execstart() -> tuple[bool, dict]:
    """#703 byte-identical guard: the INSTALLED .service ExecStart must equal
    the canonical string the self-test path exercises."""
    installed_service = _SYSTEMD_USER_DIR / _SERVICE_UNIT
    details: dict = {
        "service_file": str(installed_service),
        "expected_execstart": _EXPECTED_EXECSTART,
    }
    parsed = _parse_execstart(installed_service)
    details["parsed_execstart"] = parsed
    if parsed is None:
        details["error"] = "no ExecStart= line in the installed .service file"
        return False, details
    if parsed != _EXPECTED_EXECSTART:
        details["error"] = (
            "ExecStart drift: the installed unit does not run the exact command "
            "the deploy verified (#703 byte-identical guard)"
        )
        return False, details
    return True, details


def _step_self_check() -> tuple[bool, dict]:
    """F9(a): --self-check must print status=ok (inventory/bus/state-dir)."""
    rc, stdout, stderr = _run(_SELF_CHECK_ARGV, cwd=_REPO_ROOT)
    details: dict = {
        "self_check_rc": rc,
        "self_check_stdout_excerpt": stdout[:400],
        "self_check_stderr_excerpt": stderr[:400],
    }
    if rc != 0 or "status=ok" not in stdout:
        details["error"] = "self-check did not report status=ok"
        return False, details
    return True, details


def _tick_completed_at(tick_path: Path) -> str | None:
    """Return last-tick.json's completed_at_utc, or None if unreadable/absent."""
    try:
        data = json.loads(tick_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("completed_at_utc")
    return value if isinstance(value, str) else None


def _ledger_line_landed(ledger_dir: Path, day: str) -> bool:
    """True if today's ledger file exists and has at least one non-blank line."""
    path = ledger_dir / f"{day}.jsonl"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.strip() for line in text.splitlines())


def _step_real_unit_verify() -> tuple[bool, dict]:
    """F9(b): run the REAL unit once, then assert a fresh tick + ledger landed.

    Captures the pre-run tick timestamp, starts the actual unit (the exact
    ExecStart the timer runs), then asserts (1) last-tick.json has a
    completed_at_utc that is NEWER than the pre-run value (a genuinely fresh
    write, not a stale file), and (2) a ledger line landed under today's file.
    This proves the deployed command writes state + ledger under systemd — which
    --dry-run cannot, since dry-run writes nothing.
    """
    details: dict = {
        "tick_path": str(_TICK_PATH),
        "ledger_dir": str(_LEDGER_DIR),
    }
    before_ts = _tick_completed_at(_TICK_PATH)
    details["tick_before"] = before_ts

    rc, stdout, stderr = _run(
        ["systemctl", "--user", "start", _SERVICE_UNIT]
    )
    details["unit_start_rc"] = rc
    if rc != 0:
        details["unit_start_stderr"] = stderr[:400]
        details["error"] = "systemctl --user start felix-canary.service failed"
        return False, details

    # Assert a fresh tick-signal write.
    after_ts = _tick_completed_at(_TICK_PATH)
    details["tick_after"] = after_ts
    if after_ts is None:
        details["error"] = "last-tick.json absent or missing completed_at_utc after the real-unit run"
        return False, details
    if before_ts is not None and after_ts == before_ts:
        details["error"] = (
            "last-tick.json completed_at_utc did not advance — the real unit did "
            "not write a fresh tick (stale state file)"
        )
        return False, details

    # Assert a ledger line landed under today's date-partitioned file. The tick
    # was just written above, so anchor 'today' on the tick's own UTC date to
    # avoid a midnight-boundary mismatch.
    day = after_ts[:10]  # ISO-8601 date prefix, e.g. 2026-07-11
    details["ledger_day"] = day
    if not _ledger_line_landed(_LEDGER_DIR, day):
        details["error"] = (
            f"no ledger line landed under {_LEDGER_DIR}/{day}.jsonl after the "
            "real-unit run — the deployed command cannot write the ledger under systemd"
        )
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Step 4 — enable --now (ONLY after the F9 gate passes clean).
# --------------------------------------------------------------------------- #


def _step_enable_timer() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    details: dict = {"enable_now_rc": rc}
    if rc != 0:
        details["enable_now_stderr"] = stderr[:400]
        return False, details
    return True, details


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
        "would run `systemctl --user daemon-reload`",
        {},
    )
    _print_line(
        "DRY-RUN",
        "would assert the installed felix-canary.service ExecStart is "
        f"byte-identical to {_EXPECTED_EXECSTART!r} (#703 guard)",
        {"expected_execstart": _EXPECTED_EXECSTART},
    )
    _print_line(
        "DRY-RUN",
        "would run `python3 -m scripts.canary.run --self-check` and require "
        "status=ok (inventory readable + bus importable + state dir writable)",
        {"argv": _SELF_CHECK_ARGV},
    )
    _print_line(
        "DRY-RUN",
        "would run the REAL unit once (`systemctl --user start "
        "felix-canary.service`) and assert a fresh last-tick.json completed_at_utc "
        "+ a ledger line landed under ledger/<today>.jsonl (F9 — proves state + "
        "ledger write under systemd, which --dry-run cannot)",
        {"tick_path": str(_TICK_PATH), "ledger_dir": str(_LEDGER_DIR)},
    )
    _print_line(
        "DRY-RUN",
        "would (only if the F9 gate is clean) run `systemctl --user enable "
        f"--now {_TIMER_UNIT}`",
        {},
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-canary deploy succeeded"
            if ok
            else f"felix-canary deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-felix-canary",
                severity=severity,
                title=title,
                description=(
                    "Deployed the felix-canary 15-min timer + OnFailure shim; the "
                    "F9 verify-before-enable gate (self-check + real-unit tick/ledger "
                    "assertion) gated the enable."
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

    ok, details = _step_daemon_reload()
    _print_line("APPLY", "daemon-reload " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Inspect the systemctl output above.",
                "Manually: systemctl --user daemon-reload",
            ]
        )
        _report(ok=False, phase="daemon_reload", details=details)
        return 1

    # ---- F9 verify-before-enable gate (all BEFORE `enable --now`, #711). ---- #
    ok, details = _step_verify_execstart()
    _print_line("APPLY", "ExecStart byte-identical guard " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The installed .service ExecStart does not match the command the "
                "deploy verifies (#703). Confirm scripts/office2/felix-canary.service "
                f"ExecStart is exactly: {_EXPECTED_EXECSTART}",
            ]
        )
        _report(ok=False, phase="verify_execstart", details=details)
        return 1

    ok, details = _step_self_check()
    _print_line("APPLY", "self-check " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The --self-check did not report status=ok. Verify locally: "
                "python3 -m scripts.canary.run --self-check",
                "Likely causes: unreadable service-inventory.json, alert-bus import "
                "failure, or an unwritable /data/services/felix-canary/state dir.",
            ]
        )
        _report(ok=False, phase="self_check", details=details)
        return 1

    ok, details = _step_real_unit_verify()
    _print_line("APPLY", "real-unit tick+ledger verify " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The real unit ran but did not write a fresh tick-signal + ledger "
                "line under systemd (F9). The timer was NOT enabled, so no "
                "unverified false-positive can page the operator.",
                "Inspect: systemctl --user status felix-canary.service",
                f"Confirm {_STATE_DIR} and {_LEDGER_DIR} are writable by the claude user.",
            ]
        )
        _report(ok=False, phase="real_unit_verify", details=details)
        return 1

    # ---- Enable ONLY after the full F9 gate is clean. ---------------------- #
    ok, details = _step_enable_timer()
    _print_line("APPLY", "enable timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Inspect the systemctl output above.",
                f"Manually: systemctl --user enable --now {_TIMER_UNIT}",
            ]
        )
        _report(ok=False, phase="enable_timer", details=details)
        return 1

    _report(ok=True, phase="complete", details=details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write("usage: deploy-felix-canary.py --dry-run|--apply\n")
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
