# Work Packages: Pull-Based Deploy Pipeline

**Mission**: `pull-based-deploy-pipeline-01KTYQQS`
**Branch contract**: planning_base=`main`, merge_target=`main`, branch_matches_target=true
**Source spec**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/)

## Overview

8 work packages, ~38 subtasks total, target 200-500 lines per WP prompt. Linear execution order with one explicit parallelization opportunity (WP01 / WP07 / WP08 are independent and could lane).

Sequencing (recommended serial to avoid #1572 parallel-WP status invisibility):
**WP01 → WP07 → WP08 → WP02 → WP03 → WP04 → WP05 → WP06**

| WP | Title | Subtasks | Est. lines | Dependencies | Authoritative surface |
|---|---|---|---|---|---|
| WP01 | Manifest schema + queue layout | T001–T005 (5) | ~280 | — | `deploys/` |
| WP02 | Deploy library foundation (cron, snapshot, verify, manifest, applied) | T006–T010 (5) | ~420 | WP01 | `scripts/deploy/lib/` |
| WP03 | Tier guard + apply orchestrator + library README | T011–T015 (5) | ~340 | WP02 | `scripts/deploy/lib/` |
| WP04 | felix-deployer applier (Python + systemd + DM notify) | T016–T021 (6) | ~480 | WP02, WP03 | `scripts/deploy/felix-deployer/` |
| WP05 | Bootstrap wrapper + retroactive applied entry | T022–T025 (4) | ~290 | WP02, WP03, WP04 | `scripts/deploy/` |
| WP06 | CI tier guard + doctrinal cross-link verification | T026–T029 (4) | ~270 | WP01, WP07, WP08 | `.github/workflows/` |
| WP07 | Doctrinal anchor (charter, runbook, CLAUDE.md, issue templates) | T030–T036 (7) | ~430 | — | `docs/runbooks/deploy/` |
| WP08 | Architecture data updates | T037–T041 (5) | ~250 | — | `docs/design/architecture/data/` |

## Subtask index (reference only — `mark-status` targets the per-WP checkbox rows below)

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `deploys/{queued,applied,failed}/.gitkeep` and `deploys/schema/` dir | WP01 | |
| T002 | Author `deploys/schema/manifest-v1.schema.json` (canonical schema; mirror `contracts/manifest-v1.schema.json`) | WP01 | |
| T003 | Write `deploys/schema/README.md` (1-page summary; link to discipline runbook) | WP01 | |
| T004 | Build positive + negative manifest fixtures under `tests/deploy/fixtures/manifests/` | WP01 | |
| T005 | Write `tests/deploy/test_manifest_schema.py` covering all schema rules from data-model.md | WP01 | |
| T006 | Create `scripts/deploy/lib/__init__.py` with `LibResult` frozen dataclass | WP02 | |
| T007 | Implement `scripts/deploy/lib/cron.py` (openclaw_cron_disable/enable/edit/list) + `tests/deploy/test_cron.py` | WP02 | [P] |
| T008 | Implement `scripts/deploy/lib/snapshot.py` (verify_restic_recent) + `tests/deploy/test_snapshot.py` | WP02 | [P] |
| T009 | Implement `scripts/deploy/lib/verify.py` (verify_file_present, verify_no_stale_literal, redact_secrets) + `tests/deploy/test_verify.py` | WP02 | [P] |
| T010 | Implement `scripts/deploy/lib/manifest.py` (load+validate YAML against schema) and `scripts/deploy/lib/applied.py` (write_applied helper) + their tests | WP02 | [P] |
| T011 | Implement `scripts/deploy/lib/tier.py` (`tier_guard(manifest, mode)`) + `tests/deploy/test_tier.py` | WP03 | |
| T012 | Implement `scripts/deploy/lib/apply.py` (`dry_run_then_apply_gate` orchestrator) + `tests/deploy/test_apply.py` | WP03 | |
| T013 | Write `scripts/deploy/lib/README.md` documenting the full library API per `contracts/deploy-library-api.md` | WP03 | |
| T014 | Add module-as-CLI shims (`python3 -m scripts.deploy.lib.<module>`) for bash callers | WP03 | |
| T015 | Round-trip test: a fixture manifest passes through tier→snapshot→verify→apply orchestrator | WP03 | |
| T016 | Create `scripts/deploy/felix-deployer/__init__.py` and `scripts/deploy/felix-deployer/deployer.py` (tick loop scaffold) | WP04 | |
| T017 | Implement the tick lifecycle in `deployer.py`: `git pull` → scan queue → for each, invoke `lib.apply.dry_run_then_apply_gate` → record outcome + JSONL tick log | WP04 | |
| T018 | Implement `scripts/deploy/felix-deployer/notify.py` (synthesize openclaw cron payload per `contracts/dm-payload-v1.md`; invoke `openclaw cron run felix-deployer-alert`) + `tests/deploy/test_notify.py` | WP04 | |
| T019 | Write `scripts/deploy/felix-deployer/felix-deployer.service` (Type=oneshot user unit) and `felix-deployer.timer` (5-min cadence) | WP04 | |
| T020 | Add `scripts/deploy/felix-deployer/templates/felix-deployer-alert.txt` (the WhatsApp DM template) | WP04 | |
| T021 | Write `tests/deploy/test_deployer.py` (full tick loop with `subprocess.run` mocks for git + openclaw + entrypoints) | WP04 | |
| T022 | Implement `scripts/deploy/deploy-felix-deployer-bootstrap.sh` (dry-run + apply modes; deploys units; registers `felix-deployer-alert` openclaw cron; mirrors `deploy-149.sh` shape) | WP05 | |
| T023 | Bootstrap script writes `deploys/applied/0001-bootstrap-felix-deployer.yaml` after successful apply using `python3 -m scripts.deploy.lib.applied write_applied` | WP05 | |
| T024 | Add manual rollback instructions in script header + a `--rollback` mode that disables timer and removes units | WP05 | |
| T025 | Write `tests/deploy/test_bootstrap_record.py` (validates dry-run output structure + applied YAML schema compliance) | WP05 | |
| T026 | Author `.github/workflows/deploy-manifest-validate.yml` (sets up Python+deps; runs schema validation on `deploys/queued/` and `deploys/applied/`; rejects tier 0; runs cross-link test; <30s budget) | WP06 | |
| T027 | Write `tests/deploy/test_cross_link.py` (walks the doctrinal cross-link graph from plan.md; fails on missing edge) | WP06 | |
| T028 | Add static check in CI: grep for `crontab` literal in `scripts/deploy/lib/` (must be 0 hits OR justified inline) — implements FR-017 in CI | WP06 | |
| T029 | Add tier-0-rejection and schema-invalid integration test cases in `tests/deploy/test_cross_link.py` (run as part of the same workflow) | WP06 | |
| T030 | Rewrite `.kittify/charter/charter.md` Deployment Constraints rule to describe the manifest discipline (replaces existing rule and the proposed #154 amendment) | WP07 | |
| T031 | Run `spec-kitty charter sync`; commit synced doctrine artifacts | WP07 | |
| T032 | Author `docs/runbooks/deploy/discipline.md` (operational how-to + worked examples + library API summary + FR-018 rebaseline reminder) | WP07 | |
| T033 | Rewrite `docs/runbooks/deployment.md` to point at `deploy/discipline.md` (preserve the structural information that's still relevant) | WP07 | |
| T034 | Add "Deploys to office2" section to `CLAUDE.md` (project root); reference the discipline runbook | WP07 | |
| T035 | Add "Deploy required?" prompt + discipline-runbook link to `.github/ISSUE_TEMPLATE/feature.md` | WP07 | |
| T036 | Add "Deploy required?" prompt + discipline-runbook link to `.github/ISSUE_TEMPLATE/infra.md` | WP07 | |
| T037 | Add `felix-deployer` entry to `docs/design/architecture/data/service-inventory.json` | WP08 | |
| T038 | Add `github-to-office2-deploy-pull` flow to `docs/design/architecture/data/data-flows.json` | WP08 | |
| T039 | Add `deploys/` + `scripts/deploy/lib/` paths to `docs/design/architecture/data/audited-surfaces.json` | WP08 | |
| T040 | Add 3 deploy change-classes to `docs/design/architecture/data/signal-to-doc-map.json` (deploy-manifest-added, office2-service-deployment, deploy-library-modified) | WP08 | |
| T041 | Add deployer mutation surfaces to `docs/design/architecture/data/mutation-surfaces.json` | WP08 | |

## Phase 1 — Foundation

### WP01 — Manifest schema + queue layout

**Goal**: Establish the canonical manifest schema and directory layout that everything else depends on.

**Priority**: P1 (foundational)

**Independent test**: `pytest tests/deploy/test_manifest_schema.py` passes; positive + negative fixtures validate as expected.

**Included subtasks** (`mark-status` targets these checkboxes):

- [x] T001 Create `deploys/{queued,applied,failed}/.gitkeep` and `deploys/schema/` (WP01)
- [x] T002 Author `deploys/schema/manifest-v1.schema.json` (WP01)
- [x] T003 Write `deploys/schema/README.md` (WP01)
- [x] T004 Build manifest fixtures under `tests/deploy/fixtures/manifests/` (WP01)
- [x] T005 Write `tests/deploy/test_manifest_schema.py` (WP01)

**Implementation sketch**: Create directory skeleton with .gitkeep; copy `contracts/manifest-v1.schema.json` to `deploys/schema/manifest-v1.schema.json`; write a small README pointing at the discipline runbook (to be written by WP07); build ~6 fixtures (valid Tier 3, valid Tier 2 with verification, missing verification on Tier 1 [should fail], Tier 0 [should fail], applied entry with apply_mode, queued entry); test loops over fixtures.

**Parallel opportunities**: None (small WP).
**Dependencies**: None.
**Risks**: JSON Schema 2020-12 conditional requirements can be finicky (`allOf` + `if`/`then`). Validate against fixtures early.

### WP07 — Doctrinal anchor (charter, runbook, CLAUDE.md, issue templates)

**Goal**: Land the doctrine layer so the discipline is discoverable to future agents via CLAUDE.md, charter, runbook, and issue templates.

**Priority**: P1 (foundational; gates WP06's cross-link test).

**Independent test**: Manual review — every cross-link in plan.md's doctrinal graph resolves. Will be CI-enforced by WP06.

**Included subtasks**:

- [x] T030 Rewrite `.kittify/charter/charter.md` Deployment Constraints rule (WP07)
- [x] T031 Run `spec-kitty charter sync`; commit synced doctrine artifacts (WP07)
- [x] T032 Author `docs/runbooks/deploy/discipline.md` (WP07)
- [x] T033 Rewrite `docs/runbooks/deployment.md` to point at discipline.md (WP07)
- [x] T034 Add "Deploys to office2" section to `CLAUDE.md` (project root) (WP07)
- [x] T035 Add "Deploy required?" prompt to `.github/ISSUE_TEMPLATE/feature.md` (WP07)
- [x] T036 Add "Deploy required?" prompt to `.github/ISSUE_TEMPLATE/infra.md` (WP07)

**Implementation sketch**: Charter rewrite is single rule replacement (bullet 4 of Deployment Constraints — see plan.md Charter Check). Discipline runbook is a 1-2 page operational doc; lean on `quickstart.md` from the planning artifacts. CLAUDE.md gets a 5-10 line section. Issue templates get a checkbox + link.

**Risks**: Charter sync may surface diagnostic mismatches (charter has known tool-registry mismatch per memory `project_charter_tool_registry_mismatch`); proceed anyway, the diagnostic is noise.

### WP08 — Architecture data updates

**Goal**: Capture the deploy pipeline in the canonical machine-readable architecture data.

**Priority**: P1 (foundational; gates WP06's cross-link test for signal-to-doc-map entries).

**Independent test**: `python3 -c "import json; [json.load(open(f)) for f in 'docs/design/architecture/data/*.json'.split()]"` — well-formed JSON; manual spec-check of entries.

**Included subtasks**:

- [x] T037 Add `felix-deployer` entry to `service-inventory.json` (WP08)
- [x] T038 Add `github-to-office2-deploy-pull` flow to `data-flows.json` (WP08)
- [x] T039 Add `deploys/` + `scripts/deploy/lib/` paths to `audited-surfaces.json` (WP08)
- [x] T040 Add 3 deploy change-classes to `signal-to-doc-map.json` (WP08)
- [x] T041 Add deployer mutation surfaces to `mutation-surfaces.json` (WP08)

**Implementation sketch**: Each JSON edit mirrors an existing entry shape (e.g., service-inventory's `felix-doc-auditor` is the canonical template per memory `reference_felix_doc_auditor_ops`). Set `updated_by` to `136`. Update markdown views if present.

**Risks**: signal-to-doc-map currently has 0 deploy entries (per session research). Mapping shape uses `match.source` discriminator — confirm shape from existing audit-driven entries before extending.

## Phase 2 — Library + Applier

### WP02 — Deploy library foundation (cron, snapshot, verify, manifest, applied)

**Goal**: Implement the vetted primitives that all deploy scripts (including the applier itself) will reuse.

**Priority**: P1 (foundational for WP03+).

**Independent test**: `pytest tests/deploy/test_cron.py tests/deploy/test_snapshot.py tests/deploy/test_verify.py tests/deploy/test_manifest.py tests/deploy/test_applied.py` passes; static check finds zero `crontab` literal in `scripts/deploy/lib/`.

**Included subtasks**:

- [x] T006 `lib/__init__.py` with `LibResult` (WP02)
- [x] T007 `lib/cron.py` + `test_cron.py` (WP02)
- [x] T008 `lib/snapshot.py` + `test_snapshot.py` (WP02)
- [x] T009 `lib/verify.py` + `test_verify.py` (WP02)
- [x] T010 `lib/manifest.py` + `lib/applied.py` + their tests (WP02)

**Implementation sketch**: `LibResult` is the frozen dataclass from `contracts/deploy-library-api.md`. Each module is a thin subprocess wrapper around the canonical surface (openclaw CLI for cron; backup log file for snapshot; pathlib + grep-like checks for verify). `manifest.py` loads YAML + validates against schema; `applied.py` writes well-formed YAML to `deploys/applied/`. All mock subprocess in tests; no live calls.

**Parallel opportunities**: T007/T008/T009/T010 can lane if WPs are sliced finer; within this WP they share a single agent context.
**Dependencies**: WP01 (schema for manifest validation).
**Risks**: openclaw CLI surface may have shifted across versions (per memory `reference_openclaw_upgrade_gotchas`). Mock all subprocess calls in tests; verify against `openclaw cron --help` on office2 before declaring done.

### WP03 — Tier guard + apply orchestrator + library README

**Goal**: Compose the lower-level primitives into a canonical apply sequence and document the library.

**Priority**: P1.

**Independent test**: `pytest tests/deploy/test_tier.py tests/deploy/test_apply.py` passes; T015 round-trip test passes.

**Included subtasks**:

- [x] T011 `lib/tier.py` + `test_tier.py` (WP03)
- [x] T012 `lib/apply.py` + `test_apply.py` (WP03)
- [x] T013 `lib/README.md` (WP03)
- [x] T014 Module-as-CLI shims for bash callers (`__main__.py`) (WP03)
- [x] T015 Round-trip integration test (WP03)

**Implementation sketch**: `tier.py` reads `manifest.tier` + the change-risk-taxonomy; returns LibResult with error_code on rejection. `apply.py` orchestrates the canonical sequence from `data-model.md` (tier → snapshot → pre → dry-run → apply → post). Each module also exports a `__main__.py` that maps `argv[1]` to function calls per `contracts/deploy-library-api.md`.

**Dependencies**: WP02.
**Risks**: The `--json` mode of CLI shims must keep machine-parseable output — per memory `feedback_command_formatting` for clean output.

### WP04 — felix-deployer applier (Python + systemd + DM notify)

**Goal**: Build the autonomous office2-side process that reads the queue, applies deploys, and reports.

**Priority**: P1.

**Independent test**: `pytest tests/deploy/test_deployer.py tests/deploy/test_notify.py` passes; the deployer's tick loop is exercised end-to-end with subprocess mocks.

**Included subtasks**:

- [x] T016 `felix-deployer/__init__.py` + `deployer.py` scaffold (WP04)
- [x] T017 `deployer.py` tick lifecycle (WP04)
- [x] T018 `notify.py` + `test_notify.py` (WP04)
- [x] T019 `felix-deployer.service` + `felix-deployer.timer` systemd units (WP04)
- [x] T020 `templates/felix-deployer-alert.txt` (WP04)
- [x] T021 `test_deployer.py` end-to-end (WP04)

**Implementation sketch**: Service is `Type=oneshot`; timer fires every 5 min. Entry script: log `tick_start` → `git pull` → enumerate `deploys/queued/*.yaml` (sorted alphabetical for determinism) → for each, invoke `lib.apply.dry_run_then_apply_gate`; on success git-mv to `applied/<NNNN>-<name>.yaml` (where NNNN is monotonic from `lib.applied.next_seq()`), commit + push; on failure write `failed/<name>-<ts>.yaml`, call `notify.dispatch_failure_dm(payload)`. JSONL log line per tick + per manifest. The `.service` unit references the `claude` user's home for paths.

**Dependencies**: WP02, WP03.
**Risks**:
- Concurrency: `Type=oneshot` natural serialization (per R-02). Verify in test: simulate slow apply, confirm next timer fires no overlap.
- `git pull` failure modes (merge conflict, network) — applier should log + skip, not crash.
- `openclaw cron run` exit semantics — confirm via mock that non-zero exit doesn't trip the applier into a loop.

### WP05 — Bootstrap wrapper + retroactive applied entry

**Goal**: Ship the one-shot bootstrap that deploys the deployer itself, and record the canonical first applied/ entry.

**Priority**: P1.

**Independent test**: `pytest tests/deploy/test_bootstrap_record.py` passes; manual smoke on office2 — `./scripts/deploy/deploy-felix-deployer-bootstrap.sh --dry-run` prints expected actions; `--apply` succeeds end-to-end; `systemctl --user status felix-deployer.timer` shows active.

**Included subtasks**:

- [x] T022 `deploy-felix-deployer-bootstrap.sh` core (WP05)
- [x] T023 Bootstrap writes `deploys/applied/0001-bootstrap-felix-deployer.yaml` (WP05)
- [x] T024 `--rollback` mode + manual rollback header (WP05)
- [x] T025 `tests/deploy/test_bootstrap_record.py` (WP05)

**Implementation sketch**: Mirrors `deploy-149.sh` shape (header, modes, openclaw cron registration). Pre-flight: confirm openclaw cron is healthy via `python3 -m scripts.deploy.lib.cron openclaw_cron_list`. Apply: rsync `scripts/deploy/felix-deployer/` to office2; rsync `scripts/deploy/lib/`; install systemd user units; `systemctl --user daemon-reload`; `systemctl --user enable --now felix-deployer.timer`; register `felix-deployer-alert` openclaw cron via `openclaw cron edit`. On success: `python3 -m scripts.deploy.lib.applied write_applied --name 0001-bootstrap-felix-deployer --apply-mode bootstrap`. Rollback: disable timer, remove units, daemon-reload.

**Dependencies**: WP02, WP03, WP04.
**Risks**: First bootstrap can leave a half-installed state if interrupted; the `--rollback` mode is the operator's recovery path. Pre-flight checks gate apply mode.

## Phase 3 — CI

### WP06 — CI tier guard + doctrinal cross-link verification

**Goal**: Defense-in-depth for tier policy at PR time, and CI enforcement of the doctrinal cross-link graph that makes the discipline discoverable to agents.

**Priority**: P1.

**Independent test**: PR with deliberately-malformed manifest → red build; PR with Tier 0 → red build; PR that breaks a doctrinal cross-link → red build; PR with no manifest change → green build; total CI time <30 s.

**Included subtasks**:

- [ ] T026 `.github/workflows/deploy-manifest-validate.yml` (WP06)
- [ ] T027 `tests/deploy/test_cross_link.py` (WP06)
- [ ] T028 Static `crontab` literal check in `scripts/deploy/lib/` (WP06)
- [ ] T029 Tier-0-rejection and schema-invalid test cases in `test_cross_link.py` (WP06)

**Implementation sketch**: GH Actions workflow runs on `pull_request` and `push` to main. Steps: `actions/setup-python@v5`; `pip install PyYAML jsonschema pytest`; `pytest tests/deploy/test_manifest_schema.py tests/deploy/test_cross_link.py`. Cross-link test walks the graph from plan.md (CLAUDE.md ↔ runbook ↔ charter ↔ signal-to-doc-map ↔ issue templates) using filesystem reads + regex; fails on missing edge or broken link target.

**Dependencies**: WP01 (schema), WP07 (charter + runbook + CLAUDE.md edits), WP08 (signal-to-doc-map entries).
**Risks**: GH Actions runner is short-lived; ensure no shared-state assumptions. The 30s budget includes pip install — use `actions/cache` if needed.

## Notes for orchestration (rc42-specific)

- **#1862/#1764 mitigation**: defer `/spec-kitty.analyze` until the end (just before merge). The implement loop on a multi-WP mission would otherwise be blocked by `stale_analysis_report` after every `mark-status`.
- **#1885 mitigation**: always use the full mission slug `pull-based-deploy-pipeline-01KTYQQS` for `--mission` args; never the mid8.
- **#1832**: implement claim may print "no workspace could be resolved" — cosmetic; use the canonical `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/tasks/WPxx-*.md` prompt path directly.
- **#1572**: WPs sequenced serially in the recommended order; parallel lanes only if explicitly chosen.
- **#1883**: skip `/spec-kitty.accept`; go straight to `spec-kitty merge`.
- **#1887**: expect to re-clean `.worktrees/` tracked pollution post-merge with `git rm -r --cached .worktrees/<slug>-coord/` + cleanup commit.
