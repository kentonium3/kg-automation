---
work_package_id: WP05
title: Environment gating, resume proof, pre-merge record
dependencies:
- WP04
requirement_refs:
- FR-009
- FR-014
- FR-015
- NFR-001
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T025
- T026
- T027
- T028
phase: Phase 5 - Verification
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/check_849_premerge.py
create_intent:
- tests/research/conftest.py
- tests/research/test_arms849_resume.py
- scripts/research/check_849_premerge.py
- tests/research/test_check_849_premerge.py
execution_mode: code_change
owned_files:
- tests/research/conftest.py
- tests/research/test_arms849_resume.py
- scripts/research/check_849_premerge.py
- tests/research/test_check_849_premerge.py
- tests/research/test_arms849_integration.py
role: implementer
tracker_refs: []
tags: []
---

# Work Package Prompt: WP05 — Environment gating, resume proof, pre-merge record

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load` (the profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-preconditions`
- **Final merge target**: `feat/849-preconditions`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Make the arms' only coverage a GATE rather than a habit:
- declare the research environment once, with named and counted skips;
- prove resume across real, timestamp-bearing gate phases (C8);
- build the pre-merge checker whose commit-bound record every merge to main cites.

**Read first:**
- `research.md` D-10;
- `quickstart.md` (the live-smoke recipe, steps 0–4);
- `plan.md` § Freeze-time and post-merge steps;
- spec FR-009, FR-014, FR-015, NFR-001, SC-004, SC-007;
- the WP02/WP04 review artifacts, which list the stable node IDs of the live and required tests;
- the existing per-module guards (`importorskip`, `needs_corpus`) in `tests/research/`.

## Subtasks

### T025 — `tests/research/conftest.py` (FR-014)
- One session-scoped declaration of the research environment:
  - `graphiti_core` importable;
  - rendered corpus present;
  - tokenizer and fastembed caches present under `ARMS849_CACHE`.
- Research tests needing it skip with ONE named reason. The counts appear in the terminal summary (a `pytest_terminal_summary` hook).
- The existing per-module guards remain valid and may delegate to it. Do not rewrite other test modules beyond what delegation needs.
- The C8 test reuses the integration tests' serving/G/D/R fakes: move the shared ones into `conftest.py` (this is why WP05 co-owns `test_arms849_integration.py`) rather than duplicating them.
- CI (no research env) must show the named, counted skips and zero collection errors.

### T026 — C8 live-style resume (FR-009; SC-004)
- Drive `live_runtime` through REAL timestamp-bearing gate phases:
  - host gates, then container gates, with a real `up_ts` and an injected `PROCESS_START`;
  - a partial session;
  - a fresh process (a new `PROCESS_START`, new gates), then resume to completion.
  Never use fixed-timestamp fakes; that drift is the named risk. Use the fakes for serving, G, D and R from the integration tests.
- **Positive case:** 100% of earlier rows are byte-identical, and 0 cells are double-recorded.
- **Negative (a):** a failing fresh gate STOPS the session and is recorded.
- **Negative (b):** a session that skipped its gates cannot write a row (WP01's `session_id` binding).
- The test is corpus-dependent, so it must appear as EXECUTED in the pre-merge record, not merely skipped (T027 lists it as required).

### T027 — `scripts/research/check_849_premerge.py` (FR-015; NFR-001)
- Steps:
  1. run the office4 suite under `PYTHONHASHSEED=0` and `3` (with `ARMS849_CACHE`), with junit-xml;
  2. run the fresh-worktree CI simulation: a detached worktree of HEAD, no `build/`, a stub `graphiti_core` on PYTHONPATH raising `ModuleNotFoundError`, then `pytest -q --ignore=docs/archive`. It requires zero failures and zero collection errors, then removes the worktree;
  3. run the live smoke, REQUIRED (quickstart steps 0–4):
     - preparation: export plus preflight at this commit;
     - `substrate up`, capturing `up_ts`;
     - the host gates;
     - `substrate run -- --smoke --up-ts <up_ts> --ledger <runs>/smoke-<ts>.jsonl`;
     - `ARMS849_LIVE=1 pytest <explicit live node IDs>` (never `-m live`);
     - `substrate down` in `finally`.
- A named REQUIRED node list must EXECUTE and PASS on office4. It holds:
  - the precondition tests of FR-001–FR-016, including WP04's live-registration test and WP02's FR-016 expected-hybrid-hit live test;
  - the C8 test;
  - the post-merge C-list tests C-1, C-2 and C-5 from the previous mission.
  Name each C-list test's node explicitly; find them in `kitty-specs/arms-run-01M3APTA/` and the git log.
- The checker reads junit-xml. Any required node that is missing, deselected, skipped or failed makes the record FAIL, whatever pytest's exit code.
- Write a record (JSON) binding the commit SHA, each step's result, skip counts, the required-node verdicts and timestamps. It is INVALID for any other commit; provide a `--verify <record>` mode that checks the record against HEAD.
- Provide `--no-live` only as an explicitly FAILING mode ("record incomplete"), never as a pass.

### T028 — Checker tests
- Use a fake junit-xml and fake subprocess runners. Cover:
  - a missing required node;
  - a skipped one;
  - a failed one;
  - a pytest exit 0 that still has a skipped required node;
  - a collection error in the CI simulation;
  - a record verified against a different commit;
  - a live smoke that failed or was not run.
  Each yields a FAIL record.
- Also test that the checker never leaves a worktree behind: the `finally` path runs under an injected exception.

## Tests (red-first, NFR-002)

- FR-009, FR-014 and FR-015 each have a failing-first test, recorded. For new files, "red" is the test against a stub or absent implementation; say so.

## Definition of Done

- T025–T028 are done.
- The full suite passes on office4 under both seeds.
- The checker's own CI simulation passes.
- The required node list is in the checker, and the review artifact lists where each node comes from.
- Running the full checker (including the live smoke) is a freeze-time step after the mission merge, not this WP's acceptance. But its non-live steps must run cleanly here.

## Risks / reviewer guidance

- **Properties to verify:**
  - a required test that did not execute can never produce a passing record;
  - a record can never validate a different commit;
  - the live smoke cannot be silently omitted;
  - the C8 test uses real timestamp-bearing gate phases, not fixed stamps.
