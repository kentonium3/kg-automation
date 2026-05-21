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
