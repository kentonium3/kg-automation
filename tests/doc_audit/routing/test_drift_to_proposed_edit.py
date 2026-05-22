"""Unit tests for ``doc_audit.routing.drift_to_proposed_edit``.

Covers the translator that bridges Moment 0 (``drift_interpretation``)
and Moment 1 (``tier_classification``):

- Happy path: a valid ``PROPOSED_EDIT`` verdict at confidence ≥0.80 with
  a doc_path inside the allowed-set produces a ``ProposedEdit`` whose
  fields match the data-model E4 "Translator semantics" table exactly.
- Pre-condition violations: each of the documented invariants raises
  ``ValueError`` with a specific, debuggable message.
- Out-of-set rejection: the translator refuses any doc_path not in the
  allowed-set (defense-in-depth; mirrors
  ``drift_interpretation._parse_proposed_edit`` but is independent).
- evidence_source format: matches ``drift-event:{baseline}:{event_id}``.
- ``change_type`` constant: ``drift_derived`` (no aliasing to existing
  values).
- Allowed-set fallback: when ``allowed_doc_paths`` is None, the
  translator falls back to ``{t.path for t in context.doc_targets}``.

Independent of the Anthropic SDK / network — uses synthetic
``DriftVerdict`` and ``DriftInterpretationContext`` instances built from
the dataclass shapes exposed by ``drift_interpretation``.
"""
from __future__ import annotations

import pytest

from doc_audit.data_model import ProposedEdit
from doc_audit.judgment.drift_interpretation import (
    DocTarget,
    DriftInterpretationContext,
    DriftVerdict,
)
from doc_audit.routing import build as build_via_package
from doc_audit.routing.drift_to_proposed_edit import (
    CONFIDENCE_FLOOR,
    DEFAULT_INITIAL_TIER,
    DRIFT_DERIVED_CHANGE_TYPE,
    PROPOSED_EDIT_CONFIDENCE,
    build,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    event_id: str = "47:2026-05-22T03:00:07Z",
    baseline: str = "openclaw-cron",
    target_paths: tuple[str, ...] = (
        "docs/design/architecture/data/service-inventory.json",
    ),
) -> DriftInterpretationContext:
    """Build a minimal ``DriftInterpretationContext`` for tests."""
    targets = [
        DocTarget(
            path=path,
            contents="stub contents",
            truncated=False,
            truncation_strategy="full",
        )
        for path in target_paths
    ]
    return DriftInterpretationContext(
        event_id=event_id,
        timestamp_utc="2026-05-22T03:00:07Z",
        baseline=baseline,
        mapping_id="openclaw-cron-drift",
        mapping_rationale="Test mapping rationale.",
        diff="--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n",
        doc_targets=targets,
    )


def _make_proposed_edit_verdict(
    *,
    confidence: float = 0.85,
    doc_path: str = "docs/design/architecture/data/service-inventory.json",
    current_value: str = "1.2.3",
    proposed_value: str = "1.2.4",
    rationale: str = "Service version bumped in baseline.",
) -> DriftVerdict:
    """Build a valid PROPOSED_EDIT DriftVerdict."""
    return DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=confidence,
        rationale=rationale,
        proposed_edit={
            "doc_path": doc_path,
            "current_value": current_value,
            "proposed_value": proposed_value,
        },
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_returns_proposed_edit_with_all_seven_fields():
    """A valid PROPOSED_EDIT verdict at conf 0.85 produces a fully-populated
    ProposedEdit matching the data-model E4 "Translator semantics" table.
    """
    context = _make_context()
    verdict = _make_proposed_edit_verdict()

    result = build(
        verdict,
        context,
        allowed_doc_paths=[t.path for t in context.doc_targets],
    )

    assert isinstance(result, ProposedEdit)
    assert result.doc_path == "docs/design/architecture/data/service-inventory.json"
    assert result.change_type == DRIFT_DERIVED_CHANGE_TYPE == "drift_derived"
    assert result.current_value == "1.2.3"
    assert result.proposed_value == "1.2.4"
    assert result.evidence_source == "drift-event:openclaw-cron:47:2026-05-22T03:00:07Z"
    assert result.tier == DEFAULT_INITIAL_TIER == "tier_b"
    assert result.confidence == PROPOSED_EDIT_CONFIDENCE == "high"


def test_happy_path_at_exact_confidence_floor():
    """Confidence == 0.80 is accepted (>= floor, not strictly greater)."""
    context = _make_context()
    verdict = _make_proposed_edit_verdict(confidence=0.80)

    result = build(
        verdict,
        context,
        allowed_doc_paths=[t.path for t in context.doc_targets],
    )

    assert result.change_type == "drift_derived"


def test_build_reexported_from_routing_package():
    """``from doc_audit.routing import build`` resolves to the same callable."""
    assert build_via_package is build


# ---------------------------------------------------------------------------
# Pre-condition violations
# ---------------------------------------------------------------------------


def test_verdict_judgment_required_raises():
    """A JUDGMENT_REQUIRED verdict is rejected."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="JUDGMENT_REQUIRED",
        confidence=0.95,
        rationale="Cannot decide without operator input.",
        question="Should this dead reference be removed?",
    )

    with pytest.raises(ValueError) as exc:
        build(verdict, context)

    assert "PROPOSED_EDIT" in str(exc.value)
    assert "JUDGMENT_REQUIRED" in str(exc.value)


def test_verdict_no_change_needed_raises():
    """A NO_CHANGE_NEEDED verdict is rejected."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="NO_CHANGE_NEEDED",
        confidence=0.90,
        rationale="Doc already reflects this version.",
    )

    with pytest.raises(ValueError) as exc:
        build(verdict, context)

    assert "PROPOSED_EDIT" in str(exc.value)
    assert "NO_CHANGE_NEEDED" in str(exc.value)


def test_confidence_below_floor_raises():
    """Defense-in-depth: confidence < 0.80 raises even with PROPOSED_EDIT
    verdict (caller should have demoted already)."""
    context = _make_context()
    verdict = _make_proposed_edit_verdict(confidence=0.79)

    with pytest.raises(ValueError) as exc:
        build(
            verdict,
            context,
            allowed_doc_paths=[t.path for t in context.doc_targets],
        )

    msg = str(exc.value)
    assert "confidence" in msg
    assert "0.79" in msg
    # Hints at the upstream-demotion contract.
    assert "JUDGMENT_REQUIRED" in msg or "demote" in msg.lower()


def test_confidence_at_floor_boundary_minus_epsilon_raises():
    """Just below the floor (0.7999...) is rejected."""
    context = _make_context()
    verdict = _make_proposed_edit_verdict(confidence=CONFIDENCE_FLOOR - 0.0001)

    with pytest.raises(ValueError):
        build(
            verdict,
            context,
            allowed_doc_paths=[t.path for t in context.doc_targets],
        )


def test_proposed_edit_is_none_raises():
    """PROPOSED_EDIT verdict with proposed_edit=None violates the
    contract and is rejected."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.90,
        rationale="Service version bump.",
        proposed_edit=None,
    )

    with pytest.raises(ValueError) as exc:
        build(verdict, context)

    assert "proposed_edit" in str(exc.value)


def test_doc_path_empty_string_raises():
    """Empty doc_path is rejected."""
    context = _make_context()
    verdict = _make_proposed_edit_verdict(doc_path="")

    with pytest.raises(ValueError) as exc:
        build(verdict, context, allowed_doc_paths=["any/path.json"])

    assert "doc_path" in str(exc.value)


def test_doc_path_missing_key_raises():
    """proposed_edit dict missing the doc_path key is rejected."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.85,
        rationale="Service version bump.",
        proposed_edit={
            "current_value": "1.2.3",
            "proposed_value": "1.2.4",
        },
    )

    with pytest.raises(ValueError) as exc:
        build(verdict, context)

    assert "doc_path" in str(exc.value)


def test_doc_path_not_in_allowed_set_raises():
    """Out-of-set doc_path is rejected with an explicit message."""
    context = _make_context(
        target_paths=("docs/design/architecture/data/service-inventory.json",),
    )
    verdict = _make_proposed_edit_verdict(
        doc_path="docs/design/architecture/data/other-doc.json",
    )

    with pytest.raises(ValueError) as exc:
        build(
            verdict,
            context,
            allowed_doc_paths=[t.path for t in context.doc_targets],
        )

    msg = str(exc.value)
    assert "out-of-set" in msg
    assert "other-doc.json" in msg


def test_doc_path_not_in_explicit_allowlist_raises():
    """An explicit allowed_doc_paths list narrower than the context's
    targets is honored — out-of-list rejection wins even when the path
    appears in context.doc_targets."""
    context = _make_context(
        target_paths=(
            "docs/a.json",
            "docs/b.json",
        ),
    )
    verdict = _make_proposed_edit_verdict(doc_path="docs/b.json")

    with pytest.raises(ValueError) as exc:
        build(verdict, context, allowed_doc_paths=["docs/a.json"])

    assert "out-of-set" in str(exc.value)


def test_current_value_not_string_raises():
    """Non-string current_value is rejected with a type-named error."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.85,
        rationale="Service version bump.",
        proposed_edit={
            "doc_path": "docs/design/architecture/data/service-inventory.json",
            "current_value": 12345,
            "proposed_value": "1.2.4",
        },
    )

    with pytest.raises(ValueError) as exc:
        build(
            verdict,
            context,
            allowed_doc_paths=[t.path for t in context.doc_targets],
        )

    assert "current_value" in str(exc.value)


def test_proposed_value_not_string_raises():
    """Non-string proposed_value is rejected with a type-named error."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.85,
        rationale="Service version bump.",
        proposed_edit={
            "doc_path": "docs/design/architecture/data/service-inventory.json",
            "current_value": "1.2.3",
            "proposed_value": None,
        },
    )

    with pytest.raises(ValueError) as exc:
        build(
            verdict,
            context,
            allowed_doc_paths=[t.path for t in context.doc_targets],
        )

    assert "proposed_value" in str(exc.value)


# ---------------------------------------------------------------------------
# Allowed-set fallback to context.doc_targets
# ---------------------------------------------------------------------------


def test_allowed_paths_defaults_to_context_doc_targets():
    """When allowed_doc_paths is None, the translator uses
    context.doc_targets paths as the allowed-set."""
    context = _make_context(
        target_paths=(
            "docs/a.json",
            "docs/b.json",
        ),
    )
    verdict = _make_proposed_edit_verdict(doc_path="docs/b.json")

    result = build(verdict, context)  # allowed_doc_paths omitted

    assert result.doc_path == "docs/b.json"
    assert result.change_type == "drift_derived"


def test_allowed_paths_none_rejects_out_of_context_targets():
    """When allowed_doc_paths is None and doc_path is NOT in context.doc_targets,
    rejection still fires."""
    context = _make_context(target_paths=("docs/a.json",))
    verdict = _make_proposed_edit_verdict(doc_path="docs/elsewhere.json")

    with pytest.raises(ValueError) as exc:
        build(verdict, context)

    assert "out-of-set" in str(exc.value)


# ---------------------------------------------------------------------------
# evidence_source format
# ---------------------------------------------------------------------------


def test_evidence_source_format():
    """evidence_source MUST match ``drift-event:{baseline}:{event_id}``."""
    context = _make_context(
        event_id="123:2026-05-22T12:34:56Z",
        baseline="openclaw-cron",
    )
    verdict = _make_proposed_edit_verdict()

    result = build(
        verdict,
        context,
        allowed_doc_paths=[t.path for t in context.doc_targets],
    )

    assert result.evidence_source == "drift-event:openclaw-cron:123:2026-05-22T12:34:56Z"


def test_evidence_source_with_alternate_baseline():
    """evidence_source carries whatever baseline the context exposes."""
    context = _make_context(baseline="systemd-units")
    verdict = _make_proposed_edit_verdict()

    result = build(
        verdict,
        context,
        allowed_doc_paths=[t.path for t in context.doc_targets],
    )

    assert result.evidence_source.startswith("drift-event:systemd-units:")


# ---------------------------------------------------------------------------
# Empty-string current/proposed values are accepted (per spec)
# ---------------------------------------------------------------------------


def test_empty_string_current_and_proposed_values_accepted():
    """Per T015 spec: current_value and proposed_value may be empty strings
    in extreme cases — the translator must accept them."""
    context = _make_context()
    verdict = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.85,
        rationale="Removing a stale field that had no value.",
        proposed_edit={
            "doc_path": "docs/design/architecture/data/service-inventory.json",
            "current_value": "",
            "proposed_value": "",
        },
    )

    result = build(
        verdict,
        context,
        allowed_doc_paths=[t.path for t in context.doc_targets],
    )

    assert result.current_value == ""
    assert result.proposed_value == ""
    assert result.change_type == "drift_derived"
