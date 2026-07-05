"""Tests for scripts/deploy/migrate-inbox-state-and-logs.py (WP05 / T018).

Narrowed scope (operator decision A / #656 cycle-5): inbox-only migration —
state files (union-merge / conflict-abort / strict perms) + top-level
inbox-prescan-*.md logs only.  /home/claude/second-brain is LEFT IN PLACE.
Full decommission deferred to #659.

The migration entrypoint can't be imported as a normal module because its
filename contains hyphens, so we load it via importlib.util.

Test matrix
-----------
T-DRY         --dry-run prints the plan and mutates nothing.
T-REAL        --apply copies state files + sets modes + copies inbox-prescan logs only.
T-IDEM        A second --apply run is a safe no-op (idempotent).
T-INTACT      After --apply the source tree and observation subdirs are LEFT IN PLACE.
T-PERM-REPAIR Pre-existing target file/dir with wrong mode → repaired after --apply.
T-PERM-STRICT chown failure in strict mode (no --skip-chown) → exit 1.
T-MERGE-UNION Divergent JSONL ledger → union-merge, no entries lost.
T-CONFLICT    Divergent non-JSONL state file → exit 1, no data loss.
T-SCH         The manifest validates against the v1 schema.
"""
from __future__ import annotations

import datetime
import importlib.util
import io
import os
import shutil
import stat as _stat
from contextlib import redirect_stdout
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the migration module once at collection time.
# ---------------------------------------------------------------------------

_WORKTREE_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _WORKTREE_ROOT / "scripts" / "deploy" / "migrate-inbox-state-and-logs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "migrate_inbox_state_and_logs", _SCRIPT_PATH
    )
    assert spec is not None, f"could not locate migration script at {_SCRIPT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_module()

# ---------------------------------------------------------------------------
# Fake source tree content
# ---------------------------------------------------------------------------

_ROUTING_LOG_LINE = (
    '{"filename": "note.md", "issue_number": 42, "vikunja_task_id": 7, '
    '"routed_at": "2026-07-04T00:00:00Z", "note_excerpt": "test entry"}\n'
)
_PRESCAN_LOG_CONTENT = "# Inbox Prescan 2026-07-01\n\nSome forensic log entries.\n"
_ENRICHMENT_LOG_CONTENT = "enrichment run entry 2026-07-01\n"


def _make_stray_tree(root: Path) -> None:
    """Build a minimal fake /home/claude/second-brain tree for tests."""
    # State files
    state_dir = root / "agents" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "inbox-routing.jsonl").write_text(_ROUTING_LOG_LINE, encoding="utf-8")

    # Logs — top-level Markdown + per-agent subdir (mirrors live probe structure)
    logs_dir = root / "agents" / "logs"
    logs_dir.mkdir()
    (logs_dir / "inbox-prescan-2026-07-01.md").write_text(
        _PRESCAN_LOG_CONTENT, encoding="utf-8"
    )
    enrichment_dir = logs_dir / "enrichment"
    enrichment_dir.mkdir()
    (enrichment_dir / "enrichment-2026-07-01.log").write_text(
        _ENRICHMENT_LOG_CONTENT, encoding="utf-8"
    )


def _make_snapshot_log(base: Path) -> Path:
    """Create a fake recent Restic backup log so the snapshot gate passes."""
    log_dir = base / "backup-logs"
    log_dir.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    now_ts = (
        datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    log_file = log_dir / f"backup-{today}.log"
    log_file.write_text(
        f"{now_ts} starting restic backup\n"
        f"{now_ts} snapshot saved at deadbeefcafe123\n",
        encoding="utf-8",
    )
    return log_dir


def _invoke(
    tmp_path: Path,
    extra_args: list[str],
    *,
    skip_chown: bool = True,
) -> tuple[int, str]:
    """Run main() against tmp dirs. Returns (exit_code, captured_stdout).

    ``skip_chown=True`` (the default) adds ``--skip-chown`` to the args, which
    is necessary on dev machines where the ``claude``/``secondbrain``
    user/group do not exist.  Pass ``skip_chown=False`` only when the test
    wants to exercise the strict-ownership enforcement path (e.g. via a
    monkeypatched shutil.chown).
    """
    source_root = tmp_path / "second-brain"
    target_state_dir = tmp_path / "state"
    vault_logs_dir = tmp_path / "vault-logs"
    snapshot_log_dir = _make_snapshot_log(tmp_path)

    args = [
        "--source-root", str(source_root),
        "--target-state-dir", str(target_state_dir),
        "--vault-logs-dir", str(vault_logs_dir),
        "--snapshot-log-dir", str(snapshot_log_dir),
    ]
    if skip_chown:
        args.append("--skip-chown")
    args.extend(extra_args)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _mod.main(args)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# T-DRY: --dry-run mutates nothing
# ---------------------------------------------------------------------------

def test_dry_run_mutates_nothing(tmp_path):
    """--dry-run prints the plan and creates no files or directories."""
    _make_stray_tree(tmp_path / "second-brain")

    rc, output = _invoke(tmp_path, ["--dry-run"])

    assert rc == 0, f"dry-run exited non-zero:\n{output}"
    assert "DRY-RUN" in output, "expected DRY-RUN lines in output"

    # Target dirs must NOT have been created
    assert not (tmp_path / "state").exists(), "target state dir was created in dry-run"
    assert not (tmp_path / "vault-logs").exists(), "vault logs dir was created in dry-run"

    # Source root must still exist, untouched
    source_root = tmp_path / "second-brain"
    assert source_root.exists(), "source root was removed in dry-run"
    assert (source_root / "agents" / "state" / "inbox-routing.jsonl").exists()
    assert (source_root / "agents" / "logs" / "inbox-prescan-2026-07-01.md").exists()
    assert (source_root / "agents" / "logs" / "enrichment").exists()


# ---------------------------------------------------------------------------
# T-REAL: --apply copies state + inbox logs only; observation subdirs untouched
# ---------------------------------------------------------------------------

def test_apply_copies_state_and_inbox_logs_only(tmp_path):
    """--apply copies state files + sets permissions + copies inbox-prescan logs only.

    The observation subdir (enrichment/) must NOT appear in the vault.
    The source tree must remain in place.
    """
    _make_stray_tree(tmp_path / "second-brain")

    rc, output = _invoke(tmp_path, ["--apply"])

    assert rc == 0, f"apply failed:\n{output}"

    # State file at new canonical path with correct content
    state_file = tmp_path / "state" / "inbox-routing.jsonl"
    assert state_file.exists(), "state file not copied to target"
    assert state_file.read_text(encoding="utf-8") == _ROUTING_LOG_LINE

    # State file mode must be 0640
    file_mode = _stat.S_IMODE(state_file.stat().st_mode)
    assert file_mode == 0o640, f"state file mode {oct(file_mode)} != 0640"

    # State dir mode must be 0750
    dir_mode = _stat.S_IMODE((tmp_path / "state").stat().st_mode)
    assert dir_mode == 0o750, f"target state dir mode {oct(dir_mode)} != 0750"

    # Top-level inbox-prescan log preserved in vault
    vault_prescan = tmp_path / "vault-logs" / "inbox-prescan-2026-07-01.md"
    assert vault_prescan.exists(), "inbox-prescan log not found in vault"
    assert vault_prescan.read_text(encoding="utf-8") == _PRESCAN_LOG_CONTENT

    # Observation subdir (enrichment/) must NOT be in vault
    vault_enrichment_dir = tmp_path / "vault-logs" / "enrichment"
    assert not vault_enrichment_dir.exists(), (
        "enrichment subdir was copied to vault — should be left to #659"
    )

    # Source tree must still exist (not quarantined / not removed)
    source_root = tmp_path / "second-brain"
    assert source_root.exists(), "source root was unexpectedly removed"
    assert (source_root / "agents" / "logs" / "enrichment").exists(), (
        "enrichment subdir missing from source tree after apply"
    )


# ---------------------------------------------------------------------------
# T-IDEM: second --apply is a safe no-op
# ---------------------------------------------------------------------------

def test_second_apply_is_idempotent_noop(tmp_path):
    """A second --apply run exits 0, re-copies nothing, leaves state stable."""
    _make_stray_tree(tmp_path / "second-brain")

    # First run
    rc1, output1 = _invoke(tmp_path, ["--apply"])
    assert rc1 == 0, f"first apply failed:\n{output1}"

    state_file = tmp_path / "state" / "inbox-routing.jsonl"
    mtime_after_first = state_file.stat().st_mtime
    vault_prescan = tmp_path / "vault-logs" / "inbox-prescan-2026-07-01.md"

    # Second run
    rc2, output2 = _invoke(tmp_path, ["--apply"])
    assert rc2 == 0, f"second (idempotent) apply failed:\n{output2}"

    # State file not re-copied (mtime unchanged)
    assert state_file.stat().st_mtime == mtime_after_first, (
        "state file was re-copied on second run (not idempotent)"
    )

    # Vault inbox log still present
    assert vault_prescan.exists()

    # Observation subdir still NOT in vault after second run
    assert not (tmp_path / "vault-logs" / "enrichment").exists()

    # Source tree still in place
    source_root = tmp_path / "second-brain"
    assert source_root.exists(), "source tree removed after idempotent second run"


# ---------------------------------------------------------------------------
# T-INTACT: source tree and observation subdirs are LEFT IN PLACE after apply
# ---------------------------------------------------------------------------

def test_source_tree_left_intact_after_apply(tmp_path):
    """After --apply the /home/claude/second-brain tree and per-agent observation
    subdirs remain fully intact: not renamed, not quarantined, not removed.
    Observation log subdirs are NOT copied to the vault (#659 owns that).
    """
    _make_stray_tree(tmp_path / "second-brain")

    rc, output = _invoke(tmp_path, ["--apply"])
    assert rc == 0, f"apply failed:\n{output}"

    source_root = tmp_path / "second-brain"

    # Source root must still exist at its original path
    assert source_root.exists(), (
        "source root was removed — it must be left in place until #659"
    )

    # agents/logs/ directory still present
    assert (source_root / "agents" / "logs").exists(), (
        "agents/logs dir missing from source after apply"
    )

    # Per-agent observation subdir still present in source (not removed)
    enrichment_in_source = source_root / "agents" / "logs" / "enrichment"
    assert enrichment_in_source.exists(), (
        "enrichment subdir missing from source — it should not be touched"
    )
    assert (enrichment_in_source / "enrichment-2026-07-01.log").exists(), (
        "enrichment log file missing from source after apply"
    )

    # Per-agent observation subdir must NOT be in the vault (only inbox-prescan goes)
    assert not (tmp_path / "vault-logs" / "enrichment").exists(), (
        "enrichment subdir was copied to vault — it belongs to observation-digest (#659)"
    )


# ---------------------------------------------------------------------------
# T-PERM-REPAIR: pre-existing target file/dir with wrong mode → repaired
# ---------------------------------------------------------------------------

def test_permissions_repaired_on_preexisting_target(tmp_path):
    """Mode is corrected on a pre-existing target dir and file (not just newly-copied).

    FR-012 requires ownership/mode to be correct ALWAYS after --apply,
    including when the target file was already present from a partial run
    with wrong permissions.
    """
    _make_stray_tree(tmp_path / "second-brain")

    # Pre-create target dir and state file with WRONG modes to simulate a
    # partial prior run that set wrong permissions.
    target_state_dir = tmp_path / "state"
    target_state_dir.mkdir(parents=True)
    os.chmod(target_state_dir, 0o700)  # wrong — should be 0750

    state_file = target_state_dir / "inbox-routing.jsonl"
    state_file.write_text(_ROUTING_LOG_LINE, encoding="utf-8")  # same content as source
    os.chmod(state_file, 0o600)  # wrong — should be 0640

    rc, output = _invoke(tmp_path, ["--apply"])  # --skip-chown added by default
    assert rc == 0, f"apply with pre-existing targets failed:\n{output}"

    # SKIP emitted (content not re-copied), but perm repair must have run.
    assert "SKIP" in output, "expected SKIP message for identical pre-existing file"

    # Dir mode must be repaired to 0750.
    dir_mode = _stat.S_IMODE(target_state_dir.stat().st_mode)
    assert dir_mode == 0o750, (
        f"target state dir mode {oct(dir_mode)} not repaired to 0750 "
        "(pre-existing dir perms not enforced)"
    )

    # File mode must be repaired to 0640 (even though content was skipped).
    file_mode = _stat.S_IMODE(state_file.stat().st_mode)
    assert file_mode == 0o640, (
        f"target state file mode {oct(file_mode)} not repaired to 0640 "
        "(pre-existing file perms not enforced)"
    )


# ---------------------------------------------------------------------------
# T-PERM-STRICT: chown failure in strict mode (no --skip-chown) → exit 1
# ---------------------------------------------------------------------------

def test_strict_chown_failure_is_hard_error(tmp_path, monkeypatch):
    """When chown fails and --skip-chown is NOT set, migration must exit 1.

    In production, wrong ownership is a hard failure.  This test monkeypatches
    shutil.chown to raise PermissionError and verifies that the migration
    aborts with exit 1 and emits an ERROR/ABORT message.
    """
    _make_stray_tree(tmp_path / "second-brain")
    snapshot_log_dir = _make_snapshot_log(tmp_path)

    def _raise_perm(*args, **kwargs):
        raise PermissionError("simulated permission denied (strict-chown test)")

    monkeypatch.setattr(shutil, "chown", _raise_perm)

    # Invoke WITHOUT --skip-chown (strict mode must hard-fail on chown error).
    args = [
        "--apply",
        "--source-root", str(tmp_path / "second-brain"),
        "--target-state-dir", str(tmp_path / "state"),
        "--vault-logs-dir", str(tmp_path / "vault-logs"),
        "--snapshot-log-dir", str(snapshot_log_dir),
        # Note: --skip-chown intentionally OMITTED.
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _mod.main(args)
    output = buf.getvalue()

    assert rc == 1, (
        f"expected exit 1 when chown fails in strict mode, got {rc}:\n{output}"
    )
    assert "ERROR" in output or "ABORT" in output, (
        f"expected ERROR or ABORT in output when chown fails:\n{output}"
    )


# ---------------------------------------------------------------------------
# T-MERGE-UNION: divergent JSONL ledger → union-merge, no entries lost
# ---------------------------------------------------------------------------

def test_divergent_jsonl_ledger_is_union_merged(tmp_path):
    """Divergent inbox-routing.jsonl: union-merge preserves ALL entries (FR-005 / H1).

    Target has entries {A, B}, source has {B, C}.
    After --apply the target must contain {A, B, C}: no entry dropped.
    Source tree must remain in place (no quarantine in narrowed scope).
    """
    entry_a = (
        '{"filename": "a.md", "issue_number": 1, "vikunja_task_id": 1, '
        '"routed_at": "2026-07-04T00:00:00Z", "note_excerpt": "entry A"}'
    )
    entry_b = (
        '{"filename": "b.md", "issue_number": 2, "vikunja_task_id": 2, '
        '"routed_at": "2026-07-04T01:00:00Z", "note_excerpt": "entry B"}'
    )
    entry_c = (
        '{"filename": "c.md", "issue_number": 3, "vikunja_task_id": 3, '
        '"routed_at": "2026-07-04T02:00:00Z", "note_excerpt": "entry C"}'
    )

    # Source: entries B + C
    source_root = tmp_path / "second-brain"
    state_dir = source_root / "agents" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "inbox-routing.jsonl").write_text(
        entry_b + "\n" + entry_c + "\n", encoding="utf-8"
    )
    (source_root / "agents" / "logs").mkdir()

    # Pre-create target with entries A + B (partial / prior-run state)
    target_state_dir = tmp_path / "state"
    target_state_dir.mkdir(parents=True)
    (target_state_dir / "inbox-routing.jsonl").write_text(
        entry_a + "\n" + entry_b + "\n", encoding="utf-8"
    )

    rc, output = _invoke(tmp_path, ["--apply"])

    assert rc == 0, f"expected exit 0 for union-merge case, got {rc}:\n{output}"
    assert "MERGED" in output, f"expected MERGED label in output:\n{output}"

    result_text = (target_state_dir / "inbox-routing.jsonl").read_text(encoding="utf-8")
    assert entry_a in result_text, "entry A (target-only) lost from target after merge"
    assert entry_b in result_text, "entry B (shared) lost from target after merge"
    assert entry_c in result_text, "entry C (source-only) not merged into target"

    # Source tree must remain in place (narrowed scope — no quarantine)
    source_root = tmp_path / "second-brain"
    assert source_root.exists(), (
        "source tree was unexpectedly removed after union-merge (decommission is #659)"
    )


# ---------------------------------------------------------------------------
# T-CONFLICT: non-mergeable divergent target → exit 1, no quarantine
# ---------------------------------------------------------------------------

def test_divergent_non_mergeable_state_file_aborts_without_quarantine(tmp_path):
    """Divergent non-JSONL state file causes exit 1; source is NOT quarantined.

    A pending-calendar-clarifications.json that differs at source vs target
    cannot be auto-merged.  The migration must abort cleanly so an operator
    can resolve the conflict — no silent data loss on either side.
    """
    # Source: one version of the clarifications JSON
    source_root = tmp_path / "second-brain"
    state_dir = source_root / "agents" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "pending-calendar-clarifications.json").write_text(
        '{"pending": ["source-event-1"]}\n', encoding="utf-8"
    )
    (source_root / "agents" / "logs").mkdir()

    # Pre-create target with DIFFERENT content (e.g. written by a live agent run)
    target_state_dir = tmp_path / "state"
    target_state_dir.mkdir(parents=True)
    original_target_content = '{"pending": ["target-event-already-here"]}\n'
    target_file = target_state_dir / "pending-calendar-clarifications.json"
    target_file.write_text(original_target_content, encoding="utf-8")

    rc, output = _invoke(tmp_path, ["--apply"])

    assert rc == 1, f"expected exit 1 for non-mergeable conflict, got {rc}:\n{output}"
    assert "CONFLICT" in output, f"expected CONFLICT in output:\n{output}"

    # Source root must still exist — operator must resolve first
    source_root_path = tmp_path / "second-brain"
    assert source_root_path.exists(), (
        "source was removed despite non-mergeable conflict (data-loss risk)"
    )

    # Target content must be unchanged — migration must not corrupt the target
    assert target_file.read_text(encoding="utf-8") == original_target_content, (
        "target content was modified during conflict-abort (data-loss!)"
    )


# ---------------------------------------------------------------------------
# T-SCH: manifest validates against v1 schema
# ---------------------------------------------------------------------------

def test_manifest_validates_against_schema():
    """deploys/queued/0007-migrate-inbox-state-and-logs.yaml validates against v1 schema."""
    from scripts.deploy.lib.manifest import validate_manifest_file

    manifest_path = (
        _WORKTREE_ROOT / "deploys" / "queued" / "0007-migrate-inbox-state-and-logs.yaml"
    )
    assert manifest_path.exists(), f"manifest not found: {manifest_path}"
    result = validate_manifest_file(manifest_path)
    assert result.ok, f"Manifest validation failed:\n{result.details}"


def test_dry_run_via_shebang_from_nonrepo_cwd(tmp_path):
    """felix-deployer runs `[entrypoint, --dry-run]` via the shebang from a
    non-repo cwd with no PYTHONPATH. Reproduce that exactly: it must exit 0.
    Catches (a) the missing executable bit, (b) the sys.path shim needed for
    `from scripts.deploy.lib...`, and (c) the snapshot gate wrongly gating a
    dry-run. The prior unit tests imported main() directly and missed all three."""
    import os
    import subprocess
    from pathlib import Path as _P
    ep = _P(__file__).resolve().parents[2] / "scripts" / "deploy" / "migrate-inbox-state-and-logs.py"
    assert os.access(ep, os.X_OK), "entrypoint must be executable (git mode 100755)"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [str(ep), "--dry-run"], cwd=str(tmp_path), env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"dry-run must exit 0.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"


def test_gateway_dropin_entrypoint_dry_run_via_shebang(tmp_path):
    """Same reproduction for the WP01 gateway drop-in entrypoint."""
    import os
    import subprocess
    from pathlib import Path as _P
    ep = _P(__file__).resolve().parents[2] / "scripts" / "deploy" / "install-gateway-pythonpath-dropin.py"
    assert os.access(ep, os.X_OK), "entrypoint must be executable (git mode 100755)"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [str(ep), "--dry-run"], cwd=str(tmp_path), env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"dry-run must exit 0.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
