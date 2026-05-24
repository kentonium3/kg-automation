---
work_package_id: WP01
title: audit_interpretation + audit_ledger modules
dependencies: []
requirement_refs:
- C-004
- FR-001
- FR-002
- FR-003
- FR-005
- FR-007
- FR-010
- FR-012
- FR-014
- FR-015
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-audit-interpretation-moment0-01KSBGBS
base_commit: 335fa9eccf28888db6d7d3de05ed6fdd72fd1aef
created_at: '2026-05-24T02:53:49.827812+00:00'
subtasks:
- T001
- T002
- T003
history: []
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
mission_id: 01KSBGBS9BBDWV2Z28FESVJ9KQ
mission_slug: audit-interpretation-moment0-01KSBGBS
owned_files:
- scripts/doc_audit/judgment/audit_interpretation.py
- scripts/doc_audit/prompts/audit_interpretation.prompt.md
- scripts/doc_audit/output/audit_ledger.py
- tests/doc_audit/judgment/test_audit_interpretation.py
- tests/doc_audit/output/test_audit_ledger.py
tags: []
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "68650"
---

# WP01 — audit_interpretation + audit_ledger

## Objective

Mirror `drift_interpretation.py` + `drift_ledger.py` to build the equivalent surfaces for commit-derived audits. Per-doc LLM verdict; JSONL ledger.

## Pattern source (read first)

- `scripts/doc_audit/judgment/drift_interpretation.py` (~32KB — direct template)
- `scripts/doc_audit/prompts/drift_interpretation.prompt.md` (~6KB — direct template)
- `scripts/doc_audit/output/drift_ledger.py` (~23KB — direct template)

Adapt the input shape (audit context: issue + diff + multiple in-scope docs) and output shape (list of AuditVerdict, one per doc).

## Subtasks

### T001 — audit_interpretation.py + prompt

- Module path: `scripts/doc_audit/judgment/audit_interpretation.py`
- Public `interpret_audit(client, context) -> list[AuditVerdict]` invokes LLM ONCE PER in-scope doc (loop over context.in_scope_docs). Each call returns a single AuditVerdict.
- Reuse the truncation helper from drift_interpretation (or import it) for doc state sizing — same D2 tier strategy.
- Cache-aware prompt at `scripts/doc_audit/prompts/audit_interpretation.prompt.md`:
  - System (cached): rules, 3 verdict shapes, examples
  - User (dynamic per call): single doc path + doc current content + commit diff
- Same confidence demotion semantics as drift_interpretation: PROPOSED_EDIT or NO_CHANGE_NEEDED with conf <0.80 → demote to JUDGMENT_REQUIRED with original payload folded into rationale
- Out-of-scope doc_path in proposed_edit (LLM proposes editing a doc NOT in in_scope_docs) → demote to JUDGMENT_REQUIRED with diagnostic message
- Retry policy (30/60/120s) wraps each per-doc LLM call independently
- DriftInterpretationError class reused via import; raise on retry-exhausted

### T002 — audit_ledger.py

- Module path: `scripts/doc_audit/output/audit_ledger.py`
- Mirror drift_ledger structure exactly. Adapt schema per data-model E3:
  - Add `audit_issue: int` field
  - Add `judgment_required_posted` to VALID_OUTCOMES (drift uses `issue_filed` for analogous case; audit posts a comment instead)
  - DEFAULT_LEDGER_PATH = `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`
- Public surface: `append(entry, ledger_path=...)`, `read_window(...)`, `compute_outcome_breakdown(...)`. Mirror drift_ledger.
- CLI subcommands: `summary`, `tail` (skip triage-rate for now; can add later if useful)
- ≥85% test coverage

### T003 — Tests

- `tests/doc_audit/judgment/test_audit_interpretation.py` — mirror `test_drift_interpretation.py`:
  - All 3 verdict shapes per doc
  - Confidence demotion (PROPOSED_EDIT conf <0.80 → JUDGMENT_REQUIRED)
  - Out-of-scope doc_path rejection
  - Retry policy (mock returns invalid, then valid)
  - LLM unavailable after retries → DriftInterpretationError propagates
  - Per-doc isolation: one doc's failure doesn't affect another doc's verdict in the same audit
- `tests/doc_audit/output/test_audit_ledger.py` — mirror `test_drift_ledger.py`:
  - Atomic append (validate-before-write, fsync)
  - Field order matches data-model E3
  - read_window happy path + edge cases
  - VALID_OUTCOMES includes judgment_required_posted

Coverage target ≥85% per module.

## Definition of Done

- 3 subtasks complete; ≥85% coverage on both new modules
- Full doc_audit + escalation + habits + enrichment regression clean
- CLI smoke: both `--help` invocations exit 0

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission audit-interpretation-moment0-01KSBGBS --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-24T03:07:12Z – unknown – Ready for review: per-doc verdicts; 96 tests / 93% coverage on both modules; full doc_audit regression clean (688 passed, 2 pre-existing skips)
- 2026-05-24T03:08:46Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=68650 – Started review via action command
- 2026-05-24T03:11:59Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=68650 – Review passed (codex): 96 tests pass, 93% coverage on both new modules, 688 full doc_audit regression clean, cache-prefix ratio ~99.3%
