# Implementation Plan: Habits native repeat + JSONL state

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Mission ID**: `01KS0M59313RF0WVJZTXYDJC6C`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-19
**Spec**: [spec.md](spec.md) · **Source issue**: [#306](https://github.com/kentonium3/kg-automation/issues/306) · **ADR**: [0002 Q1, Q2, Q3-D, Q7, Q8](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

## Summary

Foundation Python helpers under `scripts/habits/` for the ADR-0002 habits migration. The mission builds the new code path alongside the existing one (which the cron continues to use until Phase 5 cutover #308). Three operator/agent tools plus two parallel `_v2.py` variants of existing query/exclude scripts. Production-state PATCH on Vikunja habit tasks via a config-driven migration helper with a Restic-protected rollback substrate. No `AGENTS.md` modifications.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/` baseline)
**Primary Dependencies**: stdlib (`json`, `urllib`, `pathlib`, `datetime`, `argparse`, `sys`, `os`, `re`) plus `yaml` (already in repo `requirements.txt`) plus the in-repo `scripts.common.state_log` from Phase 2 (#305). No new third-party dependencies (NFR-006).
**Storage**: Vikunja v0.24.6 (production task state); local JSONL at `/data/services/openclaw/state/habits-history.jsonl` (Phase 2 substrate); rollback-substrate JSON at `/data/services/openclaw/state/habits-pre-phase3-snapshot.json`
**Testing**: pytest with mocked `urllib` for the Vikunja API surface. Existing pattern in `tests/vikunja/` is the model. NFR-005 target ≥85% line + branch coverage.
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); macOS dev works for unit tests (network mocked).
**Project Type**: Single project — helpers in `scripts/habits/` alongside existing `scripts/vikunja/`, `scripts/inbox/`, `scripts/common/`.
**Performance Goals**: migration helper < 30s capture (NFR-001); record_completion < 5s p95 (NFR-002); reconcile_completions < 60s for 10 tasks (NFR-003); rollback < 5min (NFR-004)
**Constraints**: No `AGENTS.md` changes (C-002); old scripts untouched (C-001); felix-bot identity for every write (C-003); workout retired via `done=true` not delete (C-004); Tier 2 pre-flight required (C-007)
**Scale/Scope**: 10 active habit tasks post-migration (7 daily + 3 MWF). State log expected to receive ~1-3 entries per task per week.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context (compact mode): no enforced directives or tactics surfaced for this action. The Felix Constitution's Directive 6 (deterministic vs stochastic split) supports the mission's design — every helper does deterministic work; the LLM agent layer is reserved for completion classification (which happens in Phase 5 callers, not here). **No gate violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/
├── plan.md              # This file
├── spec.md              # Mission specification
├── research.md          # Phase 0 — engineering decisions
├── data-model.md        # Phase 1 — Vikunja entities, config schema, snapshot schema
├── quickstart.md        # Phase 1 — operator + agent usage
├── habits-schedule.yaml # Mission-scoped config — operator-edited per FR-012
├── contracts/           # Phase 1 — Python + CLI + config schemas
│   ├── api.md           # Python function signatures
│   ├── cli.md           # CLI surfaces for all 5 helpers
│   └── config.md        # habits-schedule.yaml schema
└── tasks/               # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/habits/                          # EXTENDS existing directory
├── (existing files — unchanged in this mission)
├── query_active_habits.py              # UNCHANGED (cron continues using this)
├── exclude_completed.py                # UNCHANGED (cron continues using this)
│
├── identify_workout_task.py            # NEW — lookup helper (one-shot operator tool)
├── migrate_schedule.py                 # NEW — config-driven PATCH helper (T1, T2, T3)
├── record_completion.py                # NEW — three-write atomic helper (FR-006)
├── reconcile_completions.py            # NEW — backfill + drift detection (FR-008, FR-009)
├── query_active_habits_v2.py           # NEW — parallel v2 variant (FR-010)
└── exclude_completed_v2.py             # NEW — parallel v2 variant (FR-011)

tests/habits/                            # NEW — created if missing
├── __init__.py
├── conftest.py                         # Shared fixtures (mocked vikunja client, sample tasks)
├── test_migrate_schedule.py            # FR-001..FR-005 coverage
├── test_record_completion.py           # FR-006..FR-007 coverage
├── test_reconcile_completions.py       # FR-008..FR-009 coverage
├── test_query_active_habits_v2.py      # FR-010 coverage
└── test_exclude_completed_v2.py        # FR-011 coverage

docs/design/architecture/data/
├── data-flows.json                     # MODIFIED — add new write/read paths (FR-013)
└── service-inventory.json              # MODIFIED — register new scripts (FR-013)

/data/services/openclaw/state/           # On office2 — created by Phase 2 already
├── habits-history.jsonl                # Phase 2 substrate; receives new entries during canary
└── habits-pre-phase3-snapshot.json     # NEW — rollback substrate (created at migration run)
```

**Structure Decision**: Single project. Helpers land under `scripts/habits/`. Tests under `tests/habits/`. Mission-scoped `habits-schedule.yaml` lives in the kitty-specs dir (not in `scripts/`) because it's a one-off migration artifact, not an ongoing operational config — operators consult `kitty-specs/<mission>/` for the canonical schedule applied during this mission. Future schedule changes (e.g., adding guitar practice) would be a separate mission or operator-driven Vikunja UI edits.

## Complexity Tracking

No charter check violations. The one design tension worth flagging: the existing `scripts/vikunja/*.py` helpers each implement their own urllib HTTP wrapper rather than sharing a client library. This mission follows the same pattern (each new helper self-contained) for consistency rather than introducing a `scripts/vikunja/api_client.py` mid-mission. Centralizing the HTTP client could be a future refactor mission but is not in this scope.

---

## Plan

Both phases (research + design) execute in this single planning pass. Phase 3's research is mostly tactical decisions (test approach, lookup ergonomics, error-handling patterns) rather than fundamental design — the ADR-0002 decisions are settled.

### Phase 0 — Research artifacts

See [research.md](research.md). Engineering decisions captured:

1. **Vikunja API client pattern** — each helper self-contained urllib (matches existing `scripts/vikunja/*.py`); no shared library extraction in this mission.
2. **Workout task ID lookup** — separate `identify_workout_task.py` helper (operator runs once, edits `habits-schedule.yaml` with result).
3. **Migration helper transaction model** — sequential single-task atomicity (each PATCH is atomic on its own; rollback is per-task reversal from snapshot). Not a batch all-or-nothing transaction (Vikunja doesn't support multi-task atomic writes).
4. **record_completion three-write ordering** — Vikunja `done=true` first, then comment, then state_log. Rationale: state_log is local and reliable; Vikunja remote ops are the failure-prone step. Failing first surfaces the network problem before any state_log line is written.
5. **Testing approach** — mocked urllib at unit-test layer plus a smoke-test invocation against a sandbox Vikunja task during canary (one of the dev test-targets, not production).
6. **Idempotency mechanism for record_completion** — check state_log first via `state_log.read("habits", task_id, date, state)`. If a record exists, short-circuit (no Vikunja calls, no log write).
7. **Drift surface in reconcile** — stdout warnings (one line per drift), exit 0 even with drift detected. Drift is operator-actionable, not a script failure.
8. **Config validation in migrate_schedule** — full YAML schema validation before any HTTP call. Refuse to run on schema error with a clear stderr message.
9. **Workout task replacement: due dates** — calculated relative to the migration run date (next Mon/Wed/Fri at or after the run). Operator can override via `habits-schedule.yaml` if a specific Monday is desired.
10. **Live-probe canary for verified API behaviors** — during canary, exercise the three-write path on the sandbox task and confirm `created_by.username == felix-bot` on the comment (per the verified gotchas in `vikunja-task-model-research.md` § Verified API gotchas). Document any new quirks discovered.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — Vikunja task fields, habits-schedule.yaml schema, snapshot schema, JSONL record shape (links to Phase 2)
- [contracts/api.md](contracts/api.md) — Python function signatures for all 6 new helpers
- [contracts/cli.md](contracts/cli.md) — CLI surface, flags, exit codes
- [contracts/config.md](contracts/config.md) — habits-schedule.yaml schema in detail
- [quickstart.md](quickstart.md) — operator migration walkthrough + future-consumer agent integration shape

### Charter re-check (post-design)

Same outcome as pre-design — no charter directives constrain this mission. Re-check pass.

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
