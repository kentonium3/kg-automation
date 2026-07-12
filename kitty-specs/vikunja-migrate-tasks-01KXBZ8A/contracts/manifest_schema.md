# Contract: `task_migration_manifest.yaml`

The committed record of Kent's locked routing (#717). Consumed by
`migrate_tasks.py`. Human-editable; validated on load.

## Required top-level keys

| key | type | meaning |
|-----|------|---------|
| `target_projects` | map[str,int] | selector-key → live project id. Must include every key referenced in `moves`. |
| `moves` | map[int,str] | task id → target project key (must be in `target_projects`). |
| `label_habit` | list[int] | task ids to receive the `t:habit` label (remain in Habits). |
| `delete_tasks` | list[int] | task ids to delete outright (test artifacts). |
| `delete_projects` | list[int] | project ids to delete, **children before parents**. |

## Invariants (enforced by `load_manifest`; violation → exit 1)

1. Every value in `moves` is a key of `target_projects`.
2. Every id is a positive integer.
3. The id sets `moves.keys()`, `label_habit`, `delete_tasks` are pairwise disjoint.
4. `delete_projects` lists Someday(4) before Everyday(2) (child before parent).
5. `target_projects` values match the #716 live ids (Personal 20, Felix 16, Intentional 9, Habits 13).

## Locked content (EXACT — matches #717; fidelity test asserts dict equality)

`moves` (29 entries) — `task_id → target` (source project in comment):

| → personal (20) | → felix (16) | → intentional (9) |
|---|---|---|
| 42,51,54,61,64,72,81 (Everyday 2) | 50 (Everyday 2) | 1,2,13 (Goals 11) |
| 6,29,30,31,32,84,85 (Someday 4) | 11,46 (Research 12) | 86 (Someday 4) |
| 59 (Personal Growth 5) | | |
| 5,25,33,79 (Household 15) | | |
| 26,34,100 (Inbox 1, open) | | |
| **= 22** | **= 3** | **= 4** |

- `label_habit` (11, all in Habits 13): 14,15,16,17,18,19,20,65,75,76,77.
- `delete_tasks` (2): 89 (in Someday 4), 44 (in Inbox 1).
- `delete_projects` (6, children first): 4, 2, 5, 15, 11, 12.

The fidelity test asserts the committed manifest's `moves`/`label_habit`/
`delete_tasks`/`delete_projects` equal these exact sets (FR-008, DIRECTIVE_010).
Total = 29 moves + 11 labels + 2 task-deletes + 6 project-deletes.
