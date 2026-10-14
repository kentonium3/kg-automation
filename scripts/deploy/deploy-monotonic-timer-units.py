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
     Persistent= without OnCalendar=. Refuse before copying anything.
  2. Copy all six into ``~/.config/systemd/user/``; ``daemon-reload``.
  3. Restart every timer. MANDATORY, not hygiene: a running timer keeps its
     deserialized state (last_trigger, disabled triggers) across
     ``daemon-reload``. Only a restart applies the new definition. Because
     each OnBootSec= is long past, each restart fires its service at once —
     expect one burst of six runs.
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
import os
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib.timer_units import directives, persistent_without_calendar  # noqa: E402

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
_SHOW_PROPS = (
    "Persistent", "UnitFileState", "ActiveState", "SubState",
    "FragmentPath", "DropInPaths", "NextElapseUSecMonotonic",
)
NEXT_ELAPSE_TIMEOUT_S = 300
_POLL_INTERVAL_S = 5

Runner = Callable[[list[str]], "tuple[int, str, str]"]


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _run(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# --- pure checks (unit-tested) ----------------------------------------------

def source_problems(text: str) -> list[str]:
    problems = []
    if "Timer" not in {s for s, _, _ in directives(text)}:
        problems.append("no [Timer] section directives")
    if persistent_without_calendar(text):
        problems.append("sets Persistent= without OnCalendar= (#1062)")
    return problems


def next_elapse_is_concrete(value: str) -> bool:
    # systemd renders a human timespan ("54min 36.9s"); only these mean "none".
    return value.strip() not in {"", "0", "infinity"}


def parse_show(out: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key] = value
    return props


def loaded_problems(name: str, props: dict[str, str], dropin_texts: list[str]) -> list[str]:
    problems = []
    if props.get("Persistent") != "no":
        problems.append(f"loaded Persistent={props.get('Persistent')!r}, want 'no'")
    if props.get("UnitFileState") != "enabled":
        problems.append(f"UnitFileState={props.get('UnitFileState')!r}, want 'enabled'")
    if props.get("ActiveState") != "active":
        problems.append(f"ActiveState={props.get('ActiveState')!r}, want 'active'")
    if props.get("FragmentPath") != str(UNIT_DIR / name):
        problems.append(f"FragmentPath={props.get('FragmentPath')!r}, want {str(UNIT_DIR / name)!r}")
    if dropin_texts and persistent_without_calendar("", *dropin_texts):
        problems.append("a drop-in re-adds Persistent=")
    return problems


# --- steps -------------------------------------------------------------------

def _preflight_user() -> bool:
    actual = pwd.getpwuid(os.geteuid()).pw_name
    home = Path.home()
    if actual != _EXPECTED_USER or home != _EXPECTED_HOME:
        _emit("preflight_failed",
              reason="user units install under $HOME; refusing to install as the wrong user",
              euid_user=actual, home=str(home))
        return False
    _emit("preflight_ok", user=actual, home=str(home))
    return True


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


def _differs(src: Path) -> bool | None:
    dst = UNIT_DIR / src.name
    if not dst.exists():
        return True
    try:
        return src.read_text() != dst.read_text()
    except OSError:
        return None


def _verify_timer(name: str, run: Runner, sleep: Callable[[float], None],
                  timeout_s: int = NEXT_ELAPSE_TIMEOUT_S) -> list[str]:
    deadline = time.monotonic() + timeout_s
    while True:
        rc, out, err = run(["systemctl", "--user", "show", name,
                            *[f"-p{p}" for p in _SHOW_PROPS]])
        if rc != 0:
            return [f"systemctl show failed rc={rc}: {err}"]
        props = parse_show(out)
        dropins = [Path(p) for p in props.get("DropInPaths", "").split() if p]
        texts = []
        for d in dropins:
            try:
                texts.append(d.read_text(encoding="utf-8"))
            except OSError as exc:
                return [f"cannot read drop-in {d}: {exc}"]
        problems = loaded_problems(name, props, texts)
        if problems:
            return problems
        if next_elapse_is_concrete(props.get("NextElapseUSecMonotonic", "")):
            _emit("timer_ok", unit=name, sub_state=props.get("SubState"),
                  next_elapse_monotonic=props["NextElapseUSecMonotonic"])
            return []
        if time.monotonic() >= deadline:
            return [f"no concrete next elapse after {timeout_s}s "
                    f"(SubState={props.get('SubState')!r}, "
                    f"NextElapseUSecMonotonic={props.get('NextElapseUSecMonotonic')!r})"]
        _emit("waiting_for_next_elapse", unit=name, sub_state=props.get("SubState"))
        sleep(_POLL_INTERVAL_S)


def _dry_run() -> int:
    if not _sources_ok():
        return 1
    for src in TIMERS:
        d = _differs(src)
        _emit("would_copy", unit=src.name, src=str(src), dst=str(UNIT_DIR / src.name),
              currently_differs=("unreadable" if d is None else d))
    _emit("would_run", argv=["systemctl", "--user", "daemon-reload"])
    for src in TIMERS:
        _emit("would_run", argv=["systemctl", "--user", "restart", src.name])
    _emit("dry_run_complete")
    return 0


def _apply(run: Runner = _run, sleep: Callable[[float], None] = time.sleep) -> int:
    if not _preflight_user() or not _sources_ok():
        return 1

    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    for src in TIMERS:
        try:
            shutil.copyfile(src, UNIT_DIR / src.name)
        except OSError as exc:
            _emit("copy_failed", unit=src.name, error=str(exc))
            return 1
        _emit("copied", unit=src.name)

    rc, _, err = run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        _emit("daemon_reload_failed", rc=rc, stderr=err)
        return 1
    _emit("daemon_reload_ok")

    failed: dict[str, list[str]] = {}
    for src in TIMERS:
        rc, _, err = run(["systemctl", "--user", "restart", src.name])
        if rc != 0:
            failed[src.name] = [f"restart failed rc={rc}: {err}"]
            _emit("timer_restart_failed", unit=src.name, rc=rc, stderr=err)
            continue
        _emit("timer_restarted", unit=src.name)

    for src in TIMERS:
        if src.name in failed:
            continue
        problems = _verify_timer(src.name, run, sleep)
        if problems:
            failed[src.name] = problems
            _emit("timer_verify_failed", unit=src.name, problems=problems)

    for src in TIMERS:
        d = _differs(src)
        if d is None or d:
            failed.setdefault(src.name, []).append(
                "deployed copy unreadable" if d is None else "deployed copy still differs")

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
