---
work_package_id: WP04
title: handle_drift_events integration
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- C-001
- C-002
- FR-001
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- FR-014
- FR-016
- NFR-005
- NFR-006
- NFR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T19:45:00+00:00'
subtasks:
- T018
- T019
- T020
- T021
- T022
- T023
history: []
authoritative_surface: scripts/doc_audit/helpers/handle_drift_events.py
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- scripts/doc_audit/helpers/handle_drift_events.py
- scripts/doc_audit/config.toml
- tests/doc_audit/helpers/test_handle_drift_events.py
tags: []
agent: "agy:gemini-2.5-pro:spec-kitty-review:reviewer"
shell_pid: "17087"
---

# WP04 — handle_drift_events integration

## Objective

Wire Moment 0 into the existing drift-event processing pipeline. This is the integration point where all upstream pieces converge (WP01 judgment, WP02 ledger, WP03 translator). Preserves backward compatibility (C-002 existing CLI unchanged) and adds the config-flag rollback (FR-012, FR-013).

## Context

- **Spec**: FR-001 (invoke Moment 0), FR-004/5/6/7 (verdict routing), FR-008/9 (retry escalation), FR-010 (ledger), FR-011 (guardrails), FR-012/13 (config flag), FR-014 (cursor reset), FR-016 (existing path unchanged)
- **Plan**: D5 (cutover script flag interaction), D6 (retry policy), D9 (config flag mechanism)
- **Dependencies**: WP01 (drift_interpretation.interpret + DriftVerdict), WP02 (drift_ledger.append + AuditLedgerEntry), WP03 (drift_to_proposed_edit.build)
- **Existing module**: `scripts/doc_audit/helpers/handle_drift_events.py` (435 lines pre-mission); extend, do NOT rewrite
- **Branching**: planning_base=`main`, merge_target=`main`.

## Subtasks

### T018 — Config.toml loading

**Purpose**: Add the `[drift_interpretation]` block to config.toml + loader.

**Steps**:

1. Read existing `scripts/doc_audit/config.toml`. Add new block:
   ```toml
   [drift_interpretation]
   enabled = true
   ledger_path = "/data/services/security-monitor/logs/drift-events-ledger.jsonl"
   model = "claude-haiku-4-5-20251001"
   api_key_path = "/data/services/openclaw/secrets/anthropic"
   timeout_seconds = 30
   confidence_threshold = 0.80
   ```
2. Read existing `scripts/doc_audit/config.py`. Add loader logic for the new section (if there's an existing config schema, extend it; otherwise add a `DriftInterpretationConfig` dataclass).
3. Loader behavior: read per-tick (called once at the start of `process_events`); validate field types; default missing-block to `enabled=false` (graceful fallback if config not yet deployed).

**Files**:
- `scripts/doc_audit/config.toml` (modified, +~10 lines)
- `scripts/doc_audit/config.py` (modified if it exists; otherwise create — check existing structure)

**Validation**:
- [ ] `python3 -c "from scripts.doc_audit.config import load_config; c = load_config(); print(c.drift_interpretation)"` prints the loaded block
- [ ] Missing config block: `enabled` defaults to `false` (graceful)

---

### T019 — Moment 0 invocation behind flag

**Purpose**: Invoke `drift_interpretation.interpret()` for every mapped event when flag is on.

**Steps**:

1. Read existing `scripts/doc_audit/helpers/handle_drift_events.py` end-to-end.
2. Locate the main event loop in `process_events()` where each event is read from the cursor and matched against `find_mapping()`.
3. Insert a new branch BEFORE `file_doc_audit_issue()` (the pre-#362 path):
   ```python
   if config.drift_interpretation.enabled and mapping is not None:
       # Build DriftInterpretationContext
       context = _build_context_from_event(event, mapping, config)
       try:
           verdict = drift_interpretation.interpret(
               client=judgment_client,
               context=context,
               model=config.drift_interpretation.model,
               timeout=config.drift_interpretation.timeout_seconds,
               confidence_threshold=config.drift_interpretation.confidence_threshold,
           )
           # Route per verdict (T020)
           ...
       except DriftInterpretationError as exc:
           # Retry exhausted — fall through to pre-#362 issue filing path (FR-009)
           logger.error("Moment 0 retry exhausted for event %s: %s", event_id, exc)
           ledger.append(AuditLedgerEntry(verdict="RETRY_EXHAUSTED", confidence=None, outcome="retry_exhausted", ...))
           _file_pre_362_fallback_issue(event, mapping, exc.to_diagnostic_block())
   else:
       # Flag off OR no mapping — use existing pre-#362 path unchanged
       file_doc_audit_issue(event, mapping, repo=...)
   ```
4. `_build_context_from_event(event, mapping, config)`:
   - event_id: f"{cursor_line}:{event.timestamp_utc}"
   - Load each doc_target's current contents (from local repo checkout)
   - Build `DocTarget` for each
   - Return `DriftInterpretationContext`

**Files**: `scripts/doc_audit/helpers/handle_drift_events.py` (modified, +~120 lines).

**Validation**:
- [ ] Flag=true: Moment 0 invocation visible in logs
- [ ] Flag=false: pre-#362 path runs identically to today (snapshot test if available)

---

### T020 — Verdict routing

**Purpose**: Dispatch per verdict.

**Steps**:

1. `_route_verdict(verdict, context, mapping, config, ledger, judgment_client, repo) -> RoutingOutcome`:
   - If `verdict.verdict == "PROPOSED_EDIT"`:
     - Translator: `proposed_edit = drift_to_proposed_edit.build(verdict, context)`
     - Pass through existing `tier_classification.classify(...)` (use the existing client)
     - Dispatch per `EditTier`:
       - `TIER_A` → auto-commit (call existing `_apply_tier_a_edit()` or equivalent)
       - `TIER_B` → file PR (call existing `_open_pending_approval_pr()` or equivalent — exact name may differ; inspect existing handle_audit_routing.py)
       - `JUDGMENT` → file DebtIssue via existing `debt_body_generation` + filing
     - outcome = "auto_committed" / "pr_filed" / "issue_filed" respectively
   - If `verdict.verdict == "JUDGMENT_REQUIRED"`:
     - File `[doc-audit]` issue with verdict.question as the body's question section
     - outcome = "issue_filed"
   - If `verdict.verdict == "NO_CHANGE_NEEDED"`:
     - No GitHub action; ledger entry only
     - outcome = "auto_closed"
   - Return RoutingOutcome(outcome, tier_classification_outcome, github_issue_number)
2. Reuse existing helpers from `handle_audit_routing.py` for the Tier A / Tier B / DebtIssue paths — do NOT reimplement.

**Files**: same module, +~150 lines.

**Validation**:
- [ ] Each verdict path produces the expected outcome value
- [ ] tier_classification is called for PROPOSED_EDIT path (mock-verified in tests)
- [ ] guardrailed paths short-circuit (defense-in-depth via tier_classification — verified in tier_classification's own tests)

---

### T021 — Ledger entry append for every event

**Purpose**: Every processed drift event produces exactly one ledger row (FR-010).

**Steps**:

1. After verdict routing completes (or RETRY_EXHAUSTED fallback fires), build `AuditLedgerEntry`:
   ```python
   entry = AuditLedgerEntry(
       event_id=event_id,
       timestamp_utc=now_iso(),
       baseline=mapping.id.split("-drift")[0],  # or extract from mapping config
       mapping_id=mapping.id,
       verdict=verdict_or_retry_exhausted,
       confidence=verdict.confidence if not retry_exhausted else None,
       outcome=routing_outcome.outcome,
       doc_paths=[t.path for t in context.doc_targets],
       retry_count=interpret_attempts,
       latency_ms=int((time.time() - event_start) * 1000),
       tier_classification_outcome=routing_outcome.tier_classification_outcome,
       github_issue_number=routing_outcome.github_issue_number,
       schema_version=1,
   )
   ledger.append(entry, ledger_path=config.drift_interpretation.ledger_path)
   ```
2. Append happens AFTER side-effects (commits / PRs / issues) complete, so failures don't leave the ledger out of sync.
3. If ledger append fails (rare): log error but don't fail the whole tick (the side-effect already happened).

**Files**: same module, +~40 lines.

**Validation**:
- [ ] Each event produces exactly one ledger row
- [ ] RETRY_EXHAUSTED events have `confidence=null`, `outcome="retry_exhausted"`, `retry_count=3`
- [ ] Successful events have `latency_ms` set

---

### T022 — `--reset-cursor` flag

**Purpose**: Support the cutover script (WP05) and operator debugging.

**Steps**:

1. Add argparse flag `--reset-cursor` to `main()`.
2. Behavior: if set, write `.drift-events.cursor` to `0` via `write_cursor_atomic(0)` (existing helper) and exit 0 BEFORE the main event loop.
3. Log: "Cursor reset to 0 by operator request"
4. Idempotent: safe to call repeatedly.

**Files**: same module, +~20 lines.

**Validation**:
- [ ] `python3 -m scripts.doc_audit.helpers.handle_drift_events --reset-cursor` exits 0 and writes cursor=0
- [ ] No side effects beyond cursor write (no LLM calls, no issue filings)

---

### T023 — Extended tests

**Purpose**: Cover all new paths.

**Steps**:

1. Open existing `tests/doc_audit/helpers/test_handle_drift_events.py`. Read structure.
2. Add new test cases:
   - **Flag disabled fallback**: config has `enabled=false`; assert pre-#362 path is called (mock verification on `file_doc_audit_issue`).
   - **PROPOSED_EDIT → Tier A**: mock `interpret()` returns PROPOSED_EDIT conf 0.90; mock `tier_classification` returns TIER_A; assert auto-commit helper called; ledger row has outcome="auto_committed", tier="tier_a".
   - **PROPOSED_EDIT → Tier B**: similar, but tier_classification returns TIER_B; PR helper called; ledger has outcome="pr_filed".
   - **PROPOSED_EDIT → judgment fallback**: tier_classification returns JUDGMENT; DebtIssue path; ledger has outcome="issue_filed", tier="judgment".
   - **JUDGMENT_REQUIRED**: mock returns JUDGMENT_REQUIRED with question; assert `[doc-audit]` issue is filed with the question in body; ledger has outcome="issue_filed".
   - **NO_CHANGE_NEEDED**: mock returns NO_CHANGE_NEEDED conf 0.90; assert no GitHub call; ledger has outcome="auto_closed".
   - **RETRY_EXHAUSTED**: mock raises DriftInterpretationError; assert pre-#362 fallback fired; ledger has verdict="RETRY_EXHAUSTED".
   - **Cursor advances on RETRY_EXHAUSTED**: ensure the loop progresses (no infinite-loop on persistent failures).
   - **Cursor advances on success**: each verdict path advances cursor.
   - **--reset-cursor flag**: invoke main with this flag; assert cursor written to 0 and exit 0.
   - **Pre-#362 CLI surface unchanged**: smoke test the existing `--events --cursor --mapping --unmapped --repo` flag set still works.

**Files**: `tests/doc_audit/helpers/test_handle_drift_events.py` (modified, +~250 lines, ~11 new tests).

**Validation**:
- [ ] `pytest tests/doc_audit/helpers/test_handle_drift_events.py -v` ≥85% coverage on the modified module
- [ ] All 6 verdict paths covered
- [ ] Pre-#362 backward compat verified

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with mocked `JudgmentClient`, mocked `tier_classification`, mocked GitHub API. ≥85% coverage on modified handle_drift_events.py.

## Definition of Done

- [ ] All 6 subtasks complete.
- [ ] `pytest tests/doc_audit/helpers/test_handle_drift_events.py -v` ≥85%.
- [ ] Pre-#362 CLI surface unchanged (no removed flags, no changed defaults).
- [ ] Ledger entry written for every processed event.
- [ ] `--reset-cursor` flag works and is idempotent.

## Risks

- **Backward compatibility**: existing CLI (per C-002) must NOT change. Tests verify all existing flags + return value shapes.
- **Cursor advance semantics**: cursor must advance on RETRY_EXHAUSTED to avoid loops. Document this clearly in code.
- **tier_classification side effects**: ensure mocked tier_classification doesn't make real LLM calls during tests.
- **Existing handle_audit_routing.py helpers**: tier A/B helpers may be in handle_audit_routing.py rather than handle_drift_events.py; verify the import path before reusing.

## Reviewer Guidance

1. Verify `enabled=false` produces byte-identical behavior to pre-#362 pipeline.
2. Verify each of the 6 verdict paths (PROPOSED_EDIT × {Tier A/B/judgment}, JUDGMENT_REQUIRED, NO_CHANGE_NEEDED, RETRY_EXHAUSTED) has a passing test.
3. Verify the ledger entry has correct verdict + outcome combinations.
4. Confirm cursor advances on every path (including RETRY_EXHAUSTED) — no infinite-loop risk.

## Implementation Command

```bash
spec-kitty agent action implement WP04 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T20:47:37Z – claude:opus:python-implementer:implementer – shell_pid=11195 – Started implementation via action command
- 2026-05-22T21:05:58Z – claude:opus:python-implementer:implementer – shell_pid=11195 – Ready for review: Moment 0 wired into pipeline; 41 tests total (17 new for #362); pre-#362 path preserved byte-identically when flag=false; cursor advances on every path including RETRY_EXHAUSTED; --reset-cursor CLI flag added; tests blocked from running by sandbox — orchestrator must verify before approving
- 2026-05-22T21:08:59Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=15159 – Started review via action command
- 2026-05-22T21:13:46Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=15159 – Moved to planned
- 2026-05-22T21:18:12Z – claude:opus:python-implementer:implementer – shell_pid=16941 – Started implementation via action command
- 2026-05-22T21:18:21Z – claude:opus:python-implementer:implementer – shell_pid=16941 – Cycle 2: deduplicated _truncate_doc_state per agy review-cycle-3.md; coverage 76% -> 85% target met; 504 tests passing in full doc_audit regression
- 2026-05-22T21:18:28Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=17087 – Started review via action command
- 2026-05-22T21:56:00Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=17087 – Review passed: Deduplication is clean with duplicate helpers/constants removed, lazy import added, and 85% coverage target met exactly.
