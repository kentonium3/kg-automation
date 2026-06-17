---
work_package_id: WP01
title: Shared audited-surface matcher
dependencies: []
requirement_refs:
- FR-001
- FR-008
- NFR-001
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
subtasks:
- T001
- T002
- T003
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: tooling/scripts/
create_intent:
- tooling/scripts/audited_surfaces.py
- tests/deploy/test_audited_surfaces.py
execution_mode: code_change
owned_files:
- tooling/scripts/audited_surfaces.py
- tooling/scripts/check_audited_surface_drift.py
- tests/deploy/test_audited_surfaces.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your agent profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity,
governance scope, and boundaries for this work package.

## Objective

Extract the reusable audited-surface matching logic from
`tooling/scripts/check_audited_surface_drift.py` into a standalone importable
module so that **both** the CI reminder (existing) and felix-deployer (WP02/WP03)
consume one source of truth. NFR-001 forbids a second pattern list.

Read first: `../spec.md` (FR-001, FR-008, NFR-001), `../research.md` (R3),
`../plan.md` (IC-01).

## Context

`check_audited_surface_drift.py` already contains the exact logic felix-deployer
needs: load `docs/design/architecture/data/audited-surfaces.json`, compute
changed files for a git range, glob-match (with `**` support) changed paths to
surface `patterns`, and return matched surfaces with their `affected_baselines`.
Today that logic is private to the CI script. We extract it; the CI script keeps
its CLI and exit semantics unchanged by importing the shared module.

## Subtasks

### T001 — Create `tooling/scripts/audited_surfaces.py`
Move these functions verbatim (behavior-preserving) into the new module:
- `load_audited_surfaces()` → returns the parsed registry dict (keep the
  `sys.exit(2)` on missing/malformed file, or raise a typed error the callers
  map to exit 2 — preserve the existing exit-2 contract).
- `changed_files(range_spec)` → `git diff --name-only <range>` (or staged when None).
- `file_matches_pattern(path, pattern)` → the `**`-aware glob (keep the
  documented over-match approximation comment).
- `match_surfaces(changed_files, audited)` → list of surfaces with `matched_files`.
Expose `REPO_ROOT` / `AUDITED_SURFACES_PATH` resolution so callers don't
re-derive it. Keep functions pure and import-light (stdlib only).

### T002 — Refactor `check_audited_surface_drift.py` to import the shared module
- Replace the inlined functions with imports from `audited_surfaces`.
- The CLI (`--range`, `--quiet`), stdout summary, GitHub-Actions `::warning`
  annotations, and **exit codes (0 normal, 2 setup-broken)** must be
  **byte-stable**. This is a pure refactor — no behavior change.

### T003 — Unit tests `tests/deploy/test_audited_surfaces.py`
- `file_matches_pattern`: `**/Dockerfile` matches nested + top-level; literal
  patterns; non-matches.
- `match_surfaces`: a changed `scripts/openclaw/openclaw.json` matches the
  `openclaw-config` surface and returns its `affected_baselines`; an unrelated
  path matches nothing.
- Parity: feeding a known changed-set through the shared matcher yields the same
  surfaces the CI script reports (guards NFR-001 against drift).

## Branch Strategy
Planning base: `main`. Final merge target: `main`. Execution worktrees are
allocated per computed lane from `lanes.json` at `spec-kitty implement` time —
do not create worktrees manually. Commit code inside the lane worktree.

## Definition of Done
- `audited_surfaces.py` exists; `check_audited_surface_drift.py` imports it with
  zero behavior change (CLI + exit codes identical).
- `pytest tests/deploy/test_audited_surfaces.py` passes.
- No second copy of surface-pattern logic exists anywhere (NFR-001).

## Risks / Reviewer guidance
- Verify the `**` over-match approximation moved verbatim (don't "fix" it — false
  positives are acceptable for the reminder and the deployer's confirm step gates real action).
- Verify exit-2 on missing/malformed registry is preserved.
- Reviewer: diff the CI script's output before/after on a sample range.
