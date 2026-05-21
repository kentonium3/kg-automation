"""Unit tests for ``doc_audit.judgment.tier_classification``.

Verifies:
- Happy-path Tier A / Tier B / judgment parsing.
- Malformed JSON safe-default to ``EditTier.JUDGMENT``.
- Invalid tier value safe-default to ``EditTier.JUDGMENT``.
- **Guardrail short-circuit**: when ``guardrail_check_result ==
  "guardrailed"``, NO LLM call is made and the response is
  ``EditTier.JUDGMENT`` with the canonical rationale.
"""
from __future__ import annotations

import pytest

from doc_audit.data_model import EditTier, ProposedEdit
from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.tier_classification import (
    PROMPT_PATH,
    classify,
)


SAMPLE_EDIT = ProposedEdit(
    doc_path="docs/design/architecture/data/service-inventory.json",
    change_type="frontmatter_field_bump",
    current_value="2026-05-15",
    proposed_value="2026-05-20",
    evidence_source="audit issue #320 (commit a5d7af05)",
    tier="tier_a",
    confidence="high",
)


def test_prompt_path_exists() -> None:
    """The checked-in prompt template is reachable."""

    assert PROMPT_PATH.is_file(), f"missing prompt template: {PROMPT_PATH}"


def test_classify_tier_a(tmp_config, mock_anthropic) -> None:
    """A canonical tier_a response is parsed correctly."""

    mock_anthropic.messages.next_fixture = "tier_classification_tier_a"
    client = JudgmentClient(tmp_config)

    tier, rationale, response = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="last_updated: 2026-05-15",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.TIER_A
    assert "Frontmatter-only" in rationale
    assert response is not None
    assert response.input_tokens == 480


def test_classify_tier_b(tmp_config, mock_anthropic) -> None:
    """tier_b parsing."""

    mock_anthropic.messages.next_fixture = "tier_classification_tier_b"
    client = JudgmentClient(tmp_config)

    tier, rationale, response = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="version: v1.4.0",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.TIER_B
    assert "Touches narrative" in rationale
    assert response is not None


def test_classify_judgment(tmp_config, mock_anthropic) -> None:
    """judgment parsing."""

    mock_anthropic.messages.next_fixture = "tier_classification_judgment"
    client = JudgmentClient(tmp_config)

    tier, rationale, response = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "Author intent" in rationale
    assert response is not None


def test_classify_malformed_json_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Non-JSON response demotes to JUDGMENT with diagnostic rationale."""

    stub_anthropic_response(
        {
            "text": "this is just prose, not JSON",
            "usage": {
                "input_tokens": 400,
                "cache_read_input_tokens": 320,
                "output_tokens": 12,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, response = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "malformed" in rationale.lower()
    assert response is not None  # the call still happened


def test_classify_invalid_tier_value_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """An unknown tier enum demotes to JUDGMENT."""

    stub_anthropic_response(
        {
            "text": '{"tier": "wrong", "rationale": "LLM hallucinated"}',
            "usage": {
                "input_tokens": 420,
                "cache_read_input_tokens": 320,
                "output_tokens": 30,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, _ = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "invalid tier" in rationale.lower()


def test_classify_empty_response_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """An empty LLM response demotes to JUDGMENT."""

    stub_anthropic_response(
        {
            "text": "",
            "usage": {
                "input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 0,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, _ = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "empty" in rationale.lower()


def test_classify_non_object_response_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Valid JSON that is not an object demotes to JUDGMENT."""

    stub_anthropic_response(
        {
            "text": '["tier_a", "rationale"]',
            "usage": {
                "input_tokens": 400,
                "cache_read_input_tokens": 320,
                "output_tokens": 12,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, _ = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "not a JSON object" in rationale or "JUDGMENT" not in rationale


def test_classify_missing_rationale_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Missing ``rationale`` field demotes to ``EditTier.JUDGMENT``.

    Per contract Moment 1, the response shape requires BOTH ``tier``
    AND ``rationale``. A missing/blank ``rationale`` is a schema
    violation — we must NEVER preserve the LLM's auto-edit tier
    without a rationale. Safe default: demote to JUDGMENT and file
    docs-debt.
    """

    stub_anthropic_response(
        {
            "text": '{"tier": "tier_a"}',
            "usage": {
                "input_tokens": 400,
                "cache_read_input_tokens": 320,
                "output_tokens": 12,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, _ = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert rationale == "LLM response missing required field — demoted to judgment"


def test_classify_blank_rationale_falls_back(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """An empty/whitespace ``rationale`` value also demotes to JUDGMENT."""

    stub_anthropic_response(
        {
            "text": '{"tier": "tier_a", "rationale": "   "}',
            "usage": {
                "input_tokens": 400,
                "cache_read_input_tokens": 320,
                "output_tokens": 12,
            },
        }
    )
    client = JudgmentClient(tmp_config)

    tier, rationale, _ = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="not_guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert "missing required field" in rationale


# ---------------------------------------------------------------------------
# Guardrail short-circuit (defense in depth)
# ---------------------------------------------------------------------------


def test_classify_guardrailed_shortcircuits(tmp_config, mock_anthropic) -> None:
    """When guardrailed, NO LLM call is made and JUDGMENT is returned.

    This is the critical defense-in-depth invariant — the driver's
    deterministic path check should have caught this, but if it ever
    misses, this module catches it before the LLM is invoked.
    """

    client = JudgmentClient(tmp_config)

    tier, rationale, response = classify(
        client,
        proposed_edit=SAMPLE_EDIT,
        audit_area_labels=["area/felix-core"],
        doc_frontmatter_excerpt="...",
        guardrail_check_result="guardrailed",
    )

    assert tier == EditTier.JUDGMENT
    assert rationale == "guardrailed path — never auto-edited"
    assert response is None
    # The critical assertion: client was NEVER called.
    assert mock_anthropic.messages.calls == []
