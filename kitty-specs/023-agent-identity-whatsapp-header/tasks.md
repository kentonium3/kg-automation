# Tasks: Agent Identity Header in WhatsApp Messages

**Feature**: 023-agent-identity-whatsapp-header
**Branch**: main → main
**Date**: 2026-04-10

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Add header to felix-admin-capture AGENTS.md | WP01 | [P] | [D] |
| T002 | Add header to felix-admin-habits AGENTS.md | WP01 | [D] |
| T003 | Add header to felix-admin-escalation AGENTS.md | WP01 | [D] |
| T004 | Add header to felix-admin-tasker AGENTS.md | WP01 | [D] |
| T005 | Investigate and add header to main agent | WP01 | | [D] |
| T006 | Sync updated AGENTS.md files to repo | WP01 | | [D] |
| T007 | Verify by triggering agent and checking output | WP01 | | [D] |

---

## Work Packages

### WP01: Add Identity Header to All Agents

**Goal**: Add `Sent by <agent-id>:<model-short-name>` as the first line of every WhatsApp message from all Felix agents.

**Priority**: High

**Dependencies**: None

**Prompt file**: [WP01-add-identity-headers.md](tasks/WP01-add-identity-headers.md)

**Subtasks**:
- [x] T001: Add header to felix-admin-capture AGENTS.md
- [x] T002: Add header to felix-admin-habits AGENTS.md
- [x] T003: Add header to felix-admin-escalation AGENTS.md
- [x] T004: Add header to felix-admin-tasker AGENTS.md
- [x] T005: Investigate and add header to main agent
- [x] T006: Sync updated AGENTS.md files to repo
- [x] T007: Verify by triggering agent and checking output

**Estimated prompt size**: ~400 lines

---

## Dependency Graph

```
WP01 (single WP — all work)
```

No dependencies. Single WP.

## Size Validation

| WP | Subtasks | Est. Lines | Status |
|---|---|---|---|
| WP01 | 7 | ~400 | ✓ Ideal range (upper) |
