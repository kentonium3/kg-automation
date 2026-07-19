#!/usr/bin/env python3
"""Deploy entrypoint — weekly OpenClaw ecosystem update-availability check (#628).

Installs the ``felix-openclaw-updates.{service,timer}`` +
``felix-openclaw-updates-onfailure.service`` systemd **user** units under the
``claude`` account on office2, **verifies the deployed command actually runs to a
clean pass under systemd BEFORE enabling the timer** (the #703/#711 lesson — a
fresh deploy must never leave a broken-but-enabled timer), then enables the
weekly timer. Tier 3 (Logic/Workflow — installs a user timer + runs the real
unit once; no Tier 0/1/2 action). ``audited_surface: true`` — systemd units are
a hashed audited surface, so felix-deployer auto-rebaselines on the happy path.

Strict, halt-on-error order:

  1. **Install units** into ``~/.config/systemd/user/``.
  2. **``daemon-reload``** — a repo unit file does nothing until installed +
     daemon-reloaded.
  3. **Byte-identical ExecStart guard (#703)** — the INSTALLED ``.service``
     ExecStart must equal the canonical string the self-test path exercises, so
     the verified command and the live timer command can never diverge.
  4. **``--self-check``** — npm present + plugin projects dir readable +
     alert-bus importable → must print ``status=ok``.
  5. **Run the REAL unit once** (``systemctl --user start
     felix-openclaw-updates.service``) — for a ``Type=oneshot`` this blocks until
     ExecStart exits and reports non-zero if the run failed, so ``rc==0`` proves
     the deployed command completes a full pass under the unit's user +
     ``EnvironmentFile`` + ``PATH`` (npm resolves, projects dir readable, emit
     path executes). Given live update state this run also fires the genuine
     first digest — the deploy's own live-verify.
  6. **``enable --now``** the weekly timer — reached ONLY after the gate is clean.
  7. **Report** via the ``#701`` felix-alert bus.

No auto-rollback — on any failure the script prints recovery instructions and
exits non-zero. Modeled on ``scripts/deploy/deploy-felix-canary.py``.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects**. Safe anywhere.
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed, OR apply completed every step.
* ``1`` — a step failed. Nothing rolled back; recovery to stderr.
* ``2`` — usage error (missing / wrong mode argument).
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
_SERVICE_UNIT = "felix-openclaw-updates.service"
_TIMER_UNIT = "felix-openclaw-updates.timer"
_ONFAILURE_UNIT = "felix-openclaw-updates-onfailure.service"
_UNIT_NAMES = (_SERVICE_UNIT, _TIMER_UNIT, _ONFAILURE_UNIT)
_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

# The canonical ExecStart the timer runs. The deploy PARSES the installed
# .service and asserts it equals this exact string (#703 byte-identical guard).
_EXPECTED_EXECSTART = "/usr/bin/python3 -m scripts.openclaw.check_ecosystem_updates --once"

# The self-check argv — the SAME module the ExecStart runs, in --self-check mode.
_SELF_CHECK_ARGV = [
    sys.executable,
    "-m",
    "scripts.openclaw.check_ecosystem_updates",
    "--self-check",
]

# The runner's self-observability tick (scripts/openclaw/check_ecosystem_updates.py
# _TICK_PATH). The real-unit verify asserts a fresh tick lands here after
# `systemctl start` — proof the deployed command writes state under systemd.
_TICK_PATH = Path("/data/services/felix-openclaw-updates/state/last-tick.json")


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

    A missing executable (``FileNotFoundError`` — e.g. ``systemctl`` absent from
    a non-office2 dry-run sandbox) is reported as rc=127 with the exception text
    on stderr rather than raising.
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
    """Return the ExecStart value from an installed .service file, or None."""
    for raw in service_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("ExecStart="):
            return line[len("ExecStart="):].strip()
    return None


# --------------------------------------------------------------------------- #
# Steps.
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


def _step_daemon_reload() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    details: dict = {"daemon_reload_rc": rc}
    if rc != 0:
        details["daemon_reload_stderr"] = stderr[:400]
        return False, details
    return True, details


def _step_verify_execstart() -> tuple[bool, dict]:
    """#703 byte-identical guard: the INSTALLED .service ExecStart must equal the
    canonical string the self-test path exercises."""
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
    """npm present + plugin projects dir readable + alert-bus importable → status=ok."""
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


def _step_real_unit_verify() -> tuple[bool, dict]:
    """Run the REAL unit once, then assert rc=0 AND a fresh tick landed.

    ``systemctl --user start`` on a ``Type=oneshot`` blocks until ExecStart
    exits and returns non-zero if the run failed. ``rc==0`` proves the deployed
    command completes a full pass under the unit's user + ``EnvironmentFile`` +
    ``PATH`` — which ``--dry-run`` alone (no npm, no emit) cannot. Asserting the
    tick-signal advanced additionally proves it can write state under systemd
    (the #703 lesson: a dry-run writes nothing). With live updates outstanding
    this run also emits the real digest — the deploy's own live-verify.
    """
    details: dict = {"unit": _SERVICE_UNIT, "tick_path": str(_TICK_PATH)}
    before_ts = _tick_completed_at(_TICK_PATH)
    details["tick_before"] = before_ts

    rc, stdout, stderr = _run(["systemctl", "--user", "start", _SERVICE_UNIT])
    details["unit_start_rc"] = rc
    if rc != 0:
        details["unit_start_stderr"] = stderr[:400]
        # Surface the unit's own journal tail for diagnosis.
        _, status_out, _ = _run(
            ["systemctl", "--user", "--no-pager", "status", _SERVICE_UNIT]
        )
        details["unit_status_excerpt"] = status_out[-600:]
        details["error"] = (
            "the real unit did not complete a clean pass (non-zero exit) — the "
            "deployed command fails under systemd; timer NOT enabled"
        )
        return False, details

    after_ts = _tick_completed_at(_TICK_PATH)
    details["tick_after"] = after_ts
    if after_ts is None:
        details["error"] = "last-tick.json absent/malformed after the real-unit run"
        return False, details
    if before_ts is not None and after_ts == before_ts:
        details["error"] = (
            "tick completed_at_utc did not advance — the real unit did not write a "
            "fresh tick (stale state)"
        )
        return False, details
    return True, details


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
    _print_line("DRY-RUN", "would run `systemctl --user daemon-reload`", {})
    _print_line(
        "DRY-RUN",
        "would assert the installed felix-openclaw-updates.service ExecStart is "
        f"byte-identical to {_EXPECTED_EXECSTART!r} (#703 guard)",
        {"expected_execstart": _EXPECTED_EXECSTART},
    )
    _print_line(
        "DRY-RUN",
        "would run `python3 -m scripts.openclaw.check_ecosystem_updates "
        "--self-check` and require status=ok (npm present + projects dir "
        "readable + bus importable)",
        {"argv": _SELF_CHECK_ARGV},
    )
    _print_line(
        "DRY-RUN",
        "would run the REAL unit once (`systemctl --user start "
        "felix-openclaw-updates.service`) and require rc=0 + a fresh last-tick.json "
        "(a completed pass under systemd — proves npm + projects dir + emit + state "
        "write; also emits the genuine digest if updates are outstanding)",
        {"unit": _SERVICE_UNIT, "tick_path": str(_TICK_PATH)},
    )
    _print_line(
        "DRY-RUN",
        "would (only if the gate is clean) run `systemctl --user enable --now "
        f"{_TIMER_UNIT}`",
        {},
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-openclaw-updates deploy succeeded"
            if ok
            else f"felix-openclaw-updates deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-openclaw-update-check",
                severity=severity,
                title=title,
                description=(
                    "Deployed the weekly OpenClaw ecosystem update-check timer + "
                    "OnFailure shim; the verify-before-enable gate (self-check + "
                    "real-unit clean-pass assertion) gated the enable."
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
        _print_recovery(["Run `systemctl --user daemon-reload` manually and inspect the error."])
        _report(ok=False, phase="daemon_reload", details=details)
        return 1

    ok, details = _step_verify_execstart()
    _print_line("APPLY", "ExecStart byte-identical guard " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The installed .service ExecStart drifted from the canonical command.",
                f"Re-copy {_SERVICE_UNIT} from {_UNIT_SOURCE_DIR} and daemon-reload.",
            ]
        )
        _report(ok=False, phase="verify_execstart", details=details)
        return 1

    ok, details = _step_self_check()
    _print_line("APPLY", "self-check " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Run `python3 -m scripts.openclaw.check_ecosystem_updates --self-check` "
                f"from {_REPO_ROOT} and resolve what it reports (npm on PATH? "
                "~/.openclaw/npm/projects present?).",
            ]
        )
        _report(ok=False, phase="self_check", details=details)
        return 1

    ok, details = _step_real_unit_verify()
    _print_line("APPLY", "real-unit clean-pass verify " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"`systemctl --user start {_SERVICE_UNIT}` did not exit 0.",
                f"Inspect `journalctl --user -u {_SERVICE_UNIT} -n 50`.",
                "The timer was NOT enabled — no broken timer left behind.",
            ]
        )
        _report(ok=False, phase="real_unit_verify", details=details)
        return 1

    ok, details = _step_enable_timer()
    _print_line("APPLY", "enable --now timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Run `systemctl --user enable --now {_TIMER_UNIT}` manually.",
                f"Verify with `systemctl --user list-timers | grep {_TIMER_UNIT}`.",
            ]
        )
        _report(ok=False, phase="enable_timer", details=details)
        return 1

    _print_line("APPLY", "deploy complete — weekly update-check timer enabled", {"timer": _TIMER_UNIT})
    _report(ok=True, phase="complete", details={"timer": _TIMER_UNIT})
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--dry-run"]:
        return _dry_run()
    if args == ["--apply"]:
        return _apply()
    sys.stderr.write("usage: deploy-openclaw-update-check.py (--dry-run | --apply)\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
