"""Data model for the felix-doc-auditor scripts-first driver.

Implements the 10 entities defined in
``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/data-model.md``
(E-001..E-010). Each entity is a Python ``@dataclass`` whose docstring
cites its data-model ID.

Immutability convention:
- Entities whose data-model table describes them as inputs / parsed
  records with invariants use ``frozen=True``.
- Entities that accumulate state across a tick (``TickResult``,
  ``AuditIssue``) are mutable.

The ``EditTier`` enum uses ``str, Enum`` so values serialize cleanly to
JSON without a custom encoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# E-005 — EditTier (defined first because other entities reference it)
# ---------------------------------------------------------------------------


class EditTier(str, Enum):
    """E-005 EditTier — Tier A / B / judgment classification.

    Returned by the ``tier_classification`` LLM call. Driver dispatches
    per value:
    - ``TIER_A`` — frontmatter-only, auto-commit per SKILL.md §4.1.a
    - ``TIER_B`` — content-touching, Level-1 gate per SKILL.md §4.1.b
    - ``JUDGMENT`` — not high confidence, file as docs-debt per §4.2
    """

    TIER_A = "tier_a"
    TIER_B = "tier_b"
    JUDGMENT = "judgment"


# ---------------------------------------------------------------------------
# E-001 — Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """E-001 Signal — normalized input to the driver.

    The unifying abstraction across signal sources. Each ``SignalSource``
    adapter produces zero or more ``Signal`` instances per tick.

    Priority ordering (lower = earlier):
    - ``pending_approval`` = 10
    - ``doc_audit`` = 20
    - ``weekly_doc_audit`` = 30
    - ``drift_event`` = 40
    """

    id: str
    source: str
    kind: str
    priority: int
    payload: dict
    created_utc: str


# ---------------------------------------------------------------------------
# E-004 — ProposedEdit (defined before PendingApproval which embeds it)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposedEdit:
    """E-004 ProposedEdit — single edit awaiting application.

    Embedded in ``PendingApproval.proposed_edits`` and (during fresh
    audit processing) in ``AuditIssue``-derived state.

    ``change_type`` is one of (per SKILL.md §4.1 #1-7):
    ``frontmatter_field_bump``, ``frontmatter_updated_by``,
    ``service_version``, ``file_path_rename``,
    ``dead_reference_removal``, ``agent_registry_add``,
    ``autonomy_level_update``.

    ``tier`` is one of ``tier_a`` / ``tier_b``. ``confidence`` is
    always ``high`` for a ``ProposedEdit`` — judgment edits become
    ``DebtIssue`` instead.
    """

    doc_path: str
    change_type: str
    current_value: str
    proposed_value: str
    evidence_source: str
    tier: str
    confidence: str


# ---------------------------------------------------------------------------
# E-002 — AuditIssue
# ---------------------------------------------------------------------------


@dataclass
class AuditIssue:
    """E-002 AuditIssue — parsed ``Doc audit:`` or ``Weekly doc audit —`` issue.

    Derived from a ``Signal`` of kind ``doc_audit`` / ``weekly_doc_audit``.
    Mutable because ``lock_acquired_at_utc`` is set as the audit moves
    through the tick lifecycle.

    Invariants:
    - ``triggering_sha`` is required when ``is_weekly`` is ``False``
      (extracted from title ``Doc audit: <sha> (<domains>)``).
    - Empty ``area_labels`` plus empty ``in_scope_docs`` means
      full-scope (typical for weekly audits per SKILL.md §3 step 2).
    """

    issue_number: int
    title: str
    is_weekly: bool
    triggering_sha: Optional[str]
    area_labels: list[str]
    in_scope_docs: list[str]
    lock_acquired_at_utc: Optional[str] = None


# ---------------------------------------------------------------------------
# E-003 — PendingApproval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingApproval:
    """E-003 PendingApproval — pending-approval issue with operator decision.

    Filed in prior ticks when an audit produced Tier-B proposals.
    Constructed in the current tick when a decision label is applied.

    Invariants:
    - ``decision`` is one of ``audit-approve``, ``audit-reject``,
      ``audit-skip``.
    - ``is_self_apply=True`` MUST NOT have its decision applied —
      triggers gate-violation handling per spec FR-008.
    - Decision processing happens BEFORE new-audit scanning in any
      tick (spec FR-004).
    """

    issue_number: int
    audit_issue_number: int
    proposed_edits: list[ProposedEdit]
    decision: str
    actor_login: str
    is_self_apply: bool
    area_labels: list[str]


# ---------------------------------------------------------------------------
# E-006 — DebtIssue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DebtIssue:
    """E-006 DebtIssue — docs-debt issue to be filed.

    Constructed when a finding qualifies as ``JUDGMENT`` per
    SKILL.md §4.2 OR is a missing-artifact per §6.

    Title format: ``Docs: <short title>``. For ``area/biz-ops``:
    ``Docs (biz-ops): <short title>`` (per SKILL.md §8).
    """

    title: str
    artifact_path: str
    gap_description: str
    area_labels: list[str]
    cross_references: list[str]
    draft_outline: str
    success_criteria: list[str]
    is_missing_artifact: bool


# ---------------------------------------------------------------------------
# E-007 — DriftEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftEvent:
    """E-007 DriftEvent — single entry from drift-events.jsonl.

    Direct mirror of the JSONL line shape emitted by ``audit.sh``.
    Consumed by ``DriftEventSignalSource`` via
    ``handle_drift_events.py``. Mapped events are filed as
    ``[doc-audit]`` GH issues (cursor advanced); unmapped events
    accumulate in ``unmapped-events.jsonl``.
    """

    timestamp: str
    source: str
    event_type: str
    baseline_name: str
    diff_b64: str


# ---------------------------------------------------------------------------
# E-008 — TickResult
# ---------------------------------------------------------------------------


@dataclass
class TickResult:
    """E-008 TickResult — internal driver outcome record.

    Aggregated as the driver processes the queue; serialized to
    ``TickSignal`` (E-009) at end-of-tick. Mutable because all the
    list/dict counters accumulate over the course of the tick.

    ``status`` is one of ``success``, ``partial``, ``failure``.

    ``judgment_calls`` shape:
        {"tier_classification": N,
         "debt_body_generation": N,
         "cross_file_implication": N}

    ``token_usage`` shape:
        {"input_tokens": N,
         "cache_hit_input_tokens": N,
         "output_tokens": N}
    (Sums across all LLM calls — NFR-001 measurement input.)
    """

    started_utc: str
    ended_utc: str
    status: str
    signals_seen: int
    signals_processed: int
    tier_a_commits: list[str] = field(default_factory=list)
    pending_approvals_filed: list[int] = field(default_factory=list)
    pending_approvals_applied: list[int] = field(default_factory=list)
    debt_filed: list[int] = field(default_factory=list)
    drift_events_consumed: int = 0
    errors: list[str] = field(default_factory=list)
    judgment_calls: dict = field(default_factory=dict)
    token_usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# E-009 — TickSignal (contract: contracts/tick-signal.contract.md schema v1.0)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickSignalTick:
    """Nested ``tick`` object inside ``TickSignal`` (E-009).

    Mirrors the ``tick.*`` fields in
    ``contracts/tick-signal.contract.md`` schema v1.0. Carries the
    per-tick processing counts and the issue/SHA lists that change
    detection consumers (operators, #327 felix-alert) read.
    """

    signals_seen: int
    signals_processed: int
    audits_processed: list[int]
    pending_approvals_applied: list[int]
    pending_approvals_filed: list[int]
    tier_a_commits: list[str]
    debt_filed: list[int]
    drift_events_consumed: int


@dataclass(frozen=True)
class TickSignalJudgment:
    """Nested ``judgment`` object inside ``TickSignal`` (E-009).

    Mirrors the ``judgment.*`` fields in
    ``contracts/tick-signal.contract.md`` schema v1.0. Carries the
    LLM-call counts and the token totals used for the NFR-001 cost
    measurement.
    """

    tier_classification_calls: int
    debt_body_generation_calls: int
    cross_file_implication_calls: int
    input_tokens: int
    cache_hit_input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class TickSignal:
    """E-009 TickSignal — JSON artifact at ``last-tick.json``.

    Structured signal consumed by operators (via ``cat``/``jq``) and
    future #327 ``felix-alert``. Derived from ``TickResult`` at end of
    tick and atomically written to
    ``/data/services/openclaw/felix-doc-auditor-driver/last-tick.json``.

    Shape mirrors ``contracts/tick-signal.contract.md`` schema v1.0
    exactly:
    - Top-level scalar/metadata fields per the table in §"Field
      constraints" of the contract.
    - Nested ``tick`` and ``judgment`` objects modeled as
      ``TickSignalTick`` / ``TickSignalJudgment`` for type safety.

    Invariants:
    - ``schema_version`` is the literal string ``"1.0"`` for this
      version of the contract. Bumped on breaking schema change.
    - ``exit_code`` is 0 (success), 2 (partial), or 1 (failure) and
      matches the process exit code.
    - ``status`` aligns with ``exit_code``: ``success`` ↔ 0,
      ``partial`` ↔ 2, ``failure`` ↔ 1.
    """

    schema_version: str
    timestamp_utc: str
    status: str
    exit_code: int
    driver_version: str
    duration_seconds: float
    host: str
    tick: "TickSignalTick"
    judgment: "TickSignalJudgment"
    errors: list[str]
    next_scheduled_tick_utc: str


# ---------------------------------------------------------------------------
# E-010 — ActivityLogEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityLogEntry:
    """E-010 ActivityLogEntry — one line per tick in the activity log.

    Preserved format per spec C-005. Written to
    ``/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md``
    (preserved location per spec C-005 Assumption 4).
    """

    timestamp_utc: str
    tick_outcome: str
    audits_processed: list[int]
    errors: list[str]
    driver_version: str


__all__ = [
    "Signal",
    "AuditIssue",
    "PendingApproval",
    "ProposedEdit",
    "EditTier",
    "DebtIssue",
    "DriftEvent",
    "TickResult",
    "TickSignal",
    "TickSignalTick",
    "TickSignalJudgment",
    "ActivityLogEntry",
]
