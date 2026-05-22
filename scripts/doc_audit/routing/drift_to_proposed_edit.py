"""Translator: Moment 0 ``DriftVerdict`` → existing ``ProposedEdit`` dataclass.

Per spec FR-004 / contract
``kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/api.md``
(``drift_to_proposed_edit.build(...)``) and data-model E4.

This module is the thin glue between the Moment 0
``drift_interpretation`` judgment and the existing
``tier_classification`` (Moment 1) pipeline. It does **not** call any
LLM, write to the ledger, or touch GitHub. It validates a single
``DriftVerdict`` against the same pre-conditions the caller is expected
to have already enforced and constructs a ``ProposedEdit`` with
``change_type = "drift_derived"`` so downstream tier_classification can
operate on it without changes (C-003).

Defense-in-depth
----------------
The caller (``handle_drift_events.process_events``) is expected to:

- gate ``verdict == "PROPOSED_EDIT"`` AND ``confidence >= 0.80`` before
  calling ``build`` (low-confidence verdicts are demoted to
  ``JUDGMENT_REQUIRED`` inside ``drift_interpretation.interpret``);
- ensure ``verdict.proposed_edit["doc_path"]`` belongs to the input
  ``context.doc_targets`` set (already enforced by
  ``drift_interpretation._parse_proposed_edit``).

``build`` re-checks every one of those pre-conditions and raises
``ValueError`` with a specific message on violation. This is the second
line of defense: if the upstream gating regresses, the translator
refuses to construct a ``ProposedEdit`` that would carry an
unverifiable edit into the auto-apply pipeline.
"""

from __future__ import annotations

from typing import Optional

from doc_audit.data_model import ProposedEdit
from doc_audit.judgment.drift_interpretation import (
    DriftInterpretationContext,
    DriftVerdict,
)


# ---------------------------------------------------------------------------
# Module constants (per data-model E4 — Translator semantics table)
# ---------------------------------------------------------------------------

#: The new ``change_type`` value introduced by this mission. Documented
#: in ``ProposedEdit``'s docstring as the 8th value. ``tier_classification``
#: handles unknown values by falling through to JUDGMENT (the safe default
#: per the defense-in-depth contract), so no enum extension is required.
DRIFT_DERIVED_CHANGE_TYPE = "drift_derived"

#: Initial tier placeholder. ``tier_classification`` (Moment 1) reads the
#: proposed edit and assigns the actual tier per SKILL.md §4.1.
#: ``tier_b`` is the conservative initial value; tier_a auto-commits are
#: gated by tier_classification's own conservative rules.
DEFAULT_INITIAL_TIER = "tier_b"

#: ``ProposedEdit.confidence`` is always ``"high"`` per E-004's docstring
#: invariant — judgment edits become ``DebtIssue`` instead.
PROPOSED_EDIT_CONFIDENCE = "high"

#: Confidence floor below which a PROPOSED_EDIT verdict must have been
#: demoted to JUDGMENT_REQUIRED by ``drift_interpretation._demote_low_confidence``
#: (FR-005). Mirrored here for the defense-in-depth check.
CONFIDENCE_FLOOR = 0.80


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build(
    verdict: DriftVerdict,
    context: DriftInterpretationContext,
    *,
    allowed_doc_paths: Optional[list[str]] = None,
) -> ProposedEdit:
    """Translate a PROPOSED_EDIT ``DriftVerdict`` into a ``ProposedEdit``.

    Per contracts/api.md and data-model E4. Builds a ``ProposedEdit``
    that ``tier_classification`` (Moment 1) consumes unchanged (C-003).

    Args:
        verdict: ``DriftVerdict`` from ``drift_interpretation.interpret``.
            MUST satisfy:

            - ``verdict.verdict == "PROPOSED_EDIT"``
            - ``verdict.confidence >= 0.80``
            - ``verdict.proposed_edit`` is not None
            - ``verdict.proposed_edit["doc_path"]`` is a non-empty
              string in ``allowed_doc_paths`` (or, if
              ``allowed_doc_paths`` is None, in
              ``{t.path for t in context.doc_targets}``)
        context: the same ``DriftInterpretationContext`` that produced
            the verdict. Supplies ``baseline`` + ``event_id`` for
            ``evidence_source`` and ``doc_targets`` for the default
            allowed-paths set.
        allowed_doc_paths: optional explicit allowed-set. If ``None``,
            defaults to ``{t.path for t in context.doc_targets}``.
            Callers can pass an explicit list when they want to scope
            the translator to a narrower set than the full mapping
            targets (e.g., when running a focused replay).

    Returns:
        ``ProposedEdit`` with:

        - ``doc_path`` = ``verdict.proposed_edit["doc_path"]``
        - ``change_type`` = ``"drift_derived"``
        - ``current_value`` = ``verdict.proposed_edit["current_value"]``
        - ``proposed_value`` = ``verdict.proposed_edit["proposed_value"]``
        - ``evidence_source`` =
          ``f"drift-event:{context.baseline}:{context.event_id}"``
        - ``tier`` = ``"tier_b"`` (placeholder; tier_classification
          may reassign)
        - ``confidence`` = ``"high"``

    Raises:
        ValueError: if any pre-condition fails. The message names the
            failing pre-condition so the caller can debug without
            re-reading the source. This is defense-in-depth: the
            caller (``handle_drift_events``) is expected to have
            gated all of these.
    """
    if verdict.verdict != "PROPOSED_EDIT":
        raise ValueError(
            "drift_to_proposed_edit.build requires verdict.verdict == 'PROPOSED_EDIT' "
            f"(got {verdict.verdict!r})"
        )

    if verdict.confidence < CONFIDENCE_FLOOR:
        raise ValueError(
            "drift_to_proposed_edit.build requires confidence >= "
            f"{CONFIDENCE_FLOOR} (got {verdict.confidence!r}); "
            "caller should have demoted to JUDGMENT_REQUIRED"
        )

    proposed_edit = verdict.proposed_edit
    if proposed_edit is None:
        raise ValueError(
            "drift_to_proposed_edit.build requires verdict.proposed_edit is not None "
            "for PROPOSED_EDIT verdicts"
        )

    doc_path = proposed_edit.get("doc_path")
    if not isinstance(doc_path, str) or not doc_path:
        raise ValueError(
            "drift_to_proposed_edit.build requires proposed_edit['doc_path'] to be "
            f"a non-empty string (got {doc_path!r})"
        )

    # Resolve the allowed-set. Explicit ``allowed_doc_paths`` wins; otherwise
    # fall back to the context's targets so the translator is usable from
    # callers that don't synthesize a separate allowlist.
    if allowed_doc_paths is None:
        allowed_set = {t.path for t in context.doc_targets}
    else:
        allowed_set = set(allowed_doc_paths)

    if doc_path not in allowed_set:
        raise ValueError(
            "drift_to_proposed_edit.build rejected out-of-set doc_path: "
            f"{doc_path!r} not in {sorted(allowed_set)!r}"
        )

    current_value = proposed_edit.get("current_value")
    proposed_value = proposed_edit.get("proposed_value")
    if not isinstance(current_value, str):
        raise ValueError(
            "drift_to_proposed_edit.build requires proposed_edit['current_value'] "
            f"to be a string (got {type(current_value).__name__})"
        )
    if not isinstance(proposed_value, str):
        raise ValueError(
            "drift_to_proposed_edit.build requires proposed_edit['proposed_value'] "
            f"to be a string (got {type(proposed_value).__name__})"
        )

    evidence_source = f"drift-event:{context.baseline}:{context.event_id}"

    return ProposedEdit(
        doc_path=doc_path,
        change_type=DRIFT_DERIVED_CHANGE_TYPE,
        current_value=current_value,
        proposed_value=proposed_value,
        evidence_source=evidence_source,
        tier=DEFAULT_INITIAL_TIER,
        confidence=PROPOSED_EDIT_CONFIDENCE,
    )


__all__ = [
    "build",
    "DRIFT_DERIVED_CHANGE_TYPE",
    "DEFAULT_INITIAL_TIER",
    "PROPOSED_EDIT_CONFIDENCE",
    "CONFIDENCE_FLOOR",
]
