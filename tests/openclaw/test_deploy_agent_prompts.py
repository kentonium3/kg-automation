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
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.deploy.lib.gitsync import AdvanceResult
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
# git_pull — now delegates to scripts.deploy.lib.gitsync.advance_checkout (#667)
# ---------------------------------------------------------------------------
#
# git_pull no longer shells out to `git pull --ff-only`; it calls
# advance_checkout(repo_root, assume_locked=True) and adapts the AdvanceResult
# onto the FROZEN public GitPullResult shape. These tests pin that mapping by
# patching advance_checkout (the seam is subprocess-mocked in gitsync's own
# suite; here we assert the GitPullResult adaptation contract).


def _advance(**kw):
    """Build an AdvanceResult, respecting its frozen invariants."""
    base = dict(
        ok=True,
        advanced=False,
        pre_head="aaaaaaa",
        post_head="aaaaaaa",
        origin_head="aaaaaaa",
        behind=0,
        ahead=0,
        diverged=False,
        reason=None,
        stderr="",
    )
    base.update(kw)
    return AdvanceResult(**base)


def test_git_pull_success_maps_advanced(tmp_path):
    """A real fast-forward → success=True, head_sha=post_head, stage=None."""
    adv = _advance(ok=True, advanced=True, pre_head="aaaaaaa", post_head="bbbbbbb",
                   origin_head="bbbbbbb", behind=2, ahead=0)
    with patch.object(dap, "advance_checkout", return_value=adv) as p:
        result = dap.git_pull(tmp_path)
    # assume_locked=True is passed (the run_tick caller holds the lock)
    assert p.call_args.kwargs.get("assume_locked") is True
    assert result.success is True
    assert result.head_sha == "bbbbbbb"
    assert result.stage is None
    assert result.advance is adv


def test_git_pull_noop_maps_success(tmp_path):
    """behind==0 clean no-op → success=True even though advanced=False."""
    adv = _advance(ok=True, advanced=False, behind=0, ahead=3, post_head="aaaaaaa")
    with patch.object(dap, "advance_checkout", return_value=adv):
        result = dap.git_pull(tmp_path)
    assert result.success is True
    assert result.head_sha == "aaaaaaa"
    assert result.stage is None


def test_git_pull_diverged_maps_failure(tmp_path):
    """diverged → success=False, stage=reason='diverged'."""
    adv = _advance(ok=False, advanced=False, behind=2, ahead=1, diverged=True,
                   reason="diverged", origin_head="ccccccc")
    with patch.object(dap, "advance_checkout", return_value=adv):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "diverged"
    assert result.advance.reason == "diverged"


def test_git_pull_fetch_failed_maps_failure(tmp_path):
    """fetch_failed → success=False, stage='fetch_failed', stderr passed through."""
    adv = _advance(ok=False, advanced=False, reason="fetch_failed", stderr="no network")
    with patch.object(dap, "advance_checkout", return_value=adv):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "fetch_failed"
    assert "no network" in result.stderr


def test_git_pull_merge_failed_maps_failure(tmp_path):
    adv = _advance(ok=False, advanced=False, behind=1, ahead=0, reason="merge_failed",
                   stderr="merge conflict")
    with patch.object(dap, "advance_checkout", return_value=adv):
        result = dap.git_pull(tmp_path)
    assert result.success is False
    assert result.stage == "merge_failed"


def test_git_pull_preserves_public_field_names():
    """GitPullResult keeps its four public fields in order (downstream depends on it)."""
    from dataclasses import fields
    names = [f.name for f in fields(dap.GitPullResult)]
    assert names[:4] == ["success", "head_sha", "stderr", "stage"]


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


@pytest.fixture(autouse=True)
def _isolate_deploy_lock(tmp_path_factory, monkeypatch):
    """Point the shared deploylock at a per-test tmp path (never /data on CI).

    run_tick now wraps its critical section in deploylock(); without this the
    lock would try to create /data/services/deploy/locks/ which does not exist
    in the test environment.
    """
    lock_dir = tmp_path_factory.mktemp("deploy-lock")
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(lock_dir / "checkout.lock"))
    # Redirect the health watermark default off the read-only /data path so
    # run_tick tests that don't pass an explicit state_path stay hermetic.
    state_dir = tmp_path_factory.mktemp("deploy-health")
    monkeypatch.setattr(dap, "HEALTH_STATE_PATH_DEFAULT", state_dir / "git-health.json")
    # Health alerts must never hit the network in tests: no topic configured →
    # dispatch_health_notification returns a benign "skipped" LibResult.
    monkeypatch.delenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", raising=False)
    monkeypatch.delenv("FELIX_DEPLOYER_NTFY_TOPIC", raising=False)


def _advance_success(post_head: str, *, advanced: bool = True):
    """AdvanceResult for a successful git_pull in run_tick tests."""
    return AdvanceResult(
        ok=True,
        advanced=advanced,
        pre_head="0000000",
        post_head=post_head,
        origin_head=post_head,
        behind=1 if advanced else 0,
        ahead=0,
        diverged=False,
    )


def _patch_advance_success(post_head: str):
    """Context manager patching dap.advance_checkout to return a success."""
    return patch.object(dap, "advance_checkout", return_value=_advance_success(post_head))


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
    adv = AdvanceResult(
        ok=False, advanced=False, pre_head="1111111", post_head="1111111",
        origin_head="", behind=0, ahead=0, diverged=False,
        reason="fetch_failed", stderr="net down",
    )
    with patch.object(dap, "advance_checkout", return_value=adv):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_GIT_PULL_FAILED
    lines = log.read_text().splitlines()
    parsed = [json.loads(line) for line in lines]
    kinds = [p["kind"] for p in parsed]
    assert "git_pull_failed" in kinds
    assert kinds[-1] == "tick_summary"
    assert parsed[-1]["exit_code"] == dap.EXIT_GIT_PULL_FAILED
    # Enriched ref-state fields present on the failure record (T016).
    fail_rec = next(p for p in parsed if p["kind"] == "git_pull_failed")
    assert fail_rec["reason"] == "fetch_failed"
    assert fail_rec["local_head"] == "1111111"
    assert fail_rec["origin_head"] == ""
    assert fail_rec["behind"] == 0
    assert fail_rec["ahead"] == 0
    # Existing success/summary record shape is unchanged: git_pull_failed keeps
    # its original keys too.
    assert fail_rec["stage"] == "fetch_failed"
    assert "git_exit_code" in fail_rec


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
    with _patch_advance_success(sha):
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
    with _patch_advance_success(sha):
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
    with _patch_advance_success(sha), \
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
    with _patch_advance_success(sha):
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
    with _patch_advance_success(sha):
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
    with _patch_advance_success(sha):
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
    with _patch_advance_success(sha):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)
    assert rc == dap.EXIT_SUCCESS
    assert (dst_dir / "AGENTS.md").read_bytes() == b"in-scope"
    assert not (dst_dir / "HEARTBEAT.md").exists()
    assert not (dst_dir / "AGENTS.md.tmpl").exists()
    assert not (dst_dir / "AGENTS.md.bak").exists()
    assert not (dst_dir / "GOVERNANCE.md").exists()


# ---------------------------------------------------------------------------
# T015 — deploylock wraps the critical section; LockUnavailable → clean defer
# ---------------------------------------------------------------------------


def test_run_tick_lock_wraps_critical_section(tmp_path):
    """The tick acquires deploylock() around git_pull + the copy loop."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_bytes(b"v2")
    (dst_dir / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])
    sha = "a" * 40

    import contextlib

    order: list[str] = []

    @contextlib.contextmanager
    def _tracking_lock(*a, **k):
        order.append("lock_enter")
        try:
            yield
        finally:
            order.append("lock_exit")

    def _advance(*a, **k):
        # The advance (git_pull) must run while the lock is held.
        assert order == ["lock_enter"], "advance ran outside the lock"
        order.append("advance")
        return _advance_success(sha)

    with patch.object(dap, "deploylock", _tracking_lock), \
         patch.object(dap, "advance_checkout", side_effect=_advance):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)

    assert rc == dap.EXIT_SUCCESS
    # Lock entered before the advance ran, exited after; the copy landed inside.
    assert order == ["lock_enter", "advance", "lock_exit"]
    assert (dst_dir / "AGENTS.md").read_bytes() == b"v2"


def test_run_tick_lock_unavailable_defers_cleanly(tmp_path):
    """LockUnavailable → git_pull_skipped audit + clean success; NO prompt copy."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_bytes(b"v2")
    (dst_dir / "AGENTS.md").write_bytes(b"v1")
    log = tmp_path / "audit.jsonl"
    args = dap.parse_args([])

    def _raise_lock(*a, **k):
        raise dap.LockUnavailable("held by other actor")

    advance_spy = patch.object(dap, "advance_checkout")
    with patch.object(dap, "deploylock", side_effect=_raise_lock), advance_spy as adv:
        rc = dap.run_tick(args, repo_root=repo, audit_path=log)

    assert rc == dap.EXIT_SUCCESS
    # advance_checkout (git_pull) was never reached — lock came first.
    adv.assert_not_called()
    # Prompt NOT copied outside the lock.
    assert (dst_dir / "AGENTS.md").read_bytes() == b"v1"
    parsed = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(parsed) == 1
    rec = parsed[0]
    assert rec["kind"] == "git_pull_skipped"
    assert rec["stage"] == "lock"
    assert rec["reason"] == "lock_unavailable"


# ---------------------------------------------------------------------------
# T017 — health watermark + notifier wiring
# ---------------------------------------------------------------------------


def test_run_tick_records_health_on_success(tmp_path):
    """A successful tick feeds the AdvanceResult into health.record."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(dst_dir)},
    })
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_bytes(b"identical")
    (dst_dir / "AGENTS.md").write_bytes(b"identical")
    log = tmp_path / "audit.jsonl"
    health_state = tmp_path / "git-health.json"
    args = dap.parse_args([])
    sha = "a" * 40

    with _patch_advance_success(sha), \
         patch.object(dap._health, "record", wraps=dap._health.record) as rec_spy:
        rc = dap.run_tick(args, repo_root=repo, audit_path=log,
                          health_state_path=health_state)

    assert rc == dap.EXIT_SUCCESS
    rec_spy.assert_called_once()
    call = rec_spy.call_args
    assert call.args[0] == dap.HEALTH_ACTOR
    assert isinstance(call.args[1], AdvanceResult)
    assert call.kwargs["state_path"] == health_state
    assert call.kwargs["notifier"] is dap._health_notifier
    # The watermark was written with a success reset.
    state = json.loads(health_state.read_text())
    assert state["consecutive_failures"] == 0
    assert state["last_success_head"] == sha


def test_run_tick_records_health_on_failure(tmp_path):
    """A failed advance increments the health streak via health.record."""
    repo = _setup_fake_repo(tmp_path, {
        "test-agent": {"source_in_repo": "src/", "workspace": str(tmp_path / "dst")},
    })
    log = tmp_path / "audit.jsonl"
    health_state = tmp_path / "git-health.json"
    args = dap.parse_args([])
    adv = AdvanceResult(
        ok=False, advanced=False, pre_head="1111111", post_head="1111111",
        origin_head="2222222", behind=1, ahead=1, diverged=True, reason="diverged",
    )
    with patch.object(dap, "advance_checkout", return_value=adv):
        rc = dap.run_tick(args, repo_root=repo, audit_path=log,
                          health_state_path=health_state)
    assert rc == dap.EXIT_GIT_PULL_FAILED
    state = json.loads(health_state.read_text())
    assert state["consecutive_failures"] == 1


def test_health_notifier_dispatches_via_generic_notify(monkeypatch):
    """_health_notifier calls dispatch_health_notification with this actor's topic env."""
    notify = dap._load_notify()
    captured = {}

    def _fake_dispatch(actor, title, body, *, topic_env):
        captured.update(actor=actor, title=title, body=body, topic_env=topic_env)

    monkeypatch.setattr(notify, "dispatch_health_notification", _fake_dispatch)
    dap._health_notifier("t", "b")
    assert captured["actor"] == dap.HEALTH_ACTOR
    assert captured["topic_env"] == dap.HEALTH_TOPIC_ENV == "AGENT_PROMPT_SYNC_NTFY_TOPIC"
    assert captured["title"] == "t"
    assert captured["body"] == "b"


def test_load_notify_resolves_hyphenated_package():
    """The cross-package importlib load resolves dispatch_health_notification."""
    notify = dap._load_notify()
    assert hasattr(notify, "dispatch_health_notification")
    # Cached on repeat.
    assert dap._load_notify() is notify
