# Tasks: Backup alerts name why the run failed
**Mission**: `backup-failure-cause-in-alert-01M502K3` · **Issue**: kentonium3/kg-automation#1067 · **Branch**: `fix/backup-failure-cause-in-alert`
Inputs: [spec.md](spec.md) · [plan.md](plan.md) · [contracts/key-ledger-cause-member.md](contracts/key-ledger-cause-member.md) · [data-model.md](data-model.md) · [research.md](research.md)

## Subtask Index
| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `cause` in `KEY_LEDGER_MEMBERS` + rule 9 checks in `check_key_ledger` | WP01 | |
| T002 | Rule 9 tests in `tests/architecture/test_key_ledger_rules.py` | WP01 | |
| T003 | `FAILURE_REASON` sentinel, fatal-branch codes, trap classification in `restic-backup.sh` | WP02 | |
| T004 | Emission tests: one code per fatal exit, `unclassified`, `null` on completion; fifteen-key pin | WP02 | |
| T005 | Inventory: `diagnostic_only.failure_reason`, `cause` member, note/`updated_by` | WP02 | |
| T006 | Reconciliation harness green + docstring prose | WP02 | |
| T007 | Runbook: cause codes + operator action per code | WP03 | |
| T008 | Architecture prose (`service-inventory.md`, `observability-and-alerting.md`) | WP03 | [P] |
| T009 | Add-only dated amendment to the key-ledger contract (rule 1 + rule 9) | WP03 | [P] |
| T010 | Runtime cause reader (total; ignores malformed member) | WP04 | |
| T011 | Enrich every non-ok return of `_probe_freshness_with_ledger` | WP04 | |
| T012 | Canary tests: enrichment, fail-safe, verdict/dedup invariance, injection | WP04 | |
| T013 | Health-check coverage line carries the cause | WP04 | |
| T014 | Docs-coverage test: every declared code appears in the runbook | WP04 | |

## WP01 — Validator learns the `cause` member (rule 9)

**Prompt**: [tasks/WP01-validator-cause-rule.md](tasks/WP01-validator-cause-rule.md) · **Depends on**: none

T001 (WP01)
T002 (WP01)

## WP02 — Backup script records the cause; inventory declares it

**Prompt**: [tasks/WP02-producer-and-declaration.md](tasks/WP02-producer-and-declaration.md) · **Depends on**: WP01

T003 (WP02)
T004 (WP02)
T005 (WP02)
T006 (WP02)

## WP03 — Operator docs and contract amendment

**Prompt**: [tasks/WP03-docs-and-contract.md](tasks/WP03-docs-and-contract.md) · **Depends on**: WP02

T007 (WP03)
T008 (WP03)
T009 (WP03)

## WP04 — Canary and health-check alerts name the cause

**Prompt**: [tasks/WP04-canary-enrichment.md](tasks/WP04-canary-enrichment.md) · **Depends on**: WP02, WP03

T010 (WP04)
T011 (WP04)
T012 (WP04)
T013 (WP04)
T014 (WP04)

## Notes

- **Sequencing**: WP01 → WP02 → WP03 → WP04, strictly serial. The validator must accept `cause` before the inventory declares it. The docs-coverage test in WP04 needs the runbook from WP03.
- **MVP**: WP01 + WP02 + WP04 deliver the alert text; WP03 is the operator documentation.
- **Out of scope** (C-005): dedup, a new alert source, sudoers, the deployed script path.
