# Tasks: Auto-Rebaseline Security Baselines on Deploy

**Mission**: auto-rebaseline-on-deploy-01KVAYJN | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

MVP scope = WP01 + WP02 + WP03 (the working auto-rebaseline). WP04 ships, documents, and verifies it (post-merge office2 integration canary, T017).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|-----|----------|
| T001 | Extract reusable matcher core into `tooling/scripts/audited_surfaces.py` | WP01 | |
| T002 | Refactor `check_audited_surface_drift.py` to import the shared matcher (CLI/exit unchanged) | WP01 | |
| T003 | Unit tests for shared matcher + CLI parity | WP01 | |
| T004 | Pending-token read/write/clear (atomic) in `rebaseline.py` | WP02 | |
| T005 | Observe step: pulled-range intersection → set/merge pending token | WP02 | |
| T006 | Reconcile step: read-only audit, parse drifted baselines, classify (clean/expected/unexpected) | WP02 | |
| T007 | Rebaseline + verify (rm baselines + audit; count==expected; audit clear) | WP02 | |
| T008 | Unit tests: all classification + failure/stale branches | WP02 | |
| T009 | Wire observe+reconcile into `_tick.py` (capture pre-pull HEAD; call engine) | WP03 | |
| T010 | Observability outcomes on tick log + deploy record | WP03 | |
| T011 | ntfy dispatch for rebaseline_failed / unexpected_drift / stale (dedupe) | WP03 | |
| T012 | Tests: tick integration, no-crash discipline | WP03 | |
| T013 | `deploys/queued/0005-felix-deployer-auto-rebaseline.yaml` (Tier 3 verify manifest) | WP04 | |
| T014 | Update CLAUDE.md Rebaseline-obligation (automation=happy path; manual=out-of-band) | WP04 | |
| T015 | Update `docs/runbooks/security-baseline-ops.md` (auto path + pending token + canary subsection + manual fallback) | WP04 | |
| T016 | Amend charter Rebaseline-Obligation section via charter-sync workflow | WP04 | |
| T017 | Post-merge office2 integration canary verifying SC-001…SC-004 (merge acceptance criterion) | WP04 | |

## Work Packages

### WP01 — Shared audited-surface matcher
- **Goal**: one importable matcher consumed by both the CI reminder and felix-deployer (NFR-001 single source of truth).
- **Priority**: P1 (foundational). **Independent test**: `pytest tests/deploy/test_audited_surfaces.py` + CI script still emits identical annotations.
- **Subtasks**:
  - [x] T001 Extract `load_audited_surfaces`, `changed_files(range)`, `file_matches_pattern`, `match_surfaces` into `tooling/scripts/audited_surfaces.py` (WP01)
  - [x] T002 Refactor `check_audited_surface_drift.py` to import them; byte-stable CLI + exit codes (WP01)
  - [x] T003 Unit tests: matcher globbing (`**`), surface matching, CLI parity (WP01)
- **Dependencies**: none. **Est.**: ~220 lines.

### WP02 — Pending-token rebaseline engine
- **Goal**: deferred-confirm engine in `scripts/deploy/felix-deployer/rebaseline.py` (FR-002/004/005/007/008/009).
- **Priority**: P1. **Independent test**: `pytest tests/deploy/test_rebaseline.py` exercises clean/expected/unexpected/failure/stale.
- **Subtasks**:
  - [ ] T004 Atomic pending-token read/write/clear per data-model.md (WP02)
  - [ ] T005 Observe: intersect pulled-range changed paths (shared matcher) → set/merge token (WP02)
  - [ ] T006 Reconcile: run read-only audit, parse drifted-baseline set, classify D⊆E / D=∅ / D⊄E (WP02)
  - [ ] T007 Rebaseline+verify: rm baselines + audit; assert count==expected_baseline_count + audit clear (WP02)
  - [ ] T008 Unit tests for every branch incl. failure + stale (WP02)
- **Dependencies**: WP01. **Est.**: ~360 lines.

### WP03 — Tick integration + stamping + ntfy
- **Goal**: wire the engine into `run_tick`, record outcomes, alert on failure/unexpected/stale (FR-003/006/009).
- **Priority**: P1. **Independent test**: `pytest tests/deploy/test_tick_rebaseline.py` with git/audit/notify mocked; tick never crashes.
- **Subtasks**:
  - [ ] T009 Capture pre-pull HEAD in `run_tick`; call observe (post-pull) + reconcile (each tick) (WP03)
  - [ ] T010 Emit outcomes (not_required/pending_set/completed/cleared_clean/unexpected_drift/failed/stale) to tick log + deploy record (WP03)
  - [ ] T011 Add ntfy dispatch in `notify.py` for rebaseline_failed/unexpected_drift/stale; dedupe via token `alerts_emitted` (WP03)
  - [ ] T012 Tests: integration + no-crash discipline + NFR-002 tick-window budget assertion (WP03)
- **Dependencies**: WP02. **Est.**: ~330 lines.

### WP04 — Deploy manifest + documentation/charter amendment + integration canary
- **Goal**: ship to office2 via manifest + make automation the documented happy path (C-002/C-004) + own the mission's explicit integration verification (post-merge office2 canary).
- **Priority**: P2 (ships MVP). **Independent test**: manifest validates against `deploys/schema/manifest-v1.schema.json`; docs render; integration-canary procedure (T017) is documented and defined as the merge acceptance criterion.
- **Subtasks**:
  - [ ] T013 `deploys/queued/0005-felix-deployer-auto-rebaseline.yaml` — Tier 3, entrypoint verifies new modules present + importable (WP04)
  - [ ] T014 CLAUDE.md Rebaseline-obligation rewrite (automation happy path; manual out-of-band) (WP04)
  - [ ] T015 `docs/runbooks/security-baseline-ops.md` — auto path + pending token + Integration-verification (canary) subsection + manual fallback (WP04)
  - [ ] T016 Amend charter Rebaseline-Obligation via charter-sync workflow (NOT direct .kittify edit) (WP04)
  - [ ] T017 Document + define the post-merge office2 integration canary (SC-001…SC-004); operator-run post-deploy, recorded as the merge acceptance criterion (WP04)
- **Dependencies**: WP03. **Est.**: ~320 lines.
