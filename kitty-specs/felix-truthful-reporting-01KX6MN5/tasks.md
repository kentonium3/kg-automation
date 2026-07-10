# Tasks: Felix Truthful Reporting Guardrails

**Mission**: felix-truthful-reporting-01KX6MN5 · **Issue**: #683 · **Branch**: `fix/felix-truthful-reporting`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Data model**: [data-model.md](./data-model.md) · **Contracts**: [contracts/detector-cli.md](./contracts/detector-cli.md)

Tests are **required** (DIRECTIVE_034 test-first; SC-005 fail-safe must be proven). Deploy to office2 is **post-merge, operator-run** (not a WP).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Draft canonical truthful-reporting + mechanism-fidelity doctrine block | WP01 | |
| T002 | Add doctrine block to all 7 fleet agent AGENTS.md (+ .tmpl) | WP01 | |
| T003 | Add no-unrequested-infrastructure block to main/AGENTS.md | WP01 | |
| T004 | Add doctrine pointer to the completion-assertion helper (manual/bypass path) | WP01 | |
| T005 | Fleet-guard test: doctrine present in all agents + main block + within budget | WP01 | |
| T006 | Create approved-crons.json baseline (7 legit crons) + schema | WP02 | [P] |
| T007 | `cron_baseline.py` — load/validate baseline | WP02 | |
| T008 | `cron_drift_detector.py` — `detect_cron_drift` pure diff (present/missing/schedule/enabled) | WP02 | |
| T009 | Live-cron enumeration wrapper (`openclaw cron list --json`, tolerant, fail-safe) | WP02 | |
| T010 | Unit tests: drift kinds incl owner-mismatch (mocked CLI JSON) | WP02 | |
| T011 | `completion_assertion.py` — `record_assertion()` + CLI (multi `artifact_ids`), fail-safe append | WP03 | [P] |
| T012 | `assertion_verifier.py` — per-artifact existence check (Vikunja), findings list | WP03 | |
| T013 | Auto-emit hook in `scripts/vikunja/create_task.py` on success (fail-safe) | WP03 | |
| T014 | Unit tests: record roundtrip, multi-artifact, missing, unverifiable, fail-safe | WP03 | |
| T015 | Findings→Alert render + severity map + emit + `drift_resolved` | WP04 | |
| T016 | Seen-findings state: baseline-hashed fingerprint, first/last-seen, 24h re-alert, resolved | WP04 | |
| T017 | `run_trust_scan.py` entrypoint (timer/preflight modes, exit-code contract, fail-safe) | WP04 | |
| T018 | systemd user units `felix-trust-scan.{service,timer}` (≤15 min) | WP04 | |
| T019 | Deploy manifest + `deploy-truthful-reporting.py` entrypoint (install+reload, prompt-sync, self-test) | WP04 | |
| T020 | Unit tests: render/severity, cadence, exit modes, entrypoint dry-run | WP04 | |
| T021 | Update `service-inventory.json` + `.md` (new felix-trust-scan service/timer) | WP05 | [P] |
| T022 | New ops runbook (detector ops, baseline maintenance, rollback) | WP05 | |
| T023 | Update `docs/INDEX.md` + `DEVELOPER_PORTAL.md` for new runbook | WP05 | |
| T024 | Regression-verification checklist (SC-001..005) cross-ref | WP05 | |

## Work Packages

### WP01 — Fleet truthful-reporting doctrine + main infra guardrail

- **Goal**: Encode truthful-reporting + mechanism-fidelity doctrine fleet-wide and a no-unrequested-infrastructure guardrail in `main`. (Prevention layer.)
- **Priority**: P1 (MVP — this is the direct #683 doctrine fix). **Independent test**: fleet-guard test asserts doctrine present in all 7 agents, main-block present, all AGENTS.md within budget.
- **Requirements**: FR-001, FR-002, FR-003. **Dependencies**: none. **Est. prompt**: ~230 lines.
- Subtasks:
  - [ ] T001 Draft canonical doctrine block (WP01)
  - [ ] T002 Apply to 7 fleet AGENTS.md + .tmpl (WP01)
  - [ ] T003 main no-unrequested-infra block (WP01)
  - [ ] T004 Doctrine pointer to assertion helper (WP01)
  - [ ] T005 Fleet-guard doctrine test (WP01)

### WP02 — Cron-drift detector + approved-cron baseline

- **Goal**: Deterministic, agent-independent cron-drift detection (live crons vs approved baseline). The load-bearing detector.
- **Priority**: P1. **Independent test**: unit tests for present/missing/schedule-mismatch/enabled-mismatch/owner-mismatch against mocked `openclaw cron list --json`.
- **Requirements**: FR-003, FR-004, FR-005, FR-006. **Dependencies**: none. **Est. prompt**: ~260 lines.
- Subtasks:
  - [ ] T006 approved-crons.json baseline + schema (WP02) [P]
  - [ ] T007 cron_baseline.py loader (WP02)
  - [ ] T008 cron_drift_detector.py pure diff (WP02)
  - [ ] T009 live-cron enumeration wrapper (WP02)
  - [ ] T010 unit tests (WP02)

### WP03 — Completion-assertion ledger + verifier + Vikunja auto-emit

- **Goal**: Deterministic action ledger auto-emitted by the Vikunja creation helper; verifier grounds asserted artifacts against existence.
- **Priority**: P1. **Independent test**: unit tests for record roundtrip, multi-artifact verify, missing-artifact finding, unverifiable-kind, fail-safe write.
- **Requirements**: FR-001, FR-004, FR-005, FR-006. **Dependencies**: none. **Est. prompt**: ~250 lines.
- Subtasks:
  - [ ] T011 completion_assertion.py record + CLI (WP03) [P]
  - [ ] T012 assertion_verifier.py per-artifact (WP03)
  - [ ] T013 Vikunja create_task.py auto-emit hook (WP03)
  - [ ] T014 unit tests (WP03)

### WP04 — Scan runner, alert render, timer & deploy

- **Goal**: Single scan entrypoint driving WP02+WP03, alert rendering via #701, seen-findings cadence, systemd timer, and the deploy manifest + entrypoint.
- **Priority**: P1. **Independent test**: unit tests for render/severity, seen-findings cadence, exit-code modes, entrypoint dry-run.
- **Requirements**: FR-005, NFR-001, NFR-002. **Dependencies**: WP02, WP03. **Est. prompt**: ~320 lines.
- Subtasks:
  - [ ] T015 findings→Alert render + emit (WP04)
  - [ ] T016 seen-findings state + cadence (WP04)
  - [ ] T017 run_trust_scan.py entrypoint (WP04)
  - [ ] T018 systemd units (WP04)
  - [ ] T019 deploy manifest + entrypoint (WP04)
  - [ ] T020 unit tests (WP04)

### WP05 — Architecture docs, runbook & regression checklist

- **Goal**: Reconcile architecture docs for the new service, add an ops runbook, and record the SC-001..005 regression checklist for the post-merge deploy.
- **Priority**: P2 (docs). **Independent test**: architecture-data validator passes; INDEX/portal links resolve.
- **Requirements**: C-004, NFR-003. **Dependencies**: WP02, WP03, WP04. **Est. prompt**: ~180 lines.
- Subtasks:
  - [ ] T021 service-inventory.json + .md (WP05) [P]
  - [ ] T022 ops runbook (WP05)
  - [ ] T023 INDEX + DEVELOPER_PORTAL (WP05)
  - [ ] T024 regression checklist (WP05)

## Dependencies & lanes

- WP01, WP02, WP03 are independent → parallel lanes.
- WP04 depends on WP02 + WP03.
- WP05 depends on WP02 + WP03 + WP04.

## MVP

WP01 (doctrine) + WP02 (cron-drift detector) are the core #683 fix. WP03 adds the assertion ledger; WP04 wires it to run; WP05 documents.
