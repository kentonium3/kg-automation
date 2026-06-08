"""Tests for scripts/openclaw/deploy/deploy_agent_prompts.py (WP01).

Per DIR-034 Test-First Development: all production functions covered by tests.
Per NFR-003: coverage gate ≥90% line / ≥85% branch (enforced via pytest-cov).

No SSH, no real /data/services/, no real git. All I/O via tmp_path fixtures
and subprocess mocking. Production behavior on office2 is verified
operator-side at install time (SC-4).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.openclaw.deploy import deploy_agent_prompts as dap


# ---------------------------------------------------------------------------
# is_in_scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,expected", [
    ("AGENTS.md", True),
    ("IDENTITY.md", True),
    ("SOUL.md", True),
    ("TOOLS.md", True),
    ("USER.md", True),
    ("HEARTBEAT.md", False),
    ("HEARTBEAT.md.bak.pre-mission-490", False),
    ("AGENTS.md.tmpl", False),
    ("TOOLS.md.tmpl", False),
    ("USER.md.tmpl", False),
    ("GOVERNANCE.md", False),
    ("AGENTS.md.bak", False),
    ("AGENTS.md.bak.foo", False),
    ("random.md", False),
    ("README.md", False),
    ("AGENTS", False),
])
def test_is_in_scope(filename, expected):
    assert dap.is_in_scope(filename) is expected


# ---------------------------------------------------------------------------
# iter_agents
# ---------------------------------------------------------------------------


def _write_inventory(path: Path, agents: dict, top_level_extras: dict | None = None):
    """Helper: write a synthetic service-inventory.json with the openclaw entry."""
    # The production service-inventory.json names this entry "openclaw-gateway".
    # Fixtures use the production name so the suite reflects what the helper
    # actually has to parse on office2.
    data = {
        "schema_version": "1.1",
        "last_updated": "2026-06-08",
        "services": [
            {
                "name": "vikunja",
                "type": "docker-compose",
            },
            {
                "name": "openclaw-gateway",
                "type": "npm-global",
                "agents": agents,
            },
        ],
    }
    if top_level_extras:
        data.update(top_level_extras)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_iter_agents_yields_only_complete_entries(tmp_path):
    inv = tmp_path / "service-inventory.json"
    _write_inventory(inv, {
        "felix-admin-capture": {
            "source_in_repo": "scripts/openclaw/agents/felix-admin-capture/",
            "workspace": "/data/services/openclaw/inbox-agent",
        },
        "missing-source": {
            "workspace": "/data/services/openclaw/missing-source",
        },
        "missing-workspace": {
            "source_in_repo": "scripts/openclaw/agents/missing-workspace/",
        },
        "empty-source": {
            "source_in_repo": "",
            "workspace": "/data/services/openclaw/empty",
        },
        "felix-admin-habits": {
            "source_in_repo": "scripts/openclaw/agents/felix-admin-habits/",
            "workspace": "/data/services/openclaw/habits-agent",
        },
    })
    agents = list(dap.iter_agents(inv))
    slugs = sorted(a.slug for a in agents)
    assert slugs == ["felix-admin-capture", "felix-admin-habits"]
    capture = next(a for a in agents if a.slug == "felix-admin-capture")
    assert isinstance(capture.source_in_repo, Path)
    assert isinstance(capture.workspace, Path)
    assert capture.source_in_repo == Path("scripts/openclaw/agents/felix-admin-capture/")
    assert capture.workspace == Path("/data/services/openclaw/inbox-agent")


def test_iter_agents_returns_nothing_when_no_openclaw_service(tmp_path):
    inv = tmp_path / "service-inventory.json"
    data = {"services": [{"name": "vikunja"}]}
    inv.write_text(json.dumps(data))
    assert list(dap.iter_agents(inv)) == []


def test_iter_agents_matches_legacy_openclaw_name(tmp_path):
    """Helper also accepts the legacy 'openclaw' service name (pre-rename inventories)."""
    inv = tmp_path / "service-inventory.json"
    data = {
        "services": [
            {"name": "vikunja"},
            {
                "name": "openclaw",
                "agents": {
                    "felix-admin-capture": {
                        "source_in_repo": "scripts/openclaw/agents/felix-admin-capture/",
                        "workspace": "/data/services/openclaw/inbox-agent",
                    },
                },
            },
        ]
    }
    inv.write_text(json.dumps(data))
    agents = list(dap.iter_agents(inv))
    assert [a.slug for a in agents] == ["felix-admin-capture"]


def test_iter_agents_fallback_finds_first_service_with_agents(tmp_path):
    """If no openclaw* named service exists, fall back to first service with agents dict."""
    inv = tmp_path / "service-inventory.json"
    data = {
        "services": [
            {"name": "unrelated-svc-name", "agents": {
                "a": {"source_in_repo": "src-a/", "workspace": "/dst-a"},
            }},
        ]
    }
    inv.write_text(json.dumps(data))
    agents = list(dap.iter_agents(inv))
    assert [a.slug for a in agents] == ["a"]


def test_iter_agents_handles_non_dict_meta(tmp_path):
    inv = tmp_path / "service-inventory.json"
    _write_inventory(inv, {
        "bad-meta": "not a dict",
        "good": {
            "source_in_repo": "src/",
            "workspace": "/dst",
        },
    })
    agents = list(dap.iter_agents(inv))
    assert [a.slug for a in agents] == ["good"]


def test_iter_agents_handles_agents_dict_missing(tmp_path):
    inv = tmp_path / "service-inventory.json"
    data = {"services": [{"name": "openclaw"}]}
    inv.write_text(json.dumps(data))
    assert list(dap.iter_agents(inv)) == []


# ---------------------------------------------------------------------------
# compute_md5
# ---------------------------------------------------------------------------


def test_compute_md5_known_content(tmp_path):
    f = tmp_path / "f.md"
    f.write_bytes(b"hello world")
    # md5("hello world") == "5eb63bbbe01eeed093cb22bb8f5acdc3"
    assert dap.compute_md5(f) == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_compute_md5_empty(tmp_path):
    f = tmp_path / "empty.md"
    f.write_bytes(b"")
    # md5("") == "d41d8cd98f00b204e9800998ecf8427e"
    assert dap.compute_md5(f) == "d41d8cd98f00b204e9800998ecf8427e"


def test_compute_md5_large_file_chunked(tmp_path):
    f = tmp_path / "big.bin"
    # 200KB > MD5_CHUNK_BYTES (64KB) — exercises the chunked read loop
    f.write_bytes(b"x" * (200 * 1024))
    result = dap.compute_md5(f)
    assert len(result) == 32
    assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# atomic_copy
# ---------------------------------------------------------------------------


def test_atomic_copy_new_destination(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"new content")
    dap.atomic_copy(src, dst)
    assert dst.read_bytes() == b"new content"


def test_atomic_copy_existing_destination_preserves_mode(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    os.chmod(dst, 0o600)
    dap.atomic_copy(src, dst)
    assert dst.read_bytes() == b"new"
    assert (dst.stat().st_mode & 0o777) == 0o600


def test_atomic_copy_existing_destination_644_mode_preserved(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    os.chmod(dst, 0o644)
    dap.atomic_copy(src, dst)
    assert (dst.stat().st_mode & 0o777) == 0o644


def test_atomic_copy_cleans_up_temp_on_success(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"new")
    dap.atomic_copy(src, dst)
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_atomic_copy_raises_and_cleans_up_temp_on_failure(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"new")
    with patch.object(dap.os, "replace", side_effect=OSError("simulated")):
        with pytest.raises(OSError, match="simulated"):
            dap.atomic_copy(src, dst)
    # temp file should not be left behind
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []
    # dst should be untouched
    assert not dst.exists()


# ---------------------------------------------------------------------------
# git_pull
# ---------------------------------------------------------------------------


def _mock_run_factory(*results):
    """Return a side_effect callable that returns successive CompletedProcess-like results."""
    iter_results = iter(results)

    def _run(*args, **kwargs):
        return next(iter_results)

    return _run


def _ok(stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=stderr)


def _fail(stderr="fatal: simulated", code=1):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout="", stderr=stderr)


def test_git_pull_success_returns_head_sha(tmp_path):
    sha = "a" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        result = dap.git_pull(tmp_path)
    assert result.success is True
    assert result.head_sha == sha
    assert result.stage is None


def test_git_pull_fetch_fails(tmp_path):
    side = _mock_run_factory(_fail("fatal: no network"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "fetch"
    assert "no network" in result.stderr


def test_git_pull_pull_fails(tmp_path):
    side = _mock_run_factory(_ok(), _fail("fatal: not possible to fast-forward"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "pull"
    assert "fast-forward" in result.stderr


def test_git_pull_argv_assertions(tmp_path):
    captured = []

    def _run(*args, **kwargs):
        captured.append((args[0], kwargs.get("cwd")))
        return _ok(stdout=("a" * 40) + "\n")

    with patch.object(dap.subprocess, "run", side_effect=_run):
        dap.git_pull(tmp_path)
    assert captured[0][0] == ["git", "fetch", "origin", "main"]
    assert captured[1][0] == ["git", "pull", "--ff-only", "origin", "main"]
    assert captured[2][0] == ["git", "rev-parse", "HEAD"]
    for _, cwd in captured:
        assert cwd == str(tmp_path)


def test_git_pull_rev_parse_fails(tmp_path):
    side = _mock_run_factory(_ok(), _ok(), _fail("rev-parse error"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "rev_parse"


# ---------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------


def test_audit_record_shape():
    rec = dap.audit_record(kind="copy", tick_id="abc", agent_slug="x", filename="y.md")
    assert rec["kind"] == "copy"
    assert rec["tick_id"] == "abc"
    assert rec["agent_slug"] == "x"
    assert rec["filename"] == "y.md"
    assert "timestamp" in rec
    assert rec["timestamp"].endswith("Z")


def test_audit_append_creates_parent_dir(tmp_path):
    log = tmp_path / "deploy" / "audit.jsonl"
    assert not log.parent.exists()
    dap.audit_append(log, dap.audit_record(kind="skip", tick_id="t1", agent_slug="x", filename="y.md"))
    assert log.exists()
    assert log.parent.exists()


def test_audit_append_appends_jsonl(tmp_path):
    log = tmp_path / "audit.jsonl"
    dap.audit_append(log, dap.audit_record(kind="skip", tick_id="t1"))
    dap.audit_append(log, dap.audit_record(kind="copy", tick_id="t1"))
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "skip"
    assert parsed[1]["kind"] == "copy"


def test_audit_tick_summary_includes_all_fields(tmp_path):
    log = tmp_path / "audit.jsonl"
    dap.audit_tick_summary(
        log_path=log,
        tick_id="t1",
        agents_processed=5,
        files_copied=2,
        files_skipped=23,
        files_errored=0,
        git_head_after_pull="b" * 40,
        exit_code=0,
        duration_ms=1234,
    )
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "tick_summary"
    assert rec["agents_processed"] == 5
    assert rec["files_copied"] == 2
    assert rec["files_skipped"] == 23
    assert rec["files_errored"] == 0
    assert rec["git_head_after_pull"] == "b" * 40
    assert rec["exit_code"] == 0
    assert rec["duration_ms"] == 1234


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_defaults():
    args = dap.parse_args([])
    assert args.dry_run is False
    assert args.agent is None


def test_parse_args_dry_run():
    args = dap.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parse_args_agent():
    args = dap.parse_args(["--agent", "felix-admin-capture"])
    assert args.agent == "felix-admin-capture"


def test_parse_args_both():
    args = dap.parse_args(["--dry-run", "--agent", "felix-admin-capture"])
    assert args.dry_run is True
    assert args.agent == "felix-admin-capture"


# ---------------------------------------------------------------------------
# run_tick / main — integration with tempdir fakes
# ---------------------------------------------------------------------------


def _setup_fake_repo(tmp_path: Path, agents_meta: dict, *, with_git: bool = True) -> Path:
    """Build a fake repo root with .git/, service-inventory.json, and agent source dirs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    if with_git:
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    inv_path = repo / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
    _write_inventory(inv_path, agents_meta)
    return repo


def test_run_tick_validation_no_git_dir(tmp_path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    args = dap.parse_args([])
    log = tmp_path / "audit.jsonl"
    rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_VALIDATION_ERROR
    assert not log.exists()


def test_run_tick_validation_no_inventory(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    args = dap.parse_args([])
    log = tmp_path / "audit.jsonl"
    rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_VALIDATION_ERROR


def test_run_tick_validation_malformed_inventory(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    inv = repo / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
    inv.parent.mkdir(parents=True)
    inv.write_text("{not valid json")
    args = dap.parse_args([])
    rc = dap.run_tick(args, repo_root=repo, audit_path=tmp_path / "audit.jsonl")
    assert rc == dap.EXIT_VALIDATION_ERROR


def test_run_tick_validation_unknown_agent_slug(tmp_path):
    repo = _setup_fake_repo(tmp_path, {
        "good": {"source_in_repo": "src/", "workspace": str(tmp_path / "dst")},
    })
    args = dap.parse_args(["--agent", "does-not-exist"])
    rc = dap.run_tick(args, repo_root=repo, audit_path=tmp_path / "audit.jsonl")
    assert rc == dap.EXIT_VALIDATION_ERROR


def test_run_tick_git_pull_failed(tmp_path):
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(tmp_path / "dst")},
    })
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_bytes(b"content")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    side = _mock_run_factory(_fail("net down"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_GIT_PULL_FAILED
    lines = log.read_text().splitlines()
    parsed = [json.loads(line) for line in lines]
    kinds = [p["kind"] for p in parsed]
    assert "git_pull_failed" in kinds
    assert kinds[-1] == "tick_summary"
    assert parsed[-1]["exit_code"] == dap.EXIT_GIT_PULL_FAILED


def test_run_tick_no_drift(tmp_path):
    """Source and dst have identical content → only skips + tick_summary."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "AGENTS.md").write_bytes(b"identical")
    (dst_dir / "AGENTS.md").write_bytes(b"identical")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "a" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    kinds = [p["kind"] for p in parsed]
    assert "copy" not in kinds
    assert "skip" in kinds
    assert kinds[-1] == "tick_summary"
    assert parsed[-1]["files_copied"] == 0
    assert parsed[-1]["files_skipped"] >= 1
    assert parsed[-1]["exit_code"] == 0


def test_run_tick_drift_copied(tmp_path):
    """Source differs from dst → one copy + tick_summary, deployed bytes match source."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "AGENTS.md").write_bytes(b"v2")
    (dst_dir / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "b" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    assert (dst_dir / "AGENTS.md").read_bytes() == b"v2"
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    kinds = [p["kind"] for p in parsed]
    assert "copy" in kinds
    assert parsed[-1]["files_copied"] == 1
    assert parsed[-1]["git_head_after_pull"] == sha


def test_run_tick_per_file_error_exit_1(tmp_path):
    """atomic_copy raises OSError on a drifted file → exit 1, error record present."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "AGENTS.md").write_bytes(b"v2")
    (dst_dir / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "c" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side), \
         patch.object(dap, "atomic_copy", side_effect=OSError("disk full")):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_PARTIAL_FAILURE
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    kinds = [p["kind"] for p in parsed]
    assert "error" in kinds
    assert parsed[-1]["files_errored"] == 1


def test_run_tick_dry_run_no_mutations(tmp_path, capsys):
    """--dry-run mode: drift present, but no audit log entries, no file changes."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "AGENTS.md").write_bytes(b"v2")
    (dst_dir / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args(["--dry-run"])
    rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    assert not log.exists()
    assert (dst_dir / "AGENTS.md").read_bytes() == b"v1"
    captured = capsys.readouterr()
    assert "DRIFT" in captured.out
    assert "test-agent" in captured.out


def test_run_tick_single_agent_filter_skips_others(tmp_path):
    dst_a = tmp_path / "dst-a"
    dst_a.mkdir()
    dst_b = tmp_path / "dst-b"
    dst_b.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "agent-a": {"source_in_repo": "src-a/", "workspace": str(dst_a)},
        "agent-b": {"source_in_repo": "src-b/", "workspace": str(dst_b)},
    })
    (repo / "src-a").mkdir()
    (repo / "src-a" / "AGENTS.md").write_bytes(b"identical")
    (dst_a / "AGENTS.md").write_bytes(b"identical")
    (repo / "src-b").mkdir()
    (repo / "src-b" / "AGENTS.md").write_bytes(b"identical")
    (dst_b / "AGENTS.md").write_bytes(b"identical")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args(["--agent", "agent-a"])
    sha = "d" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    agent_slugs = {p.get("agent_slug") for p in parsed if "agent_slug" in p}
    assert agent_slugs == {"agent-a"}
    assert parsed[-1]["agents_processed"] == 1


def test_run_tick_source_dir_missing_warns(tmp_path):
    """Agent's source_in_repo dir doesn't exist on disk → warning record, no crash."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "ghost-agent": {"source_in_repo": "src-missing/", "workspace": str(dst_dir)},
    })
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "e" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(p["kind"] == "warning" for p in parsed)


def test_run_tick_creates_workspace_dir_on_first_copy(tmp_path):
    """Workspace dir doesn't exist; helper creates it on first copy."""
    dst_dir = tmp_path / "dst-not-yet"
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "f" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    assert dst_dir.exists()
    assert (dst_dir / "AGENTS.md").read_bytes() == b"v1"


# ---------------------------------------------------------------------------
# main() — CLI entry
# ---------------------------------------------------------------------------


def test_main_uses_sys_argv_when_none_passed(tmp_path, monkeypatch):
    """main(None) reads sys.argv[1:]."""
    monkeypatch.setattr(sys, "argv", ["prog", "--dry-run"])
    monkeypatch.chdir(tmp_path)  # validation should fail (no .git/) → exit 3
    rc = dap.main()
    assert rc == dap.EXIT_VALIDATION_ERROR


def test_main_explicit_argv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = dap.main(["--dry-run"])
    assert rc == dap.EXIT_VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Excluded filenames inside sync_agent
# ---------------------------------------------------------------------------


def test_run_tick_excludes_heartbeat_tmpl_bak_governance(tmp_path):
    """Source dir contains excluded files; helper must NOT copy them even if drifted."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    src = repo / "src"
    src.mkdir()
    (src / "AGENTS.md").write_bytes(b"in-scope")
    (src / "HEARTBEAT.md").write_bytes(b"should not deploy")
    (src / "AGENTS.md.tmpl").write_bytes(b"template")
    (src / "AGENTS.md.bak").write_bytes(b"backup")
    (src / "GOVERNANCE.md").write_bytes(b"manual")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "a" * 40
    side = _mock_run_factory(_ok(), _ok(), _ok(stdout=sha + "\n"))
    with patch.object(dap.subprocess, "run", side_effect=side):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    assert (dst_dir / "AGENTS.md").read_bytes() == b"in-scope"
    assert not (dst_dir / "HEARTBEAT.md").exists()
    assert not (dst_dir / "AGENTS.md.tmpl").exists()
    assert not (dst_dir / "AGENTS.md.bak").exists()
    assert not (dst_dir / "GOVERNANCE.md").exists()
