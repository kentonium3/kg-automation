"""The backup script's state pointer, exercised rather than read (#902).

The prune outcome is only useful if `prune_exit_code` survives the paths that
*skip* the prune. Those are early `exit` branches in a bash script, which is
exactly where a shell-variable mistake hides and exactly what reading the code
tends to miss — the sibling #906 defect survived review the same way.

So these tests actually run the script, with `mountpoint`/`restic`/`du` stubbed
on PATH and the output directories redirected, and assert the emitted JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "office2" / "restic-backup.sh"

SNAPSHOT_JSON = '[{"time":"2026-08-28T04:00:05.123456Z","id":"deadbeef"}]'


def _stub(path: Path, name: str, body: str) -> None:
    f = path / name
    f.write_text("#!/usr/bin/env bash\n" + body + "\n")
    f.chmod(0o755)


@pytest.fixture
def env(tmp_path):
    """A stubbed environment; each stub's behaviour is tuned per test."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    logs = tmp_path / "logs"

    _stub(bin_dir, "mountpoint", 'exit "${STUB_MOUNT_RC:-0}"')
    _stub(bin_dir, "du", 'echo "1024\t$2"')
    # restic dispatches on its first arg so each subcommand can fail independently.
    _stub(bin_dir, "restic", f'''
case "$1" in
  snapshots) [ -n "$STUB_SNAPSHOTS_FAIL" ] && exit 1
             echo '{SNAPSHOT_JSON}'; exit 0 ;;
  backup)    exit "${{STUB_BACKUP_RC:-0}}" ;;
  forget)    exit "${{STUB_PRUNE_RC:-0}}" ;;
  check)     exit 0 ;;
  *)         exit 0 ;;
esac''')

    e = dict(os.environ)
    e["PATH"] = f"{bin_dir}:{e['PATH']}"
    e["LOG_DIR"] = str(logs)
    e["STATE_DIR"] = str(state)
    e["BACKUP_MOUNT"] = str(tmp_path / "mnt")
    e["RESTIC_REPOSITORY"] = str(tmp_path / "repo")
    e["RESTIC_PASSWORD_FILE"] = str(tmp_path / "pw")
    return e, state


def run(env_tuple, **overrides):
    e, state = env_tuple
    e = {**e, **{k: str(v) for k, v in overrides.items()}}
    proc = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True)
    pointer = json.loads((state / "last-backup.json").read_text())
    return proc, pointer


def test_pointer_is_valid_json_on_the_happy_path(env):
    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["restic_exit_code"] == 0
    assert ptr["prune_exit_code"] == 0


def test_mount_failure_records_prune_never_attempted(env):
    """The script exits before anything runs; prune must read 127, not 0."""
    proc, ptr = run(env, STUB_MOUNT_RC=1)
    assert proc.returncode == 1
    assert ptr["restic_exit_code"] == 127
    assert ptr["prune_exit_code"] == 127, "an aborted run must not report a clean prune"


def test_repo_inaccessible_records_prune_never_attempted(env):
    proc, ptr = run(env, STUB_SNAPSHOTS_FAIL="1")
    assert proc.returncode == 1
    assert ptr["prune_exit_code"] == 127


def test_backup_failure_records_prune_never_attempted(env):
    """Backup failed, so the script exits before the prune step."""
    proc, ptr = run(env, STUB_BACKUP_RC=1)
    assert proc.returncode == 1
    assert ptr["restic_exit_code"] == 1
    assert ptr["prune_exit_code"] == 127


def test_prune_failure_is_recorded(env):
    """The #902 case: backup fine, prune broken. Previously invisible."""
    proc, ptr = run(env, STUB_PRUNE_RC=1)
    assert ptr["restic_exit_code"] == 0
    assert ptr["prune_exit_code"] == 1


def test_backup_warning_with_clean_prune(env):
    """restic backup exit 3 still produced a snapshot; prune succeeded."""
    proc, ptr = run(env, STUB_BACKUP_RC=3)
    assert ptr["restic_exit_code"] == 3
    assert ptr["prune_exit_code"] == 0


def test_prune_exit_code_is_always_an_integer(env):
    """Never null: _explicit_error skips non-integers, so null reads healthy."""
    for overrides in ({}, {"STUB_MOUNT_RC": 1}, {"STUB_BACKUP_RC": 1}, {"STUB_PRUNE_RC": 2}):
        _, ptr = run(env, **overrides)
        assert isinstance(ptr["prune_exit_code"], int), f"non-integer for {overrides}"


def test_existing_fields_are_unchanged(env):
    """NFR-002: no field renamed, retyped, or dropped."""
    _, ptr = run(env)
    for key in ("schema_version", "snapshot_timestamp_utc", "snapshot_id",
                "restic_exit_code", "script_finished_at_utc", "repo_size_bytes",
                "snapshot_count", "integrity_check_run", "integrity_check_passed"):
        assert key in ptr, f"missing pre-existing field {key}"
    assert ptr["schema_version"] == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="cannot test the non-root branch as root")
def test_overrides_only_apply_when_unprivileged(env):
    """The test-only path overrides must be inert for a privileged run.

    This script is a NOPASSWD sudo target and normally runs as root. `sudo` on
    office2 is configured with env_reset + secure_path, which already strips
    these — but that makes the safety property depend on sudoers staying that
    way. The guard is intrinsic instead: a privileged run ignores the overrides
    outright, so it cannot be redirected regardless of sudo configuration.

    Asserted here by proving the guard exists and is keyed on the effective uid,
    since the test process cannot become root to exercise the other branch.
    """
    src = SCRIPT.read_text()
    assert 'if [ "$(id -u)" -eq 0 ]; then' in src, "privileged branch missing"
    guarded = src.split('if [ "$(id -u)" -eq 0 ]; then', 1)[1].split("else", 1)[0]
    for var in ("LOG_DIR", "STATE_DIR", "BACKUP_MOUNT",
                "RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE"):
        assert f'{var}="/' in guarded, f"{var} not pinned to an absolute path when root"
    # and the unprivileged branch still honours overrides, or the tests above lie
    assert 'LOG_DIR="${LOG_DIR:-' in src
