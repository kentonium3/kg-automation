#!/usr/bin/env python3
"""Deploy entrypoint — reconcile the felix-vikunja-sync systemd user units.

Reconciles a repo-vs-deployed drift reported by ``felix-trust-scan/unit-drift``
on 2026-08-31. Tier 3 (user units under the ``claude`` account; no Tier 0/1/2
action).

WHAT DRIFTED, AND WHY IT IS BENIGN.

``felix-vikunja-sync.timer`` — the deployed copy carries ``Persistent=true``;
#925 removed it from the repo. It is INERT here: systemd.timer(5) says
"this setting only has an effect on timers configured with OnCalendar=", and
this timer is monotonic (``OnUnitInactiveSec=300s``). Verified on office2 —
the unit's only two ``OnCalendar`` occurrences are in comments, and the live
directives are OnUnitInactiveSec/OnBootSec/Unit/Persistent.

``felix-vikunja-sync.service`` — directives are IDENTICAL; the drift is
comment-only. The deployed comment still names the pre-#860 credential
(``vikunja-api``) rather than the kent-owned ``vikunja-api-kent``.

So neither unit behaves differently, and this deploy changes no behaviour.
It exists because both drifts are the same defect in miniature: a comment
asserting something untrue of the running system. #925 fixed that text in the
repo only, which left the misleading version as the one actually on the
machine — the fix was not finished until it was deployed.

Order (halt on first error):
  0. Preflight — assert euid's passwd name is ``claude`` AND
     ``Path.home() == /home/claude``. User units install under ``$HOME``, and
     ``getpass.getuser()`` alone is environment-influenced, so it does not
     prove where the units will land.
  1. Assert both repo sources exist and parse as unit files.
  2. Copy both into ``~/.config/systemd/user/``; ``daemon-reload``.
  3. Restart the timer so the on-disk unit is the one in effect, then assert
     it is active AND has a concrete next elapse. Presence on disk is not
     evidence it runs.
  4. Re-diff deployed against repo and FAIL if they still differ — the whole
     point is convergence, so a copy that silently did not land must not
     report success.

⚠ Never wrap a command here in ``ssh office2-claude '...'``: this runs ON
office2 and loopback SSH fails.

Usage:
    scripts/deploy/deploy-felix-vikunja-sync-units.py --dry-run
    scripts/deploy/deploy-felix-vikunja-sync-units.py --apply
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _REPO_ROOT / "scripts" / "sync" / "systemd"
_UNIT_NAMES = ("felix-vikunja-sync.service", "felix-vikunja-sync.timer")
_TIMER = "felix-vikunja-sync.timer"
_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")
_UNIT_DIR = _EXPECTED_HOME / ".config" / "systemd" / "user"


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _run(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _preflight_user() -> bool:
    try:
        actual = pwd.getpwuid(os.geteuid()).pw_name
        env_name = getpass.getuser()
        home = Path.home()
    except (KeyError, OSError, RuntimeError) as exc:  # pragma: no cover - defensive
        _emit("preflight_error", error=f"cannot determine deploy identity: {exc}")
        return False
    if actual != _EXPECTED_USER or home != _EXPECTED_HOME:
        _emit(
            "preflight_failed",
            reason="user units install under $HOME; refusing to install as the wrong user",
            euid_user=actual,
            env_user=env_name,
            home=str(home),
            expected_user=_EXPECTED_USER,
            expected_home=str(_EXPECTED_HOME),
        )
        return False
    _emit("preflight_ok", user=actual, home=str(home))
    return True


def _sources_ok() -> bool:
    ok = True
    for name in _UNIT_NAMES:
        src = _SOURCE_DIR / name
        if not src.is_file():
            _emit("source_missing", unit=name, path=str(src))
            ok = False
            continue
        text = src.read_text()
        # A unit with no section header is not a unit; catches a truncated or
        # half-written source before it replaces a working deployed copy.
        if "[Unit]" not in text:
            _emit("source_malformed", unit=name, path=str(src),
                  reason="no [Unit] section — refusing to install")
            ok = False
    return ok


def _differs(name: str) -> bool | None:
    """True/False, or None when the deployed copy cannot be read."""
    src = _SOURCE_DIR / name
    dst = _UNIT_DIR / name
    if not dst.exists():
        return True
    try:
        return src.read_text() != dst.read_text()
    except OSError:
        return None


def _dry_run() -> int:
    if not _sources_ok():
        return 1
    for name in _UNIT_NAMES:
        d = _differs(name)
        _emit("would_copy", unit=name, src=str(_SOURCE_DIR / name),
              dst=str(_UNIT_DIR / name),
              currently_differs=("unreadable" if d is None else d))
    _emit("would_run", argv=["systemctl", "--user", "daemon-reload"])
    _emit("would_run", argv=["systemctl", "--user", "restart", _TIMER])
    _emit("dry_run_complete")
    return 0


def _apply() -> int:
    if not _preflight_user():
        return 1
    if not _sources_ok():
        return 1

    _UNIT_DIR.mkdir(parents=True, exist_ok=True)
    for name in _UNIT_NAMES:
        src, dst = _SOURCE_DIR / name, _UNIT_DIR / name
        try:
            shutil.copyfile(src, dst)
        except OSError as exc:
            _emit("copy_failed", unit=name, error=str(exc))
            return 1
        _emit("copied", unit=name, dst=str(dst))

    rc, _, err = _run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        _emit("daemon_reload_failed", rc=rc, stderr=err)
        return 1
    _emit("daemon_reload_ok")

    # Restart so the on-disk unit is the one in effect. Resets the monotonic
    # cycle, so the next tick moves by up to 5 minutes — harmless at this
    # cadence, and the driver is delta-based.
    rc, _, err = _run(["systemctl", "--user", "restart", _TIMER])
    if rc != 0:
        _emit("timer_restart_failed", rc=rc, stderr=err)
        return 1

    rc, out, _ = _run(["systemctl", "--user", "is-active", _TIMER])
    if rc != 0 or out != "active":
        _emit("timer_not_active", rc=rc, state=out)
        return 1
    rc, nxt, _ = _run(["systemctl", "--user", "show", _TIMER,
                       "-p", "NextElapseUSecMonotonic", "--value"])
    if rc != 0 or not nxt or nxt in {"0", "infinity"}:
        _emit("timer_no_next_elapse", rc=rc, value=nxt)
        return 1
    _emit("timer_ok", state=out, next_elapse_monotonic=nxt)

    # Convergence is the deliverable. A copy that silently did not land must
    # not report success — that would be a deploy asserting a state it did
    # not verify, which is the class of defect this deploy exists to clear.
    unresolved = []
    for name in _UNIT_NAMES:
        d = _differs(name)
        if d is None:
            _emit("verify_unreadable", unit=name)
            return 1
        if d:
            unresolved.append(name)
    if unresolved:
        _emit("still_drifted", units=unresolved)
        return 1
    _emit("converged", units=list(_UNIT_NAMES))
    _emit("apply_complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    return _dry_run() if args.dry_run else _apply()


if __name__ == "__main__":
    sys.exit(main())
