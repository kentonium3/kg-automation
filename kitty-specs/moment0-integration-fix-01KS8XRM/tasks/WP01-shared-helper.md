---
work_package_id: WP01
title: Extract Moment 0 routing into shared helper
dependencies: []
requirement_refs:
- C-006
- C-008
- FR-001
- FR-003
- FR-004
- NFR-003
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-moment0-integration-fix-01KS8XRM
base_commit: 29a3054a52e3b97a667f7b13eeac9945b564fb29
created_at: '2026-05-22T22:53:34.142884+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: '32428'
history: []
authoritative_surface: scripts/doc_audit/routing/
execution_mode: code_change
mission_id: 01KS8XRMC0EQZ8HCJ52GXCJ226
mission_slug: moment0-integration-fix-01KS8XRM
owned_files:
- scripts/doc_audit/routing/drift_moment0.py
- scripts/doc_audit/routing/__init__.py
- scripts/doc_audit/helpers/handle_drift_events.py
- tests/doc_audit/routing/test_drift_moment0.py
- tests/doc_audit/helpers/test_handle_drift_events.py
tags: []
---

# WP01 — Extract Moment 0 routing into shared helper

## Objective

Move the Moment 0 routing logic from `scripts/doc_audit/helpers/handle_drift_events.py` (where #362's WP04 placed it, but it's dead code at runtime) into a new shared module `scripts/doc_audit/routing/drift_moment0.py`. Refactor `process_events()` to call the shared helper. Promote `RoutingOutcome` to public. This sets up WP02's integration at the actual cron entry point.

## Context

- **Spec**: FR-001, FR-003, FR-004 (single source of truth for Moment 0 routing)
- **Plan**: D1 (helper module path), D3 (helper signature), D5 (test strategy split)
- **Contract**: [contracts/routing-helper.md](../contracts/routing-helper.md)
- **Pattern source**: existing `handle_drift_events.py` has `_handle_moment0_event`, `_route_verdict`, `_apply_tier_a_edit`, `_file_tier_b_pending_approval`, `_file_judgment_issue` — these move into the new module. Existing `routing/drift_to_proposed_edit.py` shows the routing-module style.

## Subtasks

### T001 — Create `routing/drift_moment0.py`

Steps:
1. Read existing `scripts/doc_audit/helpers/handle_drift_events.py` end-to-end. Identify the 5 inlined helpers (`_handle_moment0_event`, `_route_verdict`, `_apply_tier_a_edit`, `_file_tier_b_pending_approval`, `_file_judgment_issue`) + the `RoutingOutcome` dataclass + the `_build_context_from_event` helper.
2. Create `scripts/doc_audit/routing/drift_moment0.py`. Move:
   - `RoutingOutcome` dataclass (frozen) — promote to module-level public
   - `route_drift_event(...)` — new public function with the keyword-only signature from `contracts/routing-helper.md`. Internally calls the moved helpers.
   - The 5 inlined helpers — move as module-private (`_route_verdict`, `_apply_tier_a_edit`, `_file_tier_b_pending_approval`, `_file_judgment_issue`)
   - `_build_context_from_event` — move; remove the duplicate lazy import of `_truncate_doc_state` (the helper now uses it via normal import at module level)
3. Imports: from `doc_audit.judgment.drift_interpretation` (interpret, DriftInterpretationError, _truncate_doc_state), from `doc_audit.judgment.tier_classification` (classify), from `doc_audit.routing.drift_to_proposed_edit` (build), from `doc_audit.output.drift_ledger` (append, AuditLedgerEntry), from `doc_audit.data_model` (Mapping, EditTier).
4. The shared helper computes `latency_ms` and `retry_count` for its returned `RoutingOutcome`.
5. RETRY_EXHAUSTED behavior: `route_drift_event` does NOT catch `DriftInterpretationError` itself — caller catches it (so caller can do its own fallback path). The helper's responsibility ends at "raise on retry exhaustion; caller writes the RETRY_EXHAUSTED ledger row + fallback issue".

Validation:
- [ ] `python3 -c "from scripts.doc_audit.routing.drift_moment0 import route_drift_event, RoutingOutcome; print('ok')"` prints `ok`
- [ ] `RoutingOutcome` is `frozen=True`

### T002 — Refactor `handle_drift_events.py::process_events()`

Steps:
1. Remove the 5 helpers + the local `RoutingOutcome` dataclass + `_build_context_from_event` (they moved to WP01's new module).
2. In `process_events()` where `_handle_moment0_event` was called, replace with a call to `route_drift_event(...)` with the appropriate keyword arguments built from the event.
3. RETRY_EXHAUSTED fallback path: catch `DriftInterpretationError`, write the ledger row, file the pre-#362 fallback issue. Same observable behavior; just calls `route_drift_event` instead of inlined helpers.
4. Imports: add `from doc_audit.routing.drift_moment0 import route_drift_event, RoutingOutcome`. Remove now-unused imports of the moved helpers.

Validation:
- [ ] `git diff scripts/doc_audit/helpers/handle_drift_events.py` shows net deletion of the 5 helpers + the local RoutingOutcome
- [ ] Existing `tests/doc_audit/helpers/test_handle_drift_events.py` still passes after T005

### T003 — Update `routing/__init__.py`

Steps:
1. Read current `scripts/doc_audit/routing/__init__.py` (exports `build`, `apply`, `RoutingResult` per #362 + existing).
2. Add `route_drift_event` and `RoutingOutcome` to the public surface:
   ```python
   from .drift_moment0 import route_drift_event, RoutingOutcome
   __all__ = [..., "route_drift_event", "RoutingOutcome"]
   ```

Validation:
- [ ] `python3 -c "from scripts.doc_audit.routing import route_drift_event, RoutingOutcome; print('ok')"` prints `ok`

### T004 — Tests for shared helper

Steps:
1. Create `tests/doc_audit/routing/test_drift_moment0.py`.
2. Mock `JudgmentClient`, `tier_classification.classify`, `subprocess.run` (for gh calls), `drift_ledger.append`.
3. Test cases (cover all 6 verdict paths + retry exhaustion):
   - PROPOSED_EDIT high-conf → TIER_A → outcome="auto_committed", tier_classification_outcome="tier_a"
   - PROPOSED_EDIT high-conf → TIER_B → outcome="pr_filed"
   - PROPOSED_EDIT high-conf → JUDGMENT → outcome="issue_filed" (debt-issue path)
   - PROPOSED_EDIT low-conf → demoted to JUDGMENT_REQUIRED → outcome="issue_filed"
   - JUDGMENT_REQUIRED → outcome="issue_filed", LLM's question in body
   - NO_CHANGE_NEEDED → outcome="auto_closed", no GitHub side effect
   - DriftInterpretationError raised (retry exhausted) — propagates to caller
   - RoutingOutcome populated correctly in each happy path (retry_count, latency_ms, github_issue_number)
   - Ledger append called exactly once per call (except when DriftInterpretationError raised — caller's responsibility)
4. Coverage target ≥85% on `routing/drift_moment0.py`.

### T005 — Update `test_handle_drift_events.py`

Steps:
1. Read current test file. Identify tests that mocked the now-removed inline helpers (`_handle_moment0_event`, `_route_verdict`, etc.).
2. For each:
   - If the test verified Moment 0 happy-path behavior → rewrite to mock `route_drift_event` instead and assert it was called with correct kwargs.
   - If the test verified retry-exhausted fallback → preserve; the fallback now wraps `route_drift_event(...) → catches DriftInterpretationError`.
   - If the test verified non-Moment-0 behavior (config-disabled, no-mapping, RETRY_EXHAUSTED ledger row, cursor advance) → preserve unchanged.
3. Remove tests that are now obsolete (e.g., tests verifying the internal helper signatures we removed).
4. Verify the test count delta makes sense — don't drop coverage by removing without replacement.

Validation:
- [ ] `pytest tests/doc_audit/helpers/test_handle_drift_events.py -v` passes
- [ ] `pytest tests/doc_audit/` full suite passes
- [ ] No regression in observable behavior (config flag, retry handling, cursor advance all still tested)

## Definition of Done

- [ ] All 5 subtasks complete
- [ ] `pytest tests/doc_audit/routing/test_drift_moment0.py -v` ≥85% coverage
- [ ] `pytest tests/doc_audit/` full suite passes (no regression)
- [ ] `route_drift_event` and `RoutingOutcome` exposed via `from doc_audit.routing import ...`
- [ ] handle_drift_events.py is smaller (deleted code > added code)

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission moment0-integration-fix-01KS8XRM --agent claude:opus:python-implementer:implementer
```
