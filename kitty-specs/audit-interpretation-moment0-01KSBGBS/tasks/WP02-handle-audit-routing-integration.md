---
work_package_id: WP02
title: Wire audit_interpretation into handle_audit_routing
dependencies:
- WP01
requirement_refs:
- C-001
- C-002
- C-003
- FR-004
- FR-006
- FR-008
- FR-009
- FR-011
- FR-013
- FR-015
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-23T22:50:00+00:00'
subtasks:
- T004
- T005
history: []
authoritative_surface: scripts/doc_audit/helpers/
execution_mode: code_change
mission_id: 01KSBGBS9BBDWV2Z28FESVJ9KQ
mission_slug: audit-interpretation-moment0-01KSBGBS
owned_files:
- scripts/doc_audit/helpers/handle_audit_routing.py
- tests/doc_audit/helpers/test_handle_audit_routing.py
tags: []
agent: "claude:opus:python-implementer:implementer"
shell_pid: "69525"
---

# WP02 — Wire audit_interpretation into handle_audit_routing

## Objective

Replace the today-merged "no-proposals" branch's lock-release-and-comment behavior with the new audit_interpretation path. The lock-release-and-comment remains as the FALLBACK when audit_interpretation is disabled OR retries exhaust.

## Context

- **Today's pre-existing behavior (commit bf17c3cf)**: no-proposals branch posts a "manual operator review required" comment + removes status:in-progress lock + returns
- **New behavior (this WP)**: no-proposals branch builds an AuditInterpretationContext (audit + diff + in_scope_docs with loaded contents) and calls `interpret_audit`. Routes each verdict per spec FR-004/006/007/008.

## Subtask T004 — Wire interpret_audit + verdict routing

Steps:
1. Add import: `from doc_audit.judgment.audit_interpretation import interpret_audit, AuditInterpretationContext, AuditVerdict`. Also `from doc_audit.output.audit_ledger import append as audit_ledger_append, AuditLedgerEntry`.
2. Lazy import `DocTarget` from drift_interpretation (reuse).
3. Read `config.audit_interpretation.enabled` from the existing Config. If False → fall through to today's no-proposals handler (preserved as-is).
4. Build context: load each in_scope_doc's current contents from `repo_root`; apply D2 truncation; construct list of DocTarget; build AuditInterpretationContext.
5. Build/reuse JudgmentClient (lazy).
6. Call `interpret_audit(client, context)` — returns list[AuditVerdict] (one per doc).
7. Wrap in try/except DriftInterpretationError. On retry-exhausted: fall through to today's no-proposals handler + record one ledger entry per doc with `verdict=RETRY_EXHAUSTED`.
8. Dispatch per verdict:
   - `NO_CHANGE_NEEDED` (conf ≥0.80): ledger entry only
   - `PROPOSED_EDIT` (conf ≥0.80): build ProposedEdit (mirror drift_to_proposed_edit pattern; `change_type="audit_derived"` — add to data_model.py docstring); pass through `tier_classification.classify()`; dispatch per resulting tier (Tier A auto-commit, Tier B file PR, judgment file DebtIssue) using existing helpers in handle_audit_routing.py
   - `JUDGMENT_REQUIRED`: accumulate into a per-audit list; do NOT post comment yet
9. After all verdicts dispatched: if accumulator has ≥1 JUDGMENT_REQUIRED → post a SINGLE consolidated comment listing all questions (per research D3). Format per research.md.
10. After all dispatch + comment: if EVERY verdict was NO_CHANGE_NEEDED → auto-close the audit issue with a summary comment listing the clean docs.
11. Always: release the status:in-progress lock (already best-effort behavior from today's fix).

## Subtask T005 — Tests

Mock `interpret_audit` to return various combinations:
- All NO_CHANGE_NEEDED → audit auto-closed with summary comment
- Mixed (some NO_CHANGE_NEEDED + some JUDGMENT_REQUIRED) → single consolidated comment posted, audit stays open
- PROPOSED_EDIT @ Tier A → existing auto-commit helper called
- PROPOSED_EDIT @ Tier B → existing PR helper called
- PROPOSED_EDIT routed via tier_classification → judgment → DebtIssue helper called
- DriftInterpretationError raised → fallback no-proposals comment posted (today's behavior preserved); ledger has RETRY_EXHAUSTED per doc
- Config flag disabled → today's no-proposals behavior runs unchanged

≥85% coverage on the new code paths.

## Definition of Done

- 2 subtasks complete
- ≥85% coverage on new code paths in handle_audit_routing.py
- Full regression clean
- Smoke test: invoke route_audit_decision with a fixture state file → produces expected ledger rows + comments

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission audit-interpretation-moment0-01KSBGBS --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-24T03:12:03Z – claude:opus:python-implementer:implementer – shell_pid=69525 – Started implementation via action command
