# F010 Tasks: Obsidian Sync on office2

**Feature**: 010-obsidian-sync-office2
**Branch**: main
**Total work packages**: 4
**Total subtasks**: 15

## Dependency graph

```
WP01 (Service & Scripts)
  ├─► WP02 (Operations Runbook)
  ├─► WP03 (Architecture Docs)
  └─► WP04 (Quickstart & Validation)
```

WP02, WP03, and WP04 can run in parallel after WP01 completes.

## Work packages

### WP01: Systemd service and sync scripts

**Priority**: P0 — foundation
**Dependencies**: none
**Estimated prompt size**: ~350 lines

Create the obsidian-sync systemd user unit for continuous sync, the
vault-snapshot git backup script, the snapshot systemd service and timer
(2AM ET daily), and the `.gitignore` additions for the second-brain repo.

**Included subtasks**:
- [x] T001: Create `scripts/office2/obsidian-sync.service` — systemd user unit for `ob sync --continuous`
- [x] T002: Create `scripts/office2/vault-snapshot.sh` — outbound-only git snapshot script
- [x] T003: Create `scripts/office2/vault-snapshot.service` — systemd unit to run snapshot script
- [x] T004: Create `scripts/office2/vault-snapshot.timer` — systemd timer for 2AM ET daily
- [x] T005: Create `scripts/office2/gitignore-additions.txt` — `.gitignore` additions for second-brain repo

**Prompt file**: [tasks/WP01-service-and-scripts.md](tasks/WP01-service-and-scripts.md)

---

### WP02: Operations runbook

**Priority**: P1 — documentation
**Dependencies**: WP01
**Estimated prompt size**: ~350 lines

Create `docs/handbooks/obsidian-sync-ops.md` covering sync configuration,
status checks, re-authentication, git coexistence strategy, manual sync
triggers, and troubleshooting procedures.

**Included subtasks**:
- [ ] T006: Create runbook with standard kg-automation frontmatter
- [ ] T007: Document sync configuration, status checks, and re-authentication procedures
- [ ] T008: Document git coexistence strategy, snapshot schedule, and troubleshooting

**Prompt file**: [tasks/WP02-operations-runbook.md](tasks/WP02-operations-runbook.md)

---

### WP03: Architecture documentation updates

**Priority**: P1 — documentation
**Dependencies**: WP01
**Estimated prompt size**: ~400 lines

Update architecture JSON files and their markdown narratives to reflect
Obsidian Sync as the live vault sync mechanism and git as the snapshot
backup layer.

**Included subtasks**:
- [ ] T009: Update `docs/design/architecture/data/service-inventory.json` — obsidian-sync entry with correct config, auth method, status
- [ ] T010: Update `docs/design/architecture/data/data-flows.json` — vault sync flow reflecting Obsidian Sync as live mechanism
- [ ] T011: Update `docs/design/architecture/service-inventory.md` — narrative for obsidian-sync service
- [ ] T012: Update `docs/design/architecture/data-flows.md` — narrative for vault sync data flow

**Prompt file**: [tasks/WP03-architecture-docs.md](tasks/WP03-architecture-docs.md)

---

### WP04: Quickstart guide and validation

**Priority**: P2 — polish
**Dependencies**: WP01, WP02, WP03
**Estimated prompt size**: ~300 lines

Finalize the quickstart setup guide with exact commands, expected outputs,
and a validation checklist. This is the document Kent follows to perform
the manual setup steps on office2.

**Included subtasks**:
- [ ] T013: Finalize `kitty-specs/010-obsidian-sync-office2/quickstart.md` with exact file paths and expected outputs
- [ ] T014: Create `scripts/office2/validate-obsidian-sync.sh` — post-setup validation script
- [ ] T015: Add backfill verification and inbox processing trigger instructions

**Prompt file**: [tasks/WP04-quickstart-validation.md](tasks/WP04-quickstart-validation.md)
