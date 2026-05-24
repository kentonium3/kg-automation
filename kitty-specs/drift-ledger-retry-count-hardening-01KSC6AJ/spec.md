# Drift Ledger Retry Count Hardening

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ`
**Mission ID**: `01KSC6AJ2JK8N2NJT4QB6AB36Z`
**Type**: software-dev
**Target branch**: `main`
**Risk tier**: 3 — Logic / Workflow
**Source issue**: [#403](https://github.com/kentonium3/kg-automation/issues/403)

---

## Problem

The doc-audit driver crashes its own drift events. When a drift event exhausts the retry budget for `drift_interpretation` (currently observed on every tick because of a separate schema-validation regression tracked in [#404](https://github.com/kentonium3/kg-automation/issues/404)), the code path that writes the `RETRY_EXHAUSTED` ledger row hands the validator a value the validator's contract rejects, raising a `ValueError`. The exception kills the entire drift event mid-flight, never writes the ledger row that was supposed to document the failure, and blocks every subsequent doc-audit issue in the same tick from being processed.

The root mismatch: the retry policy attempts up to 4 calls, but the ledger schema validator's contract caps `retry_count` at 3. The two ranges have drifted out of sync. One write-site does not clamp; the value goes through unmodified and trips the bound.

This mission re-aligns the two ranges and adds the defensive clamp so the crash cannot recur, even if the bounds drift again in the future.

## Goals

- Stop drift events from crashing the tick when they exhaust their retry budget.
- Preserve the actual attempt count in the ledger (do not silently clamp away information).
- Keep the existing ledger schema additive — existing rows must continue to validate without migration.
- Add regression coverage so the drift between retry policy and ledger schema is caught by tests, not by an outage.

## Non-Goals

- Investigating *why* `drift_interpretation` schema validation fails on every call (split to [#404](https://github.com/kentonium3/kg-automation/issues/404)).
- Fixing `audit_interpretation` oversized-diff handling (split to [#402](https://github.com/kentonium3/kg-automation/issues/402)).
- Changing the `audit_ledger` or any code path that does not write `retry_count`. `audit_ledger.AuditLedgerEntry` does not have a `retry_count` field; it is unaffected.
- Changing the LLM prompt, model, retry-policy timing, or retry-policy maximum attempt count.

## Actors

- **Doc-audit driver operator** (Kent, via systemd timer) — runs the auditor; needs ticks that don't crash mid-flight.
- **Doc-audit driver process** (`felix-doc-auditor.service`) — exercises the drift event lifecycle.
- **Future maintainer** — reads the ledger schema contract and expects the validator to mean what it says.

## User Scenarios & Testing

### Primary scenario: drift event exhausts retries

1. The doc-audit driver picks up a pending drift event.
2. `drift_interpretation` is called up to the retry policy's maximum (currently 4 attempts) and all attempts fail (e.g., schema validation, transient API error).
3. The driver writes a `RETRY_EXHAUSTED` row to the drift ledger.
4. The driver moves on to the next drift event (or, if none remain, to the doc-audit issue queue).
5. **Expected outcome**: the ledger row exists with `retry_count` equal to the actual attempt count; no exception escapes; subsequent events process normally.
6. **Current outcome** (the bug): `ValueError: retry_count must be in [0, 3]; got 4` is raised; the ledger row is never written; the rest of the tick is blocked.

### Secondary scenario: drift event succeeds on first attempt

1. Driver picks up a pending drift event.
2. `drift_interpretation` succeeds on attempt 1.
3. Ledger row written with `retry_count = 0`.
4. **Expected outcome**: unchanged from today. The fix must not regress this path.

### Edge case: defensive clamp catches future drift

1. Some future change raises the retry policy's maximum to a value above whatever the ledger schema bound is set to.
2. `exc.attempts` exceeds the schema bound.
3. **Expected outcome**: the write-site clamp prevents a `ValueError`; the ledger row is still written; a test failure (the regression test from this mission) surfaces the bound/policy drift in CI before it reaches production.

### Edge case: existing ledger rows after schema widening

1. Existing ledger rows on disk all have `retry_count ∈ [0, 3]`.
2. After the schema bound widens, a reader loads those rows.
3. **Expected outcome**: all existing rows continue to validate. No migration is required.

## Requirements

### Functional Requirements

| ID      | Requirement                                                                                                                                                                                       | Status |
|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| FR-001  | When a drift event exhausts its retry budget, the `RETRY_EXHAUSTED` ledger row write SHALL complete without raising an exception.                                                                | Active |
| FR-002  | The `retry_count` value persisted to the ledger SHALL equal the actual number of LLM call attempts made, including the final failing attempt, up to the retry policy's configured maximum.       | Active |
| FR-003  | The drift-ledger schema validator SHALL accept any `retry_count` value in `[0, retry_max]`, where `retry_max` equals the retry policy's configured maximum attempt count.                        | Active |
| FR-004  | The drift-ledger write-site code path SHALL defensively clamp `retry_count` into the valid schema range before constructing the ledger entry, so the validator's contract cannot crash the path. | Active |
| FR-005  | Existing drift-ledger rows with `retry_count` values in `[0, 3]` SHALL continue to validate without modification after the schema bound is widened.                                              | Active |
| FR-006  | When the next drift event (or doc-audit issue) is queued behind a `RETRY_EXHAUSTED` event, it SHALL begin processing without being blocked by the prior event's outcome.                          | Active |

### Non-Functional Requirements

| ID      | Requirement                                                                                                                                                                       | Threshold                                                                 | Status |
|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|--------|
| NFR-001 | Ledger row on-disk JSON structure (field order, key names, `schema_version` integer) SHALL NOT change as part of this mission.                                                    | 100% identical field ordering and naming                                  | Active |
| NFR-002 | The mission SHALL ship a regression test that runs the full `drift_event.commit` path with `exc.attempts` set to each value in `{0, 1, retry_max-1, retry_max}` and asserts success. | Test added; all four cases pass; failing test demonstrates today's crash. | Active |
| NFR-003 | All existing `scripts/doc_audit/` pytest tests SHALL continue to pass after the change.                                                                                            | Test suite green                                                          | Active |
| NFR-004 | The mission SHALL update the ledger schema reference documentation (`contracts/ledger-schema.md` if present, dataclass docstrings, and any other authoritative reference) to reflect the widened bound. | All referenced docs updated to match new bound                            | Active |

### Constraints

| ID    | Constraint                                                                                                                                                  | Status |
|-------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| C-001 | Scope is limited to the drift-ledger path (`scripts/doc_audit/output/drift_ledger.py`, `scripts/doc_audit/signals/drift_event.py`, and their callers).      | Active |
| C-002 | No changes to `audit_ledger.py`, `audit_interpretation.py`, or any audit-issue code path.                                                                   | Active |
| C-003 | No investigation of `drift_interpretation`'s schema-validation root cause (split to #404).                                                                  | Active |
| C-004 | No changes to the LLM prompt, model selection, or retry policy's configured maximum attempt count.                                                          | Active |
| C-005 | Change must be additive at the schema-bound boundary. Widening only; no narrowing or breaking changes to existing rows.                                     | Active |
| C-006 | Risk tier 3 (Logic/Workflow). No deployment, network, credential, or secrets changes. No pre-flight checklist required.                                     | Active |

## Success Criteria

| ID     | Criterion                                                                                                                                                                                                            |
|--------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| SC-001 | A doc-auditor tick that processes a drift event whose `drift_interpretation` retries are exhausted completes without raising `ValueError`.                                                                           |
| SC-002 | The drift events ledger contains a `RETRY_EXHAUSTED` row whose `retry_count` field equals the actual attempt count (currently 4 per observed behavior).                                                              |
| SC-003 | Subsequent drift events and doc-audit issues queued behind a `RETRY_EXHAUSTED` event begin processing without being blocked by it.                                                                                   |
| SC-004 | A regression test exists that exercises the full `drift_event.commit` ledger-write path with `exc.attempts = retry_max` and asserts no exception is raised.                                                          |
| SC-005 | All existing `scripts/doc_audit/` pytest tests pass.                                                                                                                                                                  |
| SC-006 | Re-enabling `felix-doc-auditor.timer` on office2 after merge and triggering a single tick produces ledger rows (one per drift event) and no ValueError crashes in `journalctl --user -u felix-doc-auditor.service`.   |

## Key Entities

- **Drift event** — a queued unit of work derived from a baseline-file diff; flows through `drift_interpretation` → ledger write.
- **`AuditLedgerEntry`** (drift-ledger variant, `scripts/doc_audit/output/drift_ledger.py`) — append-only dataclass row. Includes `retry_count: int`. Validated by `_validate_entry` before write.
- **`_RetrySchemaError`** — exception carrying `.attempts` attribute (count of LLM calls made before retries exhausted). Currently raised by `drift_interpretation` on every call (root cause in #404).
- **Retry policy** — configured in `scripts/doc_audit/judgment/` retry helpers; current observed maximum is 4 attempts (1 initial + 3 retries).
- **Drift-ledger schema contract** — encoded in `_validate_entry` invariants and (likely) documented in `contracts/ledger-schema.md`. Authoritative for what the ledger row must look like.

## Assumptions

- The retry policy's maximum attempt count is **4** (1 initial + 3 retries) as observed in 2026-05-24 04:50–04:55 UTC journal entries. The plan phase MUST verify this by reading the retry helper code and not by trusting the observation alone.
- No downstream consumer of the drift ledger filters or aggregates on `retry_count ≤ 3` as a guarantee. The plan phase MUST verify this by grepping consumers before widening the bound.
- The reference at `output/drift_ledger.py:146` to `contracts/ledger-schema.md` either exists or is stale; the plan phase MUST locate and update it (or remove the stale reference).
- No code path other than `signals/drift_event.py:464` writes to the drift ledger without the `handle_drift_events.py:645` clamp. The plan phase MUST verify by grepping all `AuditLedgerEntry(` constructors.

## Dependencies

- **#404** (diagnosis of why `drift_interpretation` schema fails) is a downstream follow-on, not a blocker. This mission ships independently and makes the failure mode safe-to-retry-on; #404 then makes the failure mode go away.
- **#402** (audit_interpretation oversized-diff) is independent and can be worked in parallel.
- No spec-kitty/ infrastructure changes; no office2 deployment until merge.

## Risks

- **Risk**: `contracts/ledger-schema.md` may be checked into the repo but missed during the update sweep, leaving the contract doc out of sync with the validator. **Mitigation**: explicit task in plan phase to locate and update.
- **Risk**: `retry_max` may be derived dynamically (config, env var) rather than a constant; if so, the schema bound must read from the same source rather than hard-coding a number. **Mitigation**: plan phase identifies the source-of-truth for `retry_max` before patching.
- **Risk**: Hidden test fixtures or sample ledger rows used in tests may assume `retry_count ≤ 3` literally. **Mitigation**: run full test suite after change; treat any failure as a fixture update, not a bug in the fix.

## Validation & Quality Gates

- All existing `scripts/doc_audit/` pytest tests pass.
- New regression test passes.
- A manual office2 tick post-merge produces a `RETRY_EXHAUSTED` ledger row (per SC-006), confirming end-to-end behavior with real-world `_RetrySchemaError` traffic.
