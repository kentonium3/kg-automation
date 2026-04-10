# Tasks: Vault Path Registry MVP

**Feature**: 024-vault-path-registry-mvp
**Branch**: main → main
**Date**: 2026-04-10

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create scripts/vault/ directory and paths.json with inbox entry | WP01 | | [D] |
| T002 | Create Python resolver module (resolver.py) | WP01 | [D] |
| T003 | Create shell resolver (paths.sh) | WP01 | [D] |
| T004 | Create README.md documenting schema and usage | WP01 | [D] |
| T005 | Manual verify Python resolver (import and lookup) | WP01 | | [D] |
| T006 | Manual verify shell resolver (source and env var) | WP01 | | [D] |
| T007 | Create targets.json schema (empty targets list) | WP02 | | [D] |
| T008 | Create deploy.py with dry-run default, marker validation, idempotent writes | WP02 | | [D] |
| T009 | Manual verify deploy.py dry-run and apply modes | WP02 | | [D] |
| T010 | Manual verify deploy.py error handling (unknown marker) | WP02 | | [D] |
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
- [x] T001: Create scripts/vault/ directory and paths.json with inbox entry
- [x] T002: Create Python resolver module (resolver.py)
- [x] T003: Create shell resolver (paths.sh)
- [x] T004: Create README.md documenting schema and usage
- [x] T005: Manual verify Python resolver (import and lookup)
- [x] T006: Manual verify shell resolver (source and env var)

**Estimated prompt size**: ~450 lines

---

### WP02: Deploy Script

**Goal**: Build the deploy script that reads the registry, processes template files, and writes resolved output to their targets.

**Priority**: High — required for the migration to work.

**Dependencies**: WP01 (uses paths.json schema and resolver module)

**Prompt file**: [WP02-deploy-script.md](tasks/WP02-deploy-script.md)

**Subtasks**:
- [x] T007: Create targets.json schema (empty targets list)
- [x] T008: Create deploy.py with dry-run default, marker validation, idempotent writes
- [x] T009: Manual verify deploy.py dry-run and apply modes
- [x] T010: Manual verify deploy.py error handling (unknown marker)

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
