# Tasks: Robust Felix-Deployer Rebaseline Detection

**Mission**: felix-deployer-rebaseline-detection-01KX26DS
**Branch**: `fix/felix-deployer-rebaseline-detection`
**Source**: kentonium3/kg-automation#685

Decomposition is by **file ownership** (no two WPs share `owned_files`), because
`rebaseline.py` and `_tick.py` are touched by the watermark, fold, and grace-rule
concerns together and cannot be split across WPs.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | `read_observed_head` / `write_observed_head` (atomic; absent/corrupt → None) | WP01 | |
| T002 | Watermark validity classification + range-base selection | WP01 | |
| T003 | Structured `_record_success` result (capture SHA even if push fails) + wire observe range base | WP01 | |
| T004 | Watermark advance to last own `deploy(applied)` commit; crash-safe | WP01 | |
| T005 | Same-tick clear grace rule in `reconcile()` (`pending_clean`) | WP01 | |
| T006 | `fold_manifest_baselines(...)` + tick collects declared baselines and folds before reconcile | WP01 | |
| T007 | Unit tests in `test_rebaseline.py` (watermark, fold, grace) | WP01 | |
| T008 | Tick tests in `test_tick_rebaseline.py` (out-of-band repro, self-commit skip, push-fail capture, no-crash) | WP01 | |
| T009 | Add optional `expected_baselines` array to `manifest-v1.schema.json` | WP02 | [P] |
| T010 | Non-exiting registry read + `known_baselines()` helper in `audited_surfaces.py` | WP02 | [P] |
| T011 | `validate_manifest`: names ⊆ known baselines; require `audited_surface: true`; visible error | WP02 | [P] |
| T012 | Guard test: derived union == 14 documented baselines | WP02 | [P] |
| T013 | Validation tests in `test_manifest.py` (valid/invalid/coupling/malformed-registry-no-crash) | WP02 | [P] |
| T014 | Schema tests in `test_manifest_schema.py` (field accepted; unknown props still rejected) | WP02 | [P] |
| T015 | Update `CLAUDE.md` happy-path text (out-of-band robustness + watermark) | WP03 | |
| T016 | Update `docs/runbooks/deployment.md` (watermark observe + manifest `expected_baselines`) | WP03 | |
| T017 | Update `docs/runbooks/security-baseline-ops.md` + confirm signal-to-doc-map coverage | WP03 | |

---

## WP01 — Watermark range, fold & grace (rebaseline engine + tick)

**Goal**: Make the observe range watermark-based (complete regardless of which actor
advanced HEAD), fold manifest-declared baselines into the token, and add the same-tick
clear grace rule — all in `rebaseline.py` + `_tick.py`, fully unit-tested.
**Priority**: P1 (contains the primary #685 fix). **MVP**: yes.
**Independent test**: `pytest tests/deploy/test_rebaseline.py tests/deploy/test_tick_rebaseline.py`.
**Dependencies**: none (engine code is unit-tested with constructed manifest dicts).
**Estimated prompt size**: ~520 lines.

- [x] T001 `read_observed_head` / `write_observed_head` (atomic; absent/corrupt → None) (WP01)
- [x] T002 Watermark validity classification + range-base selection (WP01)
- [x] T003 Structured `_record_success` result + wire observe range base (WP01)
- [x] T004 Watermark advance to last own `deploy(applied)` commit; crash-safe (WP01)
- [x] T005 Same-tick clear grace rule in `reconcile()` (`pending_clean`) (WP01)
- [x] T006 `fold_manifest_baselines(...)` + tick collects declared baselines and folds (WP01)
- [x] T007 Unit tests in `test_rebaseline.py` (WP01)
- [x] T008 Tick tests in `test_tick_rebaseline.py` (WP01)

**Dependencies**: none. **Risks**: touching `_record_success`'s return contract — keep
call sites in sync. The grace rule must not permanently withhold a legitimate clear.

## WP02 — Manifest `expected_baselines` (schema + non-exiting validation)

**Goal**: Let a manifest declare the baselines it will drift, validated against the
registry's known-baseline set via a non-exiting read (so a bad registry fails the
manifest, never the tick).
**Priority**: P1. **MVP**: yes (closes the CLI-mutation gap).
**Independent test**: `pytest tests/deploy/test_manifest.py tests/deploy/test_manifest_schema.py tests/deploy/test_audited_surfaces.py`.
**Dependencies**: none.
**Estimated prompt size**: ~360 lines.

- [x] T009 Add optional `expected_baselines` array to `manifest-v1.schema.json` (WP02)
- [x] T010 Non-exiting registry read + `known_baselines()` helper in `audited_surfaces.py` (WP02)
- [x] T011 `validate_manifest`: names ⊆ known baselines; require `audited_surface: true`; visible error (WP02)
- [x] T012 Guard test: derived union == 14 documented baselines (WP02)
- [x] T013 Validation tests in `test_manifest.py` (WP02)
- [x] T014 Schema tests in `test_manifest_schema.py` (WP02)

**Dependencies**: none. **Risks**: must NOT reach the `sys.exit(2)` loader from
`validate_manifest`; `additionalProperties: false` means the field must be added to the
schema `properties` explicitly.

## WP03 — Docs & merge hygiene

**Goal**: Restore the truthfulness of the `CLAUDE.md` "happy path" guarantee, document
watermark + manifest `expected_baselines`, and confirm the signal-to-doc-map targets.
**Priority**: P2. **MVP**: no (docs follow shipped behavior).
**Independent test**: `python tooling/scripts/validate_docs.py` (docs validation) + manual read.
**Dependencies**: WP01, WP02 (docs describe their shipped behavior).
**Estimated prompt size**: ~190 lines.

- [ ] T015 Update `CLAUDE.md` happy-path text (out-of-band robustness + watermark) (WP03)
- [ ] T016 Update `docs/runbooks/deployment.md` (watermark observe + manifest `expected_baselines`) (WP03)
- [ ] T017 Update `docs/runbooks/security-baseline-ops.md` + confirm signal-to-doc-map coverage (WP03)

**Dependencies**: WP01, WP02. **Risks**: missing a doc surface — mitigate via the
`signal-to-doc-map.json` lookup (change classes: `systemd-unit-added-or-modified`,
`deploy-manifest-added`, `runbook-modified`).

---

## Execution notes

- **Parallelization**: WP01 and WP02 are independent and can run in parallel lanes. WP03
  waits on both.
- **MVP scope**: WP01 + WP02 together deliver the #685 fix; WP03 is documentation polish.
- **Coverage**: FR-001..FR-010 are covered by WP01 (001,002,003,004,006,008,009,010) and
  WP02 (005,007,009). WP03 covers the Architecture Impact doc obligations.
