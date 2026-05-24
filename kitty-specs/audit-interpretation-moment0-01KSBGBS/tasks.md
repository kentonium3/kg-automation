# Tasks: Audit interpretation Moment 0

3 work packages, lane-a sequential.

## Subtask Index

| ID | Description | WP |
|---|---|---|
| T001 | audit_interpretation.py + prompt + AuditVerdict/AuditInterpretationContext dataclasses (mirror drift_interpretation) | WP01 | [D] |
| T002 | audit_ledger.py (mirror drift_ledger but with audit_issue field + judgment_required_posted outcome) | WP01 | [D] |
| T003 | Tests for audit_interpretation + audit_ledger (≥85% coverage; mock JudgmentClient + JSONL) | WP01 | [D] |
| T004 | Wire audit_interpretation into handle_audit_routing.py no-proposals branch | WP02 | [D] |
| T005 | Extend handle_audit_routing tests for new branch | WP02 | [D] |
| T006 | Add [audit_interpretation] config block; update arch docs + runbook | WP03 | [D] |
| T007 | Cutover step: trigger manual tick to re-process the 11 currently-stuck audits | WP03 | [D] |

## Dependency Graph

WP01 → WP02 → WP03 (sequential, lane-a)

## WP01 — judgment module + ledger

**Goal**: Mirror drift_interpretation + drift_ledger for commit-derived audits.
**Dependencies**: none
**Prompt**: [WP01-judgment-module.md](tasks/WP01-judgment-module.md)

- [x] T001 audit_interpretation.py + prompt (WP01)
- [x] T002 audit_ledger.py (WP01)
- [x] T003 Tests (WP01)

## WP02 — handle_audit_routing integration

**Goal**: Wire interpret_audit into the no-proposals branch with per-verdict routing.
**Dependencies**: WP01
**Prompt**: [WP02-handle-audit-routing-integration.md](tasks/WP02-handle-audit-routing-integration.md)

- [x] T004 Wire interpret_audit + verdict routing (WP02)
- [x] T005 Tests for new branch (WP02)

## WP03 — Config + arch docs + cutover

**Goal**: Config block + arch docs + runbook + replay for the 11 stuck audits.
**Dependencies**: WP02
**Prompt**: [WP03-arch-docs-and-cutover.md](tasks/WP03-arch-docs-and-cutover.md)

- [x] T006 Config + arch docs + runbook (WP03)
- [x] T007 Cutover replay for stuck audits (WP03)

## Estimated size

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 3 | ~1200 |
| WP02 | 2 | ~500 |
| WP03 | 2 | ~250 |
| **Total** | **7** | **~1950** |
