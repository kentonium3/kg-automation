---
work_package_id: WP08
title: Harness integration, CLI, secondary binding, grading export
dependencies:
- WP03
- WP04
- WP05
- WP06
- WP07
requirement_refs:
- C-006
- C-008
- FR-002
- FR-004
- FR-005
- FR-006
- FR-007
- FR-014
- FR-015
- FR-017
- NFR-006
- NFR-008
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
subtasks:
- T031
- T032
- T033
- T034
- T035
phase: Phase 3 - Integration
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/run_849_harness.py
create_intent:
- scripts/research/arms849/grading.py
- tests/research/test_arms849_grading.py
- tests/research/test_arms849_integration.py
execution_mode: code_change
owned_files:
- scripts/research/run_849_harness.py
- scripts/research/arms849/grading.py
- tests/research/test_run_849_harness.py
- tests/research/test_arms849_grading.py
- tests/research/test_arms849_integration.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP08 — Harness integration, CLI, secondary binding, grading export

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

Rebuild `run_849_harness.py` on the modules WP03–WP07 delivered so it becomes the runner the
quickstart names, keeps every property it already has (four-gate precondition, ledger bound to
one corpus, `exceeds_model_context` never averaged), and gains the rest of the spec: attempt
rows, retry via health check, per-attempt timeout, samplers, calibration and the halt rule,
secondary binding, the blinded export. Prove it end to end with **fake arms** — the MVP the tasks
file names. Read first: `contracts/arm-interface.md`, `contracts/ledger-schema.md`,
`contracts/grading-view.md`; `data-model.md` §Cell/§Outcome/§GradingView; the existing
`run_849_harness.py` and its tests (keep every existing test passing, re-pointed to the modules).

## Subtasks

### T031 — The execute loop

**Steps**:
1. `execute(key, corpus_dir, ctx) -> row`: `attempt = ledger.begin_attempt(key)`; replay via
   `load_849_corpus.replay` and narrow via `arm_view` (existing); build `CellContext` (repeat,
   attempt, seed = 1000 + repeat, serving, prompt, embedder, calibration for R, limits,
   ledger_kind); start `GttSampler` (and `RssSampler` for G) as context managers; call the arm
   under a **per-attempt timeout** of 90 minutes (a worker thread + join; on expiry record
   `error: timeout`); catch `ContextExceeded` → `exceeds_model_context` row with `prompt_tokens`
   and `limit_applied`; catch any other exception → run `substrate.health()`; if healthy and
   attempts remain, retry (at most twice total); else `error` row with the cause.
2. G lifecycle: `build_graph` once before a question's repeat 1, `drop_graph` after repeat 3
   (record `GraphStats` on each G row); R lifecycle: when the first R cell is reached, require the
   `calibration` record — if absent, run `calibration.calibrate` (all eight G repeat-1 cells `ok`)
   and write it; on `CalibrationPopulationIncomplete` write a `halt` event, post `blocked` to the
   bus, and stop.
3. Every `ok` row carries all data-model.md fields; `summarise` unchanged in semantics.

### T032 — CLI

`--preflight` (WP04 `run_preflight` from the full checkout; refuses inside the container),
`--gates` (in-container `gates.run_all`, also run automatically before the header), `--status`,
`--grading-view`, `--secondary --primary <ledger>`, `--dry-run`, `--limit`, `--ledger`, `--corpus`,
`--skip-gates` (development only). Bus posts via the existing agent-bus MCP are **not** callable
from a script; instead write `event` rows and print a one-line status the operator relays — say so
in the docstring (FR-017's bus posts are the operator's, driven by `--status`).

### T033 — Secondary binding

`--secondary`: refuses unless the primary ledger at `--primary` is complete (72 cells, zero
`not_implemented`); opens its own ledger with `ServingConfiguration.secondary_yarn()`; runs the
secondary's context-window gate (`substrate.health` reports `n_ctx 393216` and yarn; one
full-length synthetic prompt through `serving.complete` at ~363k tokens recording peak GTT,
prefill and generation rates as an `event` row) before its first cell; plan = D × 8 × 3;
`limit_applied = permitted`. SC-006: assert the header differs from the primary's in exactly
`{rope_scaling, rope_scale, yarn_orig_ctx, n_ctx}`.

### T034 — `grading.py`

Per contracts/grading-view.md: `export(ledger, seed, out_root)` writes `views/<name>-grading.json`
(per question: `question_text`, `ask_time`, entries under blinded ids `q<Q>-<6 hex>` from
`Random(f"{seed}:{question}:{arm}:{repeat}")`, ordered by id, each `{text, truncated}`; every
`ok` cell), `admin/<name>-admin.json` (non-scored cells with arm/question/repeat/tokens),
`seals/<name>-seal.json` (`{blinded_id: {arm, question, repeat}}`, seed, header hash). Refuses
on an incomplete ledger. The three directories are distinct and the exporter refuses to write two
outputs into one.

### T035 — Integration tests with fake arms

**File**: `tests/research/test_arms849_integration.py` (~250 lines) plus updates to
`test_run_849_harness.py` and `test_arms849_grading.py`. Register three fake arms (G returns a
fixed block; D raises `ContextExceeded` on the six known questions and answers the two; R reads k
from the calibration). Must include: full 72-cell run completes with 18 `exceeds_model_context`,
zero `error`; **interrupt mid-cell** (kill the worker via a fake arm that raises `KeyboardInterrupt`
after `attempt_start`) then resume → the key has two `attempt_start` rows and one `ok`; torn-tail
ledger resumes; second writer refused; a fake G whose repeat-1 cell errors three times → `halt`
event and no R rows; grading view: entry count == `ok` count, no `G`/`D`/`R` values, no repeat
index, no timings; seal reproduces the mapping from the seed; `--secondary` refuses on an
incomplete primary and, on a complete one, produces a header differing in exactly four fields.

## Definition of Done

- Existing harness tests green, re-pointed; integration tests green; `python3 -m
  scripts.research.run_849_harness --dry-run` prints the 72-cell plan; `mark-status T031 T032
  T033 T034 T035 --status done`.

## Risks / reviewer guidance

- The per-attempt timeout must not leave a zombie request against llama-server; cancel and
  wait for the worker before recording the row.
- Reviewer: the exporter is the one place an arm identity could leak to the grader — read
  `export()` with that single question and grep its output for the forbidden strings yourself.
