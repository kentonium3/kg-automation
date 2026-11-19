# Tasks — 849 Arms Run Pre-Run Preconditions

**Branch**: `feat/849-preconditions` → the mission merge lands here; `feat → main` follows the post-merge Codex checkpoint, the T039 freeze gate and the pre-merge record.
**Plan**: [plan.md](./plan.md) @89c16cc6 · **Spec**: [spec.md](./spec.md) · **Research**: [research.md](./research.md) (D-1..D-10, D-2b, D-7a) · **Contracts**: [contracts/](./contracts/) (review #6 fold @8c460994)

This file decomposes the Implementation Concern Map (IC-01…IC-05) into **5 work packages in ONE sequential lane** (C-005: WP01 → WP02 → WP03 → WP04 → WP05, a linear dependency chain).

**Why the WPs are cut by file layer, and why ownership overlaps.** Four of the five concerns touch `run_849_harness.py`, so each WP has a primary layer:
- WP01: ledger, grading and gates;
- WP02: arms and serving;
- WP03: sampler and substrate;
- WP04: harness;
- WP05: verification.

Each IC's work is distributed across the layers in IC order. Some changes are COUPLED across layers, because the suite must stay green at every WP. For example:
- WP01 makes `session_id` required, so the harness call site must pass it;
- WP03 wires the report into summary/export;
- WP04 deletes the dead RSS classes;
- WP05 moves shared fakes into `conftest.py`.

Each WP's `owned_files` therefore declares its TRUE write scope, including those coupled files.

**The overlapping ownership is deliberate.** spec-kitty's lane computation unions WPs with overlapping `owned_files` into one lane (`lanes/compute.py` rule 1, `write_scope_overlap`). That yields exactly the ONE sequential lane C-005 requires (validate-only: `lane_ids: ["lane-a"]`). This departs from the tasks runbook's line "No two WPs may have overlapping owned_files": that rule guards against PARALLEL collisions, which a single lane cannot have, and the tool accepts overlap as a collapse signal with no ownership warning. The runbook/tool discrepancy is recorded for Kent (2026-09-27).

**Standing rules for every WP:**
- **Correction A:** any WP that adds a module to `scripts/research/arms849/` updates `gates.REQUIRED_MODULES` in the SAME commit (C4's two-way test fails otherwise).
- **NFR-002 red-first:** every FR a WP implements has at least one test shown failing on the pre-change code; the evidence is recorded per WP. FR-004 is exempt (a regression guard).
- **NFR-001:** at the end of each WP, the full suite passes on office4 under `PYTHONHASHSEED=0` and `3` (with `ARMS849_CACHE=/home/kgale/repos/kg-automation/build/849-cache`), and CI collection survives without `graphiti_core`.
- **Reviewer independence:** the implementer is Opus (python-pedro). The per-WP review is Codex (a different vendor), read-only, prompted with properties to verify.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Ledger outcomes `exceeds_memory_ceiling` + `sampler_unreadable_at_send`: validation, never averaged/scored, terminal, never retried by any session, completeness refusal | WP01 | |
| T002 | Events `premise_violated` + `session_stopped`: validation; refusal by `require_complete_primary`-facing checks, grading export and `Ledger.summarise()` (correction C) | WP01 | |
| T003 | `attempt_start.session_id` required; replay binds each attempt to its own session's passing gates (+ coupled harness pass-through) | WP01 | |
| T004 | Graph-store boundary events validated on write/replay; any per-cell graph-store column refused; `falkordb_rss_peak_mib` retired (+ coupled harness row detach) | WP01 | |
| T005 | Smoke ledger identity `SMOKE_PLAN` in the header: immutable, refused as primary and by export | WP01 | |
| T006 | C4: `REQUIRED_MODULES` names every package module, with a two-way test | WP01 | |
| T007 | One shared `ArmRefusal` + `_check_limit` (+ `PremiseViolated`, `CeilingBreached`, `CeilingUnreadable`); D/R aliases; `ctx.serving.config` fallbacks removed | WP02 | |
| T008 | G refusals (foreign items, graph not built, limit check via `ctx.config`) and `PremiseViolated` (tripwire, cross-group leak) | WP02 | |
| T009 | FR-016: per-question database routing for every G operation; per-question `Graphiti`; clone `_init_task` awaited; per-database `_indices_built` | WP02 | |
| T010 | G loop bridge: persistent loop + driver, retrieval on loop and serving on the attempt thread (`respond`), deadlines, acknowledged cancellation, `GCancellationUnacknowledged`, `close()` | WP02 | |
| T011 | `serving.complete(..., before_send)` hook: after count + limit check, immediately before the send, unwrapped | WP02 | |
| T012 | Live FR-016 test (hybrid step RETURNS ≥ 1 expected hit) + the "ran vs produced" assertion sweep | WP02 | |
| T013 | Host cgroup reader + exclusive-create generation series file (header binds series_id, trailer on clean stop, canonical UTC) | WP03 | |
| T014 | `substrate.run()` starts/stops the observational writer; descriptor via `env_extra`; `writer_status` on failure | WP03 | |
| T015 | Run-level graph-store report (`baseline_mib`, `peak_mib`, `all_resident_mib`, marginal) with every `could_not_check` rule; wired into summary/export (+ coupled wiring) | WP03 | |
| T016 | C12 canonical-UTC-only timestamps for sampler/series; NFR-004 boundary (exactly 5 intervals allowed, >5 refused) | WP03 | |
| T017 | `ARM_FACTORIES` (lazy imports), one embedder on `Resources` + `Runtime`, `close()` in `run_session`'s `finally`; live-registration red-first test; Condition A regression | WP04 | |
| T018 | `_call_with_timeout` grace path: re-raise non-`Exception` BaseException, return `("raised", exc)`; race tests | WP04 | |
| T019 | Session halts: `PremiseViolated` → `premise_violated` + stop; `GCancellationUnacknowledged` → `session_stopped{grace_s}`, no further query, exit; `CellContext.deadline` | WP04 | |
| T020 | Remove the per-attempt graph-store sampler path; emit `series_generation`, `graph_store_first_build` (both listing outcomes), `graph_store_all_resident` | WP04 | |
| T021 | Ceiling guard wiring: `before_send` closure, `ServingFacade` refuses without one, breach → `exceeds_memory_ceiling` + session stop; unreadable → `sampler_unreadable_at_send`, cell refused; secondary probe; facade fakes | WP04 | |
| T022 | `--smoke` selector (G r1 ×8 → calibration → D C1 r1 → R C1 r1) on a `SMOKE_PLAN` ledger; status/reopen | WP04 | |
| T023 | `--measure` T039 tool (8 serialised requests, block tokens, prefix sharing, exceedance set == registered six, else named error; bound to commit + preflight_sha); injectable `PROCESS_START` | WP04 | |
| T024 | NFR-003: 100 consecutive attempts with injected timeouts/cancellations against a fake graph store; no new attempt before acknowledgement | WP04 | |
| T025 | `tests/research/conftest.py`: research-environment fixture; named, counted skips (FR-014) | WP05 | |
| T026 | C8 live-style resume test across real timestamp-bearing gate phases + both negatives (FR-009) | WP05 | |
| T027 | `scripts/research/check_849_premerge.py`: both seeds, fresh-worktree CI simulation, required live smoke, junit-xml required-node check, commit-bound record (FR-015) | WP05 | |
| T028 | Tests for the pre-merge checker (a missing/skipped/failed required node fails the record; a wrong commit invalidates it) | WP05 | |

## Work Packages

### WP01 — Ledger, grading and isolation inventory (IC-01; ledger halves of IC-03/IC-04)
- **Prompt**: [tasks/WP01-ledger-grading-inventory.md](./tasks/WP01-ledger-grading-inventory.md)
- **Goal**: the ledger gains the vocabulary the later WPs need, and the isolation inventory is complete.
- **Priority**: P1 · **Depends on**: — · **Est.**: ~450 lines
- **Subtasks**: T001, T002, T003, T004, T005, T006
- **Requirements**: FR-006, FR-007, FR-008, FR-010, FR-011, NFR-005

### WP02 — Arms, refusals, G routing and loop bridge, before_send hook (IC-02 arm side; IC-04 serving side)
- **Prompt**: [tasks/WP02-arms-routing-bridge.md](./tasks/WP02-arms-routing-bridge.md)
- **Goal**: one refusal class; G reads what it wrote; G's retrieval runs on one persistent loop with acknowledged cancellation; serving exposes the send-time hook.
- **Priority**: P1 · **Depends on**: WP01 · **Est.**: ~550 lines
- **Subtasks**: T007, T008, T009, T010, T011, T012
- **Requirements**: FR-002, FR-003, FR-008, FR-016, NFR-003

### WP03 — Graph-store series and run-level report (IC-03 writer/reader side)
- **Prompt**: [tasks/WP03-series-writer-report.md](./tasks/WP03-series-writer-report.md)
- **Goal**: an observational, never-truncated per-generation cgroup series and an honest run-level report.
- **Priority**: P1 · **Depends on**: WP02 · **Est.**: ~400 lines
- **Subtasks**: T013, T014, T015, T016
- **Requirements**: FR-005, FR-006, FR-007, FR-012, NFR-004

### WP04 — Harness integration (IC-02/IC-03/IC-04 harness side; T039 tool)
- **Prompt**: [tasks/WP04-harness-integration.md](./tasks/WP04-harness-integration.md)
- **Goal**: the live runtime registers the arms, halts and stops correctly, emits the run-level events, guards the ceiling at send, and offers `--smoke` and `--measure`.
- **Priority**: P1 · **Depends on**: WP03 · **Est.**: ~650 lines
- **Subtasks**: T017, T018, T019, T020, T021, T022, T023, T024
- **Requirements**: FR-001, FR-002, FR-004, FR-005, FR-008, FR-013, NFR-003, NFR-005

### WP05 — Environment gating, resume proof, pre-merge record (IC-05)
- **Prompt**: [tasks/WP05-envgate-resume-premerge.md](./tasks/WP05-envgate-resume-premerge.md)
- **Goal**: the research environment is declared once; resume is proven across real gate phases; every merge to main carries a checked record.
- **Priority**: P1 · **Depends on**: WP04 · **Est.**: ~400 lines
- **Subtasks**: T025, T026, T027, T028
- **Requirements**: FR-009, FR-014, FR-015, NFR-001

## Not work packages (plan § Freeze-time and post-merge steps)

1. The **T039 freeze gate**: run `--measure` on the final commit after the last WP's approval, and re-run it after any post-merge fix.
2. The **post-merge Codex checkpoint** on the complete merged diff, then the pre-merge record, then `feat → main`.
3. The 72-cell run, as an operation (out of scope, C-007).
