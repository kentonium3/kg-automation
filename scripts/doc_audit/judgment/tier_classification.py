"""Tier-classification judgment moment.

Per spec FR-002 / SKILL.md §4 / contract Moment 1.

Contract: ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/judgment-prompts.contract.md``
Prompt: ``scripts/doc_audit/prompts/tier_classification.prompt.md``

Guardrail short-circuit (defense in depth)
------------------------------------------
The driver computes ``guardrail_check_result`` deterministically by
matching the doc path against SKILL.md §4.3. When the result is
``"guardrailed"``, this module returns ``EditTier.JUDGMENT`` WITHOUT
invoking the LLM. The client is never called, so no tokens are spent
and no rationale is sampled from the model.

This complements the deterministic driver check — even if the driver
ever fails to pre-filter a guardrailed path, this module's short-circuit
catches it.

Schema validation (safe default)
--------------------------------
On any of the following the module returns
``EditTier.JUDGMENT`` with a diagnostic rationale (per the contract's
"on parse failure or schema violation: log + demote" rule):

- Response is not valid JSON.
- ``tier`` field missing or not one of the three enum values.
- ``rationale`` field missing, non-string, or empty/whitespace.

The contract (Moment 1) requires BOTH ``tier`` AND ``rationale`` to be
present and non-empty. A missing/blank ``rationale`` is a schema
violation that demotes to ``EditTier.JUDGMENT`` — we never preserve
the LLM's auto-edit tier without a rationale.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from doc_audit.data_model import EditTier, ProposedEdit
from doc_audit.judgment._llm_response import _strip_code_fence
from doc_audit.judgment.client import JudgmentClient, JudgmentResponse


logger = logging.getLogger(__name__)


PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "tier_classification.prompt.md"
)


_GUARDRAIL_RATIONALE = "guardrailed path — never auto-edited"
_VALID_TIERS = {"tier_a", "tier_b", "judgment"}


def classify(
    client: JudgmentClient,
    proposed_edit: ProposedEdit,
    audit_area_labels: list[str],
    doc_frontmatter_excerpt: str,
    guardrail_check_result: str,
) -> tuple[EditTier, str, JudgmentResponse | None]:
    """Classify a proposed edit as Tier A / Tier B / judgment.

    Returns ``(tier, rationale, response_or_None)``. The third element
    is ``None`` when the guardrail short-circuit fires (no LLM call
    was made).

    The driver records LLM usage via the third element. When it is
    ``None`` the driver counts zero tokens for this call.
    """

    # Defense-in-depth: short-circuit guardrailed paths BEFORE the LLM
    # call so we never spend tokens (or risk an LLM verdict) on edits
    # the driver must never apply.
    if guardrail_check_result == "guardrailed":
        return EditTier.JUDGMENT, _GUARDRAIL_RATIONALE, None

    variable_section = _render_inputs(
        proposed_edit=proposed_edit,
        audit_area_labels=audit_area_labels,
        doc_frontmatter_excerpt=doc_frontmatter_excerpt,
        guardrail_check_result=guardrail_check_result,
    )

    response = client.call(PROMPT_PATH, variable_section)
    tier, rationale = _parse_response(
        response.content, doc_path=proposed_edit.doc_path
    )
    return tier, rationale, response


# ---------------------------------------------------------------------------
# Input rendering
# ---------------------------------------------------------------------------


def _render_inputs(
    *,
    proposed_edit: ProposedEdit,
    audit_area_labels: list[str],
    doc_frontmatter_excerpt: str,
    guardrail_check_result: str,
) -> str:
    """Render the per-call inputs section sent as the user message.

    The boilerplate is already in the cached system prompt; this
    section only carries the per-edit variables.
    """

    return (
        "## Proposed edit\n"
        f"- doc_path: {proposed_edit.doc_path}\n"
        f"- change_type: {proposed_edit.change_type}\n"
        f"- current_value: {proposed_edit.current_value}\n"
        f"- proposed_value: {proposed_edit.proposed_value}\n"
        f"- evidence_source: {proposed_edit.evidence_source}\n"
        "\n"
        "## Context\n"
        f"- audit_area_labels: {audit_area_labels}\n"
        f"- guardrail_check_result: {guardrail_check_result}\n"
        "\n"
        "## Doc frontmatter excerpt\n"
        f"{doc_frontmatter_excerpt}\n"
        "\n"
        "---\n"
        "\n"
        "Classify this edit. Return the JSON.\n"
    )


# ---------------------------------------------------------------------------
# Response parsing + schema validation
# ---------------------------------------------------------------------------


def _parse_response(content: str, *, doc_path: str) -> tuple[EditTier, str]:
    """Parse + validate the LLM response.

    On any parse error or schema violation, returns the safe default:
    ``(EditTier.JUDGMENT, "<diagnostic>")``.
    """

    text = content.strip()
    if not text:
        logger.warning(
            "tier_classification empty response for %s; demoting to judgment",
            doc_path,
        )
        return EditTier.JUDGMENT, "empty LLM response — demoted to judgment"

    try:
        parsed = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError as exc:
        logger.warning(
            "tier_classification non-JSON response for %s: %s",
            doc_path,
            exc,
        )
        return (
            EditTier.JUDGMENT,
            "malformed LLM JSON response — demoted to judgment",
        )

    if not isinstance(parsed, dict):
        logger.warning(
            "tier_classification JSON not an object for %s: %r",
            doc_path,
            parsed,
        )
        return (
            EditTier.JUDGMENT,
            "LLM response not a JSON object — demoted to judgment",
        )

    tier_value = parsed.get("tier")
    rationale = parsed.get("rationale")

    if tier_value not in _VALID_TIERS:
        logger.warning(
            "tier_classification invalid tier %r for %s; demoting",
            tier_value,
            doc_path,
        )
        return (
            EditTier.JUDGMENT,
            f"invalid tier value {tier_value!r} — demoted to judgment",
        )

    # Strict schema check (per contract Moment 1): rationale must be
    # present AND a non-empty string. Any violation demotes to JUDGMENT
    # — we NEVER preserve an auto-edit tier without a rationale.
    if not isinstance(rationale, str) or not rationale.strip():
        logger.warning(
            "tier_classification missing/blank rationale for %s; demoting to judgment",
            doc_path,
        )
        return (
            EditTier.JUDGMENT,
            "LLM response missing required field — demoted to judgment",
        )

    return EditTier(tier_value), rationale


__all__ = ["classify", "PROMPT_PATH"]
