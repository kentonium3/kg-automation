"""Tests for the Phase-1 observation-log migration (WP02 / T007).

Mission: observation-digest-repoint-01KWS2E2 (fast-follow of #656 → #659)

Mirrors the conventions of ``tests/deploy/test_migrate_inbox_state.py`` (temp
dirs, subprocess dry-run, no live office2/Restic — the snapshot gate is mocked
or skipped).  Phase 1 is strictly non-destructive: these tests assert the
source tree is never removed and that no path outside ``agents/logs/*`` (and no
``_private`` path) ever appears in the JSON plan.

Test matrix
-----------
T-UNION       union_merge_jsonl produces the set-union of src+dst lines, no dup.
T-ATOMIC      union_merge_jsonl leaves no leftover .tmp and uses os.replace.
T-IDEM        A second union_merge_jsonl is a no-op (0 new lines).
T-SCOPE       iter_source_log_files globs only agents/logs/*/*.jsonl; ignores
              top-level .md and never descends into non-agents/logs dirs.
T-DRY-SUB     --dry-run via subprocess exits 0 and mutates nothing.
T-PLAN-CLEAN  The JSON plan contains no _private and no path outside agents/logs/*.
T-XBIT        The entrypoint file has the executable bit + contains the sys.path shim.
T-APPLY       --apply union-merges into the vault under per-agent subdirs.
T-WRITABLE    check_vault_writable raises when the target is not writable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.deploy import observation_migration as om

_WORKTREE_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT = _WORKTREE_ROOT / "scripts" / "deploy" / "migrate-observation-logs.py"


# ---------------------------------------------------------------------------
# Fake stray-tree builder
# ---------------------------------------------------------------------------

_ENRICH_A = '{"agent": "enrichment", "action": "run", "ts": "2026-07-01T00:00:00Z"}'
_ENRICH_B = '{"agent": "enrichment", "action": "run", "ts": "2026-07-01T01:00:00Z"}'
_ADMIN_A = '{"agent": "felix-admin", "action": "scan", "ts": "2026-07-01T00:00:00Z"}'


def _make_stray_tree(root: Path) -> None:
    """Build a minimal fake /home/claude/second-brain tree for tests.

    Includes: per-agent JSONL logs (in scope), a top-level .md forensic log
    (out of scope), a non-agents/logs dir with a JSONL (must be ignored), and a
    top-level _private dir (must never be touched).
    """
    logs = root / "agents" / "logs"
    (logs / "enrichment").mkdir(parents=True)
    (logs / "enrichment" / "2026-07-01.jsonl").write_text(
        _ENRICH_A + "\n" + _ENRICH_B + "\n", encoding="utf-8"
    )
    (logs / "felix-admin").mkdir()
    (logs / "felix-admin" / "2026-07-01.jsonl").write_text(
        _ADMIN_A + "\n", encoding="utf-8"
    )

    # Top-level forensic markdown — must NOT be globbed (C-008).
    (logs / "inbox-prescan-2026-07-01.md").write_text("# forensic\n", encoding="utf-8")

    # A non-agents/logs directory with a JSONL — must be ignored.
    other = root / "agents" / "state"
    other.mkdir(parents=True)
    (other / "inbox-routing.jsonl").write_text("{}\n", encoding="utf-8")

    # A _private path that must never be walked toward or emitted.
    private = root / "notes" / "04-Growth" / "_private"
    private.mkdir(parents=True)
    (private / "secret.jsonl").write_text('{"secret": true}\n', encoding="utf-8")


# ---------------------------------------------------------------------------
# T-UNION / T-ATOMIC / T-IDEM: atomic union-merge
# ---------------------------------------------------------------------------

def test_union_merge_is_set_union_no_dup(tmp_path):
    """Result == union of src+dst lines; existing dst order first, no duplicates."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    # dst has {A, B}; src has {B, C} — shared B must not duplicate.
    src.write_text(_ENRICH_B + "\n" + _ADMIN_A + "\n", encoding="utf-8")
    dst.write_text(_ENRICH_A + "\n" + _ENRICH_B + "\n", encoding="utf-8")

    new_count = om.union_merge_jsonl(src, dst)

    lines = dst.read_text(encoding="utf-8").splitlines()
    assert lines == [_ENRICH_A, _ENRICH_B, _ADMIN_A], f"unexpected union order: {lines}"
    assert new_count == 1, "only the source-only line should count as new"
    # No duplicate B.
    assert lines.count(_ENRICH_B) == 1


def test_union_merge_into_missing_dst_copies_all(tmp_path):
    """When dst does not exist, the merge writes all source lines."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "sub" / "dst.jsonl"  # parent dir does not exist yet
    src.write_text(_ENRICH_A + "\n" + _ENRICH_B + "\n", encoding="utf-8")

    new_count = om.union_merge_jsonl(src, dst)

    assert dst.exists()
    assert dst.read_text(encoding="utf-8").splitlines() == [_ENRICH_A, _ENRICH_B]
    assert new_count == 2


def test_union_merge_atomic_no_leftover_tmp_and_uses_replace(tmp_path, monkeypatch):
    """The merge writes via a temp file replaced with os.replace; no .tmp remains."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    src.write_text(_ENRICH_A + "\n", encoding="utf-8")
    dst.write_text(_ENRICH_B + "\n", encoding="utf-8")

    replace_calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def _spy_replace(a, b):
        replace_calls.append((str(a), str(b)))
        return real_replace(a, b)

    monkeypatch.setattr(om.os, "replace", _spy_replace)

    om.union_merge_jsonl(src, dst)

    assert replace_calls, "os.replace was not used for the atomic write"
    assert replace_calls[0][1] == str(dst), "os.replace target must be the destination"
    # No leftover temp file in the destination directory.
    leftover = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == [], f"leftover temp file(s) after merge: {leftover}"


def test_union_merge_is_idempotent(tmp_path):
    """A second merge of the same source is a no-op (0 new lines)."""
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "dst.jsonl"
    src.write_text(_ENRICH_A + "\n" + _ENRICH_B + "\n", encoding="utf-8")

    first = om.union_merge_jsonl(src, dst)
    second = om.union_merge_jsonl(src, dst)

    assert first == 2
    assert second == 0, "second identical merge should add no new lines"
    assert dst.read_text(encoding="utf-8").splitlines() == [_ENRICH_A, _ENRICH_B]


# ---------------------------------------------------------------------------
# T-SCOPE: iter_source_log_files bounded traversal (C-008)
# ---------------------------------------------------------------------------

def test_iter_source_log_files_globs_only_agents_logs(tmp_path):
    """Only agents/logs/*/*.jsonl matched; top-level .md and other dirs ignored."""
    root = tmp_path / "second-brain"
    _make_stray_tree(root)

    found = om.iter_source_log_files(root)
    rel = sorted(str(p.relative_to(root)) for p in found)

    assert rel == [
        "agents/logs/enrichment/2026-07-01.jsonl",
        "agents/logs/felix-admin/2026-07-01.jsonl",
    ], f"unexpected discovery set: {rel}"

    # Top-level .md forensic log must NOT be matched.
    assert not any(p.suffix == ".md" for p in found)
    # No _private path may ever be discovered.
    assert not any("_private" in p.parts for p in found)
    # The non-agents/logs JSONL (agents/state/) must NOT be matched.
    assert not any("state" in p.parts for p in found)


def test_iter_source_log_files_missing_logs_dir_is_empty(tmp_path):
    """A source root with no agents/logs dir yields an empty list (no error)."""
    root = tmp_path / "empty-tree"
    root.mkdir()
    assert om.iter_source_log_files(root) == []


# ---------------------------------------------------------------------------
# T-PLAN-CLEAN: migrate_logs dry-run plan is clean and mutates nothing
# ---------------------------------------------------------------------------

def test_migrate_logs_dry_run_plan_is_clean_and_no_mutation(tmp_path):
    """Dry-run returns a clean relative plan and creates no vault files."""
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    result = om.migrate_logs(root, vault, dry_run=True)

    assert result["plan_only"] is True
    assert sorted(result["migrated"]) == [
        "enrichment/2026-07-01.jsonl",
        "felix-admin/2026-07-01.jsonl",
    ]
    # No absolute paths, no _private, nothing outside agents/logs/<agent>/<file>.
    blob = json.dumps(result)
    assert "_private" not in blob
    assert "/home/claude" not in blob
    for entry in result["migrated"]:
        assert not entry.startswith("/"), f"plan entry is absolute: {entry}"
        assert entry.count("/") == 1, f"plan entry escapes agents/logs scope: {entry}"

    # Dry-run must not create the vault dir or any per-agent subdir.
    assert not vault.exists(), "dry-run created the vault dir"


# ---------------------------------------------------------------------------
# T-APPLY: migrate_logs applies into per-agent vault subdirs
# ---------------------------------------------------------------------------

def test_migrate_logs_apply_writes_per_agent_subdirs(tmp_path):
    """--apply (dry_run=False) union-merges into vault_logs_dir/<agent>/<file>."""
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    result = om.migrate_logs(root, vault, dry_run=False)
    assert result["plan_only"] is False

    enrich = vault / "enrichment" / "2026-07-01.jsonl"
    admin = vault / "felix-admin" / "2026-07-01.jsonl"
    assert enrich.read_text(encoding="utf-8").splitlines() == [_ENRICH_A, _ENRICH_B]
    assert admin.read_text(encoding="utf-8").splitlines() == [_ADMIN_A]

    # Non-destructive: the source tree remains fully intact.
    assert (root / "agents" / "logs" / "enrichment" / "2026-07-01.jsonl").exists()
    assert (root / "notes" / "04-Growth" / "_private" / "secret.jsonl").exists()


# ---------------------------------------------------------------------------
# T-WRITABLE: check_vault_writable (C-011)
# ---------------------------------------------------------------------------

def test_check_vault_writable_ok(tmp_path):
    """A writable target passes and leaves no probe file behind."""
    vault = tmp_path / "vault-logs"
    om.check_vault_writable(vault)  # creates the dir + probes
    assert vault.exists()
    leftover = list(vault.iterdir())
    assert leftover == [], f"writability probe left files behind: {leftover}"


def test_check_vault_writable_raises_on_unwritable(tmp_path, monkeypatch):
    """A non-writable target raises a clear RuntimeError (C-011)."""
    vault = tmp_path / "vault-logs"
    vault.mkdir()

    def _deny(*args, **kwargs):
        raise PermissionError("simulated read-only vault")

    monkeypatch.setattr(om.tempfile, "mkstemp", _deny)

    with pytest.raises(RuntimeError, match="not writable"):
        om.check_vault_writable(vault)


# ---------------------------------------------------------------------------
# T-XBIT: entrypoint executable bit + sys.path shim
# ---------------------------------------------------------------------------

def test_entrypoint_has_exec_bit_and_shim():
    """The hyphenated wrapper is +x and carries the sys.path shim."""
    assert os.access(_ENTRYPOINT, os.X_OK), "entrypoint must be executable (git mode 100755)"
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3"), "missing shebang"
    assert "_REPO_ROOT = Path(__file__).resolve().parents[2]" in text, "missing sys.path shim"
    assert "sys.path.insert(0, str(_REPO_ROOT))" in text, "shim does not insert repo root"


# ---------------------------------------------------------------------------
# T-DRY-SUB: subprocess dry-run exits 0, mutates nothing, prints clean JSON
# ---------------------------------------------------------------------------

def test_dry_run_via_subprocess_exits_zero_and_no_mutation(tmp_path):
    """felix-deployer's shebang dry-run: exit 0, no mutation, one clean JSON object."""
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    # Reproduce felix-deployer: run via the shebang from a non-repo cwd with no
    # PYTHONPATH. The snapshot gate must not be reached in a dry-run.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            str(_ENTRYPOINT),
            "--dry-run",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"dry-run must exit 0.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"

    # stdout carries exactly one JSON object; it must be clean.
    plan = json.loads(proc.stdout.strip())
    assert plan["plan_only"] is True
    assert sorted(plan["migrated"]) == [
        "enrichment/2026-07-01.jsonl",
        "felix-admin/2026-07-01.jsonl",
    ]
    assert "_private" not in proc.stdout
    assert "/home/claude" not in proc.stdout

    # No mutation: the vault dir was not created by a dry-run.
    assert not vault.exists(), "dry-run created the vault dir"


def test_apply_via_subprocess_with_skip_gate(tmp_path):
    """--apply --skip-snapshot-gate migrates into the vault and exits 0."""
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            str(_ENTRYPOINT),
            "--apply",
            "--skip-snapshot-gate",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"apply failed.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
    result = json.loads(proc.stdout.strip())
    assert result["plan_only"] is False
    assert (vault / "enrichment" / "2026-07-01.jsonl").exists()
    # Source tree left intact (non-destructive).
    assert root.exists()
    assert (root / "notes" / "04-Growth" / "_private" / "secret.jsonl").exists()
