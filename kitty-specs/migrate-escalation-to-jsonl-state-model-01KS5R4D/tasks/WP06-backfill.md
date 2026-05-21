---
work_package_id: WP06
title: backfill_jsonl_from_comments (one-time)
dependencies:
- WP03
- WP04
requirement_refs:
- C-007
- FR-006
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T018
- T019
- T020
agent: "claude:opus:python-implementer:implementer"
shell_pid: "5187"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/escalation/backfill_jsonl_from_comments.py
- tests/escalation/test_backfill.py
tags: []
---

# WP06 — backfill_jsonl_from_comments (one-time)

## Objective

Implement the one-time replay of `[Felix-Escalation]` Vikunja comments to JSONL records. Reuses the Phase 4 pattern from `scripts/habits/backfill_jsonl_from_comments.py`. Adapted vocabulary mapping per data-model Entity 3. Writes a pre-backfill snapshot (Entity 4) before any JSONL writes. Reports malformed comments per Phase 4 cycle 2 lesson — collects + reports but never replays.

## Context

- **Mission spec**: FR-006 (one-time backfill, Phase 4 pattern), SC-004 (all tasks backfilled), C-007 (no comment-watcher daemon)
- **Research**: D5 (vocabulary mapping, malformed-comment handling)
- **Data model**: Entity 3 (comment → JSONL mapping table), Entity 4 (snapshot schema)
- **API contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md` — `backfill_project`, `BackfillReport`, `MalformedComment`
- **CLI contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md` — flags + exit codes
- **Habits Phase 4 precedent**: `scripts/habits/backfill_jsonl_from_comments.py` — read it before starting. Same pattern: locked vocabulary, snapshot, idempotent.
- **Dependencies**:
  - **WP03**: uses `record_event` with `source="backfill"` AND `--no-vikunja` to emit replayed records (no re-PUT of comments during replay).
  - **WP04**: backfill does NOT file hard-fail bugs. Malformed comments are summary-reported only (per D5).
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T018 — Implement `scripts/escalation/backfill_jsonl_from_comments.py`

**Purpose**: Walk every Vikunja task with `[Felix-Escalation]` comments, parse them per the locked mapping (D5), emit JSONL records. Snapshot first.

**Steps**:

1. Module docstring describing the locked mapping + idempotency.
2. Imports: stdlib + `scripts.escalation.record_completion`, `scripts.escalation.schema`. Plus a small regex toolkit for parsing comment text.
3. Module constants:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
   SNAPSHOT_PATH = Path("/data/services/openclaw/state/escalation/pre-phase6-snapshot.json")
   JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")
   FELIX_COMMENT_PREFIX = "[Felix-Escalation]"
   SNAPSHOT_VERSION = 1
   ```
4. Define `MalformedComment` and `BackfillReport` frozen dataclasses per contracts/api.md.
5. Define comment-parsing regex set:
   ```python
   _COMMENT_RE = re.compile(
       r"^\[Felix-Escalation\] (?P<date>\d{4}-\d{2}-\d{2}) \| (?P<state>[^|]+) \| (?P<disposition>\w+)$"
   )
   _SNOOZED_RE = re.compile(r"^snoozed:(\d+)d$")
   _RESCHEDULED_RE = re.compile(r"^rescheduled:(\d{4}-\d{2}-\d{2})$")
   _LEVEL_RE = re.compile(r"^level-([12])$")
   ```
6. Implement `parse_comment(comment_text: str, task_id: int, project_id: int, task_title: str) -> dict | None`:
   - Returns the parsed record dict ready for `record_event`, OR `None` if malformed.
   - If `None`: caller appends to malformed list.
   - Logic:
     - `_COMMENT_RE.match(text)` → extract `date`, `state`, `disposition`.
     - For each state token, apply the locked mapping (data-model Entity 3):
       - `level-1` → `state="level_sent", level=1`
       - `level-2` → `state="level_sent", level=2`
       - `snoozed:Nd` → `state="snoozed", snooze_days=N, snooze_until=<date + N days>`
       - `dismissed` → `state="dismissed"`
       - `done` → `state="done"`
       - `rescheduled:YYYY-MM-DD` → `state="rescheduled", reschedule_to=<date>`
     - Compose final record dict with all required fields. `source="backfill"`. `timestamp=f"{date}T12:00:00+00:00"` (noon UTC placeholder per D5).
7. Implement `_write_snapshot(snapshot_data: dict, snapshot_path: Path) -> None`:
   - Per data-model Entity 4 schema.
   - Atomic: write to `<path>.tmp`, fsync, rename to `<path>`.
8. Implement `backfill_project(project_id: int, *, base_url=..., token_path=..., dry_run=False, include_resolved=False) -> BackfillReport`:
   - Read token.
   - Enumerate tasks in project: GET /projects/{id}/tasks (paginate). Filter by `comments` field having any matching `[Felix-Escalation]` prefix (may require separate GET /tasks/{id}/comments — check Vikunja API surface).
   - Build snapshot data structure.
   - If NOT dry_run: write snapshot to disk.
   - For each task:
     - For each `[Felix-Escalation]` comment:
       - Try `parse_comment(...)`. If `None`: append to malformed list (with task_id, snippet, reason).
       - Else: if NOT dry_run, call `record_completion.record_event(record, ...)` with the `--no-vikunja` semantics. Increment `comments_replayed`.
   - Populate and return `BackfillReport`.
9. Implement `backfill_all(*, ..., dry_run=False) -> list[BackfillReport]`:
   - Iterate the projects discovered via the Vikunja API (GET /projects).
   - Skip projects with `id` in `{11, 13}` (Goals, Habits — per SKILL.md §1 exclusions).
   - Filter for projects with at least one escalation-subscribed task (via comment-prefix scan).

**Files**:
- `scripts/escalation/backfill_jsonl_from_comments.py` (new, ~380 lines)

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.escalation.backfill_jsonl_from_comments import backfill_project, BackfillReport, MalformedComment, parse_comment; print('ok')"` prints `ok`.
- [ ] `parse_comment("[Felix-Escalation] 2026-05-15 | level-1 | sent", 1, 4, "T")` returns a dict with `state="level_sent"`, `level=1`, `date="2026-05-15"`.

---

### T019 — CLI surface

**Purpose**: Per contracts/cli.md.

**Steps**:

1. `def main(argv=None) -> int` with argparse:
   - Required: one of `--project-id <int>` or `--all`.
   - Optional: `--dry-run`, `--include-resolved`, `--base-url`, `--token-path`.
2. Dispatch to `backfill_project` or `backfill_all`.
3. Stdout per contracts/cli.md:
   - Per-malformed line: `MALFORMED task=<id> project=<id> snippet="<first 80 chars>" reason=<parse-error>`.
   - Final JSON summary block.
4. Exit codes per contracts/cli.md:
   - 0: backfill complete (may include malformed).
   - 1: Vikunja fatal.
   - 2: JSONL or snapshot write failure.
   - 3: validation/usage error.
5. `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/escalation/backfill_jsonl_from_comments.py` (extended with CLI, +~100 lines)

**Validation**:
- [ ] `python3 -m scripts.escalation.backfill_jsonl_from_comments --help` prints help.
- [ ] CLI with both `--project-id` and `--all` exits 3 (mutually exclusive).

---

### T020 — Tests for backfill

**Purpose**: Cover the vocabulary mapping comprehensively, plus snapshot, malformed reporting, dry-run, and idempotency.

**Steps**:

1. Create `tests/escalation/test_backfill.py`.
2. Test cases:
   - **`parse_comment` per vocabulary row** (D5 + data-model Entity 3):
     - `test_parse_level_1_sent`
     - `test_parse_level_2_sent`
     - `test_parse_snoozed_3d` — also verifies `snooze_until` computed = comment_date + 3 days
     - `test_parse_snoozed_7d`
     - `test_parse_dismissed`
     - `test_parse_done`
     - `test_parse_rescheduled` — verify `reschedule_to` field
   - **`parse_comment` malformed cases**:
     - `test_parse_no_felix_prefix` — comment without `[Felix-Escalation]` → returns `None`.
     - `test_parse_wrong_separator` — `,` instead of ` | ` → `None`.
     - `test_parse_unknown_state` — `state="acknowledged"` (unknown vocabulary) → `None`.
     - `test_parse_invalid_date` — `2026-13-99` → `None`.
     - `test_parse_snoozed_invalid_days` — `snoozed:abcd` → `None`.
   - **`backfill_project` integration**:
     - `test_backfill_writes_snapshot_first` — assert snapshot file written before any JSONL line. Use file-existence ordering check.
     - `test_backfill_replays_parseable_comments` — mock Vikunja returns 3 tasks with 5 total comments (4 parseable, 1 malformed). Assert: 4 records emitted, 1 in malformed list.
     - `test_backfill_dry_run_no_writes` — dry_run=True. Assert: snapshot NOT written, JSONL NOT modified. Report still populated.
     - `test_backfill_skips_terminal_unless_include_resolved` — task with `done=true` in Vikunja. With `include_resolved=False` (default), no replay. With `include_resolved=True`, replay happens.
     - `test_backfill_excludes_goals_and_habits_projects` — projects 11 and 13 skipped in `backfill_all`.
   - **Idempotency**:
     - `test_backfill_idempotent_on_rerun` — run twice. Second run produces 0 new records (state_log dedup).
   - **Malformed report contents**:
     - `test_malformed_report_includes_snippet` — Malformed list entry contains `snippet` (first 80 chars of comment) + `reason`.
   - **Snapshot content**:
     - `test_snapshot_schema_v1` — snapshot JSON has `snapshot_version=1`, `created_at` ISO-8601, `tasks` array with all expected fields per Entity 4.
3. Coverage target: ≥85% line + branch.

**Files**:
- `tests/escalation/test_backfill.py` (new, ~380 lines, ~17 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_backfill.py -v` all green.
- [ ] Coverage ≥85% line + branch.
- [ ] All 6 vocabulary rows from D5 / Entity 3 have explicit parse tests.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

pytest. Vikunja API mocked via `mock_urlopen`. Filesystem writes go to `tmp_path`. The state_log idempotency test uses the real `state_log.append` against `mock_state_log_dir`.

## Definition of Done

- [ ] T018-T020 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/test_backfill.py -v` passes.
- [ ] Coverage ≥85% line + branch.
- [ ] All 6 vocabulary rows from data-model Entity 3 have explicit parse tests.
- [ ] Snapshot is written BEFORE any JSONL line is appended.
- [ ] Idempotency verified: second run = 0 new records.

## Risks

- **Vocabulary drift**: if the existing SKILL.md vocabulary is updated mid-mission, parse_comment will produce malformed-reports for the new shapes. Mitigation: SKILL.md edits are owned by WP07, which happens AFTER WP06.
- **Comment pagination**: Vikunja's GET /tasks/{id}/comments may be paginated. Implementation must handle multi-page responses or this WP misses old comments. Read Vikunja API docs (or existing habits backfill) to verify.
- **noon UTC timestamp**: per D5, backfill records use `<date>T12:00:00+00:00` as a synthetic timestamp. If actual `created` field is available from Vikunja's comment object, prefer it. Implementation should attempt to read `comment.created` first.

## Reviewer Guidance

1. Verify `parse_comment` covers every D5 row.
2. Verify snapshot is written BEFORE any JSONL writes (file-existence ordering).
3. Verify Goals (11) and Habits (13) projects are excluded from `backfill_all`.
4. Verify malformed comments are collected with snippet + reason but NEVER replayed.
5. Verify idempotency holds (second run = no new records).
6. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP06 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T20:46:45Z – claude:opus:python-implementer:implementer – shell_pid=5187 – Started implementation via action command
