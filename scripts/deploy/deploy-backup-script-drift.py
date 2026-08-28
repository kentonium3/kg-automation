#!/usr/bin/env python3
"""Deploy entrypoint — backup-script drift comparator (#903).

Mission: ``backup-integrity-observability-01M1414D`` (WP03).

Installs ``backup-script-drift.{service,timer}`` as systemd **user** units under
the ``claude`` account and enables the timer. Tier 3.

This deploy installs the *comparator*. It deliberately does NOT install
``backup.sh`` itself: ``/data/services/backup/scripts/`` must stay
non-claude-writable because it holds a ``NOPASSWD`` sudo target, and a writable
directory there is equivalent to ``NOPASSWD: ALL`` (#899). The operator installs
that script by hand; this component's whole purpose is to make it obvious when
they have not.

Order (halt on first error):
  0. Preflight — assert the euid's passwd name is ``claude`` AND
     ``Path.home() == /home/claude``. User units install under ``$HOME``, and
     ``getpass.getuser()`` alone is environment-influenced, so it does not prove
     where the units will land.
  1. Copy units into ``~/.config/systemd/user/``; ``daemon-reload``.
  2. Gate on the comparator's own ``--dry-run`` succeeding *before* enabling
     anything — presence on disk is not evidence it runs.
  3. ``enable --now``, then assert ``is-enabled`` and a concrete next elapse.

⚠ Never wrap a command here in ``ssh office2-claude '...'``: this runs ON office2
and loopback SSH fails.

Usage:
    scripts/deploy/deploy-backup-script-drift.py --dry-run
    scripts/deploy/deploy-backup-script-drift.py --apply
"""

from __future__ import annotations

import argparse
import filecmp
import getpass
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _REPO_ROOT / "scripts" / "office2"
_UNIT_NAMES = ("backup-script-drift.service", "backup-script-drift.timer")
_HELPER = _SOURCE_DIR / "backup_script_drift.py"
_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_TIMER_UNIT = "backup-script-drift.timer"
_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")


def _emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}))


def _run(argv: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _preflight_user() -> bool:
    try:
        actual = pwd.getpwuid(os.geteuid()).pw_name
        env_name = getpass.getuser()
        home = Path.home()
    except Exception as exc:  # pragma: no cover - defensive
        _emit("preflight_error", error=f"cannot determine deploy identity: {exc}")
        return False
    if actual != _EXPECTED_USER or home != _EXPECTED_HOME:
        _emit("preflight_failed",
              error=("systemd user units install under $HOME; refusing to install as "
                     f"euid-user '{actual}' with home '{home}'"),
              euid_user=actual, env_user=env_name, home=str(home))
        return False
    _emit("preflight_ok", user=actual, home=str(home))
    return True


def _check_sources() -> bool:
    ok = True
    for name in list(_UNIT_NAMES) + [_HELPER.name]:
        src = _SOURCE_DIR / name
        if not src.is_file():
            _emit("source_missing", path=str(src))
            ok = False
    return ok


def dry_run() -> int:
    _emit("mode", value="dry-run")
    if not _check_sources():
        return 1
    for name in _UNIT_NAMES:
        src, dest = _SOURCE_DIR / name, _SYSTEMD_USER_DIR / name
        if dest.exists() and filecmp.cmp(src, dest, shallow=False):
            _emit("unit_already_current", unit=name)
        else:
            _emit("would_install_unit", unit=name, src=str(src), dest=str(dest))
    _emit("would_run", argv=["/usr/bin/python3", str(_HELPER), "--dry-run"],
          note="comparator gate — must pass before the timer is enabled")
    _emit("would_run", argv=["systemctl", "--user", "daemon-reload"])
    _emit("would_run", argv=["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    _emit("dry_run_complete", changed=False)
    return 0


def apply() -> int:
    _emit("mode", value="apply")
    if not _preflight_user() or not _check_sources():
        return 1

    try:
        _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        for name in _UNIT_NAMES:
            src, dest = _SOURCE_DIR / name, _SYSTEMD_USER_DIR / name
            if dest.exists() and filecmp.cmp(src, dest, shallow=False):
                _emit("unit_unchanged", unit=name)
                continue
            shutil.copy2(src, dest)
            if not filecmp.cmp(src, dest, shallow=False):
                _emit("unit_copy_mismatch", unit=name, dest=str(dest))
                return 1
            _emit("unit_installed", unit=name, dest=str(dest))
    except OSError as exc:
        _emit("unit_install_failed", error=str(exc))
        return 1

    rc, out, err = _run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        _emit("daemon_reload_failed", rc=rc, stdout=out, stderr=err)
        return 1
    _emit("daemon_reload_ok")

    # Gate: the comparator must actually run. Exit 0 (match) or 1 (drift) both
    # mean it works; only 2 (inconclusive) or a crash means it cannot do its job.
    # Drift is EXPECTED here on first deploy, because this mission changes the
    # repo's backup script and the operator has not installed it yet.
    rc, out, err = _run(["/usr/bin/python3", str(_HELPER), "--dry-run"])
    if rc not in (0, 1):
        _emit("comparator_gate_failed", rc=rc, stdout=out, stderr=err,
              error="comparator could not complete; refusing to enable the timer")
        return 1
    _emit("comparator_gate_ok", rc=rc, note="0=match 1=drift (both mean it works)")

    rc, out, err = _run(["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    if rc != 0:
        _emit("enable_failed", rc=rc, stdout=out, stderr=err)
        return 1
    _emit("enable_ok", unit=_TIMER_UNIT)

    rc, out, err = _run(["systemctl", "--user", "is-enabled", _TIMER_UNIT])
    if rc != 0 or out != "enabled":
        _emit("verify_is_enabled_failed", rc=rc, stdout=out, stderr=err)
        return 1
    _emit("verify_is_enabled_ok", state=out)

    rc, out, err = _run(["systemctl", "--user", "show", _TIMER_UNIT,
                         "-p", "NextElapseUSecRealtime", "--value"])
    if rc != 0 or not out or out in ("0", "n/a", "infinity"):
        _emit("verify_next_elapse_failed", rc=rc, value=out, stderr=err)
        return 1
    _emit("verify_next_elapse_ok", next_elapse=out)

    # Seed the state pointer with a real run. `enable --now` on a TIMER starts the
    # timer, not the oneshot service, so on a first deploy the pointer would not
    # exist until the next daily fire -- and the manifest's post-verification
    # checks for it. Without this the deploy fails *after* enabling, leaving the
    # manifest queued and re-applying every tick with no alert (#891/#901).
    # Exit 0 (match) and 1 (drift) both mean it worked; 2 means it could not.
    rc, out, err = _run(["/usr/bin/python3", str(_HELPER)])
    if rc not in (0, 1):
        _emit("seed_run_failed", rc=rc, stdout=out, stderr=err,
              error="comparator could not complete a real run; state pointer not seeded")
        return 1
    _emit("seed_run_ok", rc=rc, note="0=match 1=drift; pointer now exists for post-verification")

    _emit("apply_complete", unit=_TIMER_UNIT)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="deploy-backup-script-drift.py",
        description="Install the backup-script drift comparator on office2 (#903).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    return dry_run() if args.dry_run else apply()


if __name__ == "__main__":
    sys.exit(main())
