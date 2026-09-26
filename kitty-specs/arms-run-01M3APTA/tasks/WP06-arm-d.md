---
work_package_id: WP06
title: Arm D — the full dump and the context gate
dependencies:
- WP01
requirement_refs:
- FR-006
- FR-009
- FR-012
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms-run-01M3APTA
base_commit: 1b9271f9762845d1c0536cd9289cf5e48d59d225
created_at: '2026-09-25T04:12:35.474766+00:00'
subtasks:
- T026
- T027
phase: Phase 2 - Arms
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/arm_d.py
create_intent:
- scripts/research/arms849/arm_d.py
- tests/research/test_arms849_arm_d.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/arm_d.py
- tests/research/test_arms849_arm_d.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP06 — Arm D

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

The honest upper bound on recall where it can run, and a correctly classified non-result where it
cannot — decided **client-side, on the exact serialised request, before anything is sent**
(rubric §2 D row, A2, A4; research.md D-7, D-11, D-13; spec FR-006, FR-009, SC-002). The dump is
the **whole** replay-visible view — events, then entities, then edges — through
`text.render_full_view`, so each D prompt is a byte prefix of the next in ask-time order and the
cache hit rate is a property of the protocol. `gate-b-context-window.md` records what this arm's
prompts cost; read it so the timings in your tests are plausible.

## Subtasks

### T026 — `arm_d.py`

**Steps**:
1. `arm_d(question, view, ctx) -> Answer`: `block = text.render_full_view(view)` (events in view
   order, then entities, then edges — assert the order and set `plan.layout =
   "events_entities_edges"`); `request = ctx.prompt.render(block, question.text)`;
   `prompt_tokens = ctx.serving.count_tokens(serialize(request))`.
2. Context gate: `limit = ctx.limits.trained` when `ctx.ledger_kind == "primary"`, else
   `ctx.limits.permitted` (D-11); if `prompt_tokens > limit` raise
   `ContextExceeded(prompt_tokens, limit_applied=…)` and send nothing. Record
   `context_limit_applied` on every D row (the harness reads it from the exception or the Answer).
3. Otherwise `ctx.serving.complete(...)` with `cache_prompt: true` and the repeat's seed; map the
   telemetry per D-13 (the serving module does it; the arm only asserts the fields are present).
4. `PlanRecord`: `layout`, `events_in_dump`, `entities_in_dump`, `edges_in_dump`,
   `assembled_context_sha256` (of the block bytes), `assembled_context_tokens` = tokens of the
   block alone (count the block bytes decoded), so §5's "assembled context excludes the fixed
   prompt and the question" holds.
5. `prefix_check(view_prev, view_next)`: helper used by the tests and by WP10's re-measurement:
   the event section of the earlier question's block is a byte prefix of the later's.

### T027 — Tests

**File**: `tests/research/test_arms849_arm_d.py` (~200 lines), real corpus + cached tokenizer
(skip if either is absent). Must include: (a) **exactly six** of the eight questions raise
`ContextExceeded` under the primary limit and **zero** under the secondary's permitted limit
(393,216 − 2,048) — this is SC-002 and D-11's "all eight secondary cells fit" in one test;
(b) `prompt_tokens` for B2 ≥ 362,772 (the registered figure is a floor now that edges are
included; record the measured value in the test's assertion message so WP10's re-measurement
can cite it); (c) the event section is a byte prefix across the eight questions in ask-time order
(NFR/§2 layout protocol); (d) entities and edges follow events, never precede; (e) an injected
fake response missing `cache_n` produces no Answer (TelemetryMissing propagates); (f) the block
bytes for C1 equal the concatenated corpus lines for C1's replayed events + records (D-7).

## Definition of Done

- Tests green; the six/zero split is asserted, not assumed; `mark-status T026 T027 --status done`.

## Risks / reviewer guidance

- The gate must count the **serialised request**, not the block; a reviewer should be able to
  point at the exact string that is sent and the exact string that is counted and see they are
  the same object.
- Do not "optimise" the dump order; the prefix property is the measurement.
