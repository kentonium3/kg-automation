# Implementation Plan: Backfill habits JSONL from Felix comments

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Mission ID**: `01KS0Y4F60A30H8CT28Z3VMVT6`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-19
**Spec**: [spec.md](spec.md) · **Source issue**: [#307](https://github.com/kentonium3/kg-automation/issues/307) · **ADR**: [0002 Phase 4](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

## Summary

One-shot operator-driven helper that reads existing `[Felix]` completion comments from Vikunja habit tasks and replays them as JSONL entries via the Phase 2 `state_log.append` library. Tier 3 (no Vikunja mutation). HISTORICAL_STATE_MAP locked to `{complete: complete, will-not-do: skipped}` per the 2026-05-19 production data probe (26 comments, 2 distinct states). Reuses `FELIX_COMMENT_PATTERN` from `scripts/habits/exclude_completed.py` (single source of truth for the regex) and the project-scoped enumeration pattern from Phase 3's `reconcile_completions.py::_resolve_habits_project_id`.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: stdlib (`json`, `urllib`, `argparse`, `pathlib`, `datetime`, `re`, `os`, `sys`, `shutil`) + `scripts.common.state_log` (Phase 2 #305) + imported regex from `scripts/habits/exclude_completed.py`. No new third-party deps.
**Storage**: Vikunja (read-only via GET); local JSONL at `/data/services/openclaw/state/habits-history.jsonl` (Phase 2 substrate); pre-backfill snapshot at `/data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak`.
**Testing**: pytest with mocked `urllib.request.urlopen`. Reuses the `mock_urlopen` + `mock_state_log_dir` + `sample_habit_task_response` fixtures from `tests/habits/conftest.py`.
**Target Platform**: Linux (office2). macOS dev works for unit tests (network mocked).
**Project Type**: Single project — new helper in `scripts/habits/` alongside Phase 3 helpers.
**Performance Goals**: <60s live (NFR-001), <30s dry-run (NFR-002) — easy targets at the current ~26-comment volume.
**Constraints**: stdlib only (NFR-003); ≥85% coverage (NFR-004); no sensitive-data leakage (NFR-005); read-only Vikunja contract (FR-011); strict adherence to Phase 2 enum (C-002).
**Scale/Scope**: ~26 records currently; helper sizing accommodates 10× growth without changes.

## Charter Check

Charter context: compact mode, no enforced directives or tactics. **No gate violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/
├── plan.md              # This file
├── spec.md              # Mission specification
├── research.md          # Phase 0 — engineering decisions
├── data-model.md        # Phase 1 — record schema, state map, snapshot shape
├── quickstart.md        # Phase 1 — operator walkthrough
├── contracts/
│   ├── api.md           # Python signatures
│   └── cli.md           # CLI surface, exit codes
└── tasks/               # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/habits/
├── (existing Phase 3 helpers — unchanged)
└── backfill_jsonl_from_comments.py         # NEW (~200 lines)

tests/habits/
├── (existing conftest + Phase 3 test files — unchanged)
└── test_backfill_jsonl_from_comments.py    # NEW (~250 lines)

docs/design/architecture/data/
├── data-flows.json                          # MODIFIED — add one-shot backfill flow
└── service-inventory.json                   # MODIFIED — register the new script

/data/services/openclaw/state/                # on office2
├── habits-history.jsonl                     # Phase 2 substrate (receives backfill entries)
└── habits-history.jsonl.pre-phase4-backfill.bak  # NEW — pre-run snapshot for rollback
```

**Structure Decision**: Single new helper + one test module + two arch-doc updates. No new directories. Mirrors existing `scripts/habits/` convention.

## Complexity Tracking

No charter violations. No complexity to justify. The one design consideration worth noting: the regex source-of-truth lives in `scripts/habits/exclude_completed.py` (the v1 sibling that C-001 mandates stay unchanged through Phase 5). The backfill helper imports it as `from scripts.habits.exclude_completed import FELIX_COMMENT_PATTERN`. This is a one-directional dependency (backfill → v1) that does NOT violate C-001 because the imported symbol is constant data, not behavior.

---

## Plan

Both phases (research + design) execute in this single pass.

### Phase 0 — Research artifacts

See [research.md](research.md). Engineering decisions documented:

1. **Regex reuse vs duplication** — import `FELIX_COMMENT_PATTERN` from `scripts/habits/exclude_completed.py`; do not duplicate the regex.
2. **State mapping shape** — module-level `dict` constant locked to the 2026-05-19 production probe values. Easy to extend reactively if new values surface.
3. **Idempotency** — rely entirely on Phase 2 state_log's `(task_id, date, state)` dedup. No additional state tracking inside the helper.
4. **Pre-backfill snapshot strategy** — `shutil.copy2` to a sibling `.bak` file before the first append. Atomic enough for the use case (one writer, operator-driven, single-machine).
5. **Timestamp parsing** — accept Vikunja's `created` field verbatim (ISO-8601 with timezone). State_log.validate_record handles format checks.
6. **Title field** — fetch from the current Vikunja task state at backfill time, NOT from the comment (comments don't carry the task title). Document the denormalization choice.
7. **Project-scoped enumeration** — mirror Phase 3's `_resolve_habits_project_id` from `reconcile_completions.py`. Same constant `HABITS_PROJECT_TITLE = "Habits"`. Avoid the broad `/tasks/all` endpoint per the WP03 lesson.
8. **Summary report format** — plain text on stdout (not JSON) — operator-facing readability over machine-parseability. The dry-run + live-run produce the same format with a header indicating mode.
9. **Test approach** — mocked urllib for all HTTP. Real `state_log.append` against a `tmp_path` `STATE_DIR`. No live integration tests in CI.
10. **Idempotency test pattern** — invoke `backfill()` twice; assert second call produces zero appends. Tests use a counter on `state_log.append` calls (monkey-patched) OR read the JSONL line count before/after.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — JSONL record shape (inherited from Phase 2), HISTORICAL_STATE_MAP, summary report shape
- [contracts/api.md](contracts/api.md) — `backfill()` Python signature, raised exceptions
- [contracts/cli.md](contracts/cli.md) — CLI flags, stdin/stdout, exit codes
- [quickstart.md](quickstart.md) — operator dry-run → live-run walkthrough + rollback procedure

### Charter re-check (post-design)

Same outcome — no constraints. Pass.

---

## Branch contract (restated)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **branch_matches_target**: `true`

---

## Stop

Planning artifacts complete. Next: `/spec-kitty.tasks`.
