# Issue matrix — vikunja-migrate-tasks-01KXBZ8A

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

Note: #13, #44, #89 are Vikunja **task ids** (not GitHub issues) that the scanner
picked up from the manifest/spec; verdicts describe how the migration acts on those
tasks. #524 is a GitHub issue documenting Vikunja POST partial-replace behavior.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #714 | Epic: Vikunja configuration reset | deferred-with-followup | Advanced by this mission (step 5); epic remains open pending #718. |
| #715 | Vikunja label taxonomy | verified-already-fixed | Merged main `0ce94826`; `t:habit` + taxonomy live. |
| #716 | Vikunja project restructure | verified-already-fixed | Merged main `450cdcf7`; topic projects (Personal 20 / Felix 16 / Clients 17 / …) live. |
| #717 | Vikunja reset: migrate tasks (this mission) | fixed | `scripts/vikunja/migrate_tasks.py` + `task_migration_manifest.yaml` + tests, WP01 commit `2269c5a4`. |
| #718 | Vikunja reset: saved filters | deferred-with-followup | Unblocked by this mission (validated against the real post-migration distribution); next in the #714 chain. |
| #524 | Vikunja POST partial-replace zeros fields | verified-already-fixed | Known behavior honored: allowlisted read-modify-write + post-move readback in `move_task` (raises on field zeroing). |
| #13 | (Vikunja task) Intentional: complete first paid engagement | fixed | Task moved Goals(11)→Intentional LLC(9) by the migration manifest `moves`. |
| #44 | (Vikunja task) 027 SC-002 test task | fixed | Test artifact in `delete_tasks`; removed by the migration. |
| #89 | (Vikunja task) TEST-679C verification event | fixed | Test artifact in `delete_tasks`; removed by the migration. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
