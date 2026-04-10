# Tasks: Vault Path Registry MVP

**Feature**: 024-vault-path-registry-mvp
**Branch**: main → main
**Date**: 2026-04-10

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create scripts/vault/ directory and paths.json with inbox entry | WP01 | |
| T002 | Create Python resolver module (resolver.py) | WP01 | [P] |
| T003 | Create shell resolver (paths.sh) | WP01 | [P] |
| T004 | Create README.md documenting schema and usage | WP01 | [P] |
| T005 | Manual verify Python resolver (import and lookup) | WP01 | |
| T006 | Manual verify shell resolver (source and env var) | WP01 | |
| T007 | Create targets.json schema (empty targets list) | WP02 | |
| T008 | Create deploy.py with dry-run default, marker validation, idempotent writes | WP02 | |
| T009 | Manual verify deploy.py dry-run and apply modes | WP02 | |
| T010 | Manual verify deploy.py error handling (unknown marker) | WP02 | |
| T011 | Create AGENTS.md.tmpl from current AGENTS.md with {{VAULT_INBOX}} on line 22 | WP03 | |
| T012 | Add felix-admin-capture target entry to targets.json | WP03 | |
| T013 | Run deploy in dry-run, verify expected diff | WP03 | |
| T014 | Run deploy with --apply, verify resolved file matches original | WP03 | |
| T015 | SCP resolved AGENTS.md to office2 and verify | WP03 | |
| T016 | Trigger inbox agent cron, verify no regression | WP03 | |

---

## Work Packages

### WP01: Registry Foundation

**Goal**: Build the path registry data file and both resolver interfaces (Python + shell), plus documentation.

**Priority**: High — foundation for everything else.

**Dependencies**: None

**Prompt file**: [WP01-registry-foundation.md](tasks/WP01-registry-foundation.md)

**Subtasks**:
- [ ] T001: Create scripts/vault/ directory and paths.json with inbox entry
- [ ] T002: Create Python resolver module (resolver.py)
- [ ] T003: Create shell resolver (paths.sh)
- [ ] T004: Create README.md documenting schema and usage
- [ ] T005: Manual verify Python resolver (import and lookup)
- [ ] T006: Manual verify shell resolver (source and env var)

**Estimated prompt size**: ~450 lines

---

### WP02: Deploy Script

**Goal**: Build the deploy script that reads the registry, processes template files, and writes resolved output to their targets.

**Priority**: High — required for the migration to work.

**Dependencies**: WP01 (uses paths.json schema and resolver module)

**Prompt file**: [WP02-deploy-script.md](tasks/WP02-deploy-script.md)

**Subtasks**:
- [ ] T007: Create targets.json schema (empty targets list)
- [ ] T008: Create deploy.py with dry-run default, marker validation, idempotent writes
- [ ] T009: Manual verify deploy.py dry-run and apply modes
- [ ] T010: Manual verify deploy.py error handling (unknown marker)

**Estimated prompt size**: ~400 lines

---

### WP03: Migration and Verification

**Goal**: Migrate the felix-admin-capture AGENTS.md to template-driven form, deploy it, sync to office2, and verify the inbox agent still works.

**Priority**: High — this is the proof-of-methodology deliverable.

**Dependencies**: WP02 (uses the deploy script)

**Prompt file**: [WP03-migration-verification.md](tasks/WP03-migration-verification.md)

**Subtasks**:
- [ ] T011: Create AGENTS.md.tmpl from current AGENTS.md with {{VAULT_INBOX}} on line 22
- [ ] T012: Add felix-admin-capture target entry to targets.json
- [ ] T013: Run deploy in dry-run, verify expected diff
- [ ] T014: Run deploy with --apply, verify resolved file matches original
- [ ] T015: SCP resolved AGENTS.md to office2 and verify
- [ ] T016: Trigger inbox agent cron, verify no regression

**Estimated prompt size**: ~400 lines

---

## Dependency Graph

```
WP01 (registry + resolvers) → WP02 (deploy script) → WP03 (migration)
```

Strictly sequential. Each WP builds on the previous.

## Size Validation

| WP | Subtasks | Est. Lines | Status |
|---|---|---|---|
| WP01 | 6 | ~450 | ✓ Ideal range |
| WP02 | 4 | ~400 | ✓ Ideal range |
| WP03 | 6 | ~400 | ✓ Ideal range |

All WPs within ideal sizing. No ownership conflicts.
