# Tasks: Agent Prompt Deploy Pipeline

**Mission**: `agent-prompt-deploy-pipeline-01KTMDDD`
**Mission ID**: `01KTMDDDGGY00S3S3VFGK0Z6P9`
**Branch**: `kitty/mission-agent-prompt-deploy-pipeline-01KTMDDD`
**Planning base / merge target**: `main`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-06-08

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Discovery functions: `is_in_scope` + `iter_agents` (tests-first + impl) | WP01 | |
| T002 | MD5 + `atomic_copy` (tests-first + impl, preserve mode) | WP01 | |
| T003 | `git_pull` subprocess wrapper (tests-first + impl, ff-only + exit codes) | WP01 | |
| T004 | Audit log primitives: `SyncAction`, `TickSummary`, `audit_record`, `audit_append`, `audit_tick_summary` | WP01 | |
| T005 | CLI surface: `parse_args`, `run_tick`, `main` (tests-first + impl, exit codes 0/1/2/3) | WP01 | |
| T006 | Integration test: `run_tick` end-to-end with mocked git_pull + tempdir source/dest/audit | WP01 | |
| T007 | Coverage gate verification: pytest --cov ≥90% line / ≥85% branch | WP01 | |
| T008 | Author `agent-prompt-sync.service` (oneshot unit) | WP02 | [P] |
| T009 | Author `agent-prompt-sync.timer` (OnUnitInactiveSec=300s) | WP02 | [P] |
| T010 | Document unit verification: `systemd-analyze --user verify` in unit header comments | WP02 | |
| T011 | Update `service-inventory.json` (new sync service + main.source_in_repo) | WP03 | [P] |
| T012 | Update `signal-to-doc-map.json` (agent-prompt-changed change_class) | WP03 | [P] |
| T013 | Update `service-inventory.md` narrative (Deploy Pipeline section) | WP03 | [P] |
| T014 | Update `openclaw-agent-setup.md` runbook (Deploy pipeline section) | WP03 | [P] |
| T015 | Create `agent-prompt-sync-ops.md` runbook (install + verify + troubleshoot + rollback) | WP03 | [P] |

`[P]` = safe to parallelize within the WP (different files, no ordering dependency).

## Work Packages

### WP01 — Deploy helper module

**Goal**: Implement the Python stdlib helper (`scripts/openclaw/deploy/deploy_agent_prompts.py`) that the office2 systemd timer invokes every 5 minutes. Includes all discovery, MD5/atomic-copy, git-pull wrapper, audit log, and CLI surfaces.

**Priority**: P1 (foundation — WP02 + WP03 depend on this)
**Independent test**: `python3 -m scripts.openclaw.deploy.deploy_agent_prompts --dry-run` (run from repo root) prints zero or more `DRIFT` lines without modifying any deployed file or writing any audit log entry, and exits 0. `pytest --cov=scripts.openclaw.deploy tests/openclaw/test_deploy_agent_prompts.py` passes the ≥90%/85% coverage gate.

**Estimated prompt size**: ~450 lines (7 subtasks × ~60 lines/subtask)
**Dependencies**: none
**Prompt file**: [tasks/WP01-deploy-helper-module.md](./tasks/WP01-deploy-helper-module.md)

#### Included subtasks

- [x] T001 Discovery functions: `is_in_scope` + `iter_agents` (tests-first + impl) (WP01)
- [x] T002 MD5 + `atomic_copy` (tests-first + impl, preserve mode) (WP01)
- [x] T003 `git_pull` subprocess wrapper (tests-first + impl, ff-only + exit codes) (WP01)
- [x] T004 Audit log primitives: `SyncAction`, `TickSummary`, `audit_record`, `audit_append`, `audit_tick_summary` (WP01)
- [x] T005 CLI surface: `parse_args`, `run_tick`, `main` (tests-first + impl, exit codes 0/1/2/3) (WP01)
- [x] T006 Integration test: `run_tick` end-to-end with mocked git_pull + tempdir source/dest/audit (WP01)
- [x] T007 Coverage gate verification: pytest --cov ≥90% line / ≥85% branch (WP01)

#### Implementation sketch

1. Start with T001 — test fixtures for `is_in_scope` + `iter_agents` first, then production functions.
2. T002 builds on T001's tempdir fixture pattern for atomic_copy mode-preservation tests.
3. T003 uses `subprocess.run` mocking (`unittest.mock.patch` on `subprocess.run`); assert on argv list.
4. T004 dataclasses are pure data + thin emit helpers; tests check JSON serialization shape per `contracts/audit-log-jsonl.md`.
5. T005 wires it all together; exit-code tests dominate.
6. T006 is the end-to-end smoke: build a fake repo tree + fake service-inventory.json + fake deploy dirs; assert one tick produces the expected audit log + file states.
7. T007 confirms coverage gate from clean checkout.

#### Risks

- Coverage gate (NFR-003) requires both line AND branch ≥ thresholds. Defensive branches (e.g., `if dst.exists(): preserve_mode` where the else path is impossible in production paths) may need `# pragma: no branch` per `[[reference_pytest_branch_coverage_pragma]]`.
- Mocking `subprocess.run` for git_pull risks mis-testing real shell semantics. Mitigation: assert on argv list passed to subprocess, NOT on shell output parsing. Production git behavior is verified by operator at install time per SC-4.

#### Parallel opportunities

None within WP01 — subtasks are sequential by tests-first dependency.

#### Dependencies

None (foundation).

---

### WP02 — Systemd unit files

**Goal**: Author the user-level systemd service + timer that invokes the deploy helper on office2 every 5 minutes. Unit files live in repo at `scripts/openclaw/deploy/` for operator copy to `~/.config/systemd/user/`.

**Priority**: P2 (deploy surface for WP01)
**Independent test**: `systemd-analyze --user verify ./scripts/openclaw/deploy/agent-prompt-sync.service ./scripts/openclaw/deploy/agent-prompt-sync.timer` returns 0 (syntactically valid units). Manual operator install on office2 (per quickstart.md) results in `systemctl --user list-timers` showing the timer scheduled.

**Estimated prompt size**: ~220 lines (3 subtasks × ~70 lines/subtask, plus boilerplate)
**Dependencies**: WP01
**Prompt file**: [tasks/WP02-systemd-unit-files.md](./tasks/WP02-systemd-unit-files.md)

#### Included subtasks

- [ ] T008 Author `agent-prompt-sync.service` (oneshot unit) (WP02) [P]
- [ ] T009 Author `agent-prompt-sync.timer` (OnUnitInactiveSec=300s) (WP02) [P]
- [ ] T010 Document unit verification: `systemd-analyze --user verify` in unit header comments (WP02)

#### Implementation sketch

1. T008 + T009 can be authored in parallel — they're independent unit files modeled directly on `scripts/sync/systemd/felix-vikunja-sync.{service,timer}` (working precedent on office2 today). Reuse header-comment style with "Operator deploy" instructions.
2. T010 adds `systemd-analyze --user verify` invocation to each unit's header comment block so operators can validate before reload.

#### Risks

- Unit syntax errors silently fail at `systemctl --user daemon-reload`. Mitigation: copy structure verbatim from the working `felix-vikunja-sync` precedent (verified at design time on office2); the only material differences are unit name, description, Documentation= path, and ExecStart command.

#### Parallel opportunities

T008 + T009 in parallel within the WP.

#### Dependencies

WP01 (the service unit's ExecStart references the `-m scripts.openclaw.deploy.deploy_agent_prompts` import path, which must exist).

---

### WP03 — Architecture documentation sync

**Goal**: Update all architecture documentation surfaces enumerated in spec.md § Architecture Documentation Updates: service-inventory.json (new top-level service entry + main.source_in_repo), signal-to-doc-map.json, service-inventory.md narrative, openclaw-agent-setup.md runbook, and a new agent-prompt-sync-ops.md operator runbook.

**Priority**: P2 (DIR-005 mandate; ships with the feature, not deferred)
**Independent test**: `python3 tooling/scripts/validate_docs.py` (the existing kg-automation doc validator) passes; manual inspection confirms each updated file has accurate content referring to the WP01 + WP02 surfaces.

**Estimated prompt size**: ~380 lines (5 subtasks × ~60 lines/subtask, plus per-file context)
**Dependencies**: WP01, WP02
**Prompt file**: [tasks/WP03-architecture-docs.md](./tasks/WP03-architecture-docs.md)

#### Included subtasks

- [ ] T011 Update `service-inventory.json` (new sync service + main.source_in_repo) (WP03) [P]
- [ ] T012 Update `signal-to-doc-map.json` (agent-prompt-changed change_class) (WP03) [P]
- [ ] T013 Update `service-inventory.md` narrative (Deploy Pipeline section) (WP03) [P]
- [ ] T014 Update `openclaw-agent-setup.md` runbook (Deploy pipeline section) (WP03) [P]
- [ ] T015 Create `agent-prompt-sync-ops.md` runbook (install + verify + troubleshoot + rollback) (WP03) [P]

#### Implementation sketch

1. Each subtask is independent — different file each. Can all run in parallel within the WP.
2. T015 (runbook creation) can lift substantial content from `quickstart.md` (already drafted in Phase 1). Don't re-invent.
3. JSON updates (T011, T012) follow the existing schema verbatim — no schema changes.
4. Narrative updates (T013, T014) are additive sections; don't restructure existing content.

#### Risks

- `service-inventory.json` schema is rich and brittle; adding malformed entries fails CI validation. Mitigation: copy structure from the existing `felix-doc-auditor` entry (similar shape: `type: systemd-timer`, `host: office2`, etc.).
- `validate_docs.py` may reject new file types or missing frontmatter. Mitigation: follow the YAML frontmatter convention used by existing runbooks under `docs/runbooks/`.

#### Parallel opportunities

T011, T012, T013, T014, T015 — all independent files, all parallel within the WP.

#### Dependencies

WP01 + WP02 — docs describe the helper + unit files that those WPs deliver.

---

## Phase Notes

- **Phase 1 (Foundation)**: WP01
- **Phase 2 (Deploy Surface)**: WP02 (sequential after WP01)
- **Phase 3 (Doc Sync)**: WP03 (sequential after WP01 + WP02)

No fully-independent WPs; sequential execution per dependency graph. Total expected time: WP01 dominates (the helper module + coverage gate); WP02 and WP03 are quick follow-ons.

## MVP Scope

WP01 alone delivers a runnable helper that an operator can invoke manually. Without WP02 the timer doesn't fire automatically; without WP03 the architecture documentation is stale. **MVP = WP01 + WP02 + WP03** — the whole mission is a single integrated feature, not a phased rollout.

## Test Strategy

Per **DIRECTIVE_034 Test-First Development**:
- Every subtask in WP01 that delivers production code starts with the test scaffolding (test file + fixtures) before the production function.
- Coverage gate (NFR-003): ≥90% line / ≥85% branch on `scripts/openclaw/deploy/deploy_agent_prompts.py`. Enforced via T007.
- Integration test (T006) covers the orchestrator end-to-end with realistic tempdir fixtures.
- WP02 has no automated tests in CI (systemd not in CI sandbox); validation is operator-driven via `systemd-analyze` and post-install observation.
- WP03 leans on existing doc-validator CI (`tooling/scripts/validate_docs.py`).

## Reviewer Guidance

- **WP01**: Focus on (a) coverage gate is genuine (no `pragma` overuse), (b) atomic-copy preserves mode correctly, (c) git_pull bails fast on failure with structured error, (d) exit codes match the contract.
- **WP02**: Focus on (a) unit files match the felix-vikunja-sync precedent in structure, (b) ExecStart uses `-m` form per NFR-005, (c) WorkingDirectory is set, (d) Persistent=true on timer.
- **WP03**: Focus on (a) JSON schemas validate, (b) service-inventory.md narrative is accurate (no stale slug→deploy-dir info), (c) runbook is runnable by an operator who has never seen this codebase.
