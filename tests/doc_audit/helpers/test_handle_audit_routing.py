"""Unit tests for the importable surfaces of ``handle_audit_routing.py``.

Per mission #343 WP01 (T005): lock in the ``route_audit_decision``
library entry point alongside existing module-level building blocks
(_resolve_state_path, _load_state, _partition, _apply_one,
_atomic_write).

External commands (``git``, ``gh``) are mocked at the module's
``subprocess.run`` boundary. Filesystem mutations target ``tmp_path``
only — no host repo writes.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from doc_audit.helpers.handle_audit_routing import (
    AUTO_APPLY_CHANGE_TYPES,
    InputValidationError,
    RouteApplyError,
    RoutingResult,
    _apply_dead_ref_removal,
    _apply_frontmatter_date,
    _apply_one,
    _apply_path_rename,
    _apply_registry_autonomy_update,
    _apply_registry_entry_add,
    _apply_version_bump,
    _atomic_write,
    _load_state,
    _parse_issue_number,
    _partition,
    _resolve_state_path,
    _rollback,
    main,
    route_audit_decision,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Input resolution + validation
# ---------------------------------------------------------------------------


def test_resolve_state_path_strips_leading_at_sign():
    assert _resolve_state_path("@/tmp/audit.json") == Path("/tmp/audit.json")
    assert _resolve_state_path("/tmp/audit.json") == Path("/tmp/audit.json")


def test_load_state_accepts_fixture():
    state = _load_state(FIXTURES_DIR / "audit_state_sample.json")
    assert state["audit_issue_number"] == 9999
    assert isinstance(state["proposals"], list)
    assert len(state["proposals"]) == 2


def test_load_state_raises_on_missing_file(tmp_path: Path):
    with pytest.raises(InputValidationError):
        _load_state(tmp_path / "missing.json")


def test_load_state_raises_on_bad_json(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    with pytest.raises(InputValidationError):
        _load_state(bad)


def test_load_state_raises_on_missing_top_keys(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"audit_issue_number": 1}))
    with pytest.raises(InputValidationError):
        _load_state(bad)


# ---------------------------------------------------------------------------
# _atomic_write — preserves mode
# ---------------------------------------------------------------------------


def test_atomic_write_preserves_existing_mode(tmp_path: Path):
    target = tmp_path / "doc.md"
    target.write_text("original\n")
    os.chmod(target, 0o600)
    _atomic_write(target, "rewritten\n")
    assert target.read_text() == "rewritten\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_creates_new_file_with_default_mode(tmp_path: Path):
    target = tmp_path / "new.md"
    _atomic_write(target, "hello\n")
    assert target.read_text() == "hello\n"
    # Default for new file in this helper is 0o664
    assert stat.S_IMODE(target.stat().st_mode) == 0o664


# ---------------------------------------------------------------------------
# Partition
# ---------------------------------------------------------------------------


def test_partition_splits_by_allowlist():
    proposals = json.loads(
        (FIXTURES_DIR / "audit_state_sample.json").read_text()
    )["proposals"]
    auto, gated = _partition(proposals)
    assert len(auto) == 1
    assert auto[0]["change_type"] == "frontmatter_date"
    assert auto[0]["change_type"] in AUTO_APPLY_CHANGE_TYPES
    assert len(gated) == 1
    assert gated[0]["change_type"] == "needs_human_judgment"


# ---------------------------------------------------------------------------
# _apply_frontmatter_date helper
# ---------------------------------------------------------------------------


def test_apply_frontmatter_date_replaces_within_frontmatter(tmp_path: Path):
    content = "---\nlast_validated: 2026-05-10\n---\n\nBody mentions 2026-05-10 too.\n"
    proposal = {
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
    }
    new_content = _apply_frontmatter_date(content, proposal)
    # Only the frontmatter occurrence should be replaced.
    assert "last_validated: 2026-05-20" in new_content
    assert "Body mentions 2026-05-10 too." in new_content


def test_apply_frontmatter_date_raises_when_current_absent(tmp_path: Path):
    content = "---\nlast_validated: 2026-05-11\n---\n"
    proposal = {
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
    }
    with pytest.raises(RouteApplyError):
        _apply_frontmatter_date(content, proposal)


# ---------------------------------------------------------------------------
# _apply_one — exercises filesystem path
# ---------------------------------------------------------------------------


def test_apply_one_writes_and_returns_path(tmp_path: Path):
    repo_root = tmp_path
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()
    target = doc_dir / "INDEX.md"
    target.write_text("---\nlast_validated: 2026-05-10\n---\n")
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    written = _apply_one(repo_root, proposal)
    assert written == target
    assert "2026-05-20" in target.read_text()


# ---------------------------------------------------------------------------
# route_audit_decision (library entry point)
# ---------------------------------------------------------------------------


def _make_state_file(
    tmp_path: Path,
    proposals: list[dict],
    audit_issue: int = 9999,
) -> Path:
    state = {
        "audit_issue_number": audit_issue,
        "commit_sha": "abc1234",
        "areas": ["area/felix-core"],
        "proposals": proposals,
        "debt_issues_filed": [],
        "missing_artifact_issues_filed": [],
    }
    p = tmp_path / "audit_state.json"
    p.write_text(json.dumps(state))
    return p


def _setup_doc_with_frontmatter(repo_root: Path) -> Path:
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / "INDEX.md"
    target.write_text("---\nlast_validated: 2026-05-10\n---\n\nBody.\n")
    return target


def _make_gh_create_response(issue_number: int = 12345) -> mock.MagicMock:
    return mock.MagicMock(
        returncode=0,
        stdout=f"https://github.com/kentonium3/kg-automation/issues/{issue_number}\n",
        stderr="",
    )


def _make_zero_rc_response() -> mock.MagicMock:
    return mock.MagicMock(returncode=0, stdout="", stderr="")


def test_route_audit_decision_empty_proposals_short_circuits(tmp_path: Path):
    state_path = _make_state_file(tmp_path, proposals=[])
    result = route_audit_decision(
        state_path=state_path,
        repo_root=tmp_path,
    )
    assert isinstance(result, RoutingResult)
    assert result.exit_code == 0
    assert result.applied_count == 0
    assert result.gated is False
    assert result.errors == []


def test_route_audit_decision_input_validation_exit_code_1(tmp_path: Path):
    missing = tmp_path / "does-not-exist.json"
    result = route_audit_decision(
        state_path=missing,
        repo_root=tmp_path,
    )
    assert result.exit_code == 1
    assert any("input validation" in e for e in result.errors)


def test_route_audit_decision_auto_apply_only_path(tmp_path: Path, monkeypatch):
    repo_root = tmp_path
    target = _setup_doc_with_frontmatter(repo_root)

    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    # All subprocess calls succeed (git add, git commit, gh comment, gh close).
    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
    )

    assert result.exit_code == 0
    assert result.applied_count == 1
    assert result.gated is False
    assert result.pending_approval_issue is None
    # File was actually rewritten on disk
    assert "2026-05-20" in target.read_text()
    # Subprocess invoked at least once (git add + commit + comment + close)
    assert fake_run.call_count >= 3


def test_route_audit_decision_gated_only_files_pending_approval(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)

    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "needs_human_judgment",
        "current_value": "x",
        "proposed_value": "y",
        "evidence_source": "test",
        "confidence": "low",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    # First call is gh issue create (gate-file) — return an issue URL;
    # subsequent calls (summary comment) return success.
    fake_run = mock.MagicMock(
        side_effect=[
            _make_gh_create_response(issue_number=54321),
            _make_zero_rc_response(),  # summary comment
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
    )

    assert result.exit_code == 0
    assert result.applied_count == 0
    assert result.gated is True
    assert result.pending_approval_issue == 54321


def test_route_audit_decision_apply_failure_exit_code_2(tmp_path: Path, monkeypatch):
    repo_root = tmp_path
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / "INDEX.md"
    # Frontmatter date is different from what the proposal expects.
    target.write_text("---\nlast_validated: 2099-01-01\n---\n")

    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",  # not in file — apply must fail
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    # _rollback may call git checkout — return success for any subprocess call.
    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
    )

    assert result.exit_code == 2
    assert result.applied_count == 0
    assert any("apply failure" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Cycle 3 additions — routing appliers
# ---------------------------------------------------------------------------


# _apply_frontmatter_date — additional failure legs (lines 249, 254, 261)


def test_apply_frontmatter_date_raises_on_identical_values():
    proposal = {"current_value": "2026-05-10", "proposed_value": "2026-05-10"}
    with pytest.raises(RouteApplyError, match="identical"):
        _apply_frontmatter_date("---\nlast_validated: 2026-05-10\n---\n", proposal)


def test_apply_frontmatter_date_raises_when_no_leading_frontmatter():
    # Document does not start with the YAML `---` opener.
    content = "no frontmatter here\nlast_validated: 2026-05-10\n"
    proposal = {"current_value": "2026-05-10", "proposed_value": "2026-05-20"}
    with pytest.raises(RouteApplyError, match="no leading YAML frontmatter"):
        _apply_frontmatter_date(content, proposal)


def test_apply_frontmatter_date_raises_when_frontmatter_unterminated():
    # Opens with `---` but never closes.
    content = "---\nlast_validated: 2026-05-10\nstill in frontmatter\n"
    proposal = {"current_value": "2026-05-10", "proposed_value": "2026-05-20"}
    with pytest.raises(RouteApplyError, match="unterminated"):
        _apply_frontmatter_date(content, proposal)


# _apply_version_bump (lines 280-289)


def test_apply_version_bump_replaces_single_occurrence():
    content = "Title v1.2.0\nBody mentions 1.2.0 too.\n"
    proposal = {"current_value": "1.2.0", "proposed_value": "1.3.0"}
    result = _apply_version_bump(content, proposal)
    # Only first occurrence is replaced.
    assert "Title v1.3.0" in result
    assert "Body mentions 1.2.0 too." in result


def test_apply_version_bump_raises_on_identical_values():
    proposal = {"current_value": "1.2.0", "proposed_value": "1.2.0"}
    with pytest.raises(RouteApplyError, match="identical"):
        _apply_version_bump("v1.2.0", proposal)


def test_apply_version_bump_raises_when_current_absent():
    proposal = {"current_value": "9.9.9", "proposed_value": "10.0.0"}
    with pytest.raises(RouteApplyError, match="not found"):
        _apply_version_bump("v1.2.0", proposal)


# _apply_path_rename (lines 299-308) — global replacement


def test_apply_path_rename_replaces_all_occurrences():
    content = "See docs/old.md\nAlso docs/old.md again.\n"
    proposal = {
        "current_value": "docs/old.md",
        "proposed_value": "docs/new.md",
    }
    result = _apply_path_rename(content, proposal)
    assert "docs/old.md" not in result
    assert result.count("docs/new.md") == 2


def test_apply_path_rename_raises_on_identical_values():
    proposal = {"current_value": "docs/x.md", "proposed_value": "docs/x.md"}
    with pytest.raises(RouteApplyError, match="identical"):
        _apply_path_rename("docs/x.md", proposal)


def test_apply_path_rename_raises_when_current_absent():
    proposal = {"current_value": "docs/missing.md", "proposed_value": "docs/new.md"}
    with pytest.raises(RouteApplyError, match="not found"):
        _apply_path_rename("nothing here", proposal)


# _apply_dead_ref_removal (lines 318-337)


def test_apply_dead_ref_removal_drops_line_with_trailing_newline():
    content = "first line\ndead ref line\nthird line\n"
    proposal = {"current_value": "dead ref line", "proposed_value": ""}
    result = _apply_dead_ref_removal(content, proposal)
    # The dead-ref line AND its trailing newline should be consumed.
    assert "dead ref line" not in result
    assert result == "first line\nthird line\n"


def test_apply_dead_ref_removal_with_explicit_replacement():
    content = "before [dead-link] after\n"
    proposal = {"current_value": "[dead-link]", "proposed_value": "(removed)"}
    result = _apply_dead_ref_removal(content, proposal)
    assert "[dead-link]" not in result
    assert "(removed)" in result


def test_apply_dead_ref_removal_raises_when_current_absent():
    proposal = {"current_value": "missing", "proposed_value": ""}
    with pytest.raises(RouteApplyError, match="dead reference"):
        _apply_dead_ref_removal("only safe content here", proposal)


def test_apply_dead_ref_removal_with_empty_proposed_value_falls_back_to_literal():
    # proposed_value is the empty string AND pattern_with_nl regex catches
    # nothing extra (the snippet does not sit on its own line). The
    # fallback literal-replace branch should still kick in.
    content = "prefix DEAD suffix"
    proposal = {"current_value": "DEAD", "proposed_value": ""}
    result = _apply_dead_ref_removal(content, proposal)
    assert "DEAD" not in result
    assert "prefix  suffix" in result


# _apply_registry_entry_add (lines 349-366)


def test_apply_registry_entry_add_inserts_after_anchor_with_newline():
    content = "anchor line\nfollowing line\n"
    proposal = {
        "current_value": "anchor line\n",
        "proposed_value": "new entry",
    }
    result = _apply_registry_entry_add(content, proposal)
    # Insert sits directly after the anchor and is newline-terminated.
    assert "anchor line\nnew entry\nfollowing line\n" == result


def test_apply_registry_entry_add_inserts_when_anchor_lacks_trailing_newline():
    # Anchor does not end with newline — the else branch must inject one.
    content = "anchor"
    proposal = {"current_value": "anchor", "proposed_value": "new entry"}
    result = _apply_registry_entry_add(content, proposal)
    assert result == "anchor\nnew entry\n"


def test_apply_registry_entry_add_preserves_proposed_trailing_newline():
    content = "anchor\n"
    proposal = {
        "current_value": "anchor\n",
        "proposed_value": "new entry\n",
    }
    result = _apply_registry_entry_add(content, proposal)
    # No extra newline tacked on when proposed_value already ends with one.
    assert result == "anchor\nnew entry\n"


def test_apply_registry_entry_add_raises_when_anchor_absent():
    proposal = {"current_value": "no-such-anchor", "proposed_value": "x"}
    with pytest.raises(RouteApplyError, match="anchor"):
        _apply_registry_entry_add("some content\n", proposal)


# _apply_registry_autonomy_update (lines 377-389)


def test_apply_registry_autonomy_update_replaces_single_occurrence():
    content = "autonomy: L1\nother L1 mention\n"
    proposal = {"current_value": "L1", "proposed_value": "L2"}
    result = _apply_registry_autonomy_update(content, proposal)
    assert "autonomy: L2" in result
    # Only first occurrence is replaced.
    assert "other L1 mention" in result


def test_apply_registry_autonomy_update_raises_on_identical_values():
    proposal = {"current_value": "L1", "proposed_value": "L1"}
    with pytest.raises(RouteApplyError, match="identical"):
        _apply_registry_autonomy_update("autonomy: L1\n", proposal)


def test_apply_registry_autonomy_update_raises_when_current_absent():
    proposal = {"current_value": "L9", "proposed_value": "L2"}
    with pytest.raises(RouteApplyError, match="not found"):
        _apply_registry_autonomy_update("autonomy: L1\n", proposal)


# ---------------------------------------------------------------------------
# _apply_one — additional branches (lines 471, 481)
# ---------------------------------------------------------------------------


def test_apply_one_raises_when_doc_not_found(tmp_path: Path):
    proposal = {
        "doc_path": "docs/missing.md",
        "change_type": "frontmatter_date",
        "current_value": "x",
        "proposed_value": "y",
        "evidence_source": "test",
        "confidence": "high",
    }
    with pytest.raises(RouteApplyError, match="doc not found"):
        _apply_one(tmp_path, proposal)


def test_apply_one_raises_when_applier_produces_no_change(tmp_path: Path, monkeypatch):
    """Force the applier to return content == content so the no-op branch fires."""
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "INDEX.md"
    target.write_text("---\nlast_validated: 2026-05-10\n---\n")
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }

    # Monkeypatch the APPLIERS dispatch so the dispatched applier becomes a no-op.
    monkeypatch.setitem(
        __import__(
            "doc_audit.helpers.handle_audit_routing",
            fromlist=["APPLIERS"],
        ).APPLIERS,
        "frontmatter_date",
        lambda content, proposal: content,
    )
    with pytest.raises(RouteApplyError, match="no change"):
        _apply_one(tmp_path, proposal)


# ---------------------------------------------------------------------------
# _rollback (lines 490-498)
# ---------------------------------------------------------------------------


def test_rollback_no_paths_is_noop(tmp_path: Path, monkeypatch):
    """Empty path list must short-circuit before invoking subprocess."""
    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )
    _rollback(tmp_path, [], "git")
    assert fake_run.call_count == 0


def test_rollback_invokes_git_checkout_for_paths(tmp_path: Path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "INDEX.md"
    target.write_text("x")
    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )
    _rollback(tmp_path, [target], "git")
    assert fake_run.call_count == 1
    args, kwargs = fake_run.call_args
    assert "checkout" in args[0]


def test_rollback_swallows_subprocess_oserror(tmp_path: Path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "INDEX.md"
    target.write_text("x")
    fake_run = mock.MagicMock(side_effect=OSError("boom"))
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )
    # Should NOT raise — best-effort rollback swallows the error.
    _rollback(tmp_path, [target], "git")


# ---------------------------------------------------------------------------
# _parse_issue_number (line 682 — None branch)
# ---------------------------------------------------------------------------


def test_parse_issue_number_returns_none_when_no_match():
    assert _parse_issue_number("not a github url") is None
    assert _parse_issue_number("") is None
    assert _parse_issue_number(None) is None  # type: ignore[arg-type]


def test_parse_issue_number_extracts_from_url():
    assert _parse_issue_number(
        "https://github.com/kentonium3/kg-automation/issues/42\n"
    ) == 42


# ---------------------------------------------------------------------------
# _load_state — additional type-check branches (419-420, 426, 433-449)
# ---------------------------------------------------------------------------


def test_load_state_raises_when_root_is_not_object(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]")  # JSON array — not an object
    with pytest.raises(InputValidationError, match="must be a JSON object"):
        _load_state(bad)


def _base_state() -> dict:
    return {
        "audit_issue_number": 1,
        "commit_sha": "abc",
        "areas": [],
        "proposals": [],
        "debt_issues_filed": [],
        "missing_artifact_issues_filed": [],
    }


def test_load_state_raises_when_audit_issue_number_wrong_type(tmp_path: Path):
    state = _base_state()
    state["audit_issue_number"] = "not an int"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="audit_issue_number"):
        _load_state(p)


def test_load_state_raises_when_commit_sha_wrong_type(tmp_path: Path):
    state = _base_state()
    state["commit_sha"] = 12345
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="commit_sha"):
        _load_state(p)


def test_load_state_raises_when_areas_wrong_type(tmp_path: Path):
    state = _base_state()
    state["areas"] = "felix-core"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="areas"):
        _load_state(p)


def test_load_state_raises_when_proposals_wrong_type(tmp_path: Path):
    state = _base_state()
    state["proposals"] = "nope"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="proposals"):
        _load_state(p)


def test_load_state_raises_when_debt_issues_wrong_type(tmp_path: Path):
    state = _base_state()
    state["debt_issues_filed"] = {}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="debt_issues_filed"):
        _load_state(p)


def test_load_state_raises_when_missing_artifact_issues_wrong_type(tmp_path: Path):
    state = _base_state()
    state["missing_artifact_issues_filed"] = {}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match="missing_artifact_issues_filed"):
        _load_state(p)


def test_load_state_raises_when_proposal_is_not_object(tmp_path: Path):
    state = _base_state()
    state["proposals"] = ["bare string instead of dict"]
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match=r"proposals\[0\] must be an object"):
        _load_state(p)


def test_load_state_raises_when_proposal_missing_keys(tmp_path: Path):
    state = _base_state()
    state["proposals"] = [{"doc_path": "x"}]  # missing the other required keys
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state))
    with pytest.raises(InputValidationError, match=r"proposals\[0\] missing keys"):
        _load_state(p)


# ---------------------------------------------------------------------------
# route_audit_decision — failure legs (commit, gate-file, summary, close)
# ---------------------------------------------------------------------------


def _make_failing_response(rc: int = 1) -> mock.MagicMock:
    return mock.MagicMock(returncode=rc, stdout="", stderr="boom")


def test_route_audit_decision_commit_failure_exit_code_3(tmp_path: Path, monkeypatch):
    """git add succeeds, git commit fails → exit code 3, no gate-file invoked."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    # First subprocess call = git add (ok), second = git commit (fail).
    fake_run = mock.MagicMock(
        side_effect=[
            _make_zero_rc_response(),  # git add
            _make_failing_response(rc=1),  # git commit
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)

    assert result.exit_code == 3
    assert any("git commit failed" in e for e in result.errors)
    # Sequencing invariant: exactly 2 subprocess calls (add + commit). No
    # gate-file, no summary, no close after the commit failed.
    assert fake_run.call_count == 2


def test_route_audit_decision_gate_file_failure_exit_code_4(tmp_path: Path, monkeypatch):
    """gh issue create fails → exit code 4, best-effort summary still attempted."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    # Gated-only proposal.
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "needs_human_judgment",
        "current_value": "x",
        "proposed_value": "y",
        "evidence_source": "test",
        "confidence": "low",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    fake_run = mock.MagicMock(
        side_effect=[
            _make_failing_response(rc=1),  # gh issue create (gate-file) FAILS
            _make_zero_rc_response(),  # best-effort summary comment
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)

    assert result.exit_code == 4
    assert result.gated is True
    assert result.pending_approval_issue is None
    assert any("gate-file" in e for e in result.errors)
    # Best-effort summary comment IS invoked after gate-file failure.
    assert fake_run.call_count == 2


def test_route_audit_decision_gate_file_unparseable_url(tmp_path: Path, monkeypatch):
    """gh issue create succeeds but stdout has no /issues/<n> → warn, exit 0."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "needs_human_judgment",
        "current_value": "x",
        "proposed_value": "y",
        "evidence_source": "test",
        "confidence": "low",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    unparseable = mock.MagicMock(returncode=0, stdout="(no url here)", stderr="")
    fake_run = mock.MagicMock(
        side_effect=[
            unparseable,  # gh issue create
            _make_zero_rc_response(),  # summary comment
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)
    # gate-file leg returned rc=0 — overall flow continues to exit 0.
    assert result.exit_code == 0
    assert result.gated is True
    assert result.pending_approval_issue is None


def test_route_audit_decision_summary_post_failure_exit_code_5(tmp_path: Path, monkeypatch):
    """Auto-apply succeeds + commit succeeds + gh issue comment fails → exit 5."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    fake_run = mock.MagicMock(
        side_effect=[
            _make_zero_rc_response(),  # git add
            _make_zero_rc_response(),  # git commit
            _make_failing_response(rc=1),  # gh issue comment (summary) FAILS
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)

    assert result.exit_code == 5
    assert any("summary-post" in e for e in result.errors)


def test_route_audit_decision_close_audit_failure_is_non_fatal(tmp_path: Path, monkeypatch):
    """All other legs succeed but `gh issue close` fails → still exit 0 (warn)."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    fake_run = mock.MagicMock(
        side_effect=[
            _make_zero_rc_response(),  # git add
            _make_zero_rc_response(),  # git commit
            _make_zero_rc_response(),  # gh issue comment (summary)
            _make_failing_response(rc=1),  # gh issue close FAILS
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)
    # Close failure is best-effort — overall exit remains 0.
    assert result.exit_code == 0
    assert result.applied_count == 1


def test_route_audit_decision_git_add_failure_propagates_as_commit_failure(tmp_path: Path, monkeypatch):
    """If `git add` itself fails, _run_git_commit returns that — exit 3."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    fake_run = mock.MagicMock(
        side_effect=[
            _make_failing_response(rc=1),  # git add FAILS — short-circuit
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=repo_root)
    assert result.exit_code == 3
    # git commit never invoked because git add already failed.
    assert fake_run.call_count == 1


def test_route_audit_decision_resolves_repo_root_via_git_when_unset(tmp_path: Path, monkeypatch):
    """When repo_root is None, route_audit_decision calls `git rev-parse`."""
    # No proposals to apply — exits cleanly after empty short-circuit. But
    # we use a NON-empty proposal here so the repo_root resolution leg runs.
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    rev_parse_result = mock.MagicMock(returncode=0, stdout=f"{repo_root}\n", stderr="")
    fake_run = mock.MagicMock(
        side_effect=[
            rev_parse_result,  # git rev-parse --show-toplevel
            _make_zero_rc_response(),  # git add
            _make_zero_rc_response(),  # git commit
            _make_zero_rc_response(),  # gh issue comment
            _make_zero_rc_response(),  # gh issue close
        ]
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=None)
    assert result.exit_code == 0


def test_route_audit_decision_repo_root_resolution_failure_exit_code_1(
    tmp_path: Path, monkeypatch
):
    """`git rev-parse` failure → exit code 1."""
    repo_root = tmp_path
    _setup_doc_with_frontmatter(repo_root)
    proposal = {
        "doc_path": "docs/INDEX.md",
        "change_type": "frontmatter_date",
        "current_value": "2026-05-10",
        "proposed_value": "2026-05-20",
        "evidence_source": "test",
        "confidence": "high",
    }
    state_path = _make_state_file(repo_root, proposals=[proposal])

    fake_run = mock.MagicMock(
        side_effect=subprocess.CalledProcessError(1, ["git", "rev-parse"])
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.subprocess.run", fake_run
    )

    result = route_audit_decision(state_path=state_path, repo_root=None)
    assert result.exit_code == 1
    assert any("repo root" in e for e in result.errors)


# ---------------------------------------------------------------------------
# _atomic_write — failure cleanup (lines 217-222)
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_up_temp_file_on_write_failure(tmp_path: Path, monkeypatch):
    """If the write step raises, the tempfile must be removed."""
    target = tmp_path / "doc.md"
    target.write_text("original\n")

    real_fdopen = os.fdopen

    def boom(*args, **kwargs):
        raise OSError("simulated write failure")

    # Patch fdopen so the `with os.fdopen(...) as fh: fh.write(...)` raises.
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.os.fdopen", boom
    )

    with pytest.raises(OSError):
        _atomic_write(target, "should fail")

    # No leftover .tmp files in the parent directory.
    leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []
    # Restore for safety (monkeypatch should auto-undo, but be explicit).
    monkeypatch.setattr(
        "doc_audit.helpers.handle_audit_routing.os.fdopen", real_fdopen
    )


# ---------------------------------------------------------------------------
# main() CLI wrapper (lines 1009-1042)
# ---------------------------------------------------------------------------


def test_main_returns_exit_code_for_empty_proposals(tmp_path: Path):
    """End-to-end CLI happy path for empty proposals via main()."""
    state_path = _make_state_file(tmp_path, proposals=[])
    rc = main(["@" + str(state_path), "--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_returns_exit_code_1_on_missing_state_file(tmp_path: Path):
    rc = main([str(tmp_path / "missing.json"), "--repo-root", str(tmp_path)])
    assert rc == 1


# ---------------------------------------------------------------------------
# audit_interpretation Moment 0 wiring (mission #400)
# ---------------------------------------------------------------------------
#
# These tests exercise the new no-proposals branch added by WP02.
# ``interpret_audit`` and ``tier_classification.classify`` are mocked at
# the dependency-injection seam exposed by ``_run_audit_interpretation_flow``
# (the ``interpret_audit_fn`` / ``tier_classify_fn`` / ``client_factory``
# kwargs) so we never spin up the real anthropic SDK.


from types import SimpleNamespace as _SNS  # noqa: E402

from doc_audit.helpers import handle_audit_routing as _har_module  # noqa: E402


def _make_audit_verdict(
    *,
    doc_path: str,
    verdict: str,
    confidence: float = 0.95,
    rationale: str = "test",
    proposed_edit: dict | None = None,
    question: str | None = None,
):
    """Build a real :class:`AuditVerdict` (the dataclass exists in WP01)."""
    from doc_audit.judgment.audit_interpretation import AuditVerdict

    return AuditVerdict(
        doc_path=doc_path,
        verdict=verdict,
        confidence=confidence,
        rationale=rationale,
        proposed_edit=proposed_edit,
        question=question,
    )


def _make_ai_config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    domain_map_payload: dict | None = None,
) -> _SNS:
    """Build a minimal duck-typed Config the new flow can consume.

    The real :class:`Config` carries many fields; the flow only reads
    ``config.audit_interpretation.enabled`` and
    ``config.paths.doc_domain_map``. Using ``SimpleNamespace`` keeps
    the tests focused on the behavior under test.
    """
    domain_map_path = tmp_path / "doc-domain-map.json"
    if domain_map_payload is None:
        domain_map_payload = {
            "domains": {
                "area/felix-core": ["docs/INDEX.md"],
            }
        }
    domain_map_path.write_text(json.dumps(domain_map_payload))

    ledger_path = tmp_path / "audit-events-ledger.jsonl"

    return _SNS(
        audit_interpretation=_SNS(
            enabled=enabled,
            ledger_path=str(ledger_path),
        ),
        paths=_SNS(
            doc_domain_map=str(domain_map_path),
        ),
    )


def _populate_in_scope_doc(repo_root: Path, rel_path: str, body: str) -> Path:
    """Create an in-scope doc file under ``repo_root`` and return its path."""
    abs_path = repo_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(body, encoding="utf-8")
    return abs_path


def _patch_flow_internals(
    monkeypatch,
    *,
    interpret_return: list | Exception,
    tier_classify_return: tuple | None = None,
    diff_text: str = "diff --git a/docs/INDEX.md b/docs/INDEX.md\n@@ -1 +1 @@\n-old\n+new\n",
):
    """Patch ``_fetch_diff_for_commit`` and the dependency-injected fns.

    Returns a SimpleNamespace exposing the mocks for assertion.
    """
    fake_fetch = mock.MagicMock(return_value=diff_text)
    monkeypatch.setattr(_har_module, "_fetch_diff_for_commit", fake_fetch)

    fake_client_factory = mock.MagicMock(return_value=object())
    fake_interpret = mock.MagicMock()
    if isinstance(interpret_return, Exception):
        fake_interpret.side_effect = interpret_return
    else:
        fake_interpret.return_value = interpret_return

    fake_tier_classify = mock.MagicMock()
    if tier_classify_return is not None:
        fake_tier_classify.return_value = tier_classify_return

    # Re-wire _run_audit_interpretation_flow's signature by injecting via
    # module-level patches the flow consumes. The flow accepts these as
    # kwargs, so we wrap the real function and provide the test mocks.
    real_flow = _har_module._run_audit_interpretation_flow

    def patched_flow(**kwargs):
        kwargs.setdefault("client_factory", fake_client_factory)
        kwargs.setdefault("interpret_audit_fn", fake_interpret)
        kwargs.setdefault("tier_classify_fn", fake_tier_classify)
        return real_flow(**kwargs)

    monkeypatch.setattr(
        _har_module, "_run_audit_interpretation_flow", patched_flow
    )

    return _SNS(
        fetch=fake_fetch,
        client_factory=fake_client_factory,
        interpret=fake_interpret,
        tier_classify=fake_tier_classify,
    )


# --- Scenario C: gate disabled → fallback path ----------------------


def test_no_proposals_with_audit_interpretation_disabled_runs_fallback(
    tmp_path: Path, monkeypatch
):
    """Config disabled → today's lock-release + comment fallback runs."""
    state_path = _make_state_file(tmp_path, proposals=[])
    config = _make_ai_config(tmp_path, enabled=False)

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=tmp_path,
        config=config,
    )

    assert result.exit_code == 0
    # Two best-effort gh calls: comment + remove-label.
    assert fake_run.call_count == 2
    # First call is the no-proposals comment.
    first_args = fake_run.call_args_list[0].args[0]
    assert "issue" in first_args and "comment" in first_args


# --- Scenario A: all NO_CHANGE_NEEDED → auto-close ------------------


def test_no_proposals_all_no_change_needed_auto_closes_audit(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "---\nx: 1\n---\nbody\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="NO_CHANGE_NEEDED",
            confidence=0.92,
            rationale="doc unrelated to diff",
        ),
    ]
    patches = _patch_flow_internals(
        monkeypatch, interpret_return=verdicts
    )

    # gh issue comment (auto-close summary) + gh issue close + gh issue
    # edit --remove-label.
    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    # interpret_audit was called.
    assert patches.interpret.call_count == 1
    # tier_classification NOT called (no PROPOSED_EDIT verdicts).
    assert patches.tier_classify.call_count == 0
    # GH side-effects: summary comment + close + lock release = 3 calls.
    assert fake_run.call_count == 3
    # Ensure the summary comment mentioned the clean doc.
    summary_args = fake_run.call_args_list[0].args[0]
    assert any("docs/INDEX.md" in str(a) for a in summary_args)
    assert "close" in fake_run.call_args_list[1].args[0]


# --- Scenario B: mixed verdicts → consolidated comment, audit stays open ---


def test_no_proposals_mixed_no_change_and_judgment_required_posts_consolidated_comment(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "---\nx: 1\n---\nbody\n")
    _populate_in_scope_doc(
        repo_root, "docs/runbooks/foo.md", "---\nfoo: bar\n---\nbody\n"
    )
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(
        tmp_path,
        enabled=True,
        domain_map_payload={
            "domains": {
                "area/felix-core": [
                    "docs/INDEX.md",
                    "docs/runbooks/foo.md",
                ],
            }
        },
    )

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="NO_CHANGE_NEEDED",
            confidence=0.91,
            rationale="ok",
        ),
        _make_audit_verdict(
            doc_path="docs/runbooks/foo.md",
            verdict="JUDGMENT_REQUIRED",
            confidence=0.65,
            rationale="needs op judgment",
            question="Does this section need updating for the new behavior?",
        ),
    ]
    _patch_flow_internals(monkeypatch, interpret_return=verdicts)

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    # Side effects: consolidated comment (1) + lock release (1). Audit
    # NOT closed (it stays open because of the JUDGMENT_REQUIRED).
    assert fake_run.call_count == 2
    # First call is the consolidated comment.
    comment_args = fake_run.call_args_list[0].args[0]
    assert "comment" in comment_args
    body_str = " ".join(str(a) for a in comment_args)
    assert "docs/runbooks/foo.md" in body_str
    assert "need your judgment" in body_str
    assert "docs/INDEX.md" in body_str  # listed as clean
    # No `gh issue close` call.
    for call in fake_run.call_args_list:
        assert "close" not in call.args[0]


# --- Scenario B': PROPOSED_EDIT @ Tier A → auto-commit -------------


def test_no_proposals_proposed_edit_tier_a_auto_commit(tmp_path: Path, monkeypatch):
    repo_root = tmp_path
    _populate_in_scope_doc(
        repo_root, "docs/INDEX.md", "Title v1.2.0\nrest\n"
    )
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="PROPOSED_EDIT",
            confidence=0.90,
            rationale="version drift detected",
            proposed_edit={
                "doc_path": "docs/INDEX.md",
                "current_value": "1.2.0",
                "proposed_value": "1.3.0",
            },
        ),
    ]
    # tier_classification returns Tier A.
    from doc_audit.data_model import EditTier

    _patch_flow_internals(
        monkeypatch,
        interpret_return=verdicts,
        tier_classify_return=(EditTier.TIER_A, "frontmatter-only", None),
    )

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    # File was actually rewritten on disk (version_bump applier matched).
    assert "v1.3.0" in (repo_root / "docs/INDEX.md").read_text()
    # Subprocess: git add + git commit + lock-release (no consolidated
    # comment, no auto-close — there was a PROPOSED_EDIT side effect).
    cmds = [tuple(c.args[0][:2]) for c in fake_run.call_args_list]
    assert ("git", "add") in cmds
    assert ("git", "commit") in cmds


# --- Scenario B'': PROPOSED_EDIT @ Tier B → file pending-approval ---


def test_no_proposals_proposed_edit_tier_b_files_pending_approval(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _populate_in_scope_doc(
        repo_root, "docs/INDEX.md", "Title v1.2.0\nrest\n"
    )
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="PROPOSED_EDIT",
            confidence=0.85,
            rationale="content change suggested",
            proposed_edit={
                "doc_path": "docs/INDEX.md",
                "current_value": "1.2.0",
                "proposed_value": "1.3.0",
            },
        ),
    ]
    from doc_audit.data_model import EditTier

    _patch_flow_internals(
        monkeypatch,
        interpret_return=verdicts,
        tier_classify_return=(EditTier.TIER_B, "content-touching", None),
    )

    # gh issue create (pending approval) returns a parseable URL.
    fake_run = mock.MagicMock(
        side_effect=[
            _make_gh_create_response(issue_number=4242),
            _make_zero_rc_response(),  # lock release
        ]
    )
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    # Two subprocess calls: gh issue create + lock release.
    assert fake_run.call_count == 2
    first_cmd = fake_run.call_args_list[0].args[0]
    assert "create" in first_cmd
    assert any("audit-pending-approval" in str(a) for a in first_cmd)


# --- Scenario D: DriftInterpretationError → fallback path + RETRY_EXHAUSTED rows ---


def test_no_proposals_retry_exhausted_falls_back_and_writes_ledger(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "---\nx: 1\n---\nbody\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    from doc_audit.judgment.drift_interpretation import (
        DriftInterpretationError,
    )

    err = DriftInterpretationError("simulated retry exhausted")
    _patch_flow_internals(monkeypatch, interpret_return=err)

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    # Fallback ran: 2 calls (no-proposals comment + lock release).
    assert fake_run.call_count == 2
    # Ledger has one RETRY_EXHAUSTED row per in-scope doc.
    ledger_path = Path(config.audit_interpretation.ledger_path)
    assert ledger_path.exists()
    rows = [
        json.loads(line)
        for line in ledger_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["verdict"] == "RETRY_EXHAUSTED"
    assert rows[0]["outcome"] == "retry_exhausted"
    assert rows[0]["doc_path"] == "docs/INDEX.md"


# --- Scenario C-006: weekly audit (no commit_sha) → fallback path ---


def test_no_proposals_weekly_audit_skips_audit_interpretation(tmp_path: Path, monkeypatch):
    """Weekly audits carry commit_sha="" — Moment 0 must NOT fire."""
    state = {
        "audit_issue_number": 555,
        "commit_sha": "",  # weekly audit
        "areas": [],
        "proposals": [],
        "debt_issues_filed": [],
        "missing_artifact_issues_filed": [],
    }
    state_path = tmp_path / "weekly.json"
    state_path.write_text(json.dumps(state))
    config = _make_ai_config(tmp_path, enabled=True)

    # interpret_audit MUST NOT be called for a weekly audit.
    fake_interpret = mock.MagicMock()
    monkeypatch.setattr(
        "doc_audit.judgment.audit_interpretation.interpret_audit",
        fake_interpret,
    )

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=tmp_path,
        config=config,
    )

    assert result.exit_code == 0
    assert fake_interpret.call_count == 0  # C-006: weekly skips Moment 0
    # Today-merged fallback ran (no-proposals comment + lock release).
    assert fake_run.call_count == 2


# --- Empty diff → fallback path ------------------------------------


def test_no_proposals_empty_diff_falls_back(tmp_path: Path, monkeypatch):
    """When git show yields no diff, the flow returns False → fallback."""
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "---\nx: 1\n---\nbody\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    fake_fetch = mock.MagicMock(return_value="")  # empty diff
    monkeypatch.setattr(_har_module, "_fetch_diff_for_commit", fake_fetch)
    fake_interpret = mock.MagicMock()
    monkeypatch.setattr(
        "doc_audit.judgment.audit_interpretation.interpret_audit",
        fake_interpret,
    )

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    fake_interpret.assert_not_called()
    # Fallback ran.
    assert fake_run.call_count == 2


# --- No in-scope docs after domain_map resolution → fallback path ---


def test_no_proposals_no_in_scope_docs_falls_back(tmp_path: Path, monkeypatch):
    state = {
        "audit_issue_number": 777,
        "commit_sha": "abc1234",
        "areas": ["area/no-such-area"],  # no map entry → no in-scope docs
        "proposals": [],
        "debt_issues_filed": [],
        "missing_artifact_issues_filed": [],
    }
    state_path = tmp_path / "s.json"
    state_path.write_text(json.dumps(state))
    config = _make_ai_config(tmp_path, enabled=True)

    fake_fetch = mock.MagicMock(
        return_value="diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n"
    )
    monkeypatch.setattr(_har_module, "_fetch_diff_for_commit", fake_fetch)
    fake_interpret = mock.MagicMock()
    monkeypatch.setattr(
        "doc_audit.judgment.audit_interpretation.interpret_audit",
        fake_interpret,
    )

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=tmp_path,
        config=config,
    )

    assert result.exit_code == 0
    fake_interpret.assert_not_called()
    # Fallback ran.
    assert fake_run.call_count == 2


# --- PROPOSED_EDIT routed via tier_classification → judgment → DebtIssue ---


def test_no_proposals_proposed_edit_judgment_files_debt_issue(
    tmp_path: Path, monkeypatch
):
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "Title v1.2.0\nrest\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="PROPOSED_EDIT",
            confidence=0.82,
            rationale="ambiguous edit",
            proposed_edit={
                "doc_path": "docs/INDEX.md",
                "current_value": "1.2.0",
                "proposed_value": "1.3.0",
            },
        ),
    ]
    from doc_audit.data_model import EditTier

    _patch_flow_internals(
        monkeypatch,
        interpret_return=verdicts,
        tier_classify_return=(
            EditTier.JUDGMENT,
            "guardrailed or ambiguous",
            None,
        ),
    )

    fake_run = mock.MagicMock(
        side_effect=[
            _make_gh_create_response(issue_number=9999),  # debt issue
            _make_zero_rc_response(),  # lock release
        ]
    )
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path,
        repo_root=repo_root,
        config=config,
    )

    assert result.exit_code == 0
    assert fake_run.call_count == 2
    first_cmd = fake_run.call_args_list[0].args[0]
    assert "create" in first_cmd
    assert any("docs-debt" in str(a) for a in first_cmd)


# --- Backward-compat: route_audit_decision callable without config kwarg ---


def test_no_proposals_no_config_kwarg_runs_lazy_load_then_fallback(
    tmp_path: Path, monkeypatch
):
    """When config kwarg is omitted, lazy-load is best-effort; failure
    is silent and the today-merged fallback runs.
    """
    state_path = _make_state_file(tmp_path, proposals=[])

    # Force the lazy loader to return None (no config available).
    monkeypatch.setattr(_har_module, "_load_config_lazy", lambda: None)

    fake_run = mock.MagicMock(return_value=_make_zero_rc_response())
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(state_path=state_path, repo_root=tmp_path)
    assert result.exit_code == 0
    # Fallback ran (comment + lock release).
    assert fake_run.call_count == 2


# --- Helper-level coverage: small but load-bearing functions --------


def test_audit_interpretation_enabled_handles_missing_attribute():
    assert _har_module._audit_interpretation_enabled(None) is False
    assert _har_module._audit_interpretation_enabled(_SNS()) is False
    assert _har_module._audit_interpretation_enabled(
        _SNS(audit_interpretation=_SNS())
    ) is False
    assert _har_module._audit_interpretation_enabled(
        _SNS(audit_interpretation=_SNS(enabled=True))
    ) is True


def test_build_consolidated_judgment_comment_lists_questions_and_clean_docs():
    body = _har_module._build_consolidated_judgment_comment(
        [
            ("docs/runbooks/foo.md", "Does foo need an update?"),
            ("docs/runbooks/bar.md", "Is bar still accurate?"),
        ],
        clean_docs=["docs/INDEX.md"],
    )
    assert "2 of 3 doc(s)" in body
    assert "docs/runbooks/foo.md" in body
    assert "docs/runbooks/bar.md" in body
    assert "docs/INDEX.md" in body
    assert "Does foo need an update?" in body


def test_build_audit_auto_close_comment_lists_clean_docs():
    body = _har_module._build_audit_auto_close_comment(
        ["docs/INDEX.md", "docs/runbooks/foo.md"]
    )
    assert "auto-closed" in body
    assert "docs/INDEX.md" in body
    assert "docs/runbooks/foo.md" in body


def test_load_doc_domain_map_path_handles_missing_file(tmp_path: Path):
    out = _har_module._load_doc_domain_map_path(tmp_path / "missing.json")
    assert out == {}


def test_load_doc_domain_map_path_handles_malformed_json(tmp_path: Path):
    bad = tmp_path / "m.json"
    bad.write_text("not json")
    assert _har_module._load_doc_domain_map_path(bad) == {}


def test_resolve_in_scope_docs_full_scope_when_areas_empty():
    domain_map = {
        "area/a": ["docs/a.md", "docs/shared.md"],
        "area/b": ["docs/b.md", "docs/shared.md"],
    }
    out = _har_module._resolve_in_scope_docs_from_areas([], domain_map)
    # Order-preserving union, no duplicates.
    assert set(out) == {"docs/a.md", "docs/shared.md", "docs/b.md"}
    assert len(out) == 3


def test_resolve_in_scope_docs_intersects_with_areas():
    domain_map = {
        "area/a": ["docs/a.md"],
        "area/b": ["docs/b.md"],
    }
    out = _har_module._resolve_in_scope_docs_from_areas(["area/a"], domain_map)
    assert out == ["docs/a.md"]


def test_build_doc_targets_skips_missing_files(tmp_path: Path):
    # Two docs requested; only one exists.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "exists.md").write_text("body\n")
    out = _har_module._build_doc_targets(
        ["docs/exists.md", "docs/missing.md"],
        diff="",
        repo_root=tmp_path,
    )
    assert len(out) == 1
    assert out[0].path == "docs/exists.md"


def test_no_proposals_tier_classification_raises_falls_back_to_debt_issue(
    tmp_path: Path, monkeypatch
):
    """tier_classification raises → debt issue filed, ledger row=issue_filed."""
    repo_root = tmp_path
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "Title v1.2.0\nrest\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="PROPOSED_EDIT",
            confidence=0.85,
            proposed_edit={
                "doc_path": "docs/INDEX.md",
                "current_value": "1.2.0",
                "proposed_value": "1.3.0",
            },
        ),
    ]

    fake_fetch = mock.MagicMock(
        return_value="diff --git a/docs/INDEX.md b/docs/INDEX.md\n@@ -1 +1 @@\n-x\n+y\n"
    )
    monkeypatch.setattr(_har_module, "_fetch_diff_for_commit", fake_fetch)

    fake_run = mock.MagicMock(
        side_effect=[
            _make_gh_create_response(issue_number=8888),  # debt issue
            _make_zero_rc_response(),  # lock release
        ]
    )
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    real_flow = _har_module._run_audit_interpretation_flow

    def patched_flow(**kwargs):
        kwargs.setdefault("client_factory", lambda: object())
        kwargs.setdefault(
            "interpret_audit_fn", mock.MagicMock(return_value=verdicts)
        )
        kwargs.setdefault(
            "tier_classify_fn",
            mock.MagicMock(side_effect=RuntimeError("boom")),
        )
        return real_flow(**kwargs)

    monkeypatch.setattr(_har_module, "_run_audit_interpretation_flow", patched_flow)

    result = route_audit_decision(
        state_path=state_path, repo_root=repo_root, config=config
    )
    assert result.exit_code == 0
    # docs-debt issue + lock release.
    assert fake_run.call_count == 2
    first_cmd = fake_run.call_args_list[0].args[0]
    assert any("docs-debt" in str(a) for a in first_cmd)


def test_no_proposals_tier_a_apply_failure_demotes_to_debt_issue(
    tmp_path: Path, monkeypatch
):
    """Tier A apply fails (no applier matches) → debt issue filed."""
    repo_root = tmp_path
    # Content does NOT match any applier — no version, no frontmatter date,
    # no path to rename. Tier A apply will fail.
    _populate_in_scope_doc(repo_root, "docs/INDEX.md", "plain content\n")
    state_path = _make_state_file(repo_root, proposals=[])
    config = _make_ai_config(tmp_path, enabled=True)

    verdicts = [
        _make_audit_verdict(
            doc_path="docs/INDEX.md",
            verdict="PROPOSED_EDIT",
            confidence=0.90,
            proposed_edit={
                "doc_path": "docs/INDEX.md",
                "current_value": "DOES_NOT_EXIST",
                "proposed_value": "REPLACEMENT",
            },
        ),
    ]
    from doc_audit.data_model import EditTier

    _patch_flow_internals(
        monkeypatch,
        interpret_return=verdicts,
        tier_classify_return=(EditTier.TIER_A, "tier-a rationale", None),
    )

    fake_run = mock.MagicMock(
        side_effect=[
            _make_gh_create_response(issue_number=7777),  # debt issue
            _make_zero_rc_response(),  # lock release
        ]
    )
    monkeypatch.setattr(_har_module.subprocess, "run", fake_run)

    result = route_audit_decision(
        state_path=state_path, repo_root=repo_root, config=config
    )
    assert result.exit_code == 0
    # Apply failed → no git add/commit; just debt issue + lock release.
    assert fake_run.call_count == 2
    first_cmd = fake_run.call_args_list[0].args[0]
    assert "create" in first_cmd
    assert any("docs-debt" in str(a) for a in first_cmd)


def test_build_audit_derived_proposed_edit_carries_audit_evidence():
    verdict = _make_audit_verdict(
        doc_path="docs/INDEX.md",
        verdict="PROPOSED_EDIT",
        proposed_edit={
            "doc_path": "docs/INDEX.md",
            "current_value": "1.0.0",
            "proposed_value": "2.0.0",
        },
    )
    pe = _har_module._build_audit_derived_proposed_edit(verdict, "abc123")
    assert pe.change_type == "audit_derived"
    assert pe.evidence_source == "audit-commit:abc123"
    assert pe.current_value == "1.0.0"
    assert pe.proposed_value == "2.0.0"
    assert pe.confidence == "high"
