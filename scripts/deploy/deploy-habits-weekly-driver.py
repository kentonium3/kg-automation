#!/usr/bin/env python3
"""Deploy entrypoint — deterministic weekly habit-report driver cutover (#723).

Mission: ``deterministic-cron-hardening-01KXA4PX`` (WP04).

Installs the ``felix-habits-weekly.{service,timer}`` +
``felix-habits-weekly-onfailure.service`` systemd **user** units under the
``claude`` account on office2, verifies the deployed driver actually reaches
its delivery path via a self-test gate BEFORE touching any scheduler state,
then performs a **transactional cutover** from the legacy
``habits-weekly-report`` openclaw cron to the new timer — never leaving both
producers active, and never leaving neither active. Tier 3 (Logic/Workflow —
installs a user timer + retires one openclaw cron; no Tier 0/1/2 action).
``audited_surface: true`` (systemd units are a hashed audited surface; the
``openclaw cron rm`` step additionally drifts the ``openclaw-cron.txt``
baseline with **no repo-file signal**, declared via the manifest's
``expected_baselines``).

Authoritative contracts:

- ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/post-plan-review-resolutions.md``
  — C2 (``--self-test`` deploy gate), C3 (transactional scheduler cutover),
  M11 (systemd unit fields), M12 (service-inventory full cleanup + postcheck).

Strict, halt-on-error order (C3):

  1. **Install units** — copy ``felix-habits-weekly.service``,
     ``felix-habits-weekly.timer``, and
     ``felix-habits-weekly-onfailure.service`` into
     ``~/.config/systemd/user/``, then ``daemon-reload``.
  2. **``--self-test`` gate (C2)** — run
     ``python3 -m scripts.habits.weekly_report_driver --self-test``: the
     driver runs the report helper, composes the message, exercises the
     full ``openclaw message send --dry-run`` round-trip (no real send),
     and writes a fresh ``last-tick.json``. Exit 0 is required. **Abort the
     deploy on any failure — no cutover on a bad build** (the #711/#703
     lesson: never enable/retire on an unverified deploy).
  3. **Retire the legacy producer** — resolve the ``habits-weekly-report``
     openclaw cron's id via ``openclaw cron list --json`` and remove it via
     ``openclaw cron rm <id>``; assert it is absent afterward. Idempotent:
     an already-absent cron is treated as success (a prior partial apply
     may have already removed it).
  4. **Enable the new producer** — ``systemctl --user enable --now
     felix-habits-weekly.timer``; assert ``next elapse`` is scheduled via
     ``systemctl --user list-timers``.
  5. **Exactly-one-producer postcheck (C3/M12)** — assert the openclaw cron
     is ABSENT and the timer is enabled. FAIL (and alert) if both producers
     exist or neither does — the cutover must never leave a half state.
  6. **Report** — outcome (success/failure) is emitted through the ``#701``
     felix-alert bus (mirrors ``deploy-felix-canary.py``); no parallel
     alerting channel.

No auto-rollback — on any failure the script prints recovery instructions
and exits non-zero. Whatever ran before the failing step is NOT undone.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects** on office2.
  Safe to run anywhere (off-office2 too).
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (install / self-test / cron-removal / enable /
  postcheck). Nothing is rolled back; recovery instructions to stderr.
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
from scripts.deploy.lib import cron as cron_lib  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants.
# --------------------------------------------------------------------------- #

_OPENCLAW_BIN = "/usr/bin/openclaw"
_PYTHON3_BIN = "/usr/bin/python3"

_UNIT_SOURCE_DIR = _REPO_ROOT / "scripts" / "office2"
_SERVICE_UNIT = "felix-habits-weekly.service"
_TIMER_UNIT = "felix-habits-weekly.timer"
_ONFAILURE_UNIT = "felix-habits-weekly-onfailure.service"
_UNIT_NAMES = (_SERVICE_UNIT, _TIMER_UNIT, _ONFAILURE_UNIT)
_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

# The legacy producer this cutover retires (habit-checkin's health_check.crons
# list, and its schedules[], were stripped of this name by T012).
_LEGACY_CRON_NAME = "habits-weekly-report"

# The self-test argv — runs the SAME module the ExecStart runs, in
# --self-test mode (dry-run send + tick write, C2).
_SELF_TEST_ARGV = [
    _PYTHON3_BIN,
    "-m",
    "scripts.habits.weekly_report_driver",
    "--self-test",
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


# --------------------------------------------------------------------------- #
# Step 1 — install the systemd user units + daemon-reload.
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


# --------------------------------------------------------------------------- #
# Step 2 — `--self-test` gate (C2). Must pass BEFORE any scheduler mutation.
# --------------------------------------------------------------------------- #


def _tick_completed_at(tick_path: Path) -> str | None:
    """Return last-tick.json's completed_at_utc, or None if unreadable/absent."""
    try:
        data = json.loads(tick_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("completed_at_utc")
    return value if isinstance(value, str) else None


# The driver's own default tick path (mirrors the module constant so this
# deploy script and the driver never diverge on where freshness is asserted).
_TICK_PATH = Path("/data/services/felix-habits-weekly/state/last-tick.json")


def _step_self_test() -> tuple[bool, dict]:
    """C2: run the driver's --self-test and assert exit 0 + a fresh tick.

    The self-test exercises the full path (helper -> compose -> dry-run send)
    without a real WhatsApp send, then writes last-tick.json. We additionally
    assert the tick advanced so a driver that silently no-ops cannot pass.
    """
    before_ts = _tick_completed_at(_TICK_PATH)
    rc, stdout, stderr = _run(_SELF_TEST_ARGV, cwd=_REPO_ROOT)
    details: dict = {
        "self_test_rc": rc,
        "self_test_stdout_excerpt": stdout[:400],
        "self_test_stderr_excerpt": stderr[:400],
        "tick_before": before_ts,
    }
    if rc != 0:
        details["error"] = "self-test exited non-zero"
        return False, details

    after_ts = _tick_completed_at(_TICK_PATH)
    details["tick_after"] = after_ts
    if after_ts is None:
        details["error"] = "last-tick.json absent or missing completed_at_utc after self-test"
        return False, details
    if before_ts is not None and after_ts == before_ts:
        details["error"] = (
            "last-tick.json completed_at_utc did not advance — the self-test "
            "did not write a fresh tick"
        )
        return False, details
    return True, details


# --------------------------------------------------------------------------- #
# Step 3 — retire the legacy openclaw cron (C3). Only after the self-test gate.
# --------------------------------------------------------------------------- #


def _resolve_cron_id(cron_name: str) -> tuple[str | None, dict]:
    """Resolve a named openclaw cron's id via the vetted read-only list primitive."""
    try:
        listing = cron_lib.openclaw_cron_list()
    except FileNotFoundError as exc:
        return None, {"error": "openclaw binary not found", "detail": str(exc)}
    if not listing.ok:
        return None, {"error": "openclaw cron list failed", **dict(listing.details)}
    jobs = list(listing.details.get("crons", []))
    for job in jobs:
        if isinstance(job, dict) and job.get("name") == cron_name:
            return job.get("id"), dict(job)
    return None, {
        "error": f"cron {cron_name!r} not registered",
        "available_names": [j.get("name") for j in jobs if isinstance(j, dict)],
    }


def _step_retire_legacy_cron() -> tuple[bool, dict]:
    """Remove the legacy `habits-weekly-report` openclaw cron.

    Idempotent: already-absent is treated as success (a prior partial apply
    may have already removed it) — mirrors deploy-deterministic-monitoring-checks.py's
    _remove_cron precedent. Uses a direct `openclaw cron rm <id>` subprocess
    (scripts.deploy.lib.cron exposes no vetted remove primitive today).
    """
    cron_id, info = _resolve_cron_id(_LEGACY_CRON_NAME)
    if cron_id is None:
        if "not registered" in str(info.get("error", "")):
            return True, {
                "cron_name": _LEGACY_CRON_NAME,
                "idempotent": True,
                "note": "already absent",
            }
        return False, {"cron_name": _LEGACY_CRON_NAME, **info}

    rc, stdout, stderr = _run([_OPENCLAW_BIN, "cron", "rm", cron_id])
    details = {
        "cron_name": _LEGACY_CRON_NAME,
        "cron_id": cron_id,
        "rm_rc": rc,
        "rm_stdout_excerpt": stdout[:400],
        "rm_stderr_excerpt": stderr[:400],
    }
    if rc != 0:
        details["error"] = "openclaw cron rm failed"
        return False, details

    # Assert absence after removal.
    after_id, after_info = _resolve_cron_id(_LEGACY_CRON_NAME)
    if after_id is not None:
        details["error"] = "cron still present after rm"
        details["post_rm_lookup"] = after_info
        return False, details
    return True, details


# --------------------------------------------------------------------------- #
# Step 4 — enable the new timer + verify it is scheduled.
# --------------------------------------------------------------------------- #


def _step_enable_and_verify_timer() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    details: dict = {"enable_rc": rc, "enable_stderr_excerpt": stderr[:400]}
    if rc != 0:
        return False, details

    rc2, stdout2, stderr2 = _run(
        ["systemctl", "--user", "list-timers", _TIMER_UNIT, "--no-pager"]
    )
    details["list_timers_rc"] = rc2
    details["list_timers_stdout"] = stdout2[:400]
    if rc2 != 0 or "felix-habits-weekly" not in stdout2:
        details["error"] = "felix-habits-weekly.timer not found in list-timers output"
        return False, details
    return True, details


def _timer_is_enabled() -> tuple[bool, dict]:
    """Read-only check: is the timer unit enabled? Used by the postcheck."""
    rc, stdout, stderr = _run(["systemctl", "--user", "is-enabled", _TIMER_UNIT])
    details = {"is_enabled_rc": rc, "is_enabled_stdout": stdout.strip(), "is_enabled_stderr": stderr[:200]}
    # `systemctl --user is-enabled` prints "enabled" and exits 0 when enabled.
    return rc == 0 and stdout.strip() == "enabled", details


# --------------------------------------------------------------------------- #
# Step 5 — exactly-one-producer postcheck (C3/M12).
# --------------------------------------------------------------------------- #


def _step_exactly_one_producer_postcheck() -> tuple[bool, dict]:
    """Assert the legacy cron is ABSENT and the new timer is enabled.

    FAILS if both producers are present (double-delivery risk) or neither is
    present (silent outage) — the cutover must never leave a half state.
    """
    cron_id, cron_info = _resolve_cron_id(_LEGACY_CRON_NAME)
    cron_present = cron_id is not None
    timer_enabled, timer_details = _timer_is_enabled()

    details = {
        "legacy_cron_present": cron_present,
        "timer_enabled": timer_enabled,
        **timer_details,
    }
    if cron_present:
        details["legacy_cron_info"] = cron_info

    if cron_present and timer_enabled:
        details["error"] = (
            "BOTH producers active — legacy openclaw cron still present AND "
            "the new timer is enabled (double-delivery risk)"
        )
        return False, details
    if not cron_present and not timer_enabled:
        details["error"] = (
            "NEITHER producer active — legacy cron absent AND the new timer "
            "is not enabled (silent outage)"
        )
        return False, details
    if cron_present and not timer_enabled:
        details["error"] = (
            "legacy cron present but new timer not enabled — cutover incomplete"
        )
        return False, details
    # Exactly one producer: legacy cron absent, timer enabled. Healthy.
    return True, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run() -> int:
    _print_line(
        "DRY-RUN",
        f"would install {', '.join(_UNIT_NAMES)} into {_SYSTEMD_USER_DIR}, then daemon-reload",
        {"units": list(_UNIT_NAMES)},
    )
    _print_line(
        "DRY-RUN",
        "would run `python3 -m scripts.habits.weekly_report_driver --self-test` "
        "and require exit 0 + a fresh last-tick.json (C2 gate — abort on failure)",
        {"argv": _SELF_TEST_ARGV, "tick_path": str(_TICK_PATH)},
    )
    _print_line(
        "DRY-RUN",
        f"would resolve + remove the legacy openclaw cron {_LEGACY_CRON_NAME!r} "
        "via `openclaw cron rm <id>` — only after the self-test gate passes (C3)",
        {"legacy_cron_name": _LEGACY_CRON_NAME},
    )
    _print_line(
        "DRY-RUN",
        f"would `systemctl --user enable --now {_TIMER_UNIT}` and verify via list-timers",
        {},
    )
    _print_line(
        "DRY-RUN",
        "would postcheck exactly-one-producer: legacy cron ABSENT AND timer "
        "ENABLED — fail if both or neither",
        {},
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-habits-weekly deploy succeeded"
            if ok
            else f"felix-habits-weekly deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-habits-weekly-driver",
                severity=severity,
                title=title,
                description=(
                    "Deployed the felix-habits-weekly timer and retired the "
                    "legacy habits-weekly-report openclaw cron; the C2 "
                    "self-test gate + C3 exactly-one-producer postcheck "
                    "gated the cutover."
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

    # ---- C2 self-test gate — MUST pass before any scheduler mutation. ------ #
    ok, details = _step_self_test()
    _print_line("APPLY", "self-test " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The --self-test did not pass. Verify locally: "
                "python3 -m scripts.habits.weekly_report_driver --self-test",
                "The legacy habits-weekly-report cron was NOT touched, so no "
                "unverified cutover happened (C2/#711 lesson).",
            ]
        )
        _report(ok=False, phase="self_test", details=details)
        return 1

    # ---- C3 transactional cutover: retire legacy cron, then enable timer. -- #
    ok, details = _step_retire_legacy_cron()
    _print_line("APPLY", "retire legacy cron " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Inspect `openclaw cron list --json` for {_LEGACY_CRON_NAME!r}.",
                f"Manually: openclaw cron rm <id-of-{_LEGACY_CRON_NAME}>",
            ]
        )
        _report(ok=False, phase="retire_legacy_cron", details=details)
        return 1

    ok, details = _step_enable_and_verify_timer()
    _print_line("APPLY", "enable+verify timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The legacy cron was already retired but the new timer failed "
                "to enable — this leaves NEITHER producer active. Manually: "
                f"systemctl --user enable --now {_TIMER_UNIT}",
                "Then re-run this deploy to confirm the postcheck passes.",
            ]
        )
        _report(ok=False, phase="enable_timer", details=details)
        return 1

    # ---- C3/M12 exactly-one-producer postcheck. ---------------------------- #
    ok, details = _step_exactly_one_producer_postcheck()
    _print_line(
        "APPLY", "exactly-one-producer postcheck " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "The cutover did not converge on exactly one producer. "
                "Inspect: openclaw cron list --json | grep habits-weekly-report",
                f"Inspect: systemctl --user is-enabled {_TIMER_UNIT}",
                "Manually reconcile to exactly one active producer before "
                "re-running this deploy.",
            ]
        )
        _report(ok=False, phase="postcheck", details=details)
        return 1

    _report(ok=True, phase="complete", details=details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write("usage: deploy-habits-weekly-driver.py --dry-run|--apply\n")
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
