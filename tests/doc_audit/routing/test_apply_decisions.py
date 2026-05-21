"""Unit tests for ``doc_audit.routing.apply_decisions``.

Verifies:
- ``_build_audit_state`` maps this mission's E-002/E-004/E-006
  entities into the JSON shape ``handle_audit_routing.py`` expects.
- ``CHANGE_TYPE_MAP`` translates mission change_type values
  (SKILL.md §4.1 #1-7) into the helper's auto-apply allowlist
  vocabulary so the helper's partition routes them correctly.
- ``apply`` writes a tempfile, invokes ``route_audit_decision``
  with that tempfile path, and cleans up the tempfile in a
  ``finally`` block even on exception.
- Returns the helper's ``RoutingResult`` verbatim.
- The re-export of ``RoutingResult`` via ``doc_audit.routing`` is
  the same class identity the helper exposes (so callers can
  import from either surface).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from doc_audit.data_model import AuditIssue, DebtIssue, ProposedEdit
from doc_audit.helpers.handle_audit_routing import (
    RoutingResult as HelperRoutingResult,
)
from doc_audit.routing import RoutingResult as RoutingNamespaceExport
from doc_audit.routing.apply_decisions import (
    CHANGE_TYPE_MAP,
    RoutingResult,
    _build_audit_state,
    _translate_change_type,
    apply,
)


# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------


def _make_audit(issue_number: int = 4242, weekly: bool = False) -> AuditIssue:
    return AuditIssue(
        issue_number=issue_number,
        title=(
            "Weekly doc audit — 2026-W21"
            if weekly
            else "Doc audit: abc1234 (felix-core)"
        ),
        is_weekly=weekly,
        triggering_sha=None if weekly else "abc1234",
        area_labels=["area/felix-core"],
        in_scope_docs=[
            "docs/constitution/FELIX-CONSTITUTION.md",
        ],
        lock_acquired_at_utc=None,
    )


def _make_edit(
    doc_path: str = "docs/INDEX.md",
    change_type: str = "frontmatter_field_bump",
    current_value: str = "2026-05-10",
    proposed_value: str = "2026-05-20",
    tier: str = "tier_a",
) -> ProposedEdit:
    return ProposedEdit(
        doc_path=doc_path,
        change_type=change_type,
        current_value=current_value,
        proposed_value=proposed_value,
        evidence_source="commit abc1234 (2026-05-20)",
        tier=tier,
        confidence="high",
    )


def _make_debt(title: str = "Docs: stub") -> DebtIssue:
    return DebtIssue(
        title=title,
        artifact_path="docs/whatever.md",
        gap_description="missing context",
        area_labels=["area/felix-core"],
        cross_references=["#4242"],
        draft_outline="- bullet",
        success_criteria=["it exists"],
        is_missing_artifact=False,
    )


# ---------------------------------------------------------------------------
# Re-export identity
# ---------------------------------------------------------------------------


def test_routing_result_reexport_matches_helper():
    """``doc_audit.routing.RoutingResult`` is the helper's class."""
    assert RoutingResult is HelperRoutingResult
    assert RoutingNamespaceExport is HelperRoutingResult


# ---------------------------------------------------------------------------
# change_type translation
# ---------------------------------------------------------------------------


def test_change_type_map_covers_all_mission_values():
    """All seven SKILL.md §4.1 change_type names map to a helper value."""
    mission_change_types = {
        "frontmatter_field_bump",
        "frontmatter_updated_by",
        "service_version",
        "file_path_rename",
        "dead_reference_removal",
        "agent_registry_add",
        "autonomy_level_update",
    }
    assert mission_change_types.issubset(set(CHANGE_TYPE_MAP.keys()))


def test_translate_change_type_known_mapping():
    assert _translate_change_type("frontmatter_field_bump") == "frontmatter_date"
    assert _translate_change_type("service_version") == "version_bump"
    assert _translate_change_type("file_path_rename") == "path_rename"
    assert _translate_change_type("dead_reference_removal") == "dead_ref_removal"
    assert _translate_change_type("agent_registry_add") == "registry_entry_add"
    assert _translate_change_type("autonomy_level_update") == "registry_autonomy_update"


def test_translate_change_type_unknown_passthrough():
    """Unmapped values flow through unchanged (helper will gate them)."""
    assert _translate_change_type("never_seen_before") == "never_seen_before"


# ---------------------------------------------------------------------------
# _build_audit_state
# ---------------------------------------------------------------------------


def test_build_audit_state_top_level_keys_match_helper_contract():
    """Top-level keys must match helper REQUIRED_TOP_KEYS exactly."""
    audit = _make_audit()
    state = _build_audit_state(audit, [], [], [])
    assert set(state.keys()) == {
        "audit_issue_number",
        "commit_sha",
        "areas",
        "proposals",
        "debt_issues_filed",
        "missing_artifact_issues_filed",
    }


def test_build_audit_state_maps_e002_fields():
    audit = _make_audit(issue_number=999)
    state = _build_audit_state(audit, [], [], [])
    assert state["audit_issue_number"] == 999
    assert state["commit_sha"] == "abc1234"
    assert state["areas"] == ["area/felix-core"]


def test_build_audit_state_weekly_audit_has_empty_commit_sha():
    """Weekly audits have no triggering SHA → empty string (helper validates type)."""
    audit = _make_audit(weekly=True)
    state = _build_audit_state(audit, [], [], [])
    assert state["commit_sha"] == ""


def test_build_audit_state_proposals_translate_change_type():
    audit = _make_audit()
    edit = _make_edit(change_type="frontmatter_field_bump")
    state = _build_audit_state(audit, [edit], [], [])
    assert len(state["proposals"]) == 1
    assert state["proposals"][0]["change_type"] == "frontmatter_date"


def test_build_audit_state_proposal_required_keys_present():
    """Each proposal entry has every helper-required key."""
    audit = _make_audit()
    edit = _make_edit()
    state = _build_audit_state(audit, [edit], [], [])
    p = state["proposals"][0]
    for key in (
        "doc_path",
        "change_type",
        "current_value",
        "proposed_value",
        "evidence_source",
        "confidence",
    ):
        assert key in p, f"missing helper-required key {key!r}"


def test_build_audit_state_proposal_does_not_carry_tier_to_helper():
    """``tier`` is a mission concept; the helper partitions by change_type."""
    audit = _make_audit()
    edit = _make_edit(tier="tier_b")
    state = _build_audit_state(audit, [edit], [], [])
    assert "tier" not in state["proposals"][0]


def test_build_audit_state_missing_artifacts_split_by_kind():
    audit = _make_audit()
    state = _build_audit_state(
        audit,
        [],
        [],
        [
            {"issue_number": 100, "kind": "debt"},
            {"issue_number": 101, "kind": "missing"},
            {"issue_number": 102, "kind": "debt"},
        ],
    )
    assert state["debt_issues_filed"] == [100, 102]
    assert state["missing_artifact_issues_filed"] == [101]


def test_build_audit_state_missing_artifacts_drops_unknown_kind():
    audit = _make_audit()
    state = _build_audit_state(
        audit,
        [],
        [],
        [
            {"issue_number": 100, "kind": "bogus"},
            {"issue_number": 101, "kind": "debt"},
        ],
    )
    assert state["debt_issues_filed"] == [101]
    assert state["missing_artifact_issues_filed"] == []


def test_build_audit_state_missing_artifacts_drops_non_int_issue_number():
    audit = _make_audit()
    state = _build_audit_state(
        audit,
        [],
        [],
        [
            {"issue_number": "abc", "kind": "debt"},
            {"issue_number": 101, "kind": "debt"},
        ],
    )
    assert state["debt_issues_filed"] == [101]


def test_build_audit_state_empty_lists_default():
    audit = _make_audit()
    state = _build_audit_state(audit, [], [], [])
    assert state["proposals"] == []
    assert state["debt_issues_filed"] == []
    assert state["missing_artifact_issues_filed"] == []


def test_build_audit_state_debt_issues_param_is_accepted_but_not_consumed():
    """``debt_issues`` typed-list is accepted for forward-compat; no number emitted today."""
    audit = _make_audit()
    state = _build_audit_state(audit, [], [_make_debt(), _make_debt()], [])
    # No GH number on DebtIssue today → debt_issues_filed empty.
    assert state["debt_issues_filed"] == []


# ---------------------------------------------------------------------------
# apply() — happy path + tempfile lifecycle
# ---------------------------------------------------------------------------


def test_apply_invokes_router_with_tempfile_path(tmp_config):
    """``apply`` writes a tempfile and passes its Path to the router."""
    audit = _make_audit()
    edit = _make_edit()
    captured: dict[str, Path | dict] = {}

    def fake_router(state_path):
        captured["state_path"] = state_path
        # Round-trip the JSON to confirm it parses.
        captured["state"] = json.loads(state_path.read_text(encoding="utf-8"))
        return HelperRoutingResult(applied_count=1, exit_code=0)

    with mock.patch(
        "doc_audit.routing.apply_decisions.route_audit_decision",
        side_effect=fake_router,
    ):
        result = apply(
            config=tmp_config,
            audit=audit,
            proposed_edits=[edit],
            debt_issues=[],
            missing_artifacts=[],
        )

    assert isinstance(captured["state_path"], Path)
    # File should already be deleted by the time we get here.
    assert not captured["state_path"].exists()
    assert captured["state"]["audit_issue_number"] == 4242
    assert captured["state"]["proposals"][0]["change_type"] == "frontmatter_date"
    assert result.applied_count == 1
    assert result.exit_code == 0


def test_apply_returns_routing_result_verbatim(tmp_config):
    audit = _make_audit()
    sentinel = HelperRoutingResult(
        applied_count=2,
        gated=True,
        pending_approval_issue=555,
        debt_issues=[100, 101],
        missing_issues=[],
        errors=[],
        exit_code=0,
    )
    with mock.patch(
        "doc_audit.routing.apply_decisions.route_audit_decision",
        return_value=sentinel,
    ):
        result = apply(
            config=tmp_config,
            audit=audit,
            proposed_edits=[_make_edit()],
            debt_issues=[],
            missing_artifacts=[],
        )
    assert result is sentinel


def test_apply_cleans_up_tempfile_on_exception(tmp_config):
    """Tempfile is unlinked even if the router raises."""
    audit = _make_audit()
    captured: dict[str, Path] = {}

    def explode(state_path):
        captured["state_path"] = state_path
        # File MUST exist at this point.
        assert state_path.exists()
        raise RuntimeError("kaboom")

    with mock.patch(
        "doc_audit.routing.apply_decisions.route_audit_decision",
        side_effect=explode,
    ):
        with pytest.raises(RuntimeError, match="kaboom"):
            apply(
                config=tmp_config,
                audit=audit,
                proposed_edits=[_make_edit()],
                debt_issues=[],
                missing_artifacts=[],
            )

    assert "state_path" in captured
    assert not captured["state_path"].exists(), "tempfile leaked on exception"


def test_apply_writes_valid_json(tmp_config):
    """The tempfile contents parse as JSON the helper would accept."""
    audit = _make_audit()
    edits = [
        _make_edit(change_type="frontmatter_field_bump"),
        _make_edit(
            doc_path="docs/two.md",
            change_type="needs_human_judgment",  # unmapped → flows through
        ),
    ]

    def assertive_router(state_path):
        data = json.loads(state_path.read_text(encoding="utf-8"))
        # Required top-level keys, per helper contract.
        for key in (
            "audit_issue_number",
            "commit_sha",
            "areas",
            "proposals",
            "debt_issues_filed",
            "missing_artifact_issues_filed",
        ):
            assert key in data
        # Unmapped value flows through verbatim.
        assert data["proposals"][1]["change_type"] == "needs_human_judgment"
        return HelperRoutingResult(exit_code=0)

    with mock.patch(
        "doc_audit.routing.apply_decisions.route_audit_decision",
        side_effect=assertive_router,
    ):
        apply(
            config=tmp_config,
            audit=audit,
            proposed_edits=edits,
            debt_issues=[],
            missing_artifacts=[],
        )


def test_apply_does_not_leak_tempfile_on_success(tmp_config):
    """On the success path, no tempfile lingers."""
    audit = _make_audit()
    captured_path: dict[str, Path] = {}

    def fake_router(state_path):
        captured_path["p"] = state_path
        return HelperRoutingResult(exit_code=0)

    with mock.patch(
        "doc_audit.routing.apply_decisions.route_audit_decision",
        side_effect=fake_router,
    ):
        apply(
            config=tmp_config,
            audit=audit,
            proposed_edits=[],
            debt_issues=[],
            missing_artifacts=[],
        )

    assert "p" in captured_path
    assert not captured_path["p"].exists()
