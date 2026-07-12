# Data Model: Vikunja Task Migration & Project Teardown

Phase 1.

## Manifest (`scripts/vikunja/task_migration_manifest.yaml`)

The committed carrier of Kent's human-judgment routing. Schema:

```yaml
target_projects:        # map: key -> live project id (from #716)
  personal: 20
  felix: 16
  intentional: 9
  habits: 13
moves:                  # map: task_id (int) -> target project key (str)
  42: personal
  50: felix
  1: intentional
  # ...
label_habit:            # list[int]: task ids that get the t:habit label
  - 14
  - 15
delete_tasks:           # list[int]: task ids to delete (test artifacts)
  - 89
  - 44
delete_projects:        # list[int]: project ids to delete, CHILDREN FIRST
  - 4
  - 2
  - 5
  - 15
  - 11
  - 12
```

**Validation** (`load_manifest`, static):
- every `moves` value is a known `target_projects` key;
- every id (keys of `moves`, members of `label_habit`/`delete_tasks`/`delete_projects`) is a positive int;
- `delete_projects` is an ordered list; a child must precede its parent (asserted for Someday(4) before Everyday(2));
- the id sets `moves.keys()`, `label_habit`, `delete_tasks` are **pairwise disjoint** (M-8);
- `target_projects` equals the locked #716 ids (personal 20, felix 16, intentional 9, habits 13).

**Live preflight** (`preflight`, before any mutation — FR-010/FR-011, C-2/H-3/H-4/M-8):
- every target project and every `delete_projects` id resolves live with the expected **title + parent id + `owner.username == "kent"`**; else abort;
- `t:habit` resolves to exactly one kent-visible label id; else abort;
- every `label_habit` task is currently in Habits(13); else abort;
- every moved task is inspected for complex state (assignees, `related_tasks`, reminders, attachments, kanban `bucket_id`, parent/subtask links); any present → **blocked**, not migrated.

## Entities (live Vikunja, read-only inputs)

### Task
| field | use |
|-------|-----|
| `id` | selector |
| `project_id` | current location; compared to target for idempotency |
| `labels` | list of `{id, title}`; checked for `t:habit` presence |
| `due_date`, `repeat_after`, `priority`, `description`, `done`, … | **preserved** across a move (RMW) |

### Project
| field | use |
|-------|-----|
| `id`, `title` | selector / reporting |
| `parent_project_id` | delete-order sanity |
| `owner.username` | kent-ownership assertion (R-07) |

### Label
| field | use |
|-------|-----|
| `id`, `title` | resolve `t:habit` id by title |

## Mutation-plan model (computed, in-memory)

`build_plan(projects, tasks, labels, manifest) -> MigrationPlan`

```
MigrationPlan:
  moves:          list[(task_id, from_project_id, to_project_id)]   # only where from != to
  labels:         list[(task_id, label_id)]                        # only where t:habit absent
  task_deletes:   list[task_id]                                    # only where still present
  project_deletes:list[(project_id, title)]                        # only where still present; empty-checked at apply
  skipped:        list[(kind, id, reason)]                         # already-satisfied (idempotency evidence)
  blocked:        list[(kind, id, reason)]                         # non-empty doomed project OR task w/ complex state (fail-loud at apply)
```

`reconcile(client, manifest, apply, backup_ref)`:
1. fetch live projects/labels + **all tasks** via `list_all_tasks` (paginated `/tasks/all`, `per_page=50`, incl done — NFR-004);
2. `preflight` (above) → abort on any identity/shape mismatch; collect complex-state `blocked`;
3. `build_plan`;
4. if not `apply` → print plan (incl `blocked`), return 0;
5. if plan has any delete and `backup_ref` is empty → raise (NFR-002);
6. if `blocked` non-empty → raise (FR-006/FR-011) — never migrate/delete around a blocked item;
7. execute in order: **moves** (RMW + post-move readback diff) → **labels** → **task-deletes** (incl the test tasks, BEFORE the project empty-check — H-5) → **project-deletes**: for each, re-list its tasks *immediately* (`list_project_tasks_for(pid)` off a fresh `/tasks/all`), refuse if non-empty, else delete; children before parents;
8. print applied summary with `backup_ref` echoed and each action classified completed / skipped / blocked (FR-009).

## Task enumeration (NFR-004, C-1)

`list_all_tasks(client) -> list[dict]`: pages `GET /tasks/all?per_page=50&page=N`
until a page returns `< 50`; concatenates; a `null` page → treat as empty; a
non-list, non-null body → `raise VikunjaError`. Includes done tasks (no
`done=false` filter). Per-project task sets are derived by filtering this list on
`project_id` — the same source the audit used, so done tasks are always counted.
Tests cover a done-only blocker and a >50-task (paged) blocker.

## State transitions

A task's `project_id` transitions exactly once (legacy → topic) or not at all
(idempotent re-run / already correct). A project transitions present → deleted
only after it is observed empty **in the same-run immediate re-list**. The
overall run is **resumable, not atomic**: a mid-run failure leaves prior
mutations committed on the live server; because every step is idempotent, the
operator simply re-runs and the plan recomputes from live state. A post-apply
dry-run recompute (empty plan) is the completion proof (SC-005).
