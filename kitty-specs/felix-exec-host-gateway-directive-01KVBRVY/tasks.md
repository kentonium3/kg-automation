# Tasks: Felix exec host=gateway directive

**Mission**: felix-exec-host-gateway-directive-01KVBRVY
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Source**: GitHub issue [#603](https://github.com/kentonium3/kg-automation/issues/603)

## Overview

A single, cohesive change: add one identical `## Tool use — exec host` hard-rule
section to each of the four Felix sub-agent `AGENTS.md` files, pinning the
OpenClaw `exec` tool to `host=gateway`. One work package; the four file edits are
parallel-safe per file but small enough to belong to one WP.

Deployment (`agent-prompt-sync.service`) and rebaseline (`#618` felix-deployer
observe→reconcile) are **automated post-merge** — no executable code. They are
captured as the WP's post-merge verification checklist and in quickstart.md, not
as separate WPs.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Add `## Tool use — exec host` section to felix-admin-capture/AGENTS.md | WP01 | [P] |
| T002 | Add identical section to felix-admin-habits/AGENTS.md | WP01 | [P] |
| T003 | Add identical section to felix-admin-tasker/AGENTS.md | WP01 | [P] |
| T004 | Add identical section to felix-admin-escalation/AGENTS.md | WP01 | [P] |
| T005 | Verify all four files carry the identical directive (grep) | WP01 | |

## Work Packages

### WP01 — Add exec host=gateway directive to the four Felix sub-agent AGENTS.md files

**Goal**: Every Felix sub-agent is instructed, as a hard rule, to use
`exec host=gateway` and never `host=node`, removing the non-deterministic host
selection that produces false-positive cron-failure alerts (#603).

**Priority**: P1 (and only) — this is the MVP and the whole mission.

**Independent test**: `grep -l "host=gateway" scripts/openclaw/agents/felix-admin-*/AGENTS.md | wc -l` returns 4, and the added section is byte-identical across all four files.

**Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, NFR-001, NFR-002.

**Included subtasks**:

- [x] T001 Add `## Tool use — exec host` section to felix-admin-capture/AGENTS.md (WP01)
- [x] T002 Add identical section to felix-admin-habits/AGENTS.md (WP01)
- [x] T003 Add identical section to felix-admin-tasker/AGENTS.md (WP01)
- [x] T004 Add identical section to felix-admin-escalation/AGENTS.md (WP01)
- [x] T005 Verify all four files carry the identical directive (WP01)

**Implementation sketch**: In each file, insert the identical section at the
shared anchor — immediately after the `## Message identity` section and before
`## Output discipline`. Do not alter any existing content.

**Dependencies**: none.

**Parallel opportunities**: T001–T004 are independent per file; T005 runs after.

**Risks**: Wording must be an unambiguous hard rule and byte-identical across all
four files (NFR-001). Must not disturb existing content (FR-005). Low risk —
additive, single-section edit.

**Estimated prompt size**: ~180 lines.

**Prompt**: [tasks/WP01-add-exec-host-gateway-directive.md](tasks/WP01-add-exec-host-gateway-directive.md)

## Post-merge verification (automated; not an executable WP)

- Deploy: `agent-prompt-sync.service` (5-min timer) copies the edited prompts to office2 — confirm via `ssh office2-claude 'grep -c "host=gateway" /data/services/openclaw/*/AGENTS.md'`.
- Rebaseline: #618 felix-deployer auto-rebaselines `openclaw-config.txt` when the change lands on `main` (via the PR `fix → main`); that PR-merge commit records the outcome.
- Close condition for #603: 7-day window with zero `exec host=node requires a paired node` errors in the gateway journal (see quickstart.md).
