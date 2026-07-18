"""Seam contract tests for the friction / Eisenhower / type / LOE label
taxonomy declared in ``scripts/common/vikunja_refs.json`` (WP01, mission
``task-intake-validation-loop-01KXS06W``, kentonium3/kg-automation#749).

The intake-validation loop resolves **every** Tier-1/Tier-2 label id through the
#748 fail-loud accessor (``scripts.common.vikunja_refs.label_id``) — no hardcoded
ids anywhere. These tests lock two things:

1. the accessor resolves every taxonomy label name (``f:1-flow`` … ``loe:l``)
   through the seam to its declared id (proved with an injected registry so the
   resolution mechanism is exercised for all 12 labels), and
2. the drift/declaration validator governs the new entries and stays green.

The live ids below were reconciled against the #715 kent-owned label set on the
live Vikunja instance (office2, kent token) — the confirmed steady state.
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_refs import VikunjaRefError
from scripts.common.vikunja_refs_validate import (
    ValidationFinding,
    main,
    validate,
    validate_declarations,
)

#: The 12 canonical taxonomy labels mapped to their reconciled live ids in the
#: kent token namespace (#715; office2 live probe). Declared as a literal so the
#: resolution assertions are not a tautology against the registry file.
TAXONOMY_LABEL_IDS: dict[str, int] = {
    "f:1-flow": 18,
    "f:2-growth": 19,
    "f:3-edge": 20,
    "f:4-overload": 21,
    "q:do": 22,
    "q:schedule": 23,
    "q:delegate": 24,
    "q:eliminate": 25,
    "t:habit": 26,
    "loe:s": 27,
    "loe:m": 28,
    "loe:l": 29,
}
TAXONOMY_LABELS: tuple[str, ...] = tuple(TAXONOMY_LABEL_IDS)


@pytest.fixture(autouse=True)
def _restore_registry() -> Any:
    """Ensure every test starts and ends on the file-backed registry.

    Tests that need isolation install their own override via
    ``set_registry_for_test``; this fixture guarantees the override is cleared
    afterwards so no in-memory registry leaks into the shipped-file tests.
    """
    vikunja_refs.set_registry_for_test(None)
    yield
    vikunja_refs.set_registry_for_test(None)


def _label_entry(name: str, value: int | None) -> dict[str, Any]:
    return {
        "name": name,
        "selector": {"kind": "label", "value": value},
        "title": name,
        "owner_token": "kent",
    }


def _registry_with(labels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_of_truth": "docs/design/vikunja-configuration-design.md",
        "last_verified_utc": "2026-07-17T00:00:00Z",
        "projects": [],
        "labels": labels,
        "private_projects": [],
    }


# ---------------------------------------------------------------------------
# Shipped registry: every taxonomy label resolves to its live id (#715)
# ---------------------------------------------------------------------------


def test_shipped_registry_declares_full_taxonomy() -> None:
    # The committed vikunja_refs.json must declare all 12 taxonomy labels for
    # the kent token (file read only, no network).
    declared = {lbl["name"]: lbl for lbl in vikunja_refs.declared_labels()}
    for name in TAXONOMY_LABELS:
        assert name in declared, f"{name!r} missing from shipped vikunja_refs.json"
        assert declared[name]["owner_token"] == "kent"
        assert declared[name]["selector"]["kind"] == "label"


def test_shipped_labels_resolve_to_live_ids() -> None:
    # Every taxonomy label resolves through the fail-loud accessor to its
    # reconciled live id in the kent namespace (file read only, no network).
    # Crucially, none returns a falsy/fabricated sentinel — each is a real
    # positive int. q:schedule (23) is unchanged.
    for name, expected_id in TAXONOMY_LABEL_IDS.items():
        resolved = vikunja_refs.label_id(name, "kent")
        assert resolved == expected_id, f"{name!r} resolved to {resolved}, want {expected_id}"
        assert isinstance(resolved, int) and not isinstance(resolved, bool)
        assert resolved > 0


def test_shipped_q_schedule_id_unchanged() -> None:
    # Regression guard: the pre-existing q:schedule id must stay 23.
    assert vikunja_refs.label_id("q:schedule", "kent") == 23


def test_label_id_undeclared_raises_fail_loud() -> None:
    # An undeclared label name must fail loud (never return None/0), even with
    # the full taxonomy declared. Uses the shipped registry.
    with pytest.raises(VikunjaRefError, match="Undeclared label"):
        vikunja_refs.label_id("f:99-nonexistent", "kent")


def test_label_id_wrong_owner_token_raises() -> None:
    # Labels are per-token (#715): resolving a kent label under another token
    # must fail loud, not silently cross namespaces. Uses the shipped registry.
    with pytest.raises(VikunjaRefError, match="per-token"):
        vikunja_refs.label_id("f:3-edge", "felix-bot")


# ---------------------------------------------------------------------------
# Validator governs the new entries and stays green
# ---------------------------------------------------------------------------


def _kinds(findings: list[ValidationFinding]) -> list[str]:
    return [f.kind for f in findings]


def test_validate_clean_when_taxonomy_matches_live() -> None:
    # With the reconciled taxonomy declared (labels-only registry), validate()
    # is clean when live Vikunja returns those exact ids in the kent namespace
    # (the #715 steady state). No drift, no unprovisioned findings.
    vikunja_refs.set_registry_for_test(
        _registry_with(
            [_label_entry(name, id_) for name, id_ in TAXONOMY_LABEL_IDS.items()]
        )
    )
    live = [{"id": id_, "title": name} for name, id_ in TAXONOMY_LABEL_IDS.items()]
    findings = validate([], {"kent": live})
    assert findings == []


def test_validate_flags_id_drift_against_live() -> None:
    # If live Vikunja moves a taxonomy label's id, validate() surfaces id_drift
    # (the #743 regression guard) rather than silently accepting the mismatch.
    vikunja_refs.set_registry_for_test(
        _registry_with(
            [_label_entry(name, id_) for name, id_ in TAXONOMY_LABEL_IDS.items()]
        )
    )
    live = [{"id": id_, "title": name} for name, id_ in TAXONOMY_LABEL_IDS.items()]
    live[0]["id"] = 999  # f:1-flow moved off its declared id 18
    findings = validate([], {"kent": live})
    assert _kinds(findings) == ["id_drift"]
    assert findings[0].name == "f:1-flow"


def test_validate_declarations_clean_on_shipped_registry() -> None:
    # The committed registry has no duplicate ids -> declaration gate is green.
    assert validate_declarations() == []


def test_validate_declarations_detects_duplicate_label_id() -> None:
    # Two distinct label names claiming the same provisioned id in one token
    # namespace is a mis-routing hazard the gate must catch.
    vikunja_refs.set_registry_for_test(
        _registry_with(
            [_label_entry("q:do", 30), _label_entry("q:schedule", 30)]
        )
    )
    findings = validate_declarations()
    assert _kinds(findings) == ["duplicate_id"]
    assert findings[0].ref_type == "label"
    assert "q:do" in findings[0].name and "q:schedule" in findings[0].name


def test_validate_declarations_ignores_duplicate_nulls() -> None:
    # Unprovisioned (value:null) labels cannot collide — a not-yet-known id is
    # not a duplicate. The gate must not false-positive on null placeholders.
    vikunja_refs.set_registry_for_test(
        _registry_with(
            [_label_entry("a:pending", None), _label_entry("b:pending", None)]
        )
    )
    assert validate_declarations() == []


def test_validate_declarations_separates_token_namespaces() -> None:
    # The same id under two different tokens is NOT a collision (per-token id
    # spaces, #715).
    vikunja_refs.set_registry_for_test(
        _registry_with(
            [
                {"name": "a:label", "selector": {"kind": "label", "value": 5},
                 "title": "a", "owner_token": "kent"},
                {"name": "b:label", "selector": {"kind": "label", "value": 5},
                 "title": "b", "owner_token": "felix-bot"},
            ]
        )
    )
    assert validate_declarations() == []


def test_declaration_gate_cli_exits_zero_on_shipped_registry() -> None:
    # `python3 -m scripts.common.vikunja_refs_validate` must exit 0 on the
    # committed registry (no duplicate ids).
    assert main([]) == 0
