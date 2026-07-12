# Research: Vikunja Task Migration & Project Teardown

Phase 0. All findings grounded in the live audit (2026-07-12) and existing
`scripts/vikunja/` helpers, not assumption.

## R-01 — Move a task to another project without data loss

**Decision**: Read-modify-write over an explicit **writable-field allowlist**
(not a blind echo of GET output): `GET /tasks/{id}` → build a payload copying
`title, description, due_date, repeat_after, repeat_mode, priority, done,
done_at, hex_color, percent_done, start_date, end_date` from the fetched task and
setting the new `project_id` → `POST /tasks/{id}`. Then **readback**: `GET
/tasks/{id}` again and assert only `project_id` changed (all allowlist fields
equal pre-move values). (Codex C-2.)

**Rationale**: Vikunja `POST /tasks/{id}` is partial-replace and **zeros unstated
fields** (#524; `scripts/vikunja/create_task.py:16`). But blindly echoing the GET
body risks server-rejected read-only fields and does not surface fields the move
can silently drop. The repo RMW precedent (`scripts/habits/record_completion.py:267`)
preserves a specific field set, not the whole object. Idempotent: if the fetched
task's `project_id` already equals the target, skip.

**Complex-state guard**: a moved task carrying assignees, `related_tasks`,
reminders, attachments, kanban `bucket_id`, or parent/subtask links is **not**
safely preservable by a field-copy POST → the preflight blocks and reports it
(FR-011) rather than migrating it. For the known 29 tasks this set is expected
empty, but the guard prevents silent loss if the live state differs.

**Alternatives**: none viable — there is no dedicated field-preserving "move"
endpoint; allowlisted RMW + readback is the safe pattern.

## R-02 — Attach the `t:habit` label

**Decision**: Resolve the label id by title via `GET /labels` (paginated,
`per_page=50`), then `PUT /tasks/{id}/labels` with `{"label_id": <id>}`.

**Rationale**: Confirmed pattern in `scripts/vikunja/setup_goals.py:227,261`.
Idempotent: fetch the task's current labels and skip if `t:habit` is already
attached. Requires the **kent** token — felix-bot gets 403 on attach (#715); the
identity guard (R-06) enforces this.

## R-03 — Delete tasks and projects

**Decision**: `DELETE /tasks/{id}` for the two test artifacts; `DELETE
/projects/{id}` for the six emptied projects. The empty-check enumerates **all**
tasks incl done via `list_all_tasks` (paginated `/tasks/all`, `per_page=50`,
no `done` filter — NFR-004) filtered by `project_id`, and is re-run
**immediately before** each individual project delete (not once up front — C-1).
Ordering: **test-task deletes run first** (so #89, which lives in the doomed
Someday(4), is gone before Someday's empty-check — otherwise the run self-blocks,
Codex H-5); then project deletes, children before parents (Someday(4) before
Everyday(2); the other four top-level).

**Rationale**: Deleting a project cascade-deletes its tasks in Vikunja, and
`/projects/{id}/tasks` may omit done tasks or truncate at 50 — so the empty-check
must use the same done-inclusive paginated source the audit used, or it could
falsely clear a project holding hidden done tasks. The immediate re-list closes
the list-then-delete race. All deletions gated on a non-empty `--backup-ref`
(NFR-002, Tier 2), echoed in the summary.

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

**Consequence — RESOLVED (Codex M-9, accepted)**: the 2 former Goals tasks (#1,
#13) move to Intentional LLC(9), which is not excluded, so they become escalation
candidates. **Decision: accept this** — both carry far-future due dates
(2026-09-30) so escalation (due-date-driven) will not nag near-term, and Felix
surfacing a real goal deadline as it approaches is desirable, not a regression.
No replacement exclusion mechanism is added (that would be scope creep and there
is no Goals project or goal label to key it on). A test asserts the 2 goal task
ids are enumerable as candidates post-move (SC-006). Removing `11` is cleanup of
a now-dead reference (excluding a deleted project id never raises — it matches
nothing). *Surfaced to Kent in the post-plan summary.*

## R-06 — Identity guard

**Decision**: Read the token only from an explicit `--token-file` defaulting to
the kent secret `/data/services/openclaw/secrets/vikunja-api-kent`; refuse the
felix-bot token path (`/data/services/openclaw/secrets/vikunja-api`) up front.

**Rationale**: Direct reuse of `reconcile_projects.py`'s guard (#716 post-merge
Codex HIGH #1). Label attach and config mutation require kent; a felix-bot run
would 403 mid-way or mutate under the wrong owner.

**Not sufficient alone (Codex H-3/H-4)**: refusing the felix-bot *path* does not
prove the token is kent's — a different wrong token at another path would pass.
So the path guard is backed by a live **preflight** (R-08): every target and
doomed project must resolve with `owner.username == "kent"` and the expected
title + parent id, and `t:habit` must resolve to exactly one kent-visible label,
before any mutation. A wrong-identity token fails these live assertions.

## R-08 — Live preflight (identity + target + complex-state)

**Decision**: Before mutating, validate against live state (FR-010/FR-011):
target projects `personal=20/felix=16/intentional=9/habits=13` and every
`delete_projects` id each match expected **title + parent + owner==kent** and are
not archived; `t:habit` resolves uniquely; every `label_habit` task is in
Habits(13); every moved task is scanned for complex state (blocked if present).
Abort fail-loud on any mismatch. This upgrades numeric-id trust into verified
live identity for a destructive migration.

## R-07 — Ownership / whoami

**Decision**: No `/user` whoami (401 for API tokens, R-07 from #716). Trust the
explicit kent token-file path + the guard; optionally assert `owner.username ==
"kent"` on projects the plan touches, mirroring reconcile.
