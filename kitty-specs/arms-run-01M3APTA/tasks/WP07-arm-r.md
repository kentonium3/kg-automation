---
work_package_id: WP07
title: Arm R — index, records, deterministic k
dependencies:
- WP01
- WP03
- WP05
requirement_refs:
- FR-010
- FR-012
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
subtasks:
- T028
- T029
- T030
phase: Phase 2 - Arms
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/arm_r.py
create_intent:
- scripts/research/arms849/arm_r.py
- tests/research/test_arms849_arm_r.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/arm_r.py
- tests/research/test_arms849_arm_r.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP07 — Arm R

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

The realistic-deployment arm (rubric §2 R row as amended by A4; research.md D-4, D-10): the
replay-visible **records** (entities and edges) always present as the structured half; **top-k
vector retrieval over events only**, with the embedder R shares with G (`arms849.embed`, WP05 —
import it; do not define a second one); retrieved events **re-sorted into ask-time order** before
insertion so R's layout matches D's and its cache prefix is meaningful; and its one free
parameter, k, derived once by D-10 (implemented in `arms849.calibration`, WP04 — R supplies the
per-question assembly callable, the harness runs the calibration and writes the record).

## Subtasks

### T028 — `arm_r.py`: index, records, assembly

**Steps**:
1. `EventIndex.build(view, embedder)`: embed `text.event_line(ref).decode()` for every event in
   the view (one event per chunk); keep `(ref, vector)`; deterministic order.
2. `retrieve(question_text, k) -> list[ref]` by cosine similarity, ties broken by `ref`
   ascending; `availability_capped = k > len(view.events)` (early questions).
3. `assemble(view, retrieved_refs) -> (Block, plan)`: re-sort the retrieved refs by the event's
   `at` (then `ref`), then `text.render_block(sorted_refs, entity_keys + edge_keys)`; `plan` =
   `k`, `retrieved_refs_by_rank` (the rank order, recorded, never shown to the model),
   `assembled_order: "ask_time"`, `entities_in_records`, `edges_in_records`,
   `availability_capped`, `assembled_context_sha256`.
4. `arm_r(question, view, ctx)`: reads `k` from `ctx.calibration` (refuse to run without it —
   never a default k); builds the index for the question's view (or reuses one the harness
   cached for the question across repeats — NFR-005 requires identical context across repeats,
   and the embedder is deterministic, so either is byte-identical; cache for speed and assert
   equality in a test); renders, counts, completes.

### T029 — `r_tokens_for` and `availability_cap` (inputs to WP04's calibration — D-10 is implemented ONCE, in `arms849/calibration.py`)

**Steps**: `r_tokens_for(question, k, tokenizer) -> int`: builds the assembly for a candidate k
on the question's replayed view and returns the assembled-block token count (records + top-k
events, exact assembled bytes tokenised); `availability_cap(question) -> int` = the number of
events in that view. These two are the ONLY things `arms849.calibration.calibrate` (WP04) calls
into R; the band, the ties, `parity`, the record and the halt rule live there and nowhere else
(design-lead E1: one implementation of D-10). R never calls `calibrate`; the harness does, once,
when all eight G repeat-1 cells are `ok`.

### T030 — Tests

**File**: `tests/research/test_arms849_arm_r.py` (~180 lines), real corpus + cache. Must include:
same view + same k twice → identical `assembled_context_sha256`; retrieved refs are re-sorted
chronologically while `retrieved_refs_by_rank` keeps rank order; records section equals D's for
the same question (byte-identical entity+edge lines); `availability_capped` on C1 with k >
772; `r_tokens_for` is monotone non-decreasing in k; running `arm_r` without a calibration
record raises; `availability_cap(C1) == 772`; `r_tokens_for` is exact (equals the tokeniser count of
the bytes the assembly would insert). The band/ties/parity tests belong to WP04, not here.

## Definition of Done

- Tests green; no second embedder definition exists (grep); `mark-status T028 T029 T030 --status done`.

## Risks / reviewer guidance

- k must come from the calibration record on every cell, including after a resume; a default k
  anywhere in the module is a defect.
- Reviewer: check that the records block R inserts is the **same bytes** D inserts for that
  question — that equality is what makes R's ratio to G meaningful.
