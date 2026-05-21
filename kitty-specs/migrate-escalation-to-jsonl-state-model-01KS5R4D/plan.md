# Implementation Plan: Migrate escalation to JSONL state model

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Mission ID**: `01KS5R4D79WQQWY2MCHZVCT85G`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-21
**Spec**: [spec.md](spec.md) · **Source issue**: [#309](https://github.com/kentonium3/kg-automation/issues/309) · **ADR**: [0002 Phase 6](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

## Summary

Migrate the `felix-admin-escalation` subsystem from `[Felix-Escalation]` comment-as-state to JSONL-canonical state, mirroring the Phase 3-5 habits pattern. Adds three Python helpers under `scripts/escalation/` (record, reconcile, backfill), extends `DOMAIN_STATES["escalation"]` in the Phase 2 schema module with the new flat-enum vocabulary, updates the deployed OpenClaw `felix-admin-escalation` agent (SKILL.md + AGENTS.md) to invoke the helpers, runs a one-time backfill of existing `[Felix-Escalation]` comments, and observes a 3-day soak before declaring complete. The OpenClaw agent driver itself is retained (per scope decision recorded 2026-05-21); driver retirement is deferred to a follow-on epic that will also fold in the priority/life-goals/time-context evolution.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/` baseline).
**Primary Dependencies**: stdlib (`json`, `urllib`, `pathlib`, `datetime`, `argparse`, `sys`) plus `scripts.common.state_log` (Phase 2 substrate). No new third-party dependencies.
**Storage**:
- Vikunja v0.24.6 — production task state and `[Felix-Escalation]` comment write surface (preserved during soak per C-001).
- Local JSONL state files on office2 at `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl` — per-project partition per NFR-003. Exact path/slug convention finalized in research.md D2.
- Backfill snapshot at `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json` — captures pre-migration `[Felix-Escalation]` comment text per task, enabling rollback.
**Testing**: pytest with mocked `urllib` (existing pattern in `tests/habits/`). New tests under `tests/escalation/`. ≥85% line + branch coverage per NFR-004.
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); macOS for unit-test dev (network mocked).
**Project Type**: Single project. Helpers in `scripts/escalation/` alongside `scripts/habits/`, `scripts/common/`.
**Performance Goals**: record_completion < 5s p95; reconcile_completions < 60s for ≤50 escalation-subscribed tasks (NFR-001).
**Constraints**: Library I/O semantics unchanged (C-003, amended); policy unchanged (C-002); v1 preserved during soak (C-001); felix-bot identity for all agent writes (FR-010); no comment-watcher daemon (C-007); privacy boundary preserved (C-006).
**Scale/Scope**: Escalation today operates on ~5-15 actively escalated tasks at any time across ~3-5 projects. State log expected to receive ~5-20 entries per week steady-state.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context (compact mode): governance unresolved due to spec-kitty 3.1.8 tool-registry mismatch (`pytest`, `python` reported unavailable despite being declared in the charter); known issue per memory `project_charter_tool_registry_mismatch.md`. Non-blocking — the Felix Constitution itself imposes no directives that conflict with this mission. Directive 6 (deterministic vs stochastic split) actively supports the design: escalation policy is purely deterministic, and the migration further removes any LLM-judgment surface from the state-derivation path. **No charter violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/
├── plan.md                  # This file
├── spec.md                  # Mission specification
├── research.md              # Phase 0 — engineering decisions (this pass)
├── data-model.md            # Phase 1 — JSONL record shape, schema enum, comment vocabulary mapping
├── quickstart.md            # Phase 1 — operator backfill + cutover walkthrough
├── contracts/               # Phase 1 — Python + CLI surfaces
│   ├── api.md               # Python function signatures for helpers
│   └── cli.md               # CLI flags + exit codes
├── checklists/
│   └── requirements.md      # Spec quality checklist (from specify phase)
└── tasks/                   # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/escalation/                       # NEW directory
├── __init__.py
├── record_completion.py                 # NEW — atomic three-write helper (FR-002, FR-009)
├── reconcile_completions.py             # NEW — drift detection + synthetic done records (FR-005)
├── backfill_jsonl_from_comments.py      # NEW — one-time Phase 4-style replay (FR-006)
├── derive_state.py                      # NEW — pure function: JSONL → current state for a task
└── (read-only helpers consumed by the OpenClaw skill)

scripts/common/
└── state_log_schema.py                  # MODIFIED — DOMAIN_STATES["escalation"] vocabulary update only
                                          #            (per amended C-003)

scripts/openclaw/agents/felix-admin-escalation/
└── AGENTS.md                            # MODIFIED — call helpers, stop comment parsing (FR-007)

scripts/openclaw/skills/escalation/
└── SKILL.md                             # MODIFIED — replace level-determination algorithm with helper invocation (FR-007)

tests/escalation/                         # NEW
├── __init__.py
├── conftest.py                          # Shared fixtures (mocked Vikunja, sample JSONL state)
├── test_record_completion.py            # FR-002, FR-003, FR-004, FR-008 coverage
├── test_reconcile_completions.py        # FR-005 coverage
├── test_backfill.py                     # FR-006 coverage
├── test_derive_state.py                 # Pure-function coverage (every event_type path)
└── test_q10_hard_fail.py                # FR-008, FR-009 dedup coverage

docs/design/architecture/data/
├── data-flows.json                      # MODIFIED — new read/write paths (C-004)
└── service-inventory.json               # MODIFIED — register scripts/escalation/* (C-004)

docs/design/architecture/                 # markdown views matching the JSON updates above

/data/services/openclaw/state/escalation/  # NEW on office2 — created during deploy
├── <project-slug>-escalation-history.jsonl  # Per-project (NFR-003)
└── pre-phase6-snapshot.json                  # Rollback substrate
```

**Structure Decision**: Single project. New `scripts/escalation/` parallels `scripts/habits/`. Tests under `tests/escalation/`. Per-project JSONL partition (NFR-003) is implemented via filename-based partitioning rather than a separate directory hierarchy — simpler ops and matches habits' single-file approach.

## Complexity Tracking

No charter violations. Two design tensions worth flagging:

1. **Per-project JSONL partition introduces a new file-routing surface.** Habits used a single `habits-history.jsonl` because all habits live in one project. Escalation tasks span ~3-5 projects, so a single file would mix projects. Research D2 commits to filename-based partition keyed on project slug; the `state_log` library doesn't need to change because each project file is just a separate `state_log` consumer.

2. **The existing OpenClaw agent prompt has dense `[Felix-Escalation]` parsing logic.** The migration removes that logic but the agent still runs and still composes WhatsApp messages. Risk: stale references in the prompt. Mitigation: a dedicated "audit the AGENTS.md + SKILL.md for residual comment-parsing language" subtask, plus a paired diff review of both files.

---

## Plan

Both phases (research + design) execute in this single planning pass. The ADR-0002 decisions and habits Phase 3-5 precedent close most of the design space; remaining decisions are tactical.

### Phase 0 — Research artifacts

See [research.md](research.md). Engineering decisions captured:

1. **DOMAIN_STATES["escalation"] vocabulary update** — per amended C-003, replace the existing `{triggered, level-1, level-2, resolved, dismissed}` enum with the Q1=A flat enum `{level_sent, snoozed, dismissed, done, rescheduled}`. The existing enum was never written to (no escalation records exist yet); zero data migration.
2. **Per-project JSONL file naming** — `<project-slug>-escalation-history.jsonl`. Slug derivation, sanitization rules.
3. **Reconcile detection semantics for "rescheduled then UI-edited"** — defer to the simple rule: reconcile emits a synthetic `rescheduled` record whenever the Vikunja `due_date` differs from the last-known `reschedule_to` AND no `done`/`dismissed` is present. Tertiary scenario (Q10 hard-fail) catches truly inconsistent state.
4. **snooze_until write-time computation** — ISO-8601 date, computed in Python's `date.today() + timedelta(days=N)` at the record-writing moment, persisted verbatim. Timezone: America/New_York (Kent's TZ); date arithmetic in local TZ.
5. **Backfill comment vocabulary mapping** — the locked HISTORICAL state map from existing `[Felix-Escalation]` comments to the new flat-enum schema. Q4-style malformed-comment handling per Phase 4 cycle 2 pattern.
6. **Three-write ordering for escalation events** — Vikunja side-effect FIRST (WhatsApp send + comment write), JSONL append LAST. Same rationale as habits Phase 3 D4: failing the unreliable remote ops first surfaces network issues before any state_log line is written.
7. **derive_state pure function shape** — input: list of JSONL records for one task (newest-first). Output: a dataclass with `current_state`, `effective_until` (for snooze), `next_eligible_level`, `last_event_recorded_at`. All escalation policy lives here.
8. **Q10 hard-fail trigger conditions** — (a) malformed JSONL line that fails schema validation, OR (b) escalation-subscribed task per Vikunja (has prior `[Felix-Escalation]` comment that hasn't been backfilled) but JSONL has no anchor records.
9. **Hard-fail dedup query format** — exact `gh issue list --search` query template; verification that the title format survives renames/moves; double-fire prevention across two ticks while issue is still open.
10. **Per-tick file-locking** — use the existing `state_log.append` locking semantics (Phase 2). No new locking surface in escalation helpers.
11. **Comment-write parity during soak (C-001 implementation)** — record_completion continues to write `[Felix-Escalation]` comments in their old format AND a JSONL record. The agent reads from JSONL only. Soak-end follow-on removes the comment write.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — JSONL record shape, per-event_type parameter fields, DOMAIN_STATES enum update, comment-vocabulary mapping, snapshot schema
- [contracts/api.md](contracts/api.md) — Python function signatures for record_completion, reconcile_completions, backfill, derive_state
- [contracts/cli.md](contracts/cli.md) — CLI surface, flags, exit codes (matches habits Phase 3 pattern)
- [quickstart.md](quickstart.md) — operator backfill walkthrough + post-cutover verification + rollback procedure

### Charter re-check (post-design)

Same outcome as pre-design — Felix Constitution imposes no directives that conflict. Re-check pass.

---

## Branch contract (restated)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **branch_matches_target**: `true`

Completed changes from this mission merge into `main`.

---

## Stop

Planning artifacts complete. Next: `/spec-kitty.tasks` to break the plan into work packages.
