"""Unit tests for ``doc_audit.data_model`` (E-001..E-010).

WP02 / T010. Locks in the shape of each entity so subsequent WPs can
rely on them. Coverage target for ``data_model.py`` is >=90%.
"""

from __future__ import annotations

import dataclasses

import pytest

from doc_audit.data_model import (
    ActivityLogEntry,
    AuditIssue,
    DebtIssue,
    DriftEvent,
    EditTier,
    PendingApproval,
    ProposedEdit,
    Signal,
    TickResult,
    TickSignal,
    TickSignalJudgment,
    TickSignalTick,
)


# ---------------------------------------------------------------------------
# E-005 — EditTier
# ---------------------------------------------------------------------------


class TestEditTier:
    def test_values(self) -> None:
        assert EditTier.TIER_A.value == "tier_a"
        assert EditTier.TIER_B.value == "tier_b"
        assert EditTier.JUDGMENT.value == "judgment"

    def test_string_equality(self) -> None:
        # str-Enum subclassing means comparison to bare strings works.
        assert EditTier.TIER_A == "tier_a"
        assert EditTier.TIER_B == "tier_b"
        assert EditTier.JUDGMENT == "judgment"

    def test_membership(self) -> None:
        assert EditTier("tier_a") is EditTier.TIER_A
        assert EditTier("judgment") is EditTier.JUDGMENT

    def test_unknown_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            EditTier("totally_not_a_tier")


# ---------------------------------------------------------------------------
# E-001 — Signal
# ---------------------------------------------------------------------------


class TestSignal:
    def test_construct_gh_issue_signal(
        self, sample_signal_gh_issue: Signal
    ) -> None:
        assert sample_signal_gh_issue.id.startswith("gh-issue:")
        assert sample_signal_gh_issue.source == "gh_issue"
        assert sample_signal_gh_issue.kind == "doc_audit"
        assert sample_signal_gh_issue.priority == 20

    def test_construct_drift_event_signal(
        self, sample_signal_drift_event: Signal
    ) -> None:
        assert sample_signal_drift_event.source == "drift_event"
        assert sample_signal_drift_event.priority == 40

    def test_priority_ordering(self) -> None:
        """E-001 invariant: lower priority = earlier."""
        priorities = {
            "pending_approval": 10,
            "doc_audit": 20,
            "weekly_doc_audit": 30,
            "drift_event": 40,
        }
        ordered = sorted(priorities.values())
        assert ordered == [10, 20, 30, 40]
        assert priorities["pending_approval"] < priorities["doc_audit"]
        assert priorities["doc_audit"] < priorities["weekly_doc_audit"]
        assert priorities["weekly_doc_audit"] < priorities["drift_event"]

    def test_frozen(self) -> None:
        sig = Signal(
            id="x", source="gh_issue", kind="doc_audit",
            priority=20, payload={}, created_utc="2026-05-20T00:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            sig.priority = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E-002 — AuditIssue
# ---------------------------------------------------------------------------


class TestAuditIssue:
    def test_construct_targeted_audit(
        self, sample_audit_issue: AuditIssue
    ) -> None:
        assert sample_audit_issue.is_weekly is False
        assert sample_audit_issue.triggering_sha == "abc1234"
        assert sample_audit_issue.area_labels == ["area/felix-core"]

    def test_construct_weekly_audit(self) -> None:
        weekly = AuditIssue(
            issue_number=4300,
            title="Weekly doc audit — 2026-05-19",
            is_weekly=True,
            triggering_sha=None,
            area_labels=[],
            in_scope_docs=[],
        )
        assert weekly.is_weekly is True
        assert weekly.triggering_sha is None
        # Empty area_labels + empty in_scope_docs = full-scope marker.
        assert weekly.area_labels == []
        assert weekly.in_scope_docs == []

    def test_lock_acquired_mutable(
        self, sample_audit_issue: AuditIssue
    ) -> None:
        """AuditIssue is mutable so the lock timestamp can be set."""
        assert sample_audit_issue.lock_acquired_at_utc is None
        sample_audit_issue.lock_acquired_at_utc = "2026-05-20T16:01:00Z"
        assert sample_audit_issue.lock_acquired_at_utc == "2026-05-20T16:01:00Z"


# ---------------------------------------------------------------------------
# E-004 — ProposedEdit
# ---------------------------------------------------------------------------


class TestProposedEdit:
    def test_construct(self) -> None:
        edit = ProposedEdit(
            doc_path="docs/runbooks/openclaw-agent-setup.md",
            change_type="service_version",
            current_value="1.2.0",
            proposed_value="1.3.0",
            evidence_source="service-inventory.json:services[name=openclaw].version",
            tier="tier_b",
            confidence="high",
        )
        assert edit.change_type == "service_version"
        assert edit.confidence == "high"

    def test_frozen(self) -> None:
        edit = ProposedEdit(
            doc_path="x.md", change_type="frontmatter_field_bump",
            current_value="a", proposed_value="b",
            evidence_source="z", tier="tier_a", confidence="high",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            edit.tier = "tier_b"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E-003 — PendingApproval
# ---------------------------------------------------------------------------


class TestPendingApproval:
    def _edit(self) -> ProposedEdit:
        return ProposedEdit(
            doc_path="docs/runbooks/openclaw-agent-setup.md",
            change_type="service_version",
            current_value="1.2.0",
            proposed_value="1.3.0",
            evidence_source="service-inventory.json",
            tier="tier_b",
            confidence="high",
        )

    def test_operator_approval(self) -> None:
        approval = PendingApproval(
            issue_number=4260,
            audit_issue_number=4242,
            proposed_edits=[self._edit()],
            decision="audit-approve",
            actor_login="kentonium3",
            is_self_apply=False,
            area_labels=["area/felix-core"],
        )
        assert approval.decision == "audit-approve"
        assert approval.is_self_apply is False
        assert len(approval.proposed_edits) == 1

    def test_self_apply_invariant_is_detectable(self) -> None:
        """E-003 invariant: is_self_apply=True triggers gate violation.

        Per spec FR-008, a self-applied decision MUST NOT be processed.
        The invariant is *checked* by the routing layer; the dataclass
        merely records the actor verification result. This test
        confirms the field round-trips so the routing layer can read it.
        """
        gate_violation = PendingApproval(
            issue_number=4244,
            audit_issue_number=4220,
            proposed_edits=[self._edit()],
            decision="audit-approve",
            actor_login="kg-felix-bot",
            is_self_apply=True,
            area_labels=["area/felix-core"],
        )
        assert gate_violation.is_self_apply is True
        # Downstream code: `if pa.is_self_apply: raise GateViolation(...)`.

    def test_decision_values(self) -> None:
        """E-003 contract: decision ∈ {approve, reject, skip}."""
        for decision in ("audit-approve", "audit-reject", "audit-skip"):
            pa = PendingApproval(
                issue_number=1,
                audit_issue_number=2,
                proposed_edits=[],
                decision=decision,
                actor_login="kentonium3",
                is_self_apply=False,
                area_labels=[],
            )
            assert pa.decision == decision


# ---------------------------------------------------------------------------
# E-006 — DebtIssue
# ---------------------------------------------------------------------------


class TestDebtIssue:
    def test_construct(self) -> None:
        debt = DebtIssue(
            title="Docs: missing retention policy for inbox-pipeline activity log",
            artifact_path="docs/runbooks/inbox-pipeline.md",
            gap_description="Activity log retention is not documented.",
            area_labels=["area/felix-core"],
            cross_references=["#4242"],
            draft_outline="## Background\n...",
            success_criteria=[
                "Retention policy section added.",
                "Doc-domain-map updated.",
            ],
            is_missing_artifact=False,
        )
        assert debt.title.startswith("Docs:")
        assert len(debt.success_criteria) == 2

    def test_biz_ops_title_convention(self) -> None:
        """SKILL.md §8: area/biz-ops uses 'Docs (biz-ops):' prefix."""
        debt = DebtIssue(
            title="Docs (biz-ops): missing income recognition guidance",
            artifact_path="docs/runbooks/biz-ops/income.md",
            gap_description="Need recognition guidance.",
            area_labels=["area/biz-ops"],
            cross_references=["#4242"],
            draft_outline="## Background\n...",
            success_criteria=["Section added."],
            is_missing_artifact=True,
        )
        assert debt.title.startswith("Docs (biz-ops):")
        assert debt.is_missing_artifact is True


# ---------------------------------------------------------------------------
# E-007 — DriftEvent
# ---------------------------------------------------------------------------


class TestDriftEvent:
    def test_construct(self) -> None:
        event = DriftEvent(
            timestamp="2026-05-20T15:00:00Z",
            source="audit.sh",
            event_type="baseline_drift",
            baseline_name="openclaw-cron.txt",
            diff_b64="ZGlmZi1nb2VzLWhlcmU=",
        )
        assert event.baseline_name == "openclaw-cron.txt"
        assert event.event_type == "baseline_drift"


# ---------------------------------------------------------------------------
# E-008 — TickResult
# ---------------------------------------------------------------------------


class TestTickResult:
    def test_empty_outcome(self) -> None:
        result = TickResult(
            started_utc="2026-05-20T16:00:00Z",
            ended_utc="2026-05-20T16:00:30Z",
            status="success",
            signals_seen=0,
            signals_processed=0,
        )
        assert result.tier_a_commits == []
        assert result.pending_approvals_filed == []
        assert result.debt_filed == []
        assert result.errors == []
        assert result.judgment_calls == {}
        assert result.token_usage == {}

    def test_full_outcome(self) -> None:
        result = TickResult(
            started_utc="2026-05-20T16:00:00Z",
            ended_utc="2026-05-20T16:01:30Z",
            status="success",
            signals_seen=8,
            signals_processed=8,
            tier_a_commits=["abc1234", "def5678"],
            pending_approvals_filed=[4260],
            pending_approvals_applied=[4244],
            debt_filed=[4261],
            drift_events_consumed=3,
            errors=[],
            judgment_calls={
                "tier_classification": 4,
                "debt_body_generation": 1,
                "cross_file_implication": 2,
            },
            token_usage={
                "input_tokens": 3200,
                "cache_hit_input_tokens": 1800,
                "output_tokens": 480,
            },
        )
        assert result.signals_processed == 8
        assert result.judgment_calls["tier_classification"] == 4
        assert result.token_usage["output_tokens"] == 480

    def test_partial_outcome_accumulating(self) -> None:
        """TickResult is mutable so counters can accumulate."""
        result = TickResult(
            started_utc="2026-05-20T16:00:00Z",
            ended_utc="2026-05-20T16:00:45Z",
            status="partial",
            signals_seen=5,
            signals_processed=3,
        )
        result.errors.append("rate_limit_hit on tier_classification call 4")
        result.tier_a_commits.append("abc1234")
        assert len(result.errors) == 1
        assert "abc1234" in result.tier_a_commits


# ---------------------------------------------------------------------------
# E-009 — TickSignal (shape locked to contracts/tick-signal.contract.md v1.0)
# ---------------------------------------------------------------------------


def _empty_tick() -> TickSignalTick:
    return TickSignalTick(
        signals_seen=0,
        signals_processed=0,
        audits_processed=[],
        pending_approvals_applied=[],
        pending_approvals_filed=[],
        tier_a_commits=[],
        debt_filed=[],
        drift_events_consumed=0,
    )


def _empty_judgment() -> TickSignalJudgment:
    return TickSignalJudgment(
        tier_classification_calls=0,
        debt_body_generation_calls=0,
        cross_file_implication_calls=0,
        input_tokens=0,
        cache_hit_input_tokens=0,
        output_tokens=0,
    )


class TestTickSignalTick:
    def test_construct(self) -> None:
        tick = TickSignalTick(
            signals_seen=2,
            signals_processed=2,
            audits_processed=[320, 321],
            pending_approvals_applied=[],
            pending_approvals_filed=[],
            tier_a_commits=["abc1234"],
            debt_filed=[340],
            drift_events_consumed=0,
        )
        assert tick.audits_processed == [320, 321]
        assert tick.tier_a_commits == ["abc1234"]

    def test_frozen(self) -> None:
        tick = _empty_tick()
        with pytest.raises(dataclasses.FrozenInstanceError):
            tick.signals_seen = 99  # type: ignore[misc]


class TestTickSignalJudgment:
    def test_construct(self) -> None:
        judgment = TickSignalJudgment(
            tier_classification_calls=3,
            debt_body_generation_calls=1,
            cross_file_implication_calls=0,
            input_tokens=6420,
            cache_hit_input_tokens=4180,
            output_tokens=540,
        )
        assert judgment.input_tokens == 6420
        # Contract constraint: cache_hit_input_tokens ≤ input_tokens.
        assert judgment.cache_hit_input_tokens <= judgment.input_tokens

    def test_frozen(self) -> None:
        judgment = _empty_judgment()
        with pytest.raises(dataclasses.FrozenInstanceError):
            judgment.input_tokens = 1  # type: ignore[misc]


class TestTickSignal:
    """E-009 TickSignal — shape mirrors tick-signal.contract.md v1.0.

    Three outcomes covered per the contract's "Failure modes" table:
    - empty: status=success with zero work done
    - full: status=success with substantive counts (matches the
      example payload in the contract)
    - partial: status=partial with exit_code=2 and errors populated
    """

    def test_empty_success_outcome(self) -> None:
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:00:30Z",
            status="success",
            exit_code=0,
            driver_version="0.1.0",
            duration_seconds=0.4,
            host="office2",
            tick=_empty_tick(),
            judgment=_empty_judgment(),
            errors=[],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        assert signal.schema_version == "1.0"
        assert signal.status == "success"
        assert signal.exit_code == 0
        assert signal.tick.signals_seen == 0
        assert signal.judgment.tier_classification_calls == 0
        assert signal.errors == []

    def test_full_success_outcome(self) -> None:
        """Mirrors the example payload in tick-signal.contract.md."""
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:00:00Z",
            status="success",
            exit_code=0,
            driver_version="0.1.0",
            duration_seconds=7.3,
            host="office2",
            tick=TickSignalTick(
                signals_seen=2,
                signals_processed=2,
                audits_processed=[320, 321],
                pending_approvals_applied=[],
                pending_approvals_filed=[],
                tier_a_commits=["abc1234"],
                debt_filed=[340],
                drift_events_consumed=0,
            ),
            judgment=TickSignalJudgment(
                tier_classification_calls=3,
                debt_body_generation_calls=1,
                cross_file_implication_calls=0,
                input_tokens=6420,
                cache_hit_input_tokens=4180,
                output_tokens=540,
            ),
            errors=[],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        assert signal.driver_version == "0.1.0"
        assert signal.exit_code == 0
        assert signal.host == "office2"
        assert signal.tick.audits_processed == [320, 321]
        assert signal.tick.tier_a_commits == ["abc1234"]
        assert signal.tick.debt_filed == [340]
        assert signal.judgment.input_tokens == 6420
        assert signal.judgment.cache_hit_input_tokens == 4180
        assert signal.judgment.output_tokens == 540

    def test_partial_outcome_with_errors(self) -> None:
        """Partial outcome: exit_code=2, status=partial, errors populated."""
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:01:30Z",
            status="partial",
            exit_code=2,
            driver_version="0.1.0",
            duration_seconds=12.1,
            host="office2",
            tick=TickSignalTick(
                signals_seen=5,
                signals_processed=3,
                audits_processed=[400, 401, 402],
                pending_approvals_applied=[],
                pending_approvals_filed=[410],
                tier_a_commits=[],
                debt_filed=[],
                drift_events_consumed=0,
            ),
            judgment=TickSignalJudgment(
                tier_classification_calls=5,
                debt_body_generation_calls=0,
                cross_file_implication_calls=2,
                input_tokens=3200,
                cache_hit_input_tokens=1800,
                output_tokens=480,
            ),
            errors=[
                "rate_limit_hit on tier_classification call 4",
                "gh issue close failed for #402: transient timeout",
            ],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        assert signal.status == "partial"
        assert signal.exit_code == 2
        assert len(signal.errors) == 2
        assert signal.tick.signals_processed < signal.tick.signals_seen

    def test_failure_outcome(self) -> None:
        """Failure outcome: exit_code=1, status=failure, written by finally."""
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:00:02Z",
            status="failure",
            exit_code=1,
            driver_version="0.1.0",
            duration_seconds=1.7,
            host="office2",
            tick=_empty_tick(),
            judgment=_empty_judgment(),
            errors=["unrecoverable: missing API key file"],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        assert signal.status == "failure"
        assert signal.exit_code == 1
        assert signal.errors == ["unrecoverable: missing API key file"]

    def test_frozen(self) -> None:
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:00:00Z",
            status="success",
            exit_code=0,
            driver_version="0.1.0",
            duration_seconds=0.4,
            host="office2",
            tick=_empty_tick(),
            judgment=_empty_judgment(),
            errors=[],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            signal.status = "failure"  # type: ignore[misc]

    def test_nested_objects_are_frozen(self) -> None:
        """Nested ``tick`` / ``judgment`` are also immutable."""
        signal = TickSignal(
            schema_version="1.0",
            timestamp_utc="2026-05-20T16:00:00Z",
            status="success",
            exit_code=0,
            driver_version="0.1.0",
            duration_seconds=0.4,
            host="office2",
            tick=_empty_tick(),
            judgment=_empty_judgment(),
            errors=[],
            next_scheduled_tick_utc="2026-05-20T17:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            signal.tick.signals_seen = 5  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            signal.judgment.input_tokens = 9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E-010 — ActivityLogEntry
# ---------------------------------------------------------------------------


class TestActivityLogEntry:
    def test_construct(self) -> None:
        entry = ActivityLogEntry(
            timestamp_utc="2026-05-20T16:00:30Z",
            tick_outcome="success: 4/4 signals processed, 1 tier_a commit",
            audits_processed=[4242, 4250],
            errors=[],
            driver_version="0.1.0",
        )
        assert entry.audits_processed == [4242, 4250]
        assert entry.driver_version == "0.1.0"
