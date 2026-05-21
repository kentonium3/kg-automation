"""Routing wrapper around ``helpers/handle_audit_routing.py``.

Per spec FR-005 / FR-006 / FR-007 / FR-009, the driver hands a
fully-judged audit (the originating ``AuditIssue`` plus the
:class:`ProposedEdit` / :class:`DebtIssue` partitions produced
upstream) to this module, which:

1. Serializes the audit state into the JSON shape the lifted
   helper expects (see ``handle_audit_routing.py`` docstring,
   §"Input JSON shape" — top-level keys ``audit_issue_number``,
   ``commit_sha``, ``areas``, ``proposals``, ``debt_issues_filed``,
   ``missing_artifact_issues_filed``).
2. Writes the serialized state to a tempfile.
3. Invokes :func:`doc_audit.helpers.handle_audit_routing.route_audit_decision`
   to actually apply edits, commit, file the pending-approval issue
   (when any proposal lands outside the helper's
   ``AUTO_APPLY_CHANGE_TYPES`` allowlist), post the summary, and
   close the originating audit.
4. Cleans up the tempfile via ``try/finally``, even on error.

Contract cross-references:
  - Helper docstring §"Input JSON shape" (the ground truth for the
    JSON contract — see file header in
    ``scripts/doc_audit/helpers/handle_audit_routing.py``).
  - This mission's data-model E-002 (``AuditIssue``), E-004
    (``ProposedEdit``), E-006 (``DebtIssue``).
  - Mission #343 WP01 lift: ``RoutingResult`` is the structured
    return shape the helper provides.

change_type vocabulary note
---------------------------
The helper's auto-apply allowlist
(``AUTO_APPLY_CHANGE_TYPES``) uses a different surface vocabulary
than this mission's :class:`ProposedEdit.change_type` enum (see
``data-model.md`` E-004 §"Field constraints"). The mission uses
SKILL.md §4.1 names (e.g. ``frontmatter_field_bump``,
``service_version``, ``file_path_rename``), while the helper uses
the auto-apply mission's vocabulary (e.g. ``frontmatter_date``,
``version_bump``, ``path_rename``). :data:`CHANGE_TYPE_MAP` below
translates the mission vocabulary to the helper vocabulary so the
auto-apply partition lands in the correct allowlist bucket. Edits
without a mapping are emitted with their original ``change_type``
verbatim, which routes them into the helper's "gated" partition
(filed as a pending-approval issue) — exactly the right behavior
for a value the helper does not know how to auto-apply.

TODO(mission #343 followup): unify the change_type vocabulary
between this mission and the auto-apply helper. The mapping table
below is a stopgap until both sides agree on a single canonical
set.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from doc_audit.config import Config
from doc_audit.data_model import AuditIssue, DebtIssue, ProposedEdit
from doc_audit.helpers.handle_audit_routing import (
    RoutingResult,
    route_audit_decision,
)

__all__ = ["RoutingResult", "apply"]


# ---------------------------------------------------------------------------
# Change-type vocabulary bridge (mission #343 / 01KS2XNX → helper #259 / 01KRG1BG)
# ---------------------------------------------------------------------------

# Maps THIS mission's `ProposedEdit.change_type` values (SKILL.md §4.1
# #1-7) to the helper's `AUTO_APPLY_CHANGE_TYPES` allowlist values.
# Any mission `change_type` not present here flows through verbatim —
# the helper's partition routine will treat it as "gated" and file a
# pending-approval issue.
CHANGE_TYPE_MAP: dict[str, str] = {
    # SKILL.md §4.1 #1 — frontmatter `last_validated` / similar date fields
    "frontmatter_field_bump": "frontmatter_date",
    # SKILL.md §4.1 #2 — frontmatter `updated_by` field
    # (no direct helper allowlist counterpart — the helper has a single
    # `frontmatter_date` bucket; for now alias to the same since the
    # change shape — single value replacement in frontmatter — is identical)
    "frontmatter_updated_by": "frontmatter_date",
    # SKILL.md §4.1 #3 — service version string
    "service_version": "version_bump",
    # SKILL.md §4.1 #4 — file path rename (global substitution)
    "file_path_rename": "path_rename",
    # SKILL.md §4.1 #5 — dead reference removal
    "dead_reference_removal": "dead_ref_removal",
    # SKILL.md §4.1 #6 — agent registry add
    "agent_registry_add": "registry_entry_add",
    # SKILL.md §4.1 #7 — autonomy level update
    "autonomy_level_update": "registry_autonomy_update",
}


def _translate_change_type(mission_change_type: str) -> str:
    """Translate a mission `change_type` to the helper's vocabulary.

    Falls through verbatim when the mission value has no mapping (the
    helper will then treat it as gated rather than auto-apply, which
    is the safe default).
    """
    return CHANGE_TYPE_MAP.get(mission_change_type, mission_change_type)


# ---------------------------------------------------------------------------
# Audit-state JSON construction
# ---------------------------------------------------------------------------


def _build_audit_state(
    audit: AuditIssue,
    proposed_edits: list[ProposedEdit],
    debt_issues: list[DebtIssue],
    missing_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct the audit-state JSON in the shape the helper expects.

    The helper's REQUIRED_TOP_KEYS contract (see
    ``handle_audit_routing.py`` for the canonical list):

    - ``audit_issue_number`` (int)
    - ``commit_sha`` (str)
    - ``areas`` (list[str])
    - ``proposals`` (list[dict] with required keys ``doc_path``,
      ``change_type``, ``current_value``, ``proposed_value``,
      ``evidence_source``, ``confidence``)
    - ``debt_issues_filed`` (list[int]) — issue numbers already filed
    - ``missing_artifact_issues_filed`` (list[int]) — issue numbers
      already filed

    Mapping notes (mission entity → helper field):
    - ``AuditIssue.issue_number`` → ``audit_issue_number``
    - ``AuditIssue.triggering_sha`` → ``commit_sha`` (empty string when
      ``is_weekly=True``; weekly audits have no triggering commit per
      data-model E-002 §"Invariants").
    - ``AuditIssue.area_labels`` → ``areas``
    - ``ProposedEdit.change_type`` → ``change_type`` (translated via
      :func:`_translate_change_type`).
    - ``ProposedEdit.{doc_path, current_value, proposed_value,
      evidence_source, confidence}`` → same-named helper keys (verbatim).
    - ``ProposedEdit.tier`` → not consumed by the helper (the helper
      partitions by ``change_type`` against its own allowlist, not by
      this mission's tier classification).
    - ``DebtIssue`` instances → caller is responsible for translating
      to issue numbers; this function consumes ``debt_issues`` purely
      as a typed container and emits an empty list when the caller has
      no numbers yet.

    Because :class:`DebtIssue` carries no GH issue-number field (the
    debt issue is filed elsewhere in the driver's pipeline), the
    ``debt_issues_filed`` and ``missing_artifact_issues_filed`` lists
    are populated from the ``missing_artifacts`` parameter when the
    caller has already filed them. The signature accepts
    ``debt_issues`` as a typed list to enforce the data-flow contract
    and lock in a place to add the issue-number wiring later (when
    debt filing moves into the driver). Today, only the explicit
    ``missing_artifacts`` list of ``{"issue_number": int, "kind":
    "debt"|"missing"}`` dicts is consulted to populate the helper's
    pre-filed buckets.

    TODO(mission #343 followup): once debt-filing lands in the driver
    and :class:`DebtIssue` carries a GH ``issue_number`` field, lift
    that here so callers don't have to pass a parallel
    ``missing_artifacts`` list.
    """
    # commit_sha — required by the helper. For weekly audits with no
    # triggering commit, fall back to "" (helper validates type only,
    # not non-empty).
    commit_sha = audit.triggering_sha or ""

    proposals_json: list[dict[str, Any]] = []
    for edit in proposed_edits:
        proposals_json.append(
            {
                "doc_path": edit.doc_path,
                "change_type": _translate_change_type(edit.change_type),
                "current_value": edit.current_value,
                "proposed_value": edit.proposed_value,
                "evidence_source": edit.evidence_source,
                "confidence": edit.confidence,
            }
        )

    debt_filed: list[int] = []
    missing_filed: list[int] = []
    for entry in missing_artifacts:
        kind = entry.get("kind")
        number = entry.get("issue_number")
        if not isinstance(number, int):
            continue
        if kind == "debt":
            debt_filed.append(number)
        elif kind == "missing":
            missing_filed.append(number)

    return {
        "audit_issue_number": int(audit.issue_number),
        "commit_sha": commit_sha,
        "areas": list(audit.area_labels),
        "proposals": proposals_json,
        "debt_issues_filed": debt_filed,
        "missing_artifact_issues_filed": missing_filed,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply(
    config: Config,
    audit: AuditIssue,
    proposed_edits: list[ProposedEdit],
    debt_issues: list[DebtIssue],
    missing_artifacts: list[dict[str, Any]],
) -> RoutingResult:
    """Execute the routing decision for one audit's outcomes.

    Constructs the audit-state JSON expected by
    :func:`route_audit_decision`, writes it to a tempfile, and invokes
    the library entry point. The tempfile is cleaned up in a
    ``finally`` block so partial state is never left on disk.

    Args:
        config: Driver :class:`Config`. Currently unused by this
            function (the helper resolves repo-root + ``gh``/``git``
            via its own argv/env), but accepted on the public
            signature for forward-compat with future config-driven
            knobs (e.g., bot identity, branch).
        audit: The originating :class:`AuditIssue` (E-002).
        proposed_edits: All :class:`ProposedEdit` instances (E-004)
            that survived the tier-classification pass and are ready
            for routing. Tier A → applied + committed; Tier B → gated
            into a pending-approval issue. The helper partitions by
            ``change_type`` against its own allowlist, not by mission
            ``tier`` — see the change_type vocabulary note in the
            module docstring.
        debt_issues: All :class:`DebtIssue` instances (E-006) the
            driver has already filed for this audit. Typed for
            forward-compat; today the helper consumes issue numbers,
            not entity instances. Pass an empty list when no debt
            issues are filed.
        missing_artifacts: A list of ``{"issue_number": int, "kind":
            "debt" | "missing"}`` dicts identifying already-filed
            debt and missing-artifact issues. Drives the helper's
            ``debt_issues_filed`` and ``missing_artifact_issues_filed``
            fields so the summary post and pending-approval body can
            cross-reference them.

    Returns:
        The :class:`RoutingResult` from the helper, carrying applied
        count, gated flag, pending-approval issue number, debt/missing
        issue numbers, errors, and suggested CLI exit code.
    """
    # ``config`` is accepted on the signature for future extension but
    # is presently unused by the routing wrapper (the helper resolves
    # repo-root + binaries on its own). Keep it on the signature so
    # the driver can pass it without churn.
    del config  # explicitly mark unused

    audit_state = _build_audit_state(
        audit=audit,
        proposed_edits=proposed_edits,
        debt_issues=debt_issues,
        missing_artifacts=missing_artifacts,
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="doc-audit-routing-",
            delete=False,
            encoding="utf-8",
        ) as f:
            json.dump(audit_state, f, indent=2)
            tmp_path = Path(f.name)
        return route_audit_decision(tmp_path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
