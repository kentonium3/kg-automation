# Tasks: Inbox GitHub Issue Routing

**Feature**: 022-inbox-github-issue-routing
**Branch**: main → main
**Date**: 2026-04-09

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Add GitHub issue row to routing table | WP01 | | [D] |
| T002 | Write trigger phrase detection rules | WP01 | | [D] |
| T003 | Write title inference instructions | WP01 | | [D] |
| T004 | Write label inference instructions with label list | WP01 | | [D] |
| T005 | Write gh issue create command template and error handling | WP01 | | [D] |
| T006 | Write confirmation response handling (accept/modify/reject) | WP02 | | [D] |
| T007 | Write out-of-scope handling (multi-repo, insufficient content) | WP02 | | [D] |
| T008 | Add GitHub issue action types to logging table | WP02 | | [D] |
| T009 | Add GitHub section to TOOLS.md | WP02 | | [D] |
| T010 | Update repo-side copies of AGENTS.md and TOOLS.md | WP03 | |
| T011 | Update service-inventory.md | WP03 | [P] |
| T012 | Test feature with a real inbox note | WP03 | |

---

## Work Packages

### WP01: AGENTS.md — Issue Creation Workflow

**Goal**: Add GitHub issue routing to the inbox agent's standing orders — trigger detection, title/label inference, issue creation, and error handling.

**Priority**: High — this is the core capability.

**Dependencies**: None

**Prompt file**: [WP01-agents-issue-creation.md](tasks/WP01-agents-issue-creation.md)

**Subtasks**:
- [x] T001: Add GitHub issue row to routing table
- [x] T002: Write trigger phrase detection rules
- [x] T003: Write title inference instructions
- [x] T004: Write label inference instructions with label list
- [x] T005: Write gh issue create command template and error handling

**Estimated prompt size**: ~400 lines

---

### WP02: AGENTS.md — Confirmation, Logging, and Tools

**Goal**: Add WhatsApp confirmation flow, out-of-scope handling, action logging, and TOOLS.md GitHub reference.

**Priority**: High — completes the interaction loop.

**Dependencies**: WP01

**Prompt file**: [WP02-agents-confirmation-logging.md](tasks/WP02-agents-confirmation-logging.md)

**Subtasks**:
- [x] T006: Write confirmation response handling (accept/modify/reject)
- [x] T007: Write out-of-scope handling (multi-repo, insufficient content)
- [x] T008: Add GitHub issue action types to logging table
- [x] T009: Add GitHub section to TOOLS.md

**Estimated prompt size**: ~300 lines

---

### WP03: Repo Sync and Validation

**Goal**: Sync office2 agent files to repo, update service inventory, and test the feature end-to-end.

**Priority**: High — ensures repo reflects deployed state and feature works.

**Dependencies**: WP02

**Prompt file**: [WP03-repo-sync-validation.md](tasks/WP03-repo-sync-validation.md)

**Subtasks**:
- [ ] T010: Update repo-side copies of AGENTS.md and TOOLS.md
- [ ] T011: Update service-inventory.md
- [ ] T012: Test feature with a real inbox note

**Estimated prompt size**: ~250 lines

---

## Dependency Graph

```
WP01 (issue creation workflow)
└─→ WP02 (confirmation + logging + tools)
    └─→ WP03 (repo sync + test)
```

Sequential — each WP builds on the previous. WP01 and WP02 both modify AGENTS.md on office2.

## Size Validation

| WP | Subtasks | Est. Lines | Status |
|---|---|---|---|
| WP01 | 5 | ~400 | ✓ Ideal range |
| WP02 | 4 | ~300 | ✓ Ideal range |
| WP03 | 3 | ~250 | ✓ Ideal range |

All WPs within ideal sizing.
