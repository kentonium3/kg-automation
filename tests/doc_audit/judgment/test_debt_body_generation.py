"""Unit tests for ``doc_audit.judgment.debt_body_generation``.

Verifies:
- A complete 6-section response round-trips unchanged.
- Missing sections are stubbed and surfaced via
  ``DebtBodyResult.stubbed_sections``.
- The originating audit number is injected as ``Refs #<N>`` when the
  LLM omits it.
- The prompt template file exists on disk.
"""
from __future__ import annotations

from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.debt_body_generation import (
    PROMPT_PATH,
    DebtBodyResult,
    generate,
)


COMPLETE_BODY = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
The runbook predates model tiering. The Choosing a Model section
lacks the Pinned vs Optimizable distinction.

## Area
- [x] area/felix-core

## Cross-references
- Refs #320 (originating audit)
- #135, #225

## Draft outline
Insert a new subsection "Choosing a Model Tier" between Choosing an
Agent Name and the verification checklist. Cover Pinned vs Optimizable,
when to choose each, and a worked example per tier.

## Success criteria
- [ ] New subsection appears in the runbook
- [ ] Both tiers have at least one named example
- [ ] AGENT-REGISTRY.md Model Assignment Policy is cross-linked
"""


MISSING_OUTLINE_BODY = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
The runbook predates model tiering.

## Area
- [x] area/felix-core

## Cross-references
- Refs #320 (originating audit)

## Success criteria
- [ ] New subsection appears in the runbook
"""


MISSING_AUDIT_REF_BODY = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
Missing model-tiering guidance in the runbook.

## Area
- [x] area/felix-core

## Cross-references
- See also #225

## Draft outline
Insert a subsection covering Pinned vs Optimizable tiers with worked
examples.

## Success criteria
- [ ] Subsection appears
- [ ] Examples present
"""


_USAGE = {
    "input_tokens": 720,
    "cache_read_input_tokens": 500,
    "output_tokens": 180,
}


def test_prompt_path_exists() -> None:
    """The checked-in prompt template is reachable."""

    assert PROMPT_PATH.is_file(), f"missing prompt template: {PROMPT_PATH}"


def test_generate_complete_body(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """A complete 6-section body round-trips unchanged."""

    stub_anthropic_response({"text": COMPLETE_BODY, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    result, response = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=["#135", "#225"],
    )

    assert isinstance(result, DebtBodyResult)
    assert result.stubbed_sections == []
    # All six headers appear in canonical order.
    for h in (
        "## Artifact",
        "## Gap description",
        "## Area",
        "## Cross-references",
        "## Draft outline",
        "## Success criteria",
    ):
        assert h in result.body
    # Audit ref preserved.
    assert "#320" in result.body
    assert response.input_tokens == 720


def test_generate_missing_section_is_stubbed(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """A missing Draft outline is stubbed and surfaced for the driver."""

    stub_anthropic_response({"text": MISSING_OUTLINE_BODY, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    assert "Draft outline" in result.stubbed_sections
    # The stub placeholder appears in the body.
    assert "LLM output was incomplete" in result.body
    # All headers still appear (driver gets a complete-looking body).
    assert "## Draft outline" in result.body
    assert "## Success criteria" in result.body


def test_generate_injects_missing_audit_ref(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """If LLM omits ``Refs #<N>``, the helper injects it before returning."""

    stub_anthropic_response(
        {"text": MISSING_AUDIT_REF_BODY, "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    # Body now contains Refs #320 even though the LLM omitted it.
    assert "Refs #320" in result.body
    # The pre-existing cross-reference is preserved.
    assert "#225" in result.body
    # Not stubbed — section was present (just missing the audit ref).
    assert "Cross-references" not in result.stubbed_sections


SUBSTRING_CONFLICT_BODY = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
Runbook lacks model-tiering guidance.

## Area
- [x] area/felix-core

## Cross-references
- See related work in #3200 and #3201

## Draft outline
Insert a subsection covering Pinned vs Optimizable tiers.

## Success criteria
- [ ] Subsection appears
"""


def test_inject_audit_ref_distinguishes_substring_match(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Regression: ``#3200`` must NOT satisfy the ``#320`` presence check.

    Without word-boundary matching the helper would silently skip
    injecting the originating-audit ``Refs #320`` backlink whenever the
    LLM happened to mention a longer issue number (e.g. ``#3200``,
    ``#3201``) whose digits start with the audit number. The debt issue
    would then lose its cross-reference to the audit that triggered it.
    """

    stub_anthropic_response(
        {"text": SUBSTRING_CONFLICT_BODY, "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    # The Refs backlink to the originating audit IS injected even though
    # the LLM body already contains "#3200" (which a substring check
    # would have falsely treated as "#320 is present").
    assert "Refs #320" in result.body
    # The pre-existing longer references are preserved verbatim.
    assert "#3200" in result.body
    assert "#3201" in result.body
    # Cross-references section was not stubbed (it had content).
    assert "Cross-references" not in result.stubbed_sections


def test_inject_audit_ref_skips_when_exact_match_present(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """When an exact-match ``#<N>`` is already present, no injection occurs.

    Pairs with ``test_inject_audit_ref_distinguishes_substring_match``
    to lock in both halves of the word-boundary contract.
    """

    body_with_exact_match = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
Runbook lacks model-tiering guidance.

## Area
- [x] area/felix-core

## Cross-references
- Refs #320 (originating audit)
- Also see #3200

## Draft outline
Insert a subsection.

## Success criteria
- [ ] Subsection appears
"""
    stub_anthropic_response(
        {"text": body_with_exact_match, "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    # Refs #320 appears exactly once — no duplicate injection.
    assert result.body.count("Refs #320") == 1


def test_generate_multiple_missing_sections_all_listed(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Multiple omissions all surface in ``stubbed_sections``."""

    truncated_body = """\
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
Runbook lacks model-tiering guidance.

## Cross-references
- Refs #320
"""
    stub_anthropic_response({"text": truncated_body, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    # Area, Draft outline, Success criteria all missing.
    stubbed = set(result.stubbed_sections)
    assert "Area" in stubbed
    assert "Draft outline" in stubbed
    assert "Success criteria" in stubbed


def test_generate_handles_empty_response(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Empty LLM response yields a fully stubbed body (no crash)."""

    stub_anthropic_response({"text": "", "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    result, _ = generate(
        client,
        artifact_path="docs/runbooks/openclaw-agent-setup.md",
        gap_description="Runbook lacks model-tiering guidance.",
        evidence_source="mission 021 plan",
        area_labels=["area/felix-core"],
        originating_audit_number=320,
        cross_references=[],
    )

    # All six sections stubbed.
    assert set(result.stubbed_sections) == {
        "Artifact",
        "Gap description",
        "Area",
        "Cross-references",
        "Draft outline",
        "Success criteria",
    }
    # Body still has all six H2s.
    for h in (
        "## Artifact",
        "## Gap description",
        "## Area",
        "## Cross-references",
        "## Draft outline",
        "## Success criteria",
    ):
        assert h in result.body
    # Audit ref still injected.
    assert "#320" in result.body
