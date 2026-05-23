# Tasks: Enforce verbatim pass-through for main-agent delegations

**Mission**: `main-verbatim-passthrough-01KSATRP`
**Branch**: `main`
**Generated**: 2026-05-23

2 work packages, 8 subtasks.

## Subtask Index

| ID | Description | WP |
|---|---|---|
| T001 | Read deployed AGENTS.md from office2; compare against repo copy at scripts/openclaw/agents/main/AGENTS.md; reconcile any drift | WP01 | [D] |
| T002 | Add §"Verbatim pass-through (ABSOLUTE)" near top of repo AGENTS.md with the locked content from research.md D3 | WP01 | [D] |
| T003 | Apply D2 trim cuts; verify file is ≤14,000 source chars | WP01 | [D] |
| T004 | Cross-reference the new section from each delegation section (habits, escalation, tasker stub) | WP01 | [D] |
| T005 | Create scripts/openclaw/helpers/rotate_main_session.py per contracts/rotation-helper.md; use _StructuredArgumentParser pattern (mirror cutover_362) | WP02 | [D] |
| T006 | Tests for rotate_main_session — happy path, dry-run, idempotent re-run, empty sessions dir, marker write failure; ≥85% coverage | WP02 | [D] |
| T007 | Update docs/runbooks/openclaw-agent-setup.md with the cutover sequence (deploy AGENTS.md + rotate session + smoke test); bump frontmatter | WP02 | [D] |
| T008 | Add architecture doc entries: scripts/openclaw/helpers/rotate_main_session.py in service-inventory.json; "main session rotation" in data-flows.json | WP02 | [D] |

## Dependency Graph

```
WP01 (AGENTS.md hardening + trim) ──── independent
WP02 (rotation helper + runbook + arch docs) ──── independent

Both lanes can run in parallel.
```

## Phase 1 — Standing orders

### WP01 — Harden main agent's AGENTS.md

**Goal**: Lock in the verbatim pass-through rule + bring AGENTS.md under the 14K budget.
**Priority**: P0
**Dependencies**: none
**Independent test**: `wc -c scripts/openclaw/agents/main/AGENTS.md` ≤14000; grep `"Verbatim pass-through (ABSOLUTE)"` returns the new section; grep `"FORBIDDEN"` returns at least one match; grep `"--message"` shows cross-references near each delegation section.
**Prompt**: [WP01-agents-md-harden.md](tasks/WP01-agents-md-harden.md)

Included:
- [x] T001 Read deployed + reconcile drift (WP01)
- [x] T002 Add verbatim section (WP01)
- [x] T003 Apply trim cuts (WP01)
- [x] T004 Cross-references from delegation sections (WP01)

## Phase 2 — Rotation helper + docs

### WP02 — Session rotation + runbook + arch docs

**Goal**: Operator can force AGENTS.md reload after deploy; runbook documents the cutover; arch docs name the new helper.
**Priority**: P0
**Dependencies**: none (parallel with WP01)
**Independent test**: `pytest tests/openclaw/helpers/test_rotate_main_session.py -v` ≥85%; `python3 scripts/openclaw/helpers/rotate_main_session.py --help` exits 0; service-inventory.json and data-flows.json parse.
**Prompt**: [WP02-rotation-helper-and-docs.md](tasks/WP02-rotation-helper-and-docs.md)

Included:
- [x] T005 rotate_main_session.py (WP02)
- [x] T006 Tests (WP02)
- [x] T007 Runbook update (WP02)
- [x] T008 Arch docs (WP02)

## Estimated size

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 4 | ~180 |
| WP02 | 4 | ~260 |
| **Total** | **8** | **~440** |

Small focused mission.

## Next step

`spec-kitty agent mission finalize-tasks --mission main-verbatim-passthrough-01KSATRP --json` then implement.
