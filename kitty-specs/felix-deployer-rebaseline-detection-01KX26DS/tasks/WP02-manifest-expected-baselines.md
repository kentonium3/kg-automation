---
work_package_id: WP02
title: Manifest expected_baselines (schema + non-exiting validation)
dependencies: []
requirement_refs:
- C-002
- FR-005
- FR-007
- FR-009
- NFR-004
- NFR-005
tracker_refs: []
planning_base_branch: fix/felix-deployer-rebaseline-detection
merge_target_branch: fix/felix-deployer-rebaseline-detection
branch_strategy: Planning artifacts for this mission were generated on fix/felix-deployer-rebaseline-detection. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-deployer-rebaseline-detection unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
- T013
- T014
agent: "claude:opus:python-pedro:implementer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/manifest.py
create_intent: []
execution_mode: code_change
owned_files:
- deploys/schema/manifest-v1.schema.json
- scripts/deploy/lib/manifest.py
- tooling/scripts/audited_surfaces.py
- tests/deploy/test_manifest.py
- tests/deploy/test_manifest_schema.py
- tests/deploy/test_audited_surfaces.py
role: implementer
tags: []
shell_pid: "10726"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries,
and TDD discipline for this WP.

## Objective

Add an optional `expected_baselines` field to the deploy manifest so a CLI-mutation deploy
(e.g. removing an OpenClaw cron via `openclaw cron rm`, which drifts `openclaw-cron.txt`
with no repo-file signal) can declare the baselines it will drift. Validate declared names
against the registry's known-baseline set through a **non-exiting** read so a malformed
registry fails the *manifest*, never the deployer tick.

Read before coding: `../spec.md` (FR-005, FR-007, FR-009; C-002), `../research.md` (R2,
R3), `../data-model.md` (Manifest entity), `../contracts/rebaseline-range-and-baselines-v1.md`
(C6).

## Context

- `deploys/schema/manifest-v1.schema.json` has `additionalProperties: false` and a fixed
  `properties` map — a new field MUST be added to `properties` explicitly or every manifest
  using it fails schema validation.
- `scripts/deploy/lib/manifest.py` — `load_manifest(path)`, `validate_manifest(...)`,
  `validate_manifest_file(...)`. Returns `LibResult`-style results (see `_cli_*` helpers).
- `tooling/scripts/audited_surfaces.py` — `load_audited_surfaces()` **calls `sys.exit(2)`**
  on a missing/malformed registry, and `match_surfaces(...)`. This exiting loader MUST NOT
  be reachable from `validate_manifest` (it runs in the tick's queue loop, outside the
  rebaseline try/except — a `SystemExit` there crashes the deployer; NFR-001).
- The registry's known-baseline set = union of every surface's `affected_baselines` plus
  every `non_repo_baselines[].name`. Verified: exactly the 14 baselines audit.sh emits
  (== `expected_baseline_count`). Names include `openclaw-cron.txt`, `crontabs.txt`,
  `brew-packages.txt`, `hosts-hash.txt`, etc.

---

### T009 — Schema field

**Steps** (`deploys/schema/manifest-v1.schema.json`): add to `properties`:
```json
"expected_baselines": {
  "type": "array",
  "items": { "type": "string" },
  "description": "Baseline filenames this deploy is expected to drift (folded into the felix-deployer rebaseline token). Each must be a known security-monitor baseline; requires audited_surface: true."
}
```
Keep `additionalProperties: false`. Do NOT add it to `required`.

### T010 — Non-exiting registry read + `known_baselines()` helper

**Steps** (`tooling/scripts/audited_surfaces.py`):
1. Add `load_audited_surfaces_or_error() -> tuple[dict | None, str | None]` — read + parse
   the registry, returning `(registry, None)` on success or `(None, "<reason>")` on
   missing/malformed. **No `sys.exit`, no print-to-stderr.** (The existing exiting
   `load_audited_surfaces` stays for the CI path — do not remove it.)
2. Add `known_baselines(registry) -> set[str]` — the union of `affected_baselines` across
   `audited_surfaces` plus `non_repo_baselines[].name`.

### T011 — Validation in `validate_manifest`

**Steps** (`scripts/deploy/lib/manifest.py`): when `expected_baselines` is present:
- Load the registry via `load_audited_surfaces_or_error()`. On error → return an invalid
  result whose message states the registry could not be read (no exit).
- If any declared name ∉ `known_baselines(registry)` → invalid; message names the
  offending value(s) and lists the field is validated against the known set.
- If `audited_surface` is not `true` → invalid; message states `expected_baselines`
  requires `audited_surface: true` (R2 coupling).
- Absent field → unchanged behavior (FR-009).
Wire the same check into `validate_manifest_file` if it validates content separately.

### T012 — Guard test (`tests/deploy/test_audited_surfaces.py`)

Assert `len(known_baselines(load_audited_surfaces())) == 14` and that the set equals the
documented inventory (list the 14 names), so a stale registry name is caught (Codex LOW).

### T013 — Validation tests (`tests/deploy/test_manifest.py`)

- valid: `expected_baselines: ["openclaw-cron.txt"]` + `audited_surface: true` → passes.
- invalid name: `["bogus.txt"]` → fails, message names `bogus.txt`.
- coupling: `["openclaw-cron.txt"]` with `audited_surface: false`/absent → fails.
- **malformed registry**: monkeypatch the registry path to a malformed file → validation
  returns an invalid result and does **NOT** raise `SystemExit` (assert no exit).
- absent field → still valid (regression).

### T014 — Schema tests (`tests/deploy/test_manifest_schema.py`)

- a manifest with `expected_baselines` passes JSON-schema validation;
- an unknown property still fails (`additionalProperties: false` intact).

## Branch Strategy

Planning base and final merge target are both `fix/felix-deployer-rebaseline-detection`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Definition of Done

- All 6 subtasks complete; `pytest tests/deploy/test_manifest.py tests/deploy/test_manifest_schema.py tests/deploy/test_audited_surfaces.py` green.
- `validate_manifest` NEVER reaches `sys.exit` for a bad registry (assert via test).
- The known-baseline guard test pins the count at 14.

## Risks & Reviewer Guidance

- Reviewer: confirm `validate_manifest` uses the non-exiting reader (grep that the exiting
  `load_audited_surfaces` is not called from `manifest.py`); confirm `additionalProperties:
  false` is preserved; confirm the CI reminder consumer (`check_audited_surface_drift.py`)
  is untouched (NFR-005, C-002).

## Activity Log

- 2026-07-09T01:49:25Z – claude:opus:python-pedro:implementer – shell_pid=10726 – Assigned agent via action command
