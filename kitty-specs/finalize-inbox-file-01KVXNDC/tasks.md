# Tasks: Atomic inbox-file finalize helper

**Mission**: finalize-inbox-file-01KVXNDC
**Planning/base branch**: `feat/finalize-inbox-file` · **Merge target**: `feat/finalize-inbox-file`

Three work packages: the helper (WP01), its test suite (WP02), and the agent
cutover + office2 deploy (WP03). WP02 and WP03 both depend on WP01.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Vault-path resolution + input validation | WP01 | |
| T002 | Atomic frontmatter `status: processed` write (idempotent) | WP01 | |
| T003 | Atomic move to processed dir + cross-FS rejection (idempotent) | WP01 | |
| T004 | Daily-log append + bootstrap (idempotent) | WP01 | |
| T005 | Orchestration: exit codes + single-line JSON stdout | WP01 | |
| T006 | Reconcile/reuse existing inbox primitives | WP01 | |
| T007 | Hermetic test harness (tmp vault, registry override, fixtures) | WP02 | |
| T008 | Happy-path + already-finalized + partial-recovery tests | WP02 | [P] |
| T009 | Permission-denied (file write + dir write) tests | WP02 | [P] |
| T010 | Missing-frontmatter + malformed-YAML tests | WP02 | [P] |
| T011 | Cross-filesystem rename-rejected test | WP02 | [P] |
| T012 | Idempotency / no-duplicate-log assertion across re-runs | WP02 | |
| T013 | Author felix-admin-capture standing-orders cutover | WP03 | |
| T014 | Author `deploys/queued/finalize-inbox-file.yaml` manifest | WP03 | |
| T015 | Document rollback + no-rebaseline rationale | WP03 | |

## WP01 — Finalize helper core

**Goal**: Deliver `scripts/inbox/finalize_inbox_file.py` — the deterministic,
atomic-per-step, idempotent finalize operation with exit-code + JSON contract.
**Priority**: P1 (foundational). **Dependencies**: none.
**Independent test**: invoke against a tmp vault file and assert status/move/log +
exit 0 + JSON stdout. **Est. prompt size**: ~280 lines.
**Requirements**: FR-001…FR-009, NFR-001, NFR-002, NFR-003, C-001, C-003, C-004, C-005.

- [ ] T001 Vault-path resolution + input validation (WP01)
- [ ] T002 Atomic frontmatter status write, idempotent (WP01)
- [ ] T003 Atomic move + cross-FS rejection, idempotent (WP01)
- [ ] T004 Daily-log append + bootstrap, idempotent (WP01)
- [ ] T005 Orchestration: exit codes + JSON stdout (WP01)
- [ ] T006 Reconcile/reuse existing inbox primitives (WP01)

Prompt: `tasks/WP01-finalize-helper-core.md`

## WP02 — Test suite

**Goal**: Prove all eight enumerated scenarios (incl. atomicity, idempotency,
error surfacing) in a hermetic tmp vault.
**Priority**: P1. **Dependencies**: WP01.
**Independent test**: `pytest tests/inbox/test_finalize_inbox_file.py -v` green.
**Est. prompt size**: ~260 lines. **Requirements**: NFR-004 (validates FR-001…FR-009, NFR-001…003).

- [ ] T007 Hermetic test harness (tmp vault, registry override) (WP02)
- [ ] T008 Happy + already-finalized + partial-recovery tests (WP02)
- [ ] T009 Permission-denied file + dir tests (WP02)
- [ ] T010 Missing-frontmatter + malformed-YAML tests (WP02)
- [ ] T011 Cross-filesystem rename-rejected test (WP02)
- [ ] T012 Idempotency / no-duplicate-log assertion (WP02)

Prompt: `tasks/WP02-test-suite.md`

## WP03 — Agent cutover + office2 deploy

**Goal**: Switch felix-admin-capture to call the helper as the single finalize
step (with exit-code handling) and deliver helper + standing-orders to office2 via
the manifest pipeline.
**Priority**: P2. **Dependencies**: WP01 (helper must exist before cutover).
**Independent test**: manifest validates against deploy discipline; standing-orders
text unambiguously maps exit 0/1/2 to agent actions.
**Est. prompt size**: ~200 lines. **Requirements**: FR-010, C-002.

- [ ] T013 Author standing-orders cutover (WP03)
- [ ] T014 Author deploys/queued/finalize-inbox-file.yaml manifest (WP03)
- [ ] T015 Document rollback + no-rebaseline rationale (WP03)

Prompt: `tasks/WP03-agent-cutover-deploy.md`

## Dependencies

- WP01 → (none)
- WP02 → WP01
- WP03 → WP01

## MVP

WP01 is the MVP: the helper itself closes the silent-partial-finalize gap. WP02
hardens it; WP03 cuts the agent over and ships it.
