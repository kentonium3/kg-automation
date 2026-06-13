"""Tests for the anthropic-verify --repair surface (WP02).

Verifies the spec contracts for the repair mode:
  * FR-007 — modes (--repair gates mutation)
  * FR-008 — backup-before-mutate (always a .pre-repair.<ts>.bak sibling)
  * FR-009 — shadow clear prints systemctl restart command verbatim
  * FR-010 — atomic rename for plaintext drift (tmp -> rename, mode 0600)
  * NFR-004 — repair integrity: either backup AND mutation land, or neither
  * C-005 — no key value ever appears in stdout/stderr/error messages

Seven scenarios are exercised, each isolated via the ``tmp_office2_root``
conftest fixture from WP01:

  1. Shadow repair end-to-end (rows cleared, backup written, systemctl line printed).
  2. Drift repair end-to-end (plaintext rewritten atomically, sha matches main).
  3. Backup-before-mutate (failure between backup and DELETE leaves SQLite unchanged).
  4. No key in repair output (capsys sweep for sentinels).
  5. Repair integrity check (post-write tampering raises RuntimeError; message scrubbed).
  6. No-op when green (no backup files, "nothing to repair", exit 0).
  7. Not-repairable findings (main_empty / plaintext_missing pass through, no mutation).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from anthropic_verify import core, repair
from tests.security.fixtures import build_fixtures as bf


SENTINELS = (
    bf.SENTINEL_CANONICAL,
    bf.SENTINEL_SHADOW,
    bf.SENTINEL_PLAINTEXT_DRIFT,
)


def _grep_for_sentinels(text: str) -> list[str]:
    """Return list of sentinels found in ``text`` (empty == no leak)."""
    return [s for s in SENTINELS if s in text]


def _find_backups(root: Path) -> list[Path]:
    """Walk ``root`` returning every file whose name contains '.pre-repair.'."""
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if ".pre-repair." in fn:
                out.append(Path(dirpath) / fn)
    return out


def _snapshot_sqlite_rows(sqlite_path: Path) -> tuple[int, int]:
    """Return (store_rows, state_rows) for the given SQLite file."""
    con = sqlite3.connect(str(sqlite_path))
    try:
        store = con.execute("SELECT COUNT(*) FROM auth_profile_store").fetchone()[0]
        state = con.execute("SELECT COUNT(*) FROM auth_profile_state").fetchone()[0]
        return int(store), int(state)
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Scenario 1 — Shadow repair end-to-end
# --------------------------------------------------------------------------- #


def test_shadow_repair_clears_rows_and_writes_backup(tmp_office2_root, capsys):
    """Shadow finding triggers backup + DELETEs + systemctl-restart line."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path, agent_id="felix-admin-capture")

    shadow_sqlite = (
        agents_dir / "felix-admin-capture" / "agent" / "openclaw-agent.sqlite"
    )
    # Pre-condition: shadowed agent has rows.
    pre_store, pre_state = _snapshot_sqlite_rows(shadow_sqlite)
    assert pre_store == 1 and pre_state == 1

    rc = repair.run_repair()
    out = capsys.readouterr().out

    # Rows cleared.
    post_store, post_state = _snapshot_sqlite_rows(shadow_sqlite)
    assert post_store == 0 and post_state == 0

    # Backup exists with the .pre-repair.<ts>.bak suffix at mode 0600.
    backups = _find_backups(agents_dir)
    assert len(backups) == 1, f"expected exactly one backup, got {backups}"
    backup = backups[0]
    assert ".pre-repair." in backup.name
    assert backup.name.endswith(".bak")
    assert (backup.stat().st_mode & 0o777) == 0o600

    # Systemctl restart line printed VERBATIM (FR-009).
    assert "systemctl --user restart openclaw-gateway.service" in out

    # Post-repair check should be green now.
    assert rc == 0
    assert "==> repair result: green" in out

    # No sentinels in output.
    assert _grep_for_sentinels(out) == []


# --------------------------------------------------------------------------- #
# Scenario 2 — Drift repair end-to-end
# --------------------------------------------------------------------------- #


def test_drift_repair_atomically_rewrites_plaintext(tmp_office2_root, capsys):
    """Drift finding triggers backup + atomic plaintext rewrite."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)

    # Pre-condition: plaintext sha differs from main's canonical sha.
    pre_state = core.read_plaintext_state(plaintext_path)
    main_sha = hashlib.sha256(bf.SENTINEL_CANONICAL.encode("utf-8")).hexdigest()[
        : core.SHA_FINGERPRINT_LEN
    ]
    assert pre_state.sha8 != main_sha

    rc = repair.run_repair()
    out = capsys.readouterr().out

    # Plaintext sha now matches main's canonical key sha.
    post_state = core.read_plaintext_state(plaintext_path)
    assert post_state.sha8 == main_sha

    # Plaintext file is mode 0600.
    assert (plaintext_path.stat().st_mode & 0o777) == 0o600

    # No leftover .tmp sibling — atomic rename completed.
    tmp_sibling = plaintext_path.parent / (plaintext_path.name + ".tmp")
    assert not tmp_sibling.exists()

    # Backup written.
    backups = _find_backups(plaintext_path.parent)
    assert len(backups) >= 1
    assert any(".pre-repair." in b.name and b.name.endswith(".bak") for b in backups)

    # Sentinel never appears in output even though we read the key value through.
    assert _grep_for_sentinels(out) == []

    # Post-repair check should be green.
    assert rc == 0


# --------------------------------------------------------------------------- #
# Scenario 3 — Backup-before-mutate (FR-008 / NFR-004)
# --------------------------------------------------------------------------- #


def test_shadow_repair_writes_backup_before_attempting_mutation(
    tmp_office2_root, monkeypatch, capsys
):
    """If the DELETE step raises, the backup must already exist and the SQLite
    rows must be unchanged. Proves backup-before-mutate ordering (FR-008)."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path, agent_id="felix-admin-capture")
    shadow_sqlite = (
        agents_dir / "felix-admin-capture" / "agent" / "openclaw-agent.sqlite"
    )
    pre_rows = _snapshot_sqlite_rows(shadow_sqlite)
    assert pre_rows == (1, 1)

    # Patch sqlite3.connect (the symbol the repair module sees) to raise
    # AFTER shutil.copy2 has written the backup but BEFORE the DELETE
    # statements land. Detection condition: a backup file with the
    # ``.pre-repair.`` marker already exists in the shadow agent's dir.
    real_connect = sqlite3.connect

    def _connect_then_raise(*args, **kwargs):
        path_arg = str(args[0]) if args else str(kwargs.get("database", ""))
        if path_arg == str(shadow_sqlite) and any(
            b.parent == shadow_sqlite.parent and ".pre-repair." in b.name
            for b in _find_backups(agents_dir)
        ):
            raise sqlite3.OperationalError("simulated mutation failure")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(repair.sqlite3, "connect", _connect_then_raise)

    with pytest.raises(sqlite3.OperationalError, match="simulated"):
        repair.run_repair()

    # Backup file must exist — written BEFORE the failing mutation.
    backups = _find_backups(agents_dir)
    assert len(backups) >= 1
    assert any(b.name.endswith(".bak") for b in backups)

    # Undo the monkey-patch so the read-back uses the real connect; the
    # shadow sqlite's "post-mutation" rowcount must equal the pre-mutation
    # snapshot, proving the DELETE never landed.
    monkeypatch.setattr(repair.sqlite3, "connect", real_connect)
    post_rows = _snapshot_sqlite_rows(shadow_sqlite)
    assert post_rows == pre_rows

    # Backup is at mode 0600 even on the abort path.
    backup = next(b for b in backups if b.parent == shadow_sqlite.parent)
    assert (backup.stat().st_mode & 0o777) == 0o600


# --------------------------------------------------------------------------- #
# Scenario 4 — No key in repair output (C-005 / FR-006)
# --------------------------------------------------------------------------- #


def test_no_sentinel_in_drift_repair_output(tmp_office2_root, capsys):
    """A successful drift repair reads the key through and writes it to the
    plaintext file. Sentinel must NOT appear anywhere in stdout or stderr."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)

    repair.run_repair()
    captured = capsys.readouterr()

    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


def test_no_sentinel_in_shadow_repair_output(tmp_office2_root, capsys):
    """Shadow repair touches no key value but the sentinel sweep should still pass."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path)

    repair.run_repair()
    captured = capsys.readouterr()

    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


# --------------------------------------------------------------------------- #
# Scenario 5 — Repair integrity check
# --------------------------------------------------------------------------- #


def test_drift_repair_raises_on_post_write_mismatch(
    tmp_office2_root, monkeypatch, capsys
):
    """If the post-rename re-fingerprint differs from main's, repair raises
    a RuntimeError naming 'REPAIR INTEGRITY FAILURE' WITHOUT including the
    key value in the error message."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)

    # Patch read_bytes on the Path class to return a tampered value AFTER
    # the rename happens. We only want to corrupt the post-write
    # verification read, not any other read — gate by path.
    original_read_bytes = Path.read_bytes
    state = {"renamed": False}

    # Install a hook that flips ``state["renamed"]`` when os.rename is
    # called on the plaintext path. After that, read_bytes returns
    # tampered content for the plaintext file specifically.
    original_rename = os.rename

    def _rename_hook(src, dst):
        result = original_rename(src, dst)
        if str(dst) == str(plaintext_path):
            state["renamed"] = True
        return result

    def _tampered_read_bytes(self):
        if state["renamed"] and str(self) == str(plaintext_path):
            return b"TAMPERED-DIFFERENT-CONTENT"
        return original_read_bytes(self)

    monkeypatch.setattr(repair.os, "rename", _rename_hook)
    monkeypatch.setattr(Path, "read_bytes", _tampered_read_bytes)

    with pytest.raises(RuntimeError, match="REPAIR INTEGRITY FAILURE") as exc_info:
        repair.run_repair()

    err_text = str(exc_info.value)
    # Error message must not contain any sentinel.
    assert _grep_for_sentinels(err_text) == []
    # Also no key-shape substring leaked through.
    assert "sk-ant-FIXTURE" not in err_text


# --------------------------------------------------------------------------- #
# Scenario 6 — No-op when green
# --------------------------------------------------------------------------- #


def test_no_op_when_green(tmp_office2_root, capsys):
    """Healthy fixture: no findings, no mutation, no backup, exit 0."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)

    rc = repair.run_repair()
    out = capsys.readouterr().out

    assert rc == 0
    assert "nothing to repair" in out

    # No backup files anywhere under the tmp root.
    backups = _find_backups(agents_dir.parent)
    assert backups == [], f"unexpected backups: {backups}"


# --------------------------------------------------------------------------- #
# Scenario 7 — Not-repairable findings pass through
# --------------------------------------------------------------------------- #


def test_main_empty_finding_is_not_repaired(tmp_office2_root, capsys):
    """main_empty is reported but not auto-repaired — operator must rotate."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_main_empty(agents_dir, plaintext_path)

    rc = repair.run_repair()
    out = capsys.readouterr().out

    assert "NOT REPAIRABLE" in out
    assert "main_empty" in out
    assert rc != 0  # findings remain after repair attempt

    # No backup files written (we never reached a mutation path).
    backups = _find_backups(agents_dir.parent)
    assert backups == []


def test_plaintext_missing_finding_is_not_repaired(tmp_office2_root, capsys):
    """plaintext_missing is reported but not auto-repaired — operator must rotate."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_plaintext_missing(agents_dir, plaintext_path)

    rc = repair.run_repair()
    out = capsys.readouterr().out

    assert "NOT REPAIRABLE" in out
    assert "plaintext_missing" in out
    assert rc != 0
    # No backup files.
    backups = _find_backups(agents_dir.parent)
    assert backups == []


# --------------------------------------------------------------------------- #
# Bash entry / dispatch wiring (T009)
# --------------------------------------------------------------------------- #


def test_main_dispatches_repair_when_module_present(tmp_office2_root, capsys):
    """With repair.py present, ``main(['--repair'])`` invokes run_repair().

    Uses the healthy fixture so it returns 0 and prints the no-op line —
    proves the lazy import + dispatch path works end-to-end without
    relying on real office2 paths.
    """
    import anthropic_verify

    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)

    rc = anthropic_verify.main(["--repair"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "nothing to repair" in out
