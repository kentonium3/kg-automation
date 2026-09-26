---
work_package_id: WP09
title: Documentation and execution — README run section, run record, preflight, primary run, hand-off, secondary, teardown
dependencies:
- WP02
- WP05
- WP06
- WP07
- WP08
requirement_refs:
- C-001
- C-003
- C-007
- FR-002
- FR-015
- FR-017
- FR-018
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
subtasks:
- T036
- T037
- T038
- T039
- T040
- T041
- T042
- T043
phase: Phase 4 - Execution
history: []
agent_profile: implementer-ivan
authoritative_surface: docs/design/research/849-synthesis/
create_intent:
- docs/design/research/849-synthesis/run-record-arms-run.md
execution_mode: planning_artifact
owned_files:
- docs/design/research/849-synthesis/README.md
- docs/design/research/849-synthesis/run-record-arms-run.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP09 — Documentation and execution

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

Two things one owner must do together: leave behind what a cold-start agent needs to find, run
and understand the harness (the charter's standing obligation), and perform the **live
verification** — run the primary and secondary on reviewed code and record everything in the run
record. **Precondition for T038 onward, non-negotiable**: WP01–WP08 merged to
`feat/849-arms-run` and the post-merge Codex read-only review of the full diff passed with
findings fixed (Kent's standing checkpoint). This WP writes no code; the ledgers, views and seals
live under `build/849-runs/` (untracked) and are cited by hash. Kent's ruling (DM1): the office4
session runs and resumes this under auto-run, model resident, any hour. Post `status` on the
agent bus at each step transition (FR-017 — the bus posts are yours; the harness prints the line
you relay). Read first: `README.md` (keep its voice), `quickstart.md`, `research.md` D-8/D-9,
rubric §2/§5/§9, `signal-to-doc-map.json` (`architecture-doc-added` → INDEX + DEVELOPER_PORTAL).

## Subtasks

### T036 — README Run section + run record skeleton

1. README: a **Run** section after Harness — the seven quickstart steps with one sentence each on
   *why* (preflight from the full checkout because the oracle checkers pass vacuously without it;
   the runner container because an export under the checkout is not a boundary; entities after
   events because the prefix is the cache measurement; the secondary never interleaved); the
   sandbox envelope copied from research.md D-9 **verbatim**; a "What the ledger cannot tell you"
   paragraph (outcomes, not scores; grading is blind and elsewhere).
2. `run-record-arms-run.md` (frontmatter per the repo doc standard: title, doc_type research,
   status draft, owner, last_updated): sections for preflight output, gate table, substrate state,
   the §2 re-measured token table, primary summary, interrupt-and-resume evidence, grading export
   paths + seal path, secondary gate measurements, secondary summary, teardown verification, and
   every hash (ledger header hash, export sha, preflight sha, code hashes). Each section starts
   with the exact command that produces its content. Fill them in T038–T043.

### T037 — Navigation

Add the run record to `docs/INDEX.md` (research section, Divio annotation as the siblings) and to
`docs/DEVELOPER_PORTAL.md` where the #849 research is listed; `python3 tooling/scripts/validate_docs.py`
green. Commit T036+T037 before starting T038 (docs land even if the run is interrupted).

### T038 — Preflight, export, substrates, gates

`run_849_harness --preflight` from the full checkout (record output + `preflight_sha`);
`substrate export` (record `content_sha`); `substrate up` (primary) + `health`;
`substrate run --self-test`; `run -- --gates`. Every gate must pass; paste the gate table. If any
refuses, stop and post `blocked` — do not edit code in this WP.

### T039 — §2 token table re-measured at code freeze

For each question: the exact serialised request's token count, the block's token count, and the
prefix sharing with the previous question (`run -- --dry-run --measure` or the D arm's
`prefix_check`). Post the table to the design lead for registration as a dated amendment-log
line (A4 ruling); paste it into the run record. The six-of-eight classification must be unchanged.

### T040 — Primary run with one deliberate interrupt-and-resume

`substrate run -- --ledger /runs/primary.jsonl`. After at least one G cell and before the first D
cell, **kill the runner container** (SC-003), re-run the same command, and confirm from `--status`
that no scored cell was re-executed and the interrupted key shows two `attempt_start` rows. Let
it complete (expect G: 24 ok; D: 6 ok + 18 exceeds_model_context; R: 24 ok; calibration record
before R). Paste `--status` and `summarise` output; record wall-clock per arm and the calibration
record.

### T041 — Grading export and hand-off

`--grading-view`; record view/admin/seal paths and the seal's header hash; post the hand-off to
the design lead with the **view path only** (never the seal); update the run record.

### T042 — Secondary

`substrate up --yarn`; `run -- --secondary --primary /runs/primary.jsonl --ledger
/runs/secondary-yarn.jsonl` — its own context gate first (record n_ctx, peak GTT, prefill and
generation at ~363k); expect D-YaRN: 24 ok; export its grading view separately; paste its summary.

### T043 — Teardown and the run record

`substrate down` — verify SC-008 (nothing matching `arms849|falkor|llama` remains; GTT < 2 GiB;
GGUF intact); complete every section of the run record with measured values and hashes; commit;
post completion on the bus. The design lead grades from the view.

## Definition of Done

- README Run section + navigation committed, `validate_docs.py` green. Primary ledger: 72 cells,
  0 `not_implemented`, 0 `error` (or each explained in the record), 18 `exceeds_model_context`,
  interrupt-and-resume evidenced. Secondary ledger: 24 cells. Views and seals exported. Teardown
  verified. Run record complete and committed. `mark-status T036 … T043 --status done`.

## Risks / reviewer guidance

- If the calibration halts (a G repeat-1 cell terminal `error`), stop and surface it — a
  registered disposition, not a retry decision here.
- Never open, post or copy the seal; the grader opens it after scores are in.
- Do not paraphrase the sandbox note — copy it, so the certification is the one the code implements.
