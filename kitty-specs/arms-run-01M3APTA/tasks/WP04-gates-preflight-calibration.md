---
work_package_id: WP04
title: Gates, preflight, samplers, calibration
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- FR-001
- FR-010
- FR-013
- NFR-003
- NFR-004
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
phase: Phase 1 - Core
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/gates.py
create_intent:
- scripts/research/arms849/preflight.py
- scripts/research/arms849/gates.py
- scripts/research/arms849/sampler.py
- scripts/research/arms849/calibration.py
- tests/research/test_arms849_gates.py
- tests/research/test_arms849_calibration.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/preflight.py
- scripts/research/arms849/gates.py
- scripts/research/arms849/sampler.py
- scripts/research/arms849/calibration.py
- tests/research/test_arms849_gates.py
- tests/research/test_arms849_calibration.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP04 — Gates, preflight, samplers, calibration

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-arms-run`
- **Final merge target**: `feat/849-arms-run`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Four small modules that decide whether a run may start and what it may claim: the preflight that
runs the oracle-dependent checkers **where the oracle exists** and binds their result into the
run; the in-container gates that compare only to **registered constants**; the two memory
samplers; and the deterministic k calibration with its halt rule. Read first: `contracts/gates.md`
(every row is a gate here), `research.md` D-10, D-11, D-13, D-16; `data-model.md` §Gate;
the existing `check_849_*` modules and `run_849_harness.verify_gates()`.

## Subtasks

### T016 — `preflight.py`: run from the FULL checkout

**Steps**:
1. `run_preflight(repo_root, corpus_dir, export_manifest_path, out_path)`: imports and runs
   `check_849_seed`, `check_849_oracle`, `check_849_freeze`, `check_849_loader` in-process (as
   `verify_gates()` does today), capturing pass/fail and their output tails.
2. **Vacuous-pass guard**: before running, assert `docs/design/research/849-synthesis/oracle/`
   exists and contains the eight oracle YAMLs; if not, refuse — the freeze and oracle checkers
   return an empty list when the oracle is absent and would pass for the wrong reason (Codex
   blocker D-2).
3. Write `preflight.json`: gate results, the three corpus fingerprints, the `record_lines_digest`
   from `arms849.text`, the export's `content_sha`, the source commit, a UTC timestamp; and
   `preflight_sha` = sha256 of the canonical JSON. Refuse to write if any gate failed.

### T017 — `gates.py`: in-container gates

Each gate is a function returning `GateResult(name, passed, detail)`; `run_all(env) -> list`;
any failure refuses with every failing detail printed. Implement, per contracts/gates.md:
`preflight_present_and_matching` (recompute fingerprints and export sha in the container and
compare; every preflight gate passed), `prompt_digest` (`arms849.prompt.verify()` — against the
constant), `question_manifest_digest` (`arms849.questions.verify()`), `oracle_absent` (the
excluded paths do not exist under the run root **and** a static scan of every file under
`scripts/research/arms849/` for `oracle`, `seed/`, `traceability` finds nothing — the scan must
find its own gate module's string literals, so keep those in a data file or build them at runtime
from parts), `boundary` (calls the WP02 self-test), `env_clean` (`OPENAI_API_KEY` unset; caches
present; `torch` not importable; a socket connect to a non-compose host fails), `tokenizer_equivalence`
(`arms849.serving.Tokenizer.equivalence_check` on 100 corpus lines), `substrate_health` (WP02
`health()` with the expected n_ctx and rope settings for the ledger kind), `code_hashes` (recompute
and compare to the header on resume).

### T018 — `sampler.py`

**Steps**: `GttSampler` — a thread sampling `/sys/class/drm/card1/device/mem_info_gtt_used` at
1 Hz (path configurable; when run inside the container, the harness passes the host-mounted
sysfs path or falls back to `/metrics` from llama.cpp if exposed — document which), exposing
`peak_gib`; `RssSampler(container="arms849-falkordb-1")` — `docker stats --no-stream` (or cgroup
memory.current if mounted) at 1 Hz over a window, exposing `peak_mib`. Both are context managers
that never raise into the arm; a sampler failure records `None` with a reason.

### T019 — `calibration.py`

**Steps**: `calibrate(ledger, r_views_by_question, assemble_r_tokens) -> Calibration` implementing
D-10 exactly: require all eight G repeat-1 cells `ok` (else raise `CalibrationPopulationIncomplete`
listing the missing/terminal-error questions — the harness turns that into a `halt` event and a
`blocked` bus post); for k = 1, 2, … compute R's assembled tokens per question via the supplied
callable (records block + top-k events, availability-capped); pick the smallest k whose median is
within `[0.8, 1.2] × median(G repeat-1 assembled tokens)`; if the records block alone exceeds 1.2×
→ `parity: unattainable` with `k = 0`; if no k reaches 0.8× within availability → `k = max
available`, `parity: infeasible`; ties to smaller k. Returns the record fields (k, the eight G
medians, the eight R medians at k, per-question ratio, parity, ts). `ratio_for(question, r_tokens,
calibration)` → float or `"unavailable:<reason>"`.

### T020 — Tests

**Files**: `tests/research/test_arms849_gates.py`, `test_arms849_calibration.py` (~300 lines).
Each gate proven to fail on its injected defect: a preflight run with the oracle dir temporarily
absent refuses (vacuous-pass guard); a preflight.json with one flipped fingerprint fails the
in-container match; a prompt text with one changed character fails `prompt_digest`; a manifest with
one changed text fails; a temp package file containing the string `oracle` fails the static scan;
`OPENAI_API_KEY=x` fails `env_clean`. Calibration: synthetic G medians and R token curves →
deterministic k; `unattainable` when records alone exceed 1.2×; `infeasible` when availability
caps; `CalibrationPopulationIncomplete` when one G repeat-1 cell is `error`; same inputs twice →
identical record. **NFR-003**: `run_all` records its own wall-clock in `preflight.json`/the gate
output and a test asserts the in-container gate set (excluding `substrate_health` waits)
completes in under 5 minutes on the real corpus. **NFR-004**: `GttSampler` exposes
`ceiling_gib = 57.5` and a `breached` flag; a test injects a reading above it and asserts the
flag — the harness (WP08) refuses to start a cell while `breached` is true.

## Definition of Done

- `run_all` green in a real export on office4 (WP10 will re-run it); every gate has a failing
  test; `mark-status T016 T017 T018 T019 T020 --status done`.

## Risks / reviewer guidance

- The static scan must not be defeatable by string concatenation in the arm modules — scan the
  AST for string constants too, and say so in the test.
- Reviewer: run the preflight with the oracle directory renamed and confirm it refuses; that
  refusal is the whole point of T016.
