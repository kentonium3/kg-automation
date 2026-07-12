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
3. No id is in both `moves` and `delete_tasks`.
4. `delete_projects` lists Someday(4) before Everyday(2) (child before parent).
5. `target_projects` values match the #716 live ids (Personal 20, Felix 16, Intentional 9, Habits 13).

## Locked content (matches #717)

- `moves`: 30 entries → Personal(20)×22, Felix(16)×3, Intentional(9)×4, (Habits handled via `label_habit`, not moved).
- `label_habit`: 14,15,16,17,18,19,20,65,75,76,77 (11 Habits tasks).
- `delete_tasks`: 89, 44.
- `delete_projects`: 4, 2, 5, 15, 11, 12.

A fidelity test asserts the committed manifest equals this locked set (FR-008,
DIRECTIVE_010).
