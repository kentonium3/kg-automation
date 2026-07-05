# Tasks: Felix-admin cron path robustness fix

**Mission**: felix-admin-cron-path-fix-01KWQTY3 · **Issue**: #656 · **Branch**: `fix/felix-admin-cron-path-fix`
**Type**: software-dev (bug fix). Tests are required (NFR-002, SC-8, charter DIRECTIVE_034).

6 work packages, 21 subtasks. WPs are file-partitioned (non-overlapping `owned_files`).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Create gateway `PYTHONPATH` systemd drop-in | WP01 | |
| T002 | Deploy entrypoint: install drop-in, reload, restart, verify in-agent | WP01 | |
| T003 | Deploy manifest for the drop-in (Tier-1; post = in-agent env check, SC-10) | WP01 | |
| T004 | `routing_log.py`: path → `/data/services/openclaw/state/`; parent mode 0750/secondbrain | WP02 | [P] |
| T005 | `handle_clarification_state.py`: `.json` path → `/data/...`; explicit mode | WP02 | [P] |
| T006 | Tests: state paths absolute under HOME/cwd monkeypatch; round-trip; modes | WP02 | |
| T007 | `prescan.py`: `DEFAULT_LOG_DIR` → `/home/kgale/second-brain/agents/logs` + docstring | WP03 | [P] |
| T008 | `prescan.py`: bare `from routing_log` → `from scripts.inbox.routing_log` (FR-011) | WP03 | |
| T009 | `append_routing_entry.py`: align `sys.path` hack → package import | WP03 | |
| T010 | Tests: dedup **active** from `/tmp` (no dedup-disabled warning); frontmatter-only dedup | WP03 | |
| T011 | Capture prompts: forensic-log path → vault (absolute); remove false "Working dir" prose | WP04 | [P] |
| T012 | Calendar + main prompts: inline `.jsonl` clarification path → `/data/...` (path only) | WP04 | [P] |
| T013 | Escalation prompt: stale `~/repos/...log_action.py` → `/home/claude/kg-automation/...`; remove false "cwd matters" prose | WP04 | [P] |
| T014 | Tasker prompts: `~/repos/...` + `~/second-brain/logs` refs → absolute (NOT `_private`) | WP04 | [P] |
| T015 | Habits prompt: remove false "cwd matters/ModuleNotFoundError" prose; KEEP `cd &&` belt | WP04 | [P] |
| T016 | Migration entrypoint: snapshot→ensure dir→copy state (perms)→recurse logs→inventory→quarantine→decommission; `--dry-run` | WP05 | |
| T017 | Migration manifest (Tier-2): pre snapshot ≤24h; post state+perms+logs+stray-gone | WP05 | |
| T018 | Tests: dry-run mutates nothing; idempotent; refuse-on-unclassified | WP05 | |
| T019 | Architecture: `service-inventory.{json,md}` — state dir, vault logs, gateway drop-in | WP06 | |
| T020 | Architecture: `data-flows.json` + consult `signal-to-doc-map.json` for other targets | WP06 | |
| T021 | Record rebaseline determination (R6): drop-in = monitored surface → rebaseline; note #621 AGENTS.md gap | WP06 | |

---

## WP01 — Gateway PYTHONPATH drop-in + deploy (foundational guardrail)

- **Goal**: Deliver FR1 as a systemd drop-in so `python3 -m scripts.*` resolves from any cwd for all agents.
- **Priority**: P1 (foundational). **Independent test**: after deploy, an agent/cron subprocess prints `PYTHONPATH=/home/claude/kg-automation` from a non-repo cwd (SC-10).
- **Requirements**: FR-001, FR-002.
- **Prompt**: `tasks/WP01-gateway-pythonpath-dropin.md` (~180 lines)
- **Dependencies**: none.
- **Subtasks**:
  - [x] T001 Create gateway `PYTHONPATH` systemd drop-in (WP01)
  - [x] T002 Deploy entrypoint: install drop-in, reload, restart, verify in-agent (WP01)
  - [x] T003 Deploy manifest for the drop-in (WP01)
- **Risks**: gateway restart is disruptive (Tier-1); env-inheritance must be verified in a real agent subprocess, not an SSH shell. Drop-in avoids #653 ExecStart collision.

## WP02 — Inbox state helpers: relocate + ownership

- **Goal**: Serve both state files from `/data/services/openclaw/state/` with the correct ownership/mode; kill the stray-dir writers (helper side).
- **Priority**: P1. **Independent test**: paths resolve to `/data/...` and are unchanged under monkeypatched HOME/cwd; round-trip read/write works.
- **Requirements**: FR-004, FR-010, FR-012.
- **Prompt**: `tasks/WP02-state-helper-relocation.md` (~200 lines)
- **Dependencies**: none.
- **Subtasks**:
  - [x] T004 `routing_log.py` path + mode (WP02)
  - [x] T005 `handle_clarification_state.py` path + mode (WP02)
  - [x] T006 State-path tests (WP02)

## WP03 — Prescan log-dir + dedup import correctness

- **Goal**: Repoint forensic logs to the vault and fix the bare import that silently disables dedup under the guardrail.
- **Priority**: P1. **Independent test**: a full prescan from `/tmp` emits no "dedup-disabled" warning (SC-8); log dir resolves to the vault.
- **Requirements**: FR-006, FR-011.
- **Prompt**: `tasks/WP03-prescan-logdir-and-imports.md` (~200 lines)
- **Dependencies**: none.
- **Subtasks**:
  - [x] T007 `prescan.py` log dir (WP03)
  - [x] T008 `prescan.py` package-absolute import (WP03)
  - [x] T009 `append_routing_entry.py` import alignment (WP03)
  - [x] T010 Dedup-active + frontmatter-only-dedup tests (WP03)

## WP04 — Agent prompt path/ref reconciliation

- **Goal**: Fix log paths, calendar `.jsonl` state path, and stale/stray refs across agent prompts; remove now-false cwd *warning* prose (keep functional `cd &&`). Audited surface.
- **Priority**: P2. **Independent test**: grep of the prompts finds no `/home/claude/second-brain` and no `~/second-brain` write/log targets (outside `_private`), no `~/repos/kg-automation`.
- **Requirements**: FR-003, FR-006, FR-007, FR-009, FR-010.
- **Prompt**: `tasks/WP04-agent-prompt-path-reconciliation.md` (~260 lines)
- **Dependencies**: none (path strings must match WP02/WP03 constants — stated in prompt).
- **Subtasks**:
  - [x] T011 Capture prompts log path + prose (WP04)
  - [x] T012 Calendar + main `.jsonl` path (WP04)
  - [x] T013 Escalation ref + prose (WP04)
  - [x] T014 Tasker refs (WP04)
  - [x] T015 Habits prose (keep `cd &&`) (WP04)

## WP05 — Migration entrypoint + manifest (Tier-2)

- **Goal**: One-time office2 data migration + safe decommission (atomic copy-before-cutover, quarantine, ownership).
- **Priority**: P1. **Independent test**: `--dry-run` prints the plan and mutates nothing; idempotent; refuses to delete if anything unclassified remains.
- **Requirements**: FR-005, FR-008, FR-012.
- **Prompt**: `tasks/WP05-migration-entrypoint-and-manifest.md` (~280 lines)
- **Dependencies**: WP02, WP03 (final paths).
- **Subtasks**:
  - [x] T016 Migration entrypoint (WP05)
  - [x] T017 Migration manifest (WP05)
  - [x] T018 Migration tests (WP05)

## WP06 — Architecture docs + rebaseline record

- **Goal**: Keep the architecture store truthful (state dir, vault logs, gateway drop-in) and record the rebaseline determination.
- **Priority**: P2. **Independent test**: `validate_architecture_data.py` passes; docs name the new locations.
- **Requirements**: (standing architecture requirement; supports FR-004/006/012 traceability)
- **Prompt**: `tasks/WP06-architecture-docs-and-rebaseline.md` (~160 lines)
- **Dependencies**: WP01, WP02, WP03, WP04, WP05.
- **Subtasks**:
  - [x] T019 service-inventory json+md (WP06)
  - [x] T020 data-flows + signal-to-doc consult (WP06)
  - [x] T021 rebaseline determination record (WP06)

---

## Dependency graph

```
WP01 (guardrail) ─┐
WP02 (state)      ─┼──> WP06 (arch docs)
WP03 (prescan)    ─┤        ^
WP04 (prompts)    ─┘        │
WP02, WP03 ──> WP05 (migration) ──┘
```

MVP = WP01 (the guardrail is the lead fix for the cron failures). WP02+WP03+WP05 deliver the state/log relocation. WP04 is prompt hygiene; WP06 closes the architecture loop.

## Deferred to #658 (not in this mission)
- Removing the functional `cd /home/claude/kg-automation &&` prefixes (guardrail-first: only after SC-10 verified live).
- Unifying the `.json`/`.jsonl` calendar-clarification format duality.
