---
work_package_id: WP01
title: Vikunja task-migration helper, manifest, scope config, tests, docs
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- NFR-001
- NFR-002
- NFR-003
- NFR-004
tracker_refs: []
planning_base_branch: feat/vikunja-migrate-tasks
merge_target_branch: feat/vikunja-migrate-tasks
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-migrate-tasks. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-migrate-tasks unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
- T008
- T009
agent: "claude"
shell_pid: "61789"
shell_pid_created_at: "1783890876.786286"
history:
- created by /spec-kitty.tasks 2026-07-12
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/
create_intent:
- scripts/vikunja/migrate_tasks.py
- scripts/vikunja/task_migration_manifest.yaml
- tests/vikunja/test_migrate_tasks.py
execution_mode: code_change
owned_files:
- scripts/vikunja/migrate_tasks.py
- scripts/vikunja/task_migration_manifest.yaml
- tests/vikunja/test_migrate_tasks.py
- scripts/common/vikunja_scope.py
- tests/common/test_vikunja_scope.py
- scripts/enrichment/reconcile_completions.py
- tests/enrichment/test_reconcile_completions.py
- docs/design/vikunja-configuration-design.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:

```
/ad-hoc-profile-load python-pedro
```

Adopt the python-pedro identity (TDD, type safety, idiomatic Python 3.12), then
continue.

## Objective

Ship a deterministic, idempotent Python helper `scripts/vikunja/migrate_tasks.py`
(driven by a committed manifest) that migrates surviving Vikunja tasks into their
correct topic projects, applies `t:habit`, deletes two test tasks, and deletes six
emptied legacy projects — plus the scope-config cleanup and a design-doc update.
The **live run is operator-invoked post-merge** (this WP ships code + tests +
manifest + docs only; it must NOT call the live Vikunja).

Implements FR-001..FR-011 and NFR-001..NFR-004. Read `spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/migrate_tasks_cli.md`,
`contracts/manifest_schema.md` in this mission dir before starting.

## Context & established idioms (match these — do not invent new patterns)

- **Client**: `scripts/common/vikunja_client.py` → `VikunjaClient` with
  `get/post/put/delete(path, *, json=..., params=..., timeout=...)`. **Paths need a
  LEADING SLASH** (`/tasks/all`), base_url already ends `/api/v1`. Stdlib only — no
  `requests`.
- **Mirror `scripts/vikunja/reconcile_projects.py` (#716)** for structure: a
  `@dataclass` plan, `build_plan()` (pure) / `reconcile()` (effectful) split,
  fail-loud `ReconcileError`, the `DEFAULT_KENT_TOKEN_FILE` /
  `FELIX_BOT_TOKEN_FILE` constants, and the identity guard that refuses the
  felix-bot path. Reuse its token-loading approach verbatim in spirit.
- **Task update / move**: `POST /tasks/{id}` is **partial-replace and zeros
  unstated fields** (#524; see `scripts/vikunja/create_task.py:16`). Move = GET the
  task, build a payload from the writable-field allowlist + new `project_id`, POST,
  then GET again (readback) and assert only `project_id` changed. Precedent for a
  field-scoped RMW: `scripts/habits/record_completion.py:267`.
- **Label attach**: `PUT /tasks/{id}/labels` with `{"label_id": <id>}` (see
  `scripts/vikunja/setup_goals.py:227,261`). Idempotent: skip if already present.
- **Label lookup**: `GET /labels` paginated `per_page=50` (see
  `scripts/vikunja/create_taxonomy_labels.py`); resolve `t:habit` id by title.
- **Pagination**: Vikunja caps `per_page` at 50; page until a short page. Never
  stop on `len < 100`.
- **Two-token model (#715)**: config/label-attach requires the **kent** token
  (`/data/services/openclaw/secrets/vikunja-api-kent`); felix-bot gets 403.
- Live audit ids (fixed): doomed = Everyday 2, Someday 4 (child of 2), Personal
  Growth 5, Household 15, Goals 11, Research 12. Targets = Personal 20, Felix/
  kg-automation 16, Intentional LLC 9, Habits 13 (retained). Inbox 1 retained.

## Subtasks

### T001 — Committed manifest + loader/validator

- Create `scripts/vikunja/task_migration_manifest.yaml` transcribing the EXACT
  locked routing from `contracts/manifest_schema.md` → "Locked content" (29 moves
  grouped by target with source-project annotations, 11 `label_habit`, 2
  `delete_tasks`, 6 `delete_projects` children-first, `target_projects` map). Do
  NOT re-derive routing — copy the committed contract table verbatim. The fidelity
  test (T008) asserts exact equality, so any transcription error fails fast.
- `load_manifest(path) -> Manifest`: parse YAML (`PyYAML`), enforce static
  invariants (data-model.md → "Validation"): every `moves` value is a known
  `target_projects` key; all ids positive ints; `moves.keys()`, `label_habit`,
  `delete_tasks` pairwise disjoint; `delete_projects` lists 4 before 2;
  `target_projects == {personal:20, felix:16, intentional:9, habits:13}`. Raise
  `ReconcileError` (fail-loud) on any violation.
- **Fidelity**: the committed manifest must equal the locked sets — a test asserts
  exact dict/list equality (FR-008).

### T002 — `list_all_tasks` (paginated, done-inclusive) + per-project derivation

- `list_all_tasks(client) -> list[dict]`: page `GET /tasks/all?per_page=50&page=N`
  until a page returns `< 50`; concat; a `null` body → `[]`; a non-list/non-null
  body → raise `VikunjaError`/`ReconcileError`. **No `done` filter** — include done
  tasks (NFR-004). This is the single source for both the move plan and the
  project empty-check (so done tasks are always counted).
- `tasks_in_project(all_tasks, pid) -> list[dict]`: client-side filter on
  `project_id`.

### T003 — `preflight` (identity + target + complex-state)

`preflight(client, all_tasks, projects, labels, manifest) -> list[blocked]`
(FR-010/FR-011, before any mutation):
- assert every `target_projects` id AND every `delete_projects` id resolves live
  with the expected title (from a title map you encode) + parent id +
  `owner.username == "kent"` and is not archived; else raise;
- resolve `t:habit` to exactly one kent-visible label id (raise on 0 or >1);
- assert every `label_habit` task is currently in Habits(13); else raise;
- scan each moved task for complex state — non-empty `assignees`,
  `related_tasks`, `reminders`, `attachments`, `bucket_id` (kanban), or a
  parent/subtask link — and return those as `blocked` (kind="move", reason). Do
  NOT migrate a blocked task.

### T004 — `build_plan` (pure diff)

`build_plan(projects, all_tasks, labels, manifest, blocked) -> MigrationPlan`
(data-model.md → "Mutation-plan model"): compute `moves` (only where current
`project_id != target`), `labels` (only where `t:habit` absent), `task_deletes`
(only where still present), `project_deletes` (only where still present),
`skipped` (already-satisfied — idempotency evidence), `blocked` (from preflight +
non-empty doomed projects). Pure: no I/O. Idempotent re-run over post-migration
state ⇒ empty plan.

### T005 — `move_task` (allowlisted RMW + readback) + `apply_habit_label`

- `_writable_payload(task) -> dict`: copy the allowlist (NFR-001): `title,
  description, due_date, repeat_after, repeat_mode, priority, done, done_at,
  hex_color, percent_done, start_date, end_date`. (Confirm exact field names
  against a live `GET /tasks/{id}` shape / existing helpers; omit any the server
  rejects on POST.)
- `move_task(client, task, to_pid)`: build payload = `_writable_payload(task)` +
  `{"project_id": to_pid}`; `POST /tasks/{id}`; **readback** `GET /tasks/{id}` and
  assert `project_id == to_pid` and each allowlist field unchanged; else raise.
- `apply_habit_label(client, task, label_id)`: skip if present; else `PUT
  /tasks/{id}/labels {"label_id": label_id}`.

### T006 — deletions + `reconcile` orchestration + summary + CLI

- `delete_test_tasks` (`DELETE /tasks/{id}`) — runs **before** the project
  empty-check (H-5: #89 lives in doomed Someday(4)).
- `delete_projects`: for each id in manifest order (children first), **re-list**
  its tasks off a fresh `list_all_tasks` *immediately* before deleting; refuse
  (raise) if non-empty; else `DELETE /projects/{id}`.
- `reconcile(client, manifest, *, apply, backup_ref)` per data-model.md steps 1–8:
  fetch → preflight → build_plan → (dry-run print & return if not apply) → raise if
  delete present and `backup_ref` empty → raise if `blocked` non-empty → execute
  moves → labels → task-deletes → project-deletes → print summary (each action
  completed/skipped/blocked; echo `backup_ref`).
- `main(argv)` + `argparse` per `contracts/migrate_tasks_cli.md`: `--manifest`,
  `--token-file` (default kent secret; **refuse the felix-bot path up front**),
  `--apply`, `--backup-ref`, `--json`. Exit 0 on dry-run / success / no-op; exit 1
  fail-loud. Module runnable as `python3 -m scripts.vikunja.migrate_tasks`.

### T007 — scope-config cleanup (BOTH seams) + tests

- `scripts/common/vikunja_scope.py`: `ESCALATION_EXCLUDED_PROJECT_IDS = [13]`
  (drop 11); update the comment (Goals deleted by #717; Habits 13 stays). **Leave
  `HABIT_SELECTOR` on `{project_id: 13}`** (C-004 — do NOT flip to label).
- `scripts/enrichment/reconcile_completions.py:153`: `EXCLUDED_PROJECT_IDS =
  frozenset({13})` (drop 11); update the comment (remove the Goals rationale, keep
  Habits).
- `tests/common/test_vikunja_scope.py`: change the two asserts `== [11, 13]` →
  `== [13]`. This encodes "former Goals tasks are no longer excluded" (SC-006).
- `tests/enrichment/test_reconcile_completions.py:452`: retarget the excluded
  fixture `project_id=11` → `project_id=13` (Habits, still excluded), keeping the
  test's intent (an excluded-project task is skipped).
- Do NOT touch `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md` (deferred
  audited-surface prompt).

### T008 — helper unit tests (`tests/vikunja/test_migrate_tasks.py`)

Mock `VikunjaClient` (no live calls), mirror `tests/vikunja/test_reconcile_projects.py`.
Cover: manifest load + all static invariants (incl. disjointness, order, target
ids); manifest **fidelity** vs locked sets; `list_all_tasks` pagination incl. a
>50-task page and a `null` body; **idempotency** (empty plan over post-migration
state → 0 mutations); move RMW **readback** (payload includes allowlist fields;
readback mismatch raises); label attach skip-if-present; **empty-check** blocks a
project holding a done-only task and a >50-task project; **ordering** (test-task
delete precedes project empty-check so Someday doesn't self-block); `--backup-ref`
required for deletes; identity guard refuses the felix-bot path; preflight blocks a
complex-state task and a wrong-owner/wrong-title project. Meet the repo
branch-coverage threshold (NFR-003).

### T009 — design-doc update

`docs/design/vikunja-configuration-design.md`: mark migration-sequence **step 5**
done; record the final project distribution (six legacy projects deleted; tasks in
Personal/Felix/Intentional/Habits). Keep frontmatter valid (docs-CI).

## Branch Strategy

Planning/base branch: `feat/vikunja-migrate-tasks`. Final merge target: `main`
(feat → main after the post-merge Codex review). This mission is flattened
`single_branch`; your execution worktree is allocated from `lanes.json` — work in
the lane worktree the implement step puts you in; all artifacts route to the
feature branch.

## Definition of Done

- [ ] All 9 subtasks complete; `migrate_tasks.py` runnable via `-m`, dry-run by default.
- [ ] `pytest tests/vikunja/test_migrate_tasks.py tests/common/test_vikunja_scope.py tests/enrichment/test_reconcile_completions.py -q` green; full `make test` green.
- [ ] Manifest fidelity test asserts the exact locked routing.
- [ ] No live Vikunja calls anywhere in tests or at import.
- [ ] `HABIT_SELECTOR` unchanged; both exclusion seams drop 11; TOOLS.md untouched.
- [ ] Design doc step 5 marked done; docs-CI (frontmatter/validate_docs) passes.

## Risks & reviewer guidance

- **Silent field loss on move** — reviewer: confirm the allowlist + readback diff, and that a readback mismatch raises (not warns).
- **Empty-check false-clear** — reviewer: confirm the empty-check uses done-inclusive `list_all_tasks` (not `/projects/{id}/tasks`) and re-lists immediately before each delete.
- **Self-block** — reviewer: confirm test-task deletes run before the project empty-check.
- **Identity** — reviewer: confirm felix-bot path refusal + preflight owner==kent.
- **Idempotency** — reviewer: confirm a second `build_plan` over post-state yields an empty plan.
- **Backup gate** — reviewer: confirm deletes require non-empty `--backup-ref`, echoed in the summary; the helper does not fake a Restic check.

## Activity Log

- 2026-07-12T21:14:47Z – claude – shell_pid=61789 – Assigned agent via action command
