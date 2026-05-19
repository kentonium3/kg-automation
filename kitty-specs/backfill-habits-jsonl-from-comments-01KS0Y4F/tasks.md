# Tasks: Backfill habits JSONL from Felix comments

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Mission ID**: `01KS0Y4F60A30H8CT28Z3VMVT6`
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Source issue**: [#307](https://github.com/kentonium3/kg-automation/issues/307)
**Branch strategy**: planning_base=`main`, merge_target=`main`, branch_matches_target=`true`

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Implement `scripts/habits/backfill_jsonl_from_comments.py` — HISTORICAL_STATE_MAP, project-scoped enumeration (mirroring Phase 3 reconcile), backfill() with idempotency + .bak snapshot + summary report, `__main__` CLI | WP01 | | [D] |
| T002 | Create `tests/habits/test_backfill_jsonl_from_comments.py` — dry-run, live, idempotency, unmapped state, malformed comment, project resolution failures | WP01 | | [D] |
| T003 | Update `docs/design/architecture/data/data-flows.json` — add the one-shot backfill flow (source="historical-backfill") | WP01 | [D] |
| T004 | Update `docs/design/architecture/data/service-inventory.json` — register the new script under `habit-checkin` | WP01 | [D] |

`[P]` = parallel-safe (different file/concern; no inter-subtask dependency)

---

## Work Packages

### WP01 — Backfill helper + tests + architecture documentation

**Prompt**: [tasks/WP01-backfill-helper-and-arch-docs.md](tasks/WP01-backfill-helper-and-arch-docs.md)
**Goal**: Deliver the complete one-shot backfill helper (`scripts/habits/backfill_jsonl_from_comments.py`), its exhaustive test suite, and architecture-doc updates. After this WP merges and the operator runs the helper, historical `[Felix]` completion comments become JSONL records via the Phase 2 `state_log` library — preserving the data before Phase 5 cutover (#308).
**Priority**: P0 (only WP — full Phase 4 scope)
**Dependencies**: none (Phase 3 deliverables already on main via mission #40)
**Estimated prompt size**: ~400 lines

#### Included subtasks

- [x] T001 Implement `scripts/habits/backfill_jsonl_from_comments.py`
- [x] T002 Create `tests/habits/test_backfill_jsonl_from_comments.py`
- [x] T003 Update `docs/design/architecture/data/data-flows.json`
- [x] T004 Update `docs/design/architecture/data/service-inventory.json`

#### Implementation sketch

1. **Helper** (T001): import `FELIX_COMMENT_PATTERN` from `scripts.habits.exclude_completed` (single source of truth for the regex). Mirror `_resolve_habits_project_id` pattern from `scripts.habits.reconcile_completions`. Implement `backfill()` per `contracts/api.md` — pre-flight read of state log (Phase 2 handles dedup), per-task comment enumeration, per-comment parse + map + append, summary report build. `__main__` CLI per `contracts/cli.md` with flags `--dry-run`, `--token-file`, `--base-url` and exit codes 0/1/2/3/4.
2. **Tests** (T002): three layers per research D9 — mocked urllib for HTTP, real `state_log.append` against `tmp_path` STATE_DIR, no live-probe in CI. Cover: happy-path dry-run, happy-path live, idempotency (re-run after live = 0 appends), unmapped state value handling, malformed comment skipping, project resolution failure (0 or >1 matches), snapshot creation, snapshot skip when source doesn't exist, anomaly reporting (missing comment.created).
3. **Doc updates** (T003, T004): both small. T003 adds an entry to `data-flows.json`'s flows list; T004 adds an entry to the existing `habit-checkin` service's `config_files`/`scripts` section.

#### Parallel opportunities

T001 and T002 are sequential (test depends on the helper). T003 and T004 are independent of each other AND of T001/T002 — could be tackled first as warm-up edits if desired.

#### Risks

- **Vikunja `created` field shape**: assumed ISO-8601 with timezone. If a comment has a missing or malformed `created`, the helper logs the anomaly and skips (no append). Test must cover this.
- **Importing from `exclude_completed.py`**: this is a one-directional read of `FELIX_COMMENT_PATTERN`. C-001 forbids MODIFYING `exclude_completed.py` until Phase 5 cutover; READING from it is fine. Reviewer should confirm no edits leak into the v1 file.
- **State_log.append OSError mid-batch**: rare (local I/O), but if it happens, the helper should record an anomaly + continue. Per-record append failure does not abort the run.
- **Snapshot copy failure**: live run aborts with exit 3 BEFORE any append. Operator triages (disk full, perm, etc.) then re-runs.
- **Operator forgets `--dry-run` first**: spec doesn't enforce a dry-first gate; this is operator discipline. The runbook (quickstart.md) makes the dry-run-first pattern explicit. The helper is forgiving — re-runs are idempotent.

#### Success criteria (from spec.md)

Mapped to:
- FR-001..FR-012 (full functional surface)
- NFR-001..NFR-005 (latency, no-deps, coverage ≥85%, no sensitive-data leakage)
- C-001..C-007 (constraints — felix-bot identity, no enum extension, dual surface, regex reuse, retired workout in scope, new MWF no-op, no cron change)

---

## Dependency graph

```
WP01 (only WP, no deps)
```

Single-WP mission. Phase 3 deliverables (state_log library #305, reconcile + record + identify helpers from #306) are all on main already.

## MVP scope

**MVP = WP01** (the entire mission). No staging; the helper either ships in working form or doesn't.

## Parallelization summary

Within WP01: T003 + T004 (doc updates) are parallel-safe with T001 + T002 (code). Implementer can tackle them in any order; the file-level concerns are independent.

## Notes for implementer

- The Vikunja `created` field format observed in production probes is `YYYY-MM-DDTHH:MM:SSZ` (ISO-8601 with `Z` suffix). Phase 2's `state_log.validate_record` accepts this via `datetime.fromisoformat()` (Python 3.11+).
- `HABITS_PROJECT_TITLE = "Habits"` matches Phase 3's `reconcile_completions.py` constant. The 2026-05-19 probe confirmed the Habits project ID is 13 — but the helper resolves dynamically, not by hardcoded ID, in case the project is recreated.
- Production data is sparse (~26 comments total across 8 tasks). Tests should validate behavior with both empty datasets (new MWF tasks have zero comments) AND populated datasets (the 8 original habits).
- The summary report's `unmapped-state-values` section is the operator's primary signal for whether to update `HISTORICAL_STATE_MAP`. Make sure the report names every distinct unmapped value, the count per value, and 1-2 example source comments so the operator can make the mapping decision intelligently.
- Spec FR-005 mandates `title` field is the Vikunja task's CURRENT title at backfill time (not the comment-time title — comments don't carry titles). Document this in the helper's docstring per research D6.
