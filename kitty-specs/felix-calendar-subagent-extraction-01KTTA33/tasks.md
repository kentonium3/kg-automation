# Tasks — Felix Calendar Subagent Extraction

**Mission**: `felix-calendar-subagent-extraction-01KTTA33`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md) | **Data model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/) | **Quickstart**: [quickstart.md](./quickstart.md)

**Branch contract**: Planning/base/merge target = `main` (post-FF; rc41 #1784 absorbed at tasks-finalize handoff).

## Subtask Index

| Subtask | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/openclaw/agents/tests/__init__.py` + `conftest.py` | WP01 | — |
| T002 | Create fixture `scripts/openclaw/agents/tests/fixtures/openclaw-sample.json` (sanitized snapshot of office2 openclaw.json shape) | WP01 | [P] |
| T003 | Author `test_agents_md_size.py` with main < 12K + felix-admin-calendar < 12K assertions (red initially) | WP01 | [P] |
| T004 | Author `test_openclaw_config_schema.py` with felix-admin-calendar entry + path pattern + known-model assertions (red initially) | WP01 | [P] |
| T005 | Confirm `pytest scripts/openclaw/agents/tests/` produces expected red state | WP01 | — |
| T006 | Create `scripts/openclaw/agents/felix-admin-calendar/` directory | WP02 | — |
| T007 | Author IDENTITY.md (per felix-admin-habits pattern) | WP02 | [P] |
| T008 | Author SOUL.md (voice + privacy boundary + Output Discipline block) | WP02 | [P] |
| T009 | Author AGENTS.md (charter + calendar event creation handler + clarification reply handler; --agent value updated to felix-admin-calendar) | WP02 | — |
| T010 | Author TOOLS.md (gog references, OAuth notes) | WP02 | [P] |
| T011 | Author USER.md (Kent identity) | WP02 | [P] |
| T012 | Verify pytest WP01 file-size assertion for felix-admin-calendar passes (green) | WP02 | — |
| T013 | Remove calendar handlers from main/AGENTS.md (current lines 259–440) | WP03 | — |
| T014 | Add "Calendar delegation" section in main/AGENTS.md mirroring habit/inbox delegation pattern | WP03 | — |
| T015 | Measure file size; conduct whole-file compression review if over 12K | WP03 | — |
| T016 | Verify final main/AGENTS.md < 12K and semantics preserved (review checklist) | WP03 | — |
| T017 | Verify pytest WP01 main-file assertion passes (green) | WP03 | — |
| T018 | Author deploy script pre-flight block (Restic age, SSH reachable, artifact presence, pytest invocation) | WP04 | — |
| T019 | Author agent-prompt-sync trigger + post-sync verification block | WP04 | — |
| T020 | Author openclaw.json edit block (SSH+jq with backup, idempotency, validation) | WP04 | — |
| T021 | Author service restart + activity check block | WP04 | — |
| T022 | Author journal-watch block (NFR-002 grep) | WP04 | — |
| T023 | Author post-flight reporting block (smoke runbook path, rebaseline command) | WP04 | — |
| T024 | Add rollback documentation in deploy script header + exit-code conventions | WP04 | — |
| T025 | Add felix-admin-calendar entry to `docs/constitution/agent-registry.json` per data-model.md | WP05 | [P] |
| T026 | Update `docs/constitution/AGENT-REGISTRY.md` markdown view | WP05 | [P] |
| T027 | Add felix-admin-calendar service entry to `docs/design/architecture/data/service-inventory.json` | WP05 | [P] |
| T028 | Update `docs/design/architecture/service-inventory.md` narrative | WP05 | [P] |
| T029 | Update `docs/design/architecture/service-dependencies.view.md` diagram | WP05 | — |
| T030 | Verify (and update if needed) `docs/runbooks/openclaw-agent-setup.md` | WP06 | [P] |
| T031 | Verify (and update if needed) `docs/runbooks/agent-prompt-sync-ops.md` | WP06 | [P] |
| T032 | Verify (and update if needed) `docs/design/felix-capability-roadmap.md` calendar capability status | WP06 | [P] |
| T033 | Verify `docs/design/architecture/data/audited-surfaces.json` patterns still cover the new agent dir | WP06 | [P] |
| T034 | Author `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md` per `contracts/smoke-runbook-shape.md` | WP07 | — |
| T035 | Add entry to `docs/INDEX.md` (active docs map) | WP07 | [P] |
| T036 | Add entry to `docs/DEVELOPER_PORTAL.md` (developer onboarding sitemap) | WP07 | [P] |

## Work Packages

### WP01 — Test-first verification helpers

**Goal**: Author the deterministic verification surface (pytest helpers) before any production code. Per DIRECTIVE_034.

**Priority**: P1 (foundation — gates the deploy script and validates spec NFRs)
**Independent test**: `pytest scripts/openclaw/agents/tests/ -v` runs and shows the expected red state (size assertions fail; openclaw schema fixture passes the static shape but felix-admin-calendar entry absent → test failure).
**Estimated prompt size**: ~300 lines (5 subtasks)
**Dependencies**: none
**Prompt file**: [tasks/WP01-test-helpers.md](./tasks/WP01-test-helpers.md)
**Requirements covered**: NFR-001, NFR-004

**Included subtasks**:

- [x] T001 Create `scripts/openclaw/agents/tests/__init__.py` + `conftest.py` (WP01)
- [x] T002 Create fixture `tests/fixtures/openclaw-sample.json` (WP01)
- [x] T003 Author `test_agents_md_size.py` (WP01)
- [x] T004 Author `test_openclaw_config_schema.py` (WP01)
- [x] T005 Confirm pytest runs and produces expected red state (WP01)

**Implementation sketch**: Stand up the test package; write a sanitized openclaw.json fixture (no real auth token); write assertions for char-count + schema; verify pytest discovers and runs the tests. Tests fail initially — that's the test-first discipline.

**Parallel opportunities**: T002/T003/T004 can be authored in parallel after T001 lands the package skeleton.

**Risks**: pytest discovery path collisions with other test trees in the repo; mitigated by self-contained `__init__.py`.

### WP02 — Create felix-admin-calendar agent

**Goal**: Stand up the new OpenClaw subagent's workspace files following the established Felix subagent pattern.

**Priority**: P1 (foundation for FR-002, FR-003, FR-006)
**Independent test**: `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_felix_admin_calendar_agents_md_under_12k` passes (green).
**Estimated prompt size**: ~500 lines (7 subtasks)
**Dependencies**: WP01
**Prompt file**: [tasks/WP02-create-felix-admin-calendar.md](./tasks/WP02-create-felix-admin-calendar.md)
**Requirements covered**: FR-002, FR-003, FR-004, FR-006, NFR-004

**Included subtasks**:

- [ ] T006 Create `scripts/openclaw/agents/felix-admin-calendar/` directory (WP02)
- [ ] T007 Author IDENTITY.md (WP02)
- [ ] T008 Author SOUL.md (WP02)
- [ ] T009 Author AGENTS.md — charter + handlers (WP02)
- [ ] T010 Author TOOLS.md (WP02)
- [ ] T011 Author USER.md (WP02)
- [ ] T012 Verify pytest felix-admin-calendar size assertion green (WP02)

**Implementation sketch**: Mirror `felix-admin-habits` triad as the canonical reference. AGENTS.md content moves from main/AGENTS.md lines 259–440 with `--agent` log_action values updated to `felix-admin-calendar`. Broader calendar-substrate charter prefaces the handlers per spec discovery Q2=A+C.

**Parallel opportunities**: T007/T008/T010/T011 in parallel after T006; T009 is the longest individual subtask (canonical handler content) and benefits from being its own focused pass.

**Risks**: Charter prose drift pushing AGENTS.md over 12K — iterate until under cap per NFR-004 (the pytest assertion gates this).

### WP03 — Tighten main/AGENTS.md

**Goal**: Remove calendar handlers and tighten main/AGENTS.md to fit under the 12K bootstrap context cap, restoring the habit-tracking delegation that was being truncated (FR-001).

**Priority**: P1 (resolves the bug)
**Independent test**: `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_main_agents_md_under_12k` passes (green). Manual review confirms delegation sections (capture, habits, tasker, escalation, calendar) all preserved.
**Estimated prompt size**: ~400 lines (5 subtasks)
**Dependencies**: WP02 (calendar content needs its new home before removal here)
**Prompt file**: [tasks/WP03-tighten-main-agents-md.md](./tasks/WP03-tighten-main-agents-md.md)
**Requirements covered**: FR-001, FR-007, FR-012, NFR-001

**Included subtasks**:

- [ ] T013 Remove calendar handlers (current lines 259–440) (WP03)
- [ ] T014 Add calendar delegation pointer section (~15-20 lines, mirror habit/inbox pattern) (WP03)
- [ ] T015 Compress whole file if still over 12K (WP03)
- [ ] T016 Verify final size < 12K and semantics preserved (WP03)
- [ ] T017 Verify pytest main-file assertion green (WP03)

**Implementation sketch**: T013 is a straight excision of lines 259–440 in the current file. T014 inserts the delegation pointer matching the existing habit/inbox patterns (the new home is `felix-admin-calendar`, with the same dispatch-payload contract per data-model.md). T015 runs only if T013+T014 don't already get under 12K — review every section for compression opportunities while preserving meaning. T016 review by a reviewer with the original main/AGENTS.md side-by-side.

**Parallel opportunities**: None internally — this is a single-file sequential WP.

**Risks**: Compression that removes load-bearing instructions; mitigated by the diff review checklist and operator smoke runbook coverage (WP07).

### WP04 — Deploy script (Bash, strict order-of-operations)

**Goal**: Build `scripts/deploy/deploy-felix-admin-calendar.sh` per DIR-005 strict-order-of-operations pattern, including the rc41 #1784 awareness and rebaseline reminder.

**Priority**: P1 (FR-009, FR-010)
**Independent test**: `bash -n scripts/deploy/deploy-felix-admin-calendar.sh` parses; `shellcheck scripts/deploy/deploy-felix-admin-calendar.sh` passes; deploy script's pre-flight section runs in dry-run mode without errors.
**Estimated prompt size**: ~500 lines (7 subtasks)
**Dependencies**: WP01 (deploy invokes pytest)
**Prompt file**: [tasks/WP04-deploy-script.md](./tasks/WP04-deploy-script.md)
**Requirements covered**: FR-002, FR-004, FR-008, FR-009, FR-010, NFR-002

**Included subtasks**:

- [x] T018 Pre-flight block (Restic age, SSH reachable, artifact presence, pytest invocation) (WP04)
- [x] T019 agent-prompt-sync trigger + post-sync verification (WP04)
- [x] T020 openclaw.json edit block (SSH+jq with backup, idempotency, validation) (WP04)
- [x] T021 Service restart + activity check (WP04)
- [x] T022 Journal-watch (NFR-002) (WP04)
- [x] T023 Post-flight reporting (smoke link, rebaseline command) (WP04)
- [x] T024 Rollback documentation in script header + exit-code conventions (WP04)

**Implementation sketch**: Single Bash file with `set -euo pipefail`; clear stepwise functions; SSH invocations to `office2-claude`; jq mutation matches `contracts/openclaw-json-entry.md` exactly. Idempotency check on T020 (skip if entry already present). Halt on any error with rollback instructions printed.

**Parallel opportunities**: None internally — single-file sequential WP.

**Risks**: CLI flag-shape mismatch (per `feedback_verify_cli_flag_shape`). Mitigation: verify systemctl/jq/journalctl flag shapes by `<cmd> --help` in T018 pre-flight implementation; verify `agent-prompt-sync.service` unit exists by name on office2 in WP04 author's first SSH probe.

### WP05 — Architecture + Constitution doc sync

**Goal**: Update the canonical architecture and constitution data + narrative views to reflect the new felix-admin-calendar agent.

**Priority**: P2 (doc sync per DIR-014)
**Independent test**: `python tooling/scripts/validate_docs.py` passes (or whatever doc-validation entry point is current); reviewer reads service-inventory.json/.md and confirms felix-admin-calendar entry matches existing felix-admin-* shape.
**Estimated prompt size**: ~350 lines (5 subtasks)
**Dependencies**: WP02 (entries describe the new agent)
**Prompt file**: [tasks/WP05-architecture-constitution-docsync.md](./tasks/WP05-architecture-constitution-docsync.md)
**Requirements covered**: FR-005, FR-011

**Included subtasks**:

- [ ] T025 Add felix-admin-calendar entry to `docs/constitution/agent-registry.json` (WP05)
- [ ] T026 Update `docs/constitution/AGENT-REGISTRY.md` markdown view (WP05)
- [ ] T027 Add felix-admin-calendar service entry to `docs/design/architecture/data/service-inventory.json` (WP05)
- [ ] T028 Update `docs/design/architecture/service-inventory.md` narrative (WP05)
- [ ] T029 Update `docs/design/architecture/service-dependencies.view.md` diagram (WP05)

**Implementation sketch**: Use data-model.md as the source-of-truth for entry shape. Reference existing felix-admin-tasker / felix-admin-escalation entries as the canonical template for service-inventory and agent-registry rows. For the dependencies view, add the felix-admin-calendar node and its incoming edge from main (delegation) + outgoing edge to gog/Google Calendar.

**Parallel opportunities**: T025/T026/T027/T028 can be authored in parallel; T029 (diagram) reviews after the others have landed.

**Risks**: Stale narrative views that disagree with JSON authoritative sources (per CLAUDE.md "machine-readable wins"). Mitigation: a reviewer reads narrative + JSON together and flags divergence.

### WP06 — Runbook + roadmap + audited-surfaces verifications

**Goal**: Verify (and update if drifted) the existing runbooks and capability roadmap to confirm the new agent fits the established patterns; check audited-surfaces patterns cover the new directory.

**Priority**: P3 (doc hygiene)
**Independent test**: Manual verification — reviewer reads each doc and confirms it remains accurate post-mission. Audited-surfaces.json pattern `scripts/openclaw/agents/*/AGENTS.md` should glob-match the new `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` without any pattern change needed (T033 verifies this).
**Estimated prompt size**: ~250 lines (4 subtasks)
**Dependencies**: none (purely verification of EXISTING docs; can run any time after WP02 conceptually but is path-independent)
**Prompt file**: [tasks/WP06-runbook-roadmap-verify.md](./tasks/WP06-runbook-roadmap-verify.md)
**Requirements covered**: FR-011

**Included subtasks**:

- [x] T030 Verify `docs/runbooks/openclaw-agent-setup.md` still accurate (WP06)
- [x] T031 Verify `docs/runbooks/agent-prompt-sync-ops.md` still accurate (WP06)
- [x] T032 Verify `docs/design/felix-capability-roadmap.md` calendar capability status; update if drifted (WP06)
- [x] T033 Verify `docs/design/architecture/data/audited-surfaces.json` patterns cover new agent dir (no pattern change expected) (WP06)

**Implementation sketch**: Read each doc top to bottom; for each, decide PASS or UPDATE. Document the decision in the WP's history note so reviewer understands what was checked.

**Parallel opportunities**: All 4 subtasks fully parallel.

**Risks**: Subtle drift in a runbook that the reviewer misses. Mitigation: each subtask requires a written rationale ("verified accurate because <observation>" or "updated section X because <change>").

### WP07 — Smoke runbook + navigation entries

**Goal**: Author the operator smoke runbook (the canonical behavioral verification surface for this mission) and add navigation entries.

**Priority**: P1 (NFR-003 verification path; mission acceptance gate)
**Independent test**: The runbook is structurally complete (all sections from `contracts/smoke-runbook-shape.md` present); INDEX.md and DEVELOPER_PORTAL.md show the new entry in the appropriate section.
**Estimated prompt size**: ~300 lines (3 subtasks)
**Dependencies**: WP02 (runbook references the new agent's expected behavior)
**Prompt file**: [tasks/WP07-smoke-runbook-and-nav.md](./tasks/WP07-smoke-runbook-and-nav.md)
**Requirements covered**: FR-011, NFR-003

**Included subtasks**:

- [ ] T034 Author smoke runbook per contracts/smoke-runbook-shape.md (WP07)
- [ ] T035 Add INDEX.md entry (WP07)
- [ ] T036 Add DEVELOPER_PORTAL.md entry (WP07)

**Implementation sketch**: Follow the shape contract in `contracts/smoke-runbook-shape.md`. Cover all 8 SCs; explicit DM templates per subagent; doc-auditor `last-tick.json` check (separate substrate per F-05 in research); decision criteria block.

**Parallel opportunities**: T035 and T036 can be authored in parallel after T034 (both reference the runbook).

**Risks**: Runbook drift from contract shape. Mitigation: contract IS the spec — implementer follows it line-for-line.

## Execution Phasing

```
Phase 1 (no deps):
  WP01 [P]    — Test helpers
  WP06 [P]    — Runbook verifications

Phase 2 (after WP01):
  WP02 [P]    — Create felix-admin-calendar
  WP04 [P]    — Deploy script

Phase 3 (after WP02):
  WP03        — Tighten main/AGENTS.md (depends on calendar handler having a new home)
  WP05 [P]    — Architecture + Constitution doc sync
  WP07 [P]    — Smoke runbook + nav
```

## MVP Scope

The "smallest deployable shape that satisfies the bug fix":

- WP01 (tests) + WP02 (new agent) + WP03 (tighten main) + WP04 (deploy script)

That's the minimum to deploy + verify NFR-001/002/004 + restore FR-001. Doc sync (WP05/06/07) is mandatory for mission acceptance per DIR-014 but doesn't gate the bug fix.

## Branch Strategy (restate)

- **Planning base**: `main` (post-FF)
- **Merge target**: `main`
- **Execution worktrees**: each lane gets its own `.worktrees/felix-calendar-subagent-extraction-01KTTA33-<mid8>-lane-<x>/` per `lanes.json` (computed by `finalize-tasks`)
