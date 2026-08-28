#!/usr/bin/env python3
"""Deploy entrypoint — hourly claude-crontab capture (#895).

Mission: ``crontab-backup-coverage-01M12V87`` (WP03).

Installs ``crontab-capture.{service,timer}`` as systemd **user** units under the
``claude`` account on office2 and enables the timer. Tier 3 (Logic/Workflow —
installs a user timer; no Tier 0/1/2 action). ``audited_surface: true``: enabling
a user timer drifts ``systemd-user-units.txt`` and
``systemd-user-unit-contents.txt``, but the unit files are tracked in the repo,
so felix-deployer's observe range sees the repo-file signal and auto-rebaselines.
``expected_baselines`` is therefore NOT declared — that field is for runtime-CLI
mutations with no repo-file signal (the canonical case being ``openclaw cron
rm``). Precedent: ``deploys/applied/0020-openclaw-ecosystem-update-check.yaml``.

Why a timer and not a sixth crontab entry: ``Linger=yes`` is set for ``claude``
and 15 user timers already run there, while the crontab holds only the five
legacy jobs #890 exists to retire. A timer is repo-tracked, manifest-deployable,
and ``Persistent=true`` catches up a run missed while the host was down — cron
silently skips it. It also means this deploy performs **no crontab edit**, so it
cannot drift ``crontabs.txt`` during the window in which that baseline is still
the only copy of the crontab.

Order (halt on first error):

  0. **Preflight: assert the deploy user** (``--apply`` only). User units install
     under ``Path.home()``; abort BEFORE any mutation if this is not the intended
     office2 ``claude`` account. Adopted from the #723 precedent.
  1. Create ``/data/services/host-state/crontabs/``.
  2. Copy both units into ``~/.config/systemd/user/``; ``daemon-reload``.
  3. ``systemctl --user enable --now crontab-capture.timer``.
  4. Verify: ``is-enabled`` reports enabled and ``list-timers`` shows a next elapse.

Idempotent: re-running on an installed host is a clean no-op that still exits 0.

⚠ Never wrap a command here in ``ssh office2-claude '...'``. This entrypoint runs
ON office2 as ``claude``; that host alias is defined in the Mac's SSH config and
loopback SSH from office2 to itself fails.

Invocation note: felix-deployer invokes entrypoints by file path
(``subprocess.run([path, "--dry-run"], shell=False)``), NOT via ``python3 -m``.

Usage:
    scripts/deploy/deploy-crontab-capture.py --dry-run
    scripts/deploy/deploy-crontab-capture.py --apply
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
_UNIT_NAMES = ("crontab-capture.service", "crontab-capture.timer")
_SOURCE_DIR = _REPO_ROOT / "scripts" / "office2"
_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_TIMER_UNIT = "crontab-capture.timer"
_ARTIFACT_DIR = Path("/data/services/host-state/crontabs")
_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")
_HELPER = _SOURCE_DIR / "crontab_capture.py"


def _emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}))


def _run(argv: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _preflight_user() -> bool:
    """Abort before any mutation if this is not the office2 `claude` account."""
    # Check the effective uid's real passwd name, not just getpass.getuser() --
    # getpass consults LOGNAME/USER/USERNAME and is environment-influenced, so on
    # its own it does not prove where units will land. And assert Path.home()
    # directly, because that is the value the install path is actually derived
    # from (post-review, Codex LOW-2).
    try:
        actual = pwd.getpwuid(os.geteuid()).pw_name
        env_name = getpass.getuser()
        home = Path.home()
    except Exception as exc:  # pragma: no cover - defensive
        _emit("preflight_error", error=f"cannot determine deploy identity: {exc}")
        return False
    if actual != _EXPECTED_USER or home != _EXPECTED_HOME:
        _emit(
            "preflight_failed",
            error="systemd user units install under $HOME; refusing to install as "
            f"euid-user '{actual}' with home '{home}' instead of "
            f"'{_EXPECTED_USER}' / '{_EXPECTED_HOME}'",
            euid_user=actual,
            env_user=env_name,
            home=str(home),
        )
        return False
    _emit("preflight_ok", user=actual, home=str(home))
    return True


def _check_sources() -> bool:
    ok = True
    for name in _UNIT_NAMES:
        src = _SOURCE_DIR / name
        if not src.is_file():
            _emit("source_missing", path=str(src))
            ok = False
    helper = _SOURCE_DIR / "crontab_capture.py"
    if not helper.is_file():
        _emit("source_missing", path=str(helper))
        ok = False
    return ok


def dry_run() -> int:
    _emit("mode", value="dry-run")
    if not _check_sources():
        return 1
    _emit("would_create_dir", path=str(_ARTIFACT_DIR))
    for name in _UNIT_NAMES:
        src, dest = _SOURCE_DIR / name, _SYSTEMD_USER_DIR / name
        if dest.exists() and filecmp.cmp(src, dest, shallow=False):
            _emit("unit_already_current", unit=name, dest=str(dest))
        else:
            _emit("would_install_unit", unit=name, src=str(src), dest=str(dest))
    _emit("would_run", argv=["/usr/bin/python3", str(_HELPER), "--dry-run"],
          note="helper gate — must pass before the timer is enabled")
    _emit("would_run", argv=["systemctl", "--user", "daemon-reload"])
    _emit("would_run", argv=["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    _emit("would_verify", argv=["systemctl", "--user", "is-enabled", _TIMER_UNIT])
    _emit("dry_run_complete", changed=False)
    return 0


def apply() -> int:
    _emit("mode", value="apply")
    if not _preflight_user():
        return 1
    if not _check_sources():
        return 1

    try:
        _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        _ARTIFACT_DIR.chmod(0o755)
        _emit("artifact_dir_ready", path=str(_ARTIFACT_DIR))
    except OSError as exc:
        _emit("artifact_dir_failed", path=str(_ARTIFACT_DIR), error=str(exc))
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

    # Gate: prove the helper actually runs BEFORE touching scheduler state.
    # Presence on disk is not evidence it works -- `crontab -l` could fail or
    # return empty, and the manifest's post-verification would only discover that
    # after the timer was already enabled, leaving a failed deploy with a live
    # timer. Same shape as the #723 precedent's --self-test gate. --dry-run
    # writes nothing, so this is safe to run before install.
    rc, out, err = _run(["/usr/bin/python3", str(_HELPER), "--dry-run"])
    if rc != 0:
        _emit("helper_gate_failed", rc=rc, stdout=out, stderr=err,
              error="helper --dry-run failed; refusing to enable the timer")
        return 1
    _emit("helper_gate_ok", output=out.splitlines()[-1:] or [])

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

    # `list-timers` exits 0 even when it lists nothing, so assert a concrete
    # scheduled elapse instead of trusting the exit code (post-review, LOW-3).
    rc, out, err = _run([
        "systemctl", "--user", "show", _TIMER_UNIT,
        "-p", "NextElapseUSecRealtime", "--value",
    ])
    if rc != 0 or not out or out in ("0", "n/a", "infinity"):
        _emit("verify_next_elapse_failed", rc=rc, value=out, stderr=err,
              error="timer reports no scheduled next elapse")
        return 1
    _emit("verify_next_elapse_ok", next_elapse=out)

    _emit("apply_complete", unit=_TIMER_UNIT)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="deploy-crontab-capture.py",
        description="Install the hourly claude-crontab capture timer on office2 (#895).",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Report intended actions; change nothing.")
    g.add_argument("--apply", action="store_true", help="Perform the install.")
    args = p.parse_args(argv)
    return dry_run() if args.dry_run else apply()


if __name__ == "__main__":
    sys.exit(main())
