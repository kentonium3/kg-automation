---
work_package_id: WP02
title: Wire shared helper into signals/drift_event.py
dependencies:
- WP01
requirement_refs:
- C-006
- C-007
- FR-002
- FR-005
- FR-006
- FR-007
- FR-009
- FR-010
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T22:50:00+00:00'
subtasks:
- T006
- T007
- T008
- T009
history: []
authoritative_surface: scripts/doc_audit/signals/
execution_mode: code_change
mission_id: 01KS8XRMC0EQZ8HCJ52GXCJ226
mission_slug: moment0-integration-fix-01KS8XRM
owned_files:
- scripts/doc_audit/signals/drift_event.py
- tests/doc_audit/signals/test_drift_event.py
tags: []
agent: "claude:opus:python-implementer:implementer"
shell_pid: "75889"
---

# WP02 — Wire shared helper into signals/drift_event.py

## Objective

Integrate `routing.drift_moment0.route_drift_event(...)` (from WP01) into the actual cron entry point — `DriftEventSignalSource.commit()`. This is the bug fix: the cron service runs `signals/drift_event.py`, so the Moment 0 invocation must happen there.

## Context

- **Spec**: FR-002, FR-005, FR-006, FR-009, FR-010
- **Plan**: D2 (JudgmentClient lifecycle: lazy, one per tick, never instantiated when disabled)
- **Existing module**: `scripts/doc_audit/signals/drift_event.py` (~430 lines including a multi-line docstring) — extend, do NOT rewrite. Cursor + drain logic at lines 260-400 MUST NOT be changed.
- **Pattern source**: WP01's handle_drift_events.py refactor produces the call site pattern that signals/drift_event.py mirrors.
- **Dependencies**: WP01 (route_drift_event + RoutingOutcome must exist and be importable).

## Subtasks

### T006 — JudgmentClient lazy lifecycle

Steps:
1. In `DriftEventSignalSource.__init__`, add `self._judgment_client: Optional[JudgmentClient] = None`.
2. Add method `_get_judgment_client(self) -> JudgmentClient`:
   ```python
   def _get_judgment_client(self) -> JudgmentClient:
       if self._judgment_client is None:
           api_key_path = Path(self.config.drift_interpretation.api_key_path)
           self._judgment_client = JudgmentClient(api_key_path=api_key_path)
       return self._judgment_client
   ```
3. Import `JudgmentClient` from `doc_audit.judgment.client`. Import `route_drift_event, RoutingOutcome` from `doc_audit.routing.drift_moment0`. Import `DriftInterpretationError` from `doc_audit.judgment.drift_interpretation`. Import `AuditLedgerEntry, append as ledger_append` from `doc_audit.output.drift_ledger`.

Validation:
- [ ] `_get_judgment_client()` is called from exactly one place: inside the Moment 0 branch in `commit()`
- [ ] No top-level instantiation of JudgmentClient on import

### T007 — `commit()` Moment 0 invocation

Steps:
1. Read existing `commit()` carefully — note the cursor idempotency check, the same-tick committed-buffer check, the no-mapping path, and the mapping-matched-call-file_doc_audit_issue path.
2. Modify ONLY the mapping-matched branch. Where today it's:
   ```python
   if mapping is None:
       append_unmapped(self._unmapped_path, event)
   else:
       ok, output = file_doc_audit_issue(event, mapping, self._repo, dry_run=False)
       if not ok:
           raise RuntimeError(...)
   ```
   Insert the Moment 0 check at the start of the `else` branch:
   ```python
   else:
       if self.config.drift_interpretation.enabled:
           try:
               event_id = f"{line_number}:{event.get('timestamp_utc', '')}"
               timestamp_utc = event.get('timestamp_utc', '')
               outcome = route_drift_event(
                   event=event,
                   mapping=mapping,
                   config=self.config,
                   client=self._get_judgment_client(),
                   ledger_path=Path(self.config.drift_interpretation.ledger_path),
                   repo=self._repo,
                   event_id=event_id,
                   timestamp_utc=timestamp_utc,
                   cursor_line=line_number,
                   repo_root=Path(self.config.paths.repo_root),  # OR similar — check actual config field
               )
               # success — outcome is logged via journalctl through the helper
           except DriftInterpretationError as exc:
               # Retry exhausted — fall back to pre-#362 path (FR-006)
               logger.error("Moment 0 retry exhausted for event %s: %s", event_id, exc)
               # Append RETRY_EXHAUSTED ledger row
               ledger_append(
                   AuditLedgerEntry(
                       event_id=event_id,
                       timestamp_utc=_now_iso(),  # or compute via existing util
                       baseline=str(event.get("baseline_name", event.get("baseline", "unknown"))),
                       mapping_id=mapping.id,
                       verdict="RETRY_EXHAUSTED",
                       confidence=None,
                       outcome="retry_exhausted",
                       doc_paths=list(mapping.doc_targets),
                       retry_count=getattr(exc, "attempts", 3),
                       latency_ms=0,  # caller didn't time it precisely
                       tier_classification_outcome=None,
                       github_issue_number=None,
                       schema_version=1,
                   ),
                   ledger_path=Path(self.config.drift_interpretation.ledger_path),
               )
               # File pre-#362 fallback issue
               ok, output = file_doc_audit_issue(event, mapping, self._repo, dry_run=False)
               if not ok:
                   raise RuntimeError(f"file_doc_audit_issue failed during fallback: {output}")
       else:
           # Config flag disabled — pre-#362 path (FR-002 fallback / FR-010)
           ok, output = file_doc_audit_issue(event, mapping, self._repo, dry_run=False)
           if not ok:
               raise RuntimeError(...)
   ```
3. The exact location of `repo_root` and other config fields — verify by reading `scripts/doc_audit/config.py` first. Use what's actually there.

Validation:
- [ ] When config flag disabled: `_get_judgment_client()` is NEVER called (FR-010 enforced by test)
- [ ] When config flag enabled and mapping matches: `route_drift_event()` is called
- [ ] When DriftInterpretationError raised: ledger gets RETRY_EXHAUSTED row + `file_doc_audit_issue` is invoked
- [ ] Cursor + drain logic at end of `commit()` is unchanged (still calls `self._committed_lines.add(line_number)` + `self._drain(current)`)

### T008 — Preserve cursor/drain semantics

Steps:
1. Verify by inspection: the two idempotency checks at the top of `commit()` (line < cursor; line in committed_lines) still run BEFORE the Moment 0 branch. They short-circuit just as they did before.
2. Verify by inspection: the no-mapping branch (`if mapping is None: append_unmapped(...)`) is unchanged. Moment 0 only kicks in when `mapping is not None`.
3. Verify by inspection: regardless of whether the new Moment 0 branch ran or the old fallback ran, the code reaches `self._committed_lines.add(line_number)` + `self._drain(current)` at the end. This is the SAME cursor advance path.
4. Add a unit test (in WP02's test file) that exercises both paths and asserts cursor advances correctly in each.

Validation:
- [ ] Cursor advances on all paths: (a) flag enabled + helper succeeds, (b) flag enabled + DriftInterpretationError raised + fallback succeeds, (c) flag disabled + fallback succeeds, (d) no-mapping path unchanged
- [ ] Idempotent re-commit on already-passed line: no side effects, no Moment 0 invocation, no JudgmentClient instantiation

### T009 — Tests

Steps:
1. Open existing `tests/doc_audit/signals/test_drift_event.py`. Read structure.
2. Add new test cases:
   - **Flag enabled — happy path**: mock `route_drift_event` returns RoutingOutcome; assert helper called with correct kwargs; cursor advances; no fallback `file_doc_audit_issue` call
   - **Flag enabled — DriftInterpretationError**: mock `route_drift_event` raises; assert RETRY_EXHAUSTED ledger row written + `file_doc_audit_issue` called as fallback
   - **Flag disabled** (FR-010): config has `enabled=false`; assert `route_drift_event` is NOT called; assert `JudgmentClient.__init__` is NOT called (verify via mock); assert `file_doc_audit_issue` is called (pre-#362 path)
   - **No mapping**: assert `route_drift_event` NOT called; existing append_unmapped path runs unchanged
   - **Idempotent re-commit on passed line**: assert no `route_drift_event` call, no `JudgmentClient` instantiation, no side effects
   - **Cursor advance on all paths**: parametrize (enabled-success, enabled-failure, disabled, no-mapping) and assert cursor advances
   - **JudgmentClient memoization**: assert `_get_judgment_client()` returns the same instance on second call (mock-instance identity)
3. Coverage target ≥85% on the modified code paths.

Validation:
- [ ] All new test cases pass
- [ ] Full `pytest tests/doc_audit/` suite passes (no regression)

## Definition of Done

- [ ] All 4 subtasks complete
- [ ] `pytest tests/doc_audit/signals/test_drift_event.py -v` passes; ≥85% coverage on new paths
- [ ] `pytest tests/doc_audit/ -q` full suite passes
- [ ] FR-010 verified: disabled flag never constructs JudgmentClient
- [ ] Cursor + drain semantics unchanged on all paths

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission moment0-integration-fix-01KS8XRM --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-23T04:12:04Z – claude:opus:python-implementer:implementer – shell_pid=75889 – Started implementation via action command
