# Research: Engineering decisions

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Phase**: 0 (research — tactical decisions)

Phase 4 is small in scope (one helper) and most architectural decisions are inherited from prior phases. This document records the few tactical choices specific to the backfill helper.

---

## D1 — Regex reuse: import vs duplicate

**Decision**: Import `FELIX_COMMENT_PATTERN` from `scripts/habits/exclude_completed.py`. Do NOT duplicate the regex.

**Rationale**:
- Single source of truth (per spec C-004).
- The regex is already validated against production data in `exclude_completed.py`'s test suite.
- One-directional dependency: backfill → exclude_completed v1. Constant-only import, no behavior coupling.
- C-001 (v1 sibling untouched until Phase 5) is NOT violated by reading from the file; it's only violated by modifying it.

**Implementation**:
```python
from scripts.habits.exclude_completed import FELIX_COMMENT_PATTERN
```

**Rejected alternatives**:
- **Duplicate the regex in backfill_jsonl_from_comments.py**: violates DRY; drift risk over time.
- **Extract regex to `scripts/common/`**: requires a Phase 2 amendment + coordination with the v1 sibling. Defer; revisit if Phase 5 cutover also needs the regex.

---

## D2 — HISTORICAL_STATE_MAP shape

**Decision**: Module-level `dict[str, str]` constant in the backfill helper. Locked to the 2026-05-19 production probe values:

```python
HISTORICAL_STATE_MAP: dict[str, str] = {
    "complete": "complete",
    "will-not-do": "skipped",
}
```

**Rationale**:
- Production data is small (26 records, 2 distinct state values). The map covers everything observed.
- Static dict is the simplest possible declaration; auditable in one glance.
- If new values surface during backfill, the helper's summary report's "unmapped-state-values" section names them, and the operator can extend the map + re-run.

**Rejected alternatives**:
- **YAML/JSON config file**: over-engineered for a 2-entry map. The helper is one-shot; a config file adds friction without benefit.
- **Class-based registry**: same overkill.
- **Inline `case` statements in the loop**: less discoverable; harder to audit at a glance.

---

## D3 — Idempotency: rely on Phase 2 dedup

**Decision**: The backfill helper does NOT maintain any "already-backfilled" state of its own. It relies entirely on Phase 2's `state_log.append` short-circuiting on the `(task_id, date, state)` dedup tuple.

**Rationale**:
- Phase 2 already provides idempotency at the API layer. Re-implementing it in the backfill helper would be duplicative.
- The dedup tuple is the canonical identity per ADR-0002 Q3; the backfill should not bypass it.
- Behavioral consequence: re-running the backfill is a fast no-op (each comment's `state_log.append` short-circuits without filesystem write). The summary report shows zero new writes on re-run.

**Rejected alternatives**:
- **Track a "last successful backfill" timestamp**: adds state that can drift from reality. Reject.
- **Use a hash-of-comment-id index sidecar**: more complex than needed; the dedup tuple already covers it.

---

## D4 — Pre-backfill snapshot strategy

**Decision**: `shutil.copy2` of `habits-history.jsonl` to `habits-history.jsonl.pre-phase4-backfill.bak` BEFORE the first append in a live run. Skipped if the JSONL log file doesn't yet exist.

**Rationale**:
- Operator-restorable rollback substrate: `cp <bak> <original>` undoes the backfill.
- `shutil.copy2` preserves mtime + permissions (cleaner than a raw `cp` equivalent).
- Skipping when the file doesn't exist avoids creating an empty `.bak` that would mask a real "log was empty" state during rollback.

**Atomicity caveats**:
- Single-writer model: the backfill helper is the only writer during its run (no concurrent agents writing to habits-history.jsonl at the same time — Phase 5 cutover hasn't happened).
- If the helper crashes mid-run between the copy and the first append, the `.bak` is identical to the live file. Safe.
- If it crashes after a partial backfill, the `.bak` has the pre-backfill state. Operator can restore.

**Rejected alternatives**:
- **Symlink snapshot**: doesn't capture content; useless for rollback.
- **Skip the snapshot, rely on append-only**: workable (filter `source="historical-backfill"` from the JSONL to undo), but a one-line `.bak` snapshot is simpler and faster to restore.
- **fsync the .bak**: marginal benefit; the OS will sync it before the next file operation. Don't over-engineer.

---

## D5 — Timestamp from comment.created

**Decision**: Use Vikunja's `created` field on each comment as the JSONL `timestamp`. Pass through verbatim without re-parsing.

**Rationale**:
- Phase 2's `state_log.validate_record` requires ISO-8601 with timezone. Vikunja's `created` is ISO-8601 with `Z` suffix (UTC).
- The historical timestamp is the most accurate signal of "when did this completion get recorded" — better than the backfill run time.
- Re-parsing risks introducing subtle formatting differences. Pass-through is safer.

**Edge case**: comment.created could in theory be malformed or missing. Helper should:
- Log to the summary report's `anomalies` section.
- Skip the record (do NOT call append with a malformed timestamp — state_log would reject anyway).

---

## D6 — Title denormalization

**Decision**: Fetch the `title` field for each JSONL record from the Vikunja task's current state at backfill time, NOT from the comment body. Comments don't carry the task title.

**Rationale**:
- Phase 2 JSONL schema requires `title` (it's `denormalized for human-readable history` per data-model.md from Phase 2).
- The Vikunja task's current title is the closest approximation. If the title has changed over time (e.g., "Workout" → "Workout 45 min"), all historical entries get the CURRENT title — that's a known and accepted limitation.

**Rejected alternatives**:
- **Use a placeholder like "<unknown>"**: violates the schema spirit.
- **Skip the title field**: state_log.validate_record rejects records missing required fields.

---

## D7 — Project-scoped enumeration (mirror Phase 3)

**Decision**: Reuse the project-scoping pattern from `scripts/habits/reconcile_completions.py::_resolve_habits_project_id`. Helper resolves "Habits" project via `GET /projects` (exact title match), then enumerates tasks via `GET /projects/<id>/tasks?filter=is_archived=false`.

**Rationale**:
- The Phase 3 WP03 rejection cycle explicitly punished broad enumeration (`/tasks/all`) because non-habit completions could leak into the habits log.
- Backfill has the same risk: if it enumerated all unarchived tasks, comments on non-habit tasks could parse as `[Felix]` records and be backfilled to the habits domain.
- The project-scoped pattern is the established convention; following it keeps the helper consistent with the rest of the habits domain.

**Implementation note**: copy-and-adapt the function from reconcile_completions.py (the helpers don't share a module). This is acceptable per D1 of Phase 3's research — each helper self-contained — but if it happens often, a shared module is the right long-term refactor.

---

## D8 — Summary report: plain text vs JSON

**Decision**: Plain text on stdout. Operator-facing readability prioritized.

**Rationale**:
- The backfill is operator-driven; Kent reads the output directly.
- Plain text with clear section headers is easier to scan than JSON.
- The summary's content is the same for dry-run vs live-run, just with a header line indicating mode + a `Records appended` vs `Records planned` distinction.

**Rejected alternatives**:
- **JSON output**: makes machine-parsing easier but adds friction to the operator workflow. Operator workflow is the priority.
- **Both** (e.g., `--format json` flag): scope creep for a one-shot helper.

---

## D9 — Test approach

**Decision**: Three test layers (per the Phase 3 pattern).

1. **Unit tests with mocked `urllib.request.urlopen`** (in `tests/habits/test_backfill_jsonl_from_comments.py`): cover all logic including dry-run, live-run, idempotency, unmapped-state handling, malformed-comment handling, project resolution failure.
2. **Real `state_log.append` against `tmp_path` STATE_DIR**: integration with Phase 2's library exercised at the file-I/O level (not mocked).
3. **No live-probe in CI**: per Kent's standing preference (#317 follow-up). Operator-driven canary on dry-run before live-run is the live integration check.

**Idempotency test pattern**: invoke `backfill()` twice in the same test. Assert the JSONL line count is the same after both calls. Optionally assert the per-call summary's "records appended" delta.

---

## D10 — Comment dedup within a single task

**Decision**: No explicit per-task comment deduplication in the helper. If a task somehow has multiple `[Felix]` comments with the same `(date, state)` tuple, only the first one's data gets persisted (the second one's `state_log.append` call short-circuits on dedup).

**Rationale**:
- Trust the Phase 2 dedup as the single source of truth.
- Don't second-guess Vikunja's data; just replay what's there.
- The summary report's `Records appended` vs `Records skipped (dedup)` counts will surface this if it happens, and the operator can investigate.

**Edge case**: a task with two comments for the same `(task_id, date, state)` triple is unusual but not impossible. Real-world cause: Kent typed the same `[Felix]` line twice in the UI. Cost of the bug: we lose the second comment's `note` field, if it differs. Acceptable.

---

## Summary

Ten engineering decisions documented. No `[NEEDS CLARIFICATION]` markers remain. The mission is small and most architectural decisions come from prior phases (Phase 2 state_log, Phase 3 project-scoping pattern). Ready for Phase 1 design artifacts.
