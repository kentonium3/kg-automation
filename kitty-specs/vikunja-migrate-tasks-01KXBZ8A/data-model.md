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

**Validation** (`load_manifest`):
- every `moves` value is a known `target_projects` key;
- every id (keys of `moves`, members of `label_habit`/`delete_tasks`/`delete_projects`) is a positive int;
- `delete_projects` is an ordered list; a child must precede its parent (asserted for Someday(4) before Everyday(2));
- no task id appears in both `moves` and `delete_tasks`.

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
  blocked:        list[(project_id, reason)]                       # non-empty doomed project (fail-loud at apply)
```

`reconcile(client, manifest, apply, backup_confirmed)`:
1. fetch live projects/tasks/labels;
2. `build_plan`;
3. if `blocked` non-empty → raise (FR-006);
4. if not `apply` → print plan, return;
5. if any delete and not `backup_confirmed` → raise (NFR-002);
6. execute moves (RMW) → labels → task deletes → project deletes (children first);
7. print applied summary (FR-009).

## State transitions

A task's `project_id` transitions exactly once (legacy → topic) or not at all
(idempotent re-run / already correct). A project transitions present → deleted
only after it is observed empty. No transition is partial: a failed step raises
and leaves the remainder unapplied (operator re-runs; idempotency makes the
re-run safe).
