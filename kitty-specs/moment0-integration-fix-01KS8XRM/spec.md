# Spec: Fix Moment 0 wiring — integrate at signals adapter

**Mission**: `moment0-integration-fix-01KS8XRM`
**Mission ID**: `01KS8XRMC0EQZ8HCJ52GXCJ226`
**Source**: GitHub issue [kentonium3/kg-automation#391](https://github.com/kentonium3/kg-automation/issues/391)
**Risk tier**: Tier 3 — Logic / Workflow (standard)
**Generated**: 2026-05-22

## Overview

Mission `drift-event-auto-resolution-01KS8J32` (#362, mission_number=47, commit `cdc91f6`) deployed but its Moment 0 LLM integration is dead code at runtime. The systemd service `felix-doc-auditor.service` runs `scripts/doc_audit/run.py`, which processes drift events via `scripts/doc_audit/signals/drift_event.py::DriftEventSignalSource.commit()` — calling `file_doc_audit_issue()` directly and bypassing everything WP04 wired into `scripts/doc_audit/helpers/handle_drift_events.py::process_events()`.

This mission re-points the integration to the correct entry point. To avoid recreating the DRY violation that agy caught on #362's WP04 cycle 1, the Moment 0 routing is extracted into a shared helper (`scripts/doc_audit/routing/drift_moment0.py`) and invoked from BOTH the cron path (via `signals/drift_event.py::commit()`) AND the library/CLI path (via `handle_drift_events.py::process_events()`).

The mission also closes the 13 `[doc-audit]` issues (#378-#390) that the broken pipeline re-filed when cutover_362 reset the cursor on 2026-05-22T22:28.

## User Scenarios & Testing

### Primary user

Kent (operator) runs the doc-audit pipeline via the hourly systemd timer `felix-doc-auditor.timer`. The deployed code path is `run.py` -> `signals/drift_event.py::commit()`. The fix must take effect at this path; the standalone CLI surface (`handle_drift_events.py`) is secondary but must remain consistent.

### Acceptance scenarios

#### Scenario A — Cron tick processes a drift event via Moment 0

- **Given**: `[drift_interpretation].enabled = true` in `config.toml` (current deployed state)
- **When**: `felix-doc-auditor.service` fires (cron tick) and processes a mapped drift event
- **Then**: `signals/drift_event.py::commit()` calls `routing.drift_moment0.route_drift_event(...)`, which invokes `drift_interpretation.interpret()`
- **And**: the verdict is routed (PROPOSED_EDIT through tier_classification, JUDGMENT_REQUIRED files an issue with the LLM's question, NO_CHANGE_NEEDED auto-closes)
- **And**: a row is appended to `/data/services/security-monitor/logs/drift-events-ledger.jsonl`
- **And**: journalctl shows non-zero LLM token usage (`tokens=in:N(cache:0)/out:M`)

#### Scenario B — Library/CLI invocation produces identical verdict

- **Given**: `python3 -m doc_audit.helpers.handle_drift_events ...` is invoked directly (operator replay)
- **When**: it processes the same drift event as Scenario A
- **Then**: it calls the same `route_drift_event(...)` helper and produces an equivalent verdict + ledger entry
- **And**: no logic duplication — Moment 0 routing exists in exactly one place

#### Scenario C — Config flag disabled produces pre-#362 behavior

- **Given**: `[drift_interpretation].enabled = false`
- **When**: cron tick processes a mapped drift event
- **Then**: `commit()` calls `file_doc_audit_issue()` directly (current pre-fix behavior — byte-identical to pre-#362)
- **And**: no LLM tokens consumed; no ledger row written

#### Scenario D — Backlog cleanup of #378-390

- **Given**: 13 `[doc-audit]` issues (#378-390) were filed by the broken 2026-05-22T22:28 cutover replay
- **When**: the fix mission deploys and the post-deploy cleanup runs
- **Then**: those 13 issues are closed with a comment referencing #391 + this mission's commit
- **And**: no new operator triage burden on already-known drift events

#### Scenario E — Rollback via config flag

- **Given**: a defect surfaces post-deploy (e.g., spurious verdicts)
- **When**: the operator sets `[drift_interpretation].enabled = false`
- **Then**: the next cron tick falls back to pre-#362 behavior on the cron path
- **And**: the standalone CLI behaves identically (same config flag read by the shared helper)

### Edge cases

- Adapter's `commit()` is called for an already-passed line (cursor idempotency) -> no Moment 0 invocation; existing idempotent-skip behavior preserved
- Adapter's `commit()` is called inside the same tick for a line already committed -> no Moment 0 invocation; existing same-tick idempotency preserved
- `route_drift_event(...)` raises `DriftInterpretationError` (retry exhausted) -> fall back to `file_doc_audit_issue()` (pre-#362 path); ledger row appended with `verdict=RETRY_EXHAUSTED` (same FR-009 semantics as #362)
- Ledger append fails -> log error; do not fail the tick (side effect already completed)
- Existing `Doc audit:` commit-derived path is NOT touched — pipeline through `handle_audit_routing.py` continues unchanged

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | A new helper module `scripts/doc_audit/routing/drift_moment0.py` shall expose `route_drift_event(event, mapping, config, client, ledger_path, repo) -> RoutingOutcome` containing the Moment 0 + verdict-routing logic | Planned |
| FR-002 | `signals/drift_event.py::DriftEventSignalSource.commit()` shall invoke `route_drift_event(...)` when `config.drift_interpretation.enabled and mapping is not None`; otherwise it shall fall through to the existing `file_doc_audit_issue()` path (byte-identical pre-#362 behavior) | Planned |
| FR-003 | `handle_drift_events.py::process_events()` shall be refactored to call `route_drift_event(...)` instead of its inline Moment 0 logic; same observable behavior on its CLI surface | Planned |
| FR-004 | The Moment 0 routing logic shall live in exactly ONE place (the shared helper) — no inline duplicate in either `signals/drift_event.py` or `handle_drift_events.py` | Planned |
| FR-005 | `signals/drift_event.py::commit()` shall append a ledger row for every Moment 0-processed drift event (same `AuditLedgerEntry` shape as #362) | Planned |
| FR-006 | RETRY_EXHAUSTED fallback path in the cron driver shall match the existing #362 behavior: write a ledger row, then file the pre-#362 `[doc-audit]` issue with the diagnostic block | Planned |
| FR-007 | Cursor advancement semantics in `commit()` shall be preserved (same idempotency + drain rules as today) | Planned |
| FR-008 | A cleanup script `scripts/doc_audit/helpers/cleanup_391.py` (or operator-driven inline `gh` commands) shall bulk-close issues #378-390 with a comment referencing this mission | Planned |
| FR-009 | `JudgmentClient` instance shall be lazily constructed inside the shared helper or by the adapter on first use — one client per tick, not per event | Planned |
| FR-010 | If `[drift_interpretation].enabled = false`, the adapter shall NEVER instantiate a `JudgmentClient` (no API key file read, no Anthropic SDK construction) | Planned |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | Operator-triage rate over the 3-day window post-deploy: `count(JUDGMENT_REQUIRED) / count(*)` per ledger (inherits #362's NFR-001 metric) | ≤30% | Planned |
| NFR-002 | First post-deploy cron tick shows non-zero LLM token usage in journalctl (success-of-fix gate) | tokens.in > 0 and tokens.out > 0 | Planned |
| NFR-003 | Test coverage on new `routing/drift_moment0.py` module | ≥85% | Planned |
| NFR-004 | Test coverage on modified `signals/drift_event.py` (commit() Moment 0 path) | ≥85% | Planned |
| NFR-005 | No regression: existing `tests/doc_audit/` suite passes (currently 504+ tests + the WP-added ones) | 100% pass | Planned |
| NFR-006 | Per-tick latency P95 (including all events) | ≤90 seconds (inherits #362's NFR-006) | Planned |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | The existing `Doc audit:` (commit-derived) issue processing in `handle_audit_routing.py` shall not be modified | Locked |
| C-002 | The `audit.sh` detection layer + `drift-events.jsonl` format shall not be modified | Locked |
| C-003 | The existing `tier_classification`, `cross_file_implication`, `debt_body_generation`, `drift_interpretation`, `drift_ledger`, `drift_to_proposed_edit` modules shall not be modified (all reused as-is) | Locked |
| C-004 | The data_model.py `ProposedEdit` dataclass shall not be modified (the `drift_derived` change_type addition from #362 stays) | Locked |
| C-005 | No new third-party dependencies | Locked |
| C-006 | `signals/drift_event.py` cursor + drain logic shall be preserved exactly — only the side-effect call inside `commit()` changes | Locked |
| C-007 | Rollback path: config flag `[drift_interpretation].enabled = false` reverts both code paths to pre-#362 behavior identically | Locked |
| C-008 | The shared helper API shall match the #362 contracts (no contract changes); only the invocation site moves | Locked |
| C-009 | The mission shall close the 13 broken-pipeline artifacts (#378-390) as part of cutover; do not leave them in the operator queue | Locked |

## Success Criteria

1. **First post-deploy cron tick** shows non-zero LLM token usage (NFR-002).
2. **Ledger file** is created at `/data/services/security-monitor/logs/drift-events-ledger.jsonl` and accumulates rows.
3. **Triage rate** measurable + within ≤30% target over 3-day window.
4. **#378-390 closed** by cleanup step; no fresh operator burden.
5. **No regression** on the existing `Doc audit:` commit-derived path or on the standalone CLI surface.
6. **Rollback verified**: `enabled = false` reverts to pre-#362 behavior within one cron tick.

## Key Entities

### RoutingOutcome (reused from #362)

The shared helper's return value: `{outcome, tier_classification_outcome, github_issue_number}`. Same shape WP04 defined locally; promoted to the shared helper module.

### Shared helper signature

```python
def route_drift_event(
    *,
    event: dict[str, Any],
    mapping: Mapping,
    config: Config,
    client: JudgmentClient | None,
    ledger_path: Path,
    repo: str,
    event_id: str,
    timestamp_utc: str,
) -> RoutingOutcome:
    """Moment 0 + tier_classification + ledger append for one drift event.

    Side effects: LLM call, GitHub API call (issue/PR/auto-commit per verdict),
    ledger append. Returns outcome metadata for caller diagnostics.

    Raises DriftInterpretationError after retry exhaustion; caller
    handles the pre-#362 fallback path.
    """
```

## Assumptions

1. The existing `Config` dataclass already exposes `config.drift_interpretation.*` fields per #362 (verified by reading deployed `config.toml` — block is present).
2. `JudgmentClient` is the existing class from `scripts/doc_audit/judgment/client.py` (already imported by `drift_interpretation`).
3. `DriftEventSignalSource.__init__` will be extended to lazily create a `JudgmentClient` on first need (held as instance state for tick lifetime).
4. The Moment 0 helpers WP04 added to `handle_drift_events.py` (`_handle_moment0_event`, `_route_verdict`, `_apply_tier_a_edit`, `_file_tier_b_pending_approval`, `_file_judgment_issue`) move to `routing/drift_moment0.py` essentially unchanged — small adjustments for the new signature.
5. Cleanup of #378-390 can use a thin script analog to `cutover_362.py` (pattern reuse) OR direct `gh` invocation by the operator.

## Out of Scope

- New baselines or signal-to-doc mappings
- Architectural changes beyond the integration-point relocation
- De-duplication of repeat-drift across cron runs (existing behavior preserved)
- Shadow-mode rollout (cut over immediately — fix is straightforward; existing guardrails apply)

## Dependencies

- #362 (parent feature — code merged, integration broken)
- Mission `drift-event-auto-resolution-01KS8J32` (mission_number=47, commit `cdc91f6`)
- All modules introduced by #362: `drift_interpretation`, `drift_ledger`, `drift_to_proposed_edit`, `cutover_362` — used as-is

## Cross-References

- GitHub issue: kentonium3/kg-automation#391
- Parent feature: kentonium3/kg-automation#362
- Memory: `feedback_design_phase_research.md` (post-mortem lesson; sub-pattern "trace the entry point upward")
- Issues for cleanup: #378, #379, #380, #381, #382, #383, #384, #385, #386, #387, #388, #389, #390
