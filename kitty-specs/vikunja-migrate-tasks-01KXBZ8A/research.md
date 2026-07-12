# Research: Vikunja Task Migration & Project Teardown

Phase 0. All findings grounded in the live audit (2026-07-12) and existing
`scripts/vikunja/` helpers, not assumption.

## R-01 — Move a task to another project without data loss

**Decision**: Read-modify-write. `GET /tasks/{id}` → `POST /tasks/{id}` with the
**full** existing task body plus the new `project_id`.

**Rationale**: Vikunja `POST /tasks/{id}` is partial-replace and **zeros unstated
fields** (#524; documented in `scripts/vikunja/create_task.py:16`). A naive
`POST {"project_id": N}` would wipe `due_date`, `repeat_after`, `labels`, etc.
RMW preserves them (NFR-001). Idempotent: if the fetched task's `project_id`
already equals the target, skip (no POST).

**Alternatives**: none viable — there is no dedicated "move" endpoint that
preserves fields; RMW is the established pattern.

## R-02 — Attach the `t:habit` label

**Decision**: Resolve the label id by title via `GET /labels` (paginated,
`per_page=50`), then `PUT /tasks/{id}/labels` with `{"label_id": <id>}`.

**Rationale**: Confirmed pattern in `scripts/vikunja/setup_goals.py:227,261`.
Idempotent: fetch the task's current labels and skip if `t:habit` is already
attached. Requires the **kent** token — felix-bot gets 403 on attach (#715); the
identity guard (R-06) enforces this.

## R-03 — Delete tasks and projects

**Decision**: `DELETE /tasks/{id}` for the two test artifacts; `DELETE
/projects/{id}` for the six emptied projects. Before deleting a project, re-list
its tasks and **refuse** (fail-loud) if any remain. Delete children before
parents: Someday(4) before Everyday(2); the other four are top-level.

**Rationale**: Deleting a project cascade-deletes its tasks in Vikunja; the
empty-check (FR-006) prevents cascade-deleting an unmigrated task. Ordering
avoids orphaning a child under a just-deleted parent. All deletions gated on
`--backup-confirmed` (NFR-002, Tier 2).

## R-04 — Idempotency & dry-run

**Decision**: `build_plan(live_state, manifest)` is a pure function computing the
mutation set (moves needed, labels needed, deletes needed) by diffing the
manifest against live state. Default invocation prints the plan (dry-run);
`--apply` executes it. A re-run after a complete apply yields an empty plan →
zero mutations (FR-005, SC-005).

**Rationale**: Mirrors the shipped `reconcile_projects.py` (#716) `build_plan` /
`reconcile` split — same idiom, tests, and operator ergonomics.

## R-05 — `vikunja_scope.py` blast radius

**Decision**: Remove `11` from `ESCALATION_EXCLUDED_PROJECT_IDS` (→ `[13]`).
Leave `HABIT_SELECTOR` on `{project_id: 13}` (C-004).

**Consumers** (grep-verified):
- `scripts/habits/query_active_habits_weekly.py:91` → `habit_project_id()` (reads HABIT_SELECTOR). **Unaffected** — Habits(13) retained, selector unchanged.
- `scripts/escalation/enumerate_candidates.py:72` → `get_escalation_excluded_project_ids()`. Returns `[13]` after the edit.
- Tests: `tests/escalation/test_enumerate_candidates.py` (sources exclusions from scope) and the `vikunja_scope` unit test pinning `[11,13]` → update to `[13]`.

**Consequence noted**: the 2 former Goals tasks (#1, #13) move to Intentional
LLC(9), which is not excluded, so they become escalation candidates. Both carry
far-future due dates (2026-09-30); escalation is due-date-driven, so no near-term
nagging. Removing `11` is cleanup of a now-dead reference (excluding a deleted
project id never raises — it simply matches nothing), consistent with SC-006.
*Flag for post-plan review: confirm goals-as-candidates is acceptable vs. adding
a goal-exclusion mechanism (out of current scope).*

## R-06 — Identity guard

**Decision**: Read the token only from an explicit `--token-file` defaulting to
the kent secret `/data/services/openclaw/secrets/vikunja-api-kent`; refuse the
felix-bot token path (`/data/services/openclaw/secrets/vikunja-api`) up front.

**Rationale**: Direct reuse of `reconcile_projects.py`'s guard (#716 post-merge
Codex HIGH #1). Label attach and config mutation require kent; a felix-bot run
would 403 mid-way or mutate under the wrong owner.

## R-07 — Ownership / whoami

**Decision**: No `/user` whoami (401 for API tokens, R-07 from #716). Trust the
explicit kent token-file path + the guard; optionally assert `owner.username ==
"kent"` on projects the plan touches, mirroring reconcile.
