# Tasks: Felix Core Digest

**Feature**: 014-felix-core-digest
**Date**: 2026-04-04
**Work Packages**: 6
**Total Subtasks**: 32

---

## Dependency Graph

```
WP01 (Registry + Config)
 ├── WP02 (Log Writer)       ← parallel with WP03
 │    └── WP04 (Agent Docs)
 └── WP03 (summarize.py)     ← parallel with WP02
      └─┬─ WP05 (Infrastructure + Deploy) ← also depends on WP04
         └── WP06 (Documentation)
```

**Parallel opportunity**: WP02 and WP03 run simultaneously after WP01.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Add felix-admin-tasker to agent-registry.json | WP01 | — |
| T002 | Add log_verbosity: "standard" to all three agents in registry | WP01 | — |
| T003 | Implement log_verbosity() in config.py | WP01 | — |
| T004 | Write tests for log_verbosity() in test_config.py | WP01 | — |
| T005 | Write test_log_action.py (all test cases, test-first) | WP02 | [P] |
| T006 | Implement log_action.py CLI interface (argparse) | WP02 | [P] |
| T007 | Implement schema validation (required fields, category enum) | WP02 | — |
| T008 | Implement JSONL serialization, ts/run_id generation, file I/O | WP02 | — |
| T009 | Implement truncation enforcement (120 char max) | WP02 | — |
| T010 | Implement verbosity filtering (reads registry via config.py) | WP02 | — |
| T011 | Create JSONL equivalents of 6 existing Markdown fixtures | WP03 | [P] |
| T012 | Implement parse_jsonl_log() replacing parse_log_file() | WP03 | [P] |
| T013 | Rewrite find_log_files() for per-agent subdirectory walking | WP03 | — |
| T014 | Add malformed JSONL line handling (stderr + skip) | WP03 | — |
| T015 | Update digest output: new paths, generate_digest(), generate_agent_detail() | WP03 | — |
| T016 | Implement 5-day retention and idempotency check | WP03 | — |
| T017 | Update test_summarize.py for JSONL; remove old Markdown fixtures and regex | WP03 | — |
| T018 | Update felix-admin-capture AGENTS.md Action Logging section | WP04 | [P] |
| T019 | Update felix-admin-habits AGENTS.md Action Logging section | WP04 | [P] |
| T020 | Update felix-admin-tasker AGENTS.md Action Logging section | WP04 | [P] |
| T021 | Cross-verify field mappings against research.md R4 | WP04 | — |
| T022 | Create felix-core-digest.timer (systemd user timer) | WP05 | [P] |
| T023 | Create felix-core-digest.service (systemd oneshot) | WP05 | [P] |
| T024 | Create deploy-f014.sh following F013 pattern | WP05 | — |
| T025 | Add gitignore update and validation to deploy script | WP05 | — |
| T026 | Create docs/handbooks/observation-ops.md runbook | WP06 | [P] |
| T027 | Update service-inventory.json (felix-core-digest as type "cron") | WP06 | [P] |
| T028 | Update data-flows.json (observation flow) | WP06 | [P] |
| T029 | Update service-inventory.md | WP06 | — |
| T030 | Update data-flows.md | WP06 | — |
| T031 | Verify JSON-Markdown consistency | WP06 | — |
| T032 | Cross-verify architecture docs reflect deployed state | WP06 | — |

---

## WP01: Registry and Config Foundation

**Prompt**: [tasks/WP01-registry-config-foundation.md](tasks/WP01-registry-config-foundation.md)
**Priority**: Critical (blocks all other WPs)
**Dependencies**: None
**Estimated size**: ~300 lines

### Goal

Establish the registry and config infrastructure that log_action.py and
summarize.py both depend on: add the missing tasker agent to the registry,
add log_verbosity to all agents, and expose the verbosity lookup in config.py.

### Included Subtasks

- [x] T001: Add felix-admin-tasker to agent-registry.json
- [x] T002: Add log_verbosity: "standard" to all three agents in registry
- [x] T003: Implement log_verbosity() in config.py
- [x] T004: Write tests for log_verbosity() in test_config.py

### Risks

- Tasker registry entry must match the schema of existing entries (capture, habits)
- log_verbosity() must follow the exact autonomy_level() pattern

---

## WP02: Log Writer (log_action.py)

**Prompt**: [tasks/WP02-log-writer.md](tasks/WP02-log-writer.md)
**Priority**: High
**Dependencies**: WP01
**Estimated size**: ~500 lines

### Goal

Create log_action.py as the deterministic log writer — the single boundary
between stochastic agent judgment and well-formed JSONL output. Test-first.

### Included Subtasks

- [ ] T005: Write test_log_action.py (all test cases, test-first)
- [ ] T006: Implement log_action.py CLI interface (argparse)
- [ ] T007: Implement schema validation (required fields, category enum)
- [ ] T008: Implement JSONL serialization, ts/run_id generation, file I/O
- [ ] T009: Implement truncation enforcement (120 char max)
- [ ] T010: Implement verbosity filtering (reads registry via config.py)

### Parallel Opportunity

Can run simultaneously with WP03 — no file overlap.

### Risks

- Must handle concurrent appends if multiple agents run simultaneously
- run_id format must be deterministic and unique per run

---

## WP03: summarize.py JSONL Rewrite

**Prompt**: [tasks/WP03-summarize-jsonl-rewrite.md](tasks/WP03-summarize-jsonl-rewrite.md)
**Priority**: High
**Dependencies**: WP01
**Estimated size**: ~500 lines

### Goal

Replace all Markdown regex parsing in summarize.py with JSONL parsing,
update output paths to Agent-Logs/, add 5-day retention, add idempotency,
and rewrite all test fixtures.

### Included Subtasks

- [ ] T011: Create JSONL equivalents of 6 existing Markdown fixtures
- [ ] T012: Implement parse_jsonl_log() replacing parse_log_file()
- [ ] T013: Rewrite find_log_files() for per-agent subdirectory walking
- [ ] T014: Add malformed JSONL line handling (stderr + skip)
- [ ] T015: Update digest output: new paths, generate_digest(), generate_agent_detail()
- [ ] T016: Implement 5-day retention and idempotency check
- [ ] T017: Update test_summarize.py for JSONL; remove old Markdown fixtures and regex

### Parallel Opportunity

Can run simultaneously with WP02 — no file overlap.

### Risks

- Fixture mapping must be exact: same agent names, categories, action text
- Processing layer (filter_actions_by_autonomy, etc.) must work with new dict shape
- Retention must parse dates from filenames, never mtime

---

## WP04: Agent AGENTS.md Updates

**Prompt**: [tasks/WP04-agent-docs-update.md](tasks/WP04-agent-docs-update.md)
**Priority**: Medium
**Dependencies**: WP02
**Estimated size**: ~350 lines

### Goal

Update all three deployed agents' Action Logging sections to reference
log_action.py, with per-agent action types and categories documented.
No fields silently dropped.

### Included Subtasks

- [ ] T018: Update felix-admin-capture AGENTS.md Action Logging section
- [ ] T019: Update felix-admin-habits AGENTS.md Action Logging section
- [ ] T020: Update felix-admin-tasker AGENTS.md Action Logging section
- [ ] T021: Cross-verify field mappings against research.md R4

### Risks

- Each agent has a different logging format today; mappings must be verified
- Habits agent uses Vikunja comments, not file logs — distinction must be clear

---

## WP05: Infrastructure and Deploy

**Prompt**: [tasks/WP05-infrastructure-deploy.md](tasks/WP05-infrastructure-deploy.md)
**Priority**: Medium
**Dependencies**: WP03, WP04
**Estimated size**: ~400 lines

### Goal

Create the systemd timer/service for 15-minute cron, create the deploy script,
and include the gitignore update step for the second-brain repo.

### Included Subtasks

- [ ] T022: Create felix-core-digest.timer (systemd user timer)
- [ ] T023: Create felix-core-digest.service (systemd oneshot)
- [ ] T024: Create deploy-f014.sh following F013 pattern
- [ ] T025: Add gitignore update and validation to deploy script

### Risks

- claude user must be able to enable user timers without sudo
- Deploy script must handle both fresh install and update scenarios

---

## WP06: Documentation and Architecture

**Prompt**: [tasks/WP06-documentation-architecture.md](tasks/WP06-documentation-architecture.md)
**Priority**: Medium
**Dependencies**: WP05
**Estimated size**: ~450 lines

### Goal

Create the operations runbook and update all architecture documentation
to reflect the deployed state.

### Included Subtasks

- [ ] T026: Create docs/handbooks/observation-ops.md runbook
- [ ] T027: Update service-inventory.json (felix-core-digest as type "cron")
- [ ] T028: Update data-flows.json (observation flow)
- [ ] T029: Update service-inventory.md
- [ ] T030: Update data-flows.md
- [ ] T031: Verify JSON-Markdown consistency
- [ ] T032: Cross-verify architecture docs reflect deployed state

### Risks

- JSON and Markdown must stay in sync
- service-inventory.json entry must use updated_by: "F014"
