# Tasks: OpenClaw Skills Deploy/Sync

**Mission**: openclaw-skills-sync-01KXW1DQ (#775) · **Branch**: `feat/openclaw-skills-sync` (single_branch)
**Artifacts**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [quickstart.md](./quickstart.md) · [codex-review-1.md](./codex-review-1.md)

Four work packages. WP01 is the foundation (the sync helper); WP02 (drift check) and WP03 (units +
deploy) both depend only on WP01 and can run in parallel; WP04 (doc-sync) documents all three.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Local `compute_md5` + `atomic_copy` (dest.parent create, mode-preserve, temp-cleanup) | WP01 | |
| T002 | Skill scope enumerator (repo-dir derivation, SKILL.md presence, multi-file warning guard, `--skill` filter, unknown-skill validation) | WP01 | |
| T003 | `sync_skill` (MD5-compare, drift atomic-copy, `*.backup*` ignore, copy/skip/warning/error audit records) | WP01 | |
| T004 | `run_tick` orchestration (deploylock, gitsync advance, exit-code contract, `--dry-run`, tick_summary, `skills-last-tick.json` freshness) | WP01 | |
| T005 | Health watermarks (git-advance + copy-failure) via `alert_bus.emit(...).ok` notifier + skills render | WP01 | |
| T006 | Unit + integration tests for the sync helper (test-first) | WP01 | |
| T007 | Independent drift comparator `skills_drift_check.py` (repo↔deployed MD5, `*.backup*` ignore, orphan detection, exit contract, `--json`) | WP02 | [P] |
| T008 | Register the drift + freshness checks as canary probes (`scripts/canary/registry.py`) | WP02 | [P] |
| T009 | Unit + integration tests for the drift check (drift / clean / orphan / backup-ignored) | WP02 | [P] |
| T010 | `agent-skill-sync.service` (oneshot, `-m` ExecStart, alert-bus EnvironmentFile, TimeoutStartSec) | WP03 | [P] |
| T011 | `agent-skill-sync.timer` (OnUnitInactiveSec=300s, OnBootSec, Persistent) + `systemd-analyze verify` | WP03 | [P] |
| T012 | `deploys/queued/skills-sync.yaml` v1 manifest (tier 3, audited_surface, pre/post verification) | WP03 | [P] |
| T013 | `scripts/deploy/deploy-skills-sync.sh` — HARD verify-before-enable gate (preflight → place → daemon-reload → smoke → enable → assert is-enabled/list-timers, `XDG_RUNTIME_DIR`) | WP03 | [P] |
| T014 | Extend `audited-surfaces.json` globs to cover the new unit + deploy script | WP04 | |
| T015 | `service-inventory.json` + `.md` — new sync service + `skills-last-tick.json` health_check | WP04 | |
| T016 | `data-flows.json` + `.md` + `.view.md` — new repo→office2 skill-sync flow; `service-dependencies.view.md` | WP04 | |
| T017 | `docs/runbooks/agent-skill-sync-ops.md` (new) + `deployment.md` note + `INDEX.md` + `DEVELOPER_PORTAL.md` + roadmap | WP04 | |

---

## WP01 — Skills sync helper (foundation)

- **Goal**: The deterministic sync — enumerate repo skills, MD5-compare against deployed copies,
  atomic-copy drift (creating dest dirs first), copy-only, emit audit + freshness + streak-dedup
  health signals, `--dry-run`, `--skill` filter. Mirrors `deploy_agent_prompts.py` discipline,
  reuses `scripts/deploy/lib/{gitsync,deploylock,health}`, alerts via `scripts.common.alert_bus`.
- **Priority**: P1 (MVP). **Independent test**: `pytest tests/openclaw/deploy/test_deploy_agent_skills.py`.
- **Dependencies**: none.
- **Requirements**: FR-001…FR-008, FR-010, FR-011, FR-015, FR-016, NFR-001…NFR-006.
- **Subtasks**:
  - [ ] T001 Local `compute_md5` + `atomic_copy` (WP01)
  - [ ] T002 Skill scope enumerator + multi-file guard + `--skill` filter (WP01)
  - [ ] T003 `sync_skill` MD5-compare + drift copy + backup-ignore + audit records (WP01)
  - [ ] T004 `run_tick` (deploylock + gitsync + exit codes + dry-run + freshness) (WP01)
  - [ ] T005 Health watermarks via `alert_bus.emit(...).ok` notifier (WP01)
  - [ ] T006 Unit + integration tests (WP01)
- **Est. prompt size**: ~480 lines.

## WP02 — Independent drift check + canary registration

- **Goal**: A standalone comparator independent of the sync code path that MD5-compares repo↔deployed
  per skill, alert-only, ignores `*.backup*`, reports orphans; registered as a canary probe.
- **Priority**: P1. **Independent test**: `pytest tests/openclaw/enforcement/test_skills_drift_check.py`.
- **Dependencies**: WP01 (references the freshness signal + shares the skill-path model; not an import).
- **Requirements**: FR-009, FR-010, FR-014, NFR-003, NFR-006.
- **Subtasks**:
  - [ ] T007 `skills_drift_check.py` comparator (drift + orphan + backup-ignore + exit + `--json`) (WP02)
  - [ ] T008 Register drift + freshness canary probes (WP02)
  - [ ] T009 Unit + integration tests (WP02)
- **Est. prompt size**: ~300 lines.

## WP03 — Systemd units + deploy manifest + entrypoint (hard enable gate)

- **Goal**: Schedule the sync on office2 (systemd `--user` timer) and roll it out via a
  `deploys/queued/` manifest whose entrypoint runs a HARD verify-before-enable gate.
- **Priority**: P1. **Independent test**: `systemd-analyze --user verify` on the units; `bash -n` +
  dry-run of the deploy script; manifest validates against `deploys/schema/manifest-v1.schema.json`.
- **Dependencies**: WP01 (the helper must exist for the smoke to run).
- **Requirements**: FR-008, FR-012, C-002.
- **Subtasks**:
  - [ ] T010 `agent-skill-sync.service` (WP03)
  - [ ] T011 `agent-skill-sync.timer` + `systemd-analyze verify` (WP03)
  - [ ] T012 `deploys/queued/skills-sync.yaml` manifest (WP03)
  - [ ] T013 `deploy-skills-sync.sh` hard verify-before-enable gate (WP03)
- **Est. prompt size**: ~420 lines.

## WP04 — Documentation synchronization + audited-surface globs

- **Goal**: Register the new service/unit/data-flow across the architecture docs, extend the
  audited-surface globs so C-002's rebaseline claim holds, and ship the ops runbook.
- **Priority**: P2 (polish; must land in-mission per DIR-014). **Independent test**:
  `python3 tooling/scripts/validate_docs.py` + `validate_architecture_data.py` pass.
- **Dependencies**: WP01, WP02, WP03 (documents what they build).
- **Requirements**: FR-013.
- **Subtasks**:
  - [ ] T014 Extend `audited-surfaces.json` globs (WP04)
  - [ ] T015 `service-inventory.json` + `.md` + health_check (WP04)
  - [ ] T016 `data-flows.*` + `service-dependencies.view.md` (WP04)
  - [ ] T017 `agent-skill-sync-ops.md` + `deployment.md` + `INDEX.md` + `DEVELOPER_PORTAL.md` + roadmap (WP04)
- **Est. prompt size**: ~360 lines.

---

## Parallelization

- **WP02 ∥ WP03** — both depend only on WP01, touch disjoint files (`enforcement/` + `canary/` vs
  `deploy/` + `deploys/`); safe to run as parallel lanes.
- **WP04** waits on all three (it documents their surfaces).

## MVP

**WP01** is the MVP — a working, tested sync helper. WP02–WP04 harden (independent drift observation),
schedule/deploy, and document.
