#!/usr/bin/env python3
"""Deploy entrypoint — remove Persistent= from six monotonic user timers (#1062).

Tier 3 (user units under the ``claude`` account; no Tier 0/1/2 action).

WHY. ``Persistent=true`` on a monotonic timer (OnBootSec + OnUnitActiveSec /
OnUnitInactiveSec, no OnCalendar) makes systemd load a stamp-file
``last_trigger`` at manager start. When the claude user manager starts after
``OnBootSec=`` has already passed (18.7 min on 2026-10-14, and late on
2026-09-27 too), the boot trigger is disabled as already fired. The service
never runs, so the timer stays ``active (elapsed)`` with no next elapse for the
whole boot. felix-canary, felix-trust-scan, felix-heartbeat-gate,
felix-core-digest, agent-prompt-sync and agent-skill-sync were dead
2026-09-27 → 2026-10-14. See ``scripts/deploy/lib/timer_units.py``.

Only the ``.timer`` files change; the services are untouched.

Order (each step must hold before the next):
  0. Preflight — euid's passwd name is ``claude`` AND ``Path.home()`` is
     ``/home/claude``. User units install under ``$HOME``.
  1. Validate every source: it has a ``[Timer]`` section and does NOT set
     Persistent= on a monotonic timer. Refuse before copying anything.
  2. Copy all six into ``~/.config/systemd/user/``; ``daemon-reload``.
  3. Restart every timer. MANDATORY, not hygiene: a running timer keeps its
     deserialized state (last_trigger, disabled triggers) across
     ``daemon-reload``. Only a restart applies the new definition. Observed
     on apply (2026-10-14): when the service has already run in this manager
     lifetime, the restart keeps the in-memory last trigger, so no burst.
     The past OnBootSec= stays spent and OnUnit*Sec= continues from the last
     run. A timer whose service never ran would fire at once.
  4. Verify the LOADED config, not just the file on disk: Persistent=no,
     UnitFileState=enabled (so it comes back next boot), ActiveState=active,
     FragmentPath is the installed file, no drop-in re-adds Persistent=.
  5. Poll (bounded) for a concrete NextElapseUSecMonotonic. Right after a
     restart the timer may be ``running`` while its service executes, and
     systemd reports next elapse ``infinity`` until the service finishes, so
     an immediate check could fail a good deploy.
  6. Re-diff deployed against repo and fail if anything did not converge.
Every timer is verified and reported individually; the run fails at the end
if any one failed.

⚠ Never wrap a command here in ``ssh office2-claude '...'``: this runs ON
office2 and loopback SSH fails.

Usage:
    scripts/deploy/deploy-monotonic-timer-units.py --dry-run
    scripts/deploy/deploy-monotonic-timer-units.py --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib import userunits  # noqa: E402
from scripts.deploy.lib.timer_units import directives, persistent_on_monotonic  # noqa: E402

TIMERS: tuple[Path, ...] = (
    _REPO_ROOT / "scripts/office2/felix-canary.timer",
    _REPO_ROOT / "scripts/office2/felix-trust-scan.timer",
    _REPO_ROOT / "scripts/office2/felix-heartbeat-gate.timer",
    _REPO_ROOT / "scripts/office2/felix-core-digest.timer",
    _REPO_ROOT / "scripts/openclaw/deploy/agent-prompt-sync.timer",
    _REPO_ROOT / "scripts/openclaw/deploy/agent-skill-sync.timer",
)
_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")
UNIT_DIR = _EXPECTED_HOME / ".config" / "systemd" / "user"
NEXT_ELAPSE_TIMEOUT_S = 300

Runner = Callable[[list[str]], "tuple[int, str, str]"]


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _run(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# --- policy (this deploy's rules; the mechanism lives in lib.userunits) -------

def source_problems(text: str) -> list[str]:
    problems = []
    if "Timer" not in {s for s, _, _ in directives(text)}:
        problems.append("no [Timer] section directives")
    if persistent_on_monotonic(text):
        problems.append("sets Persistent= on a monotonic timer (#1062)")
    return problems


# The loaded properties every timer must show after the restart.
EXPECT_LOADED = {"Persistent": "no", "UnitFileState": "enabled", "ActiveState": "active"}


def _no_persistent_in_loaded_files(_props: dict[str, str], unit_texts: list[str]) -> list[str]:
    # Belt-and-braces over the loaded Persistent= above: re-derive it from the
    # files systemd actually loaded, fragment plus drop-ins, as one stream.
    if unit_texts and persistent_on_monotonic(*unit_texts):
        return ["installed fragment/drop-ins set Persistent= on a monotonic timer"]
    return []


# --- steps -------------------------------------------------------------------

def _sources_ok() -> bool:
    ok = True
    for src in TIMERS:
        if not src.is_file():
            _emit("source_missing", unit=src.name, path=str(src))
            ok = False
            continue
        problems = source_problems(src.read_text(encoding="utf-8"))
        if problems:
            _emit("source_rejected", unit=src.name, problems=problems)
            ok = False
    return ok


def _verify_timer(name: str, run: Runner, sleep: Callable[[float], None],
                  timeout_s: int = NEXT_ELAPSE_TIMEOUT_S,
                  deadline: float | None = None,
                  read: Callable[[Path], str] = lambda p: p.read_text(encoding="utf-8"),
                  ) -> list[str]:
    """This deploy's verification policy, bound onto userunits.verify_unit."""
    res = userunits.verify_unit(
        name, run, unit_dir=UNIT_DIR, expect=EXPECT_LOADED,
        extra_check=_no_persistent_in_loaded_files, wait_next_elapse=True,
        sleep=sleep, deadline=deadline, timeout_s=timeout_s, read=read, emit=_emit,
    )
    if res.ok:
        _emit("timer_ok", unit=name, sub_state=res.details["props"].get("SubState"),
              next_elapse_monotonic=res.details["props"].get("NextElapseUSecMonotonic"))
        return []
    return list(res.details["problems"])


def _dry_run() -> int:
    if not _sources_ok():
        return 1
    plan = userunits.plan_install(TIMERS, UNIT_DIR)
    for unit in plan.details["units"]:
        d = unit["differs"]
        _emit("would_copy", unit=unit["name"], src=unit["src"], dst=unit["dst"],
              currently_differs=("unreadable" if d is None else d))
    _emit("would_run", argv=["systemctl", "--user", "daemon-reload"])
    for src in TIMERS:
        _emit("would_run", argv=["systemctl", "--user", "restart", src.name])
    _emit("dry_run_complete")
    return 0


def _apply(run: Runner = _run, sleep: Callable[[float], None] = time.sleep) -> int:
    pre = userunits.preflight_user(expected_user=_EXPECTED_USER, expected_home=_EXPECTED_HOME)
    if not pre.ok:
        _emit("preflight_failed",
              reason="user units install under $HOME; refusing to install as the wrong user",
              **pre.details)
        return 1
    _emit("preflight_ok", user=pre.details["euid_user"], home=pre.details["home"])
    if not _sources_ok():
        return 1

    # Install all, reload once, restart all. The restart is MANDATORY, not
    # hygiene: a running timer keeps its deserialized state across
    # daemon-reload; only a restart applies the new definition.
    applied = userunits.apply_units(TIMERS, UNIT_DIR, action="restart", run=run)
    if "units" not in applied.details or applied.details.get("error_code") in {"SOURCE_MISSING", "COPY_FAILED"}:
        _emit("copy_failed", **{k: v for k, v in applied.details.items() if k != "units"})
        return 1
    for unit in applied.details.get("installed", []):
        _emit("copied", unit=unit["name"])
    if applied.details.get("error_code") == "DAEMON_RELOAD_FAILED":
        _emit("daemon_reload_failed", rc=applied.details.get("rc"), stderr=applied.details.get("stderr_excerpt"))
        return 1
    _emit("daemon_reload_ok")

    failed: dict[str, list[str]] = dict(applied.details.get("failed", {}))
    for unit in applied.details["units"]:
        if unit["ok"]:
            _emit("timer_restarted", unit=unit["name"])
        else:
            _emit("timer_restart_failed", unit=unit["name"], rc=unit.get("rc"), stderr=unit.get("stderr_excerpt"))

    # ONE deadline shared by every timer, so a broken deploy holds the
    # deployer tick for at most ~NEXT_ELAPSE_TIMEOUT_S in total.
    deadline = time.monotonic() + NEXT_ELAPSE_TIMEOUT_S
    for src in TIMERS:
        if src.name in failed:
            continue
        problems = _verify_timer(src.name, run, sleep, deadline=deadline)
        if problems:
            failed[src.name] = problems
            _emit("timer_verify_failed", unit=src.name, problems=problems)

    conv = userunits.converged(TIMERS, UNIT_DIR)
    for unit in conv.details["units"]:
        if unit["differs"] is not False:
            failed.setdefault(unit["name"], []).append(
                "deployed copy unreadable" if unit["differs"] is None else "deployed copy still differs")

    if failed:
        _emit("apply_failed", failed=failed)
        return 1
    _emit("apply_complete", units=[s.name for s in TIMERS])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    return _dry_run() if args.dry_run else _apply()


if __name__ == "__main__":
    sys.exit(main())
