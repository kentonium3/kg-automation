# Vikunja Task Migration & Project Teardown

**Mission**: vikunja-migrate-tasks-01KXBZ8A
**Type**: software-dev
**Source**: kentonium3/kg-automation#717 (epic #714, migration-sequence step 5)

## Purpose

After the label taxonomy (#715) and topic-project creation (#716), the Vikunja
task store holds two structures at once: tasks still live in the flat legacy
projects (Everyday, Someday, Personal Growth & Transformation, Household, Goals,
Research) while the new topic projects sit empty. This mission runs the
human-judgment migration — routing every surviving task into its correct topic
project, labelling habits, deleting test artifacts, and removing the emptied
legacy projects — so Felix task-intake and escalation reason over one coherent
structure.

## User Scenarios & Testing

### Primary scenario

The operator runs the migration helper (post-merge, on office2, authenticated as
`kent`). Every task named in the committed routing manifest moves to its
designated topic project with all original fields intact; every Habits task
gains the `t:habit` label; the two test-artifact tasks are deleted; and each of
the six legacy projects — once confirmed to hold no tasks — is deleted, children
before parents. The helper prints a summary (moved / labelled / deleted counts)
for verification. Kent confirms in the Vikunja UI that the legacy projects are
gone, the topic projects hold the expected tasks, and habits are labelled.

### Idempotent re-run

The operator runs the helper a second time after a complete run. It detects that
every task is already in its target project, every habit already carries the
label, and the legacy projects no longer exist, and performs **zero** mutations,
printing an all-no-op summary.

### Exception: a doomed project is not empty

If a project slated for deletion still contains a task (e.g. a manifest omission
or a task created after the audit), the helper **refuses** to delete that
project and reports it, rather than cascade-deleting an unmigrated task.

### Exception: wrong identity

If the helper is invoked with the felix-bot task-CRUD token instead of the
kent-owned token, it refuses up front (label attach requires the kent token;
felix-bot receives 403), rather than partially mutating.

## Requirements

### Functional

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Move each task listed in the routing manifest from its current project to its designated topic project (Personal, Felix / kg-automation, Intentional LLC, or retained Habits). | Accepted |
| FR-002 | Apply the `t:habit` label to every Habits task named in the manifest; tasks remain in the Habits project. | Accepted |
| FR-003 | Delete the two designated test-artifact tasks (#89 TEST-679C, #44 027 SC-002 test task). | Accepted |
| FR-004 | Delete each of the six emptied legacy projects (Someday, Everyday, Personal Growth & Transformation, Household, Goals, Research) only after confirming it holds **zero tasks including done tasks** (enumerated via paginated `/tasks/all` filtered by project id — see NFR-004), re-checked **immediately before** each delete, deleting children before parents (Someday before its parent Everyday). Test-artifact deletions (FR-003) run **before** the empty-check so a doomed project holding a designated test task does not self-block. | Accepted |
| FR-005 | The helper is idempotent: re-running it after a complete run performs zero mutations and reports all no-ops. | Accepted |
| FR-006 | The helper fails loud rather than proceeding when (a) a project marked for deletion still holds tasks, or (b) it is run as any identity other than `kent`. | Accepted |
| FR-007 | Update the escalation scope config so it no longer references the deleted Goals project id (11); habit identity stays project-id based (Habits retained) with `t:habit` applied additively. Former Goals tasks (#1, #13) move to Intentional LLC and are **accepted as normal escalation candidates** (far-future due dates; no near-term change) — verified by a test. | Accepted |
| FR-008 | The routing decisions are carried in a committed manifest whose contents **exactly** match the locked id→target map in #717 (asserted by a fidelity test — exact dict equality, not counts). | Accepted |
| FR-009 | The helper emits a machine-and-human-readable summary of the actions taken (moves, labels, deletions), each classified completed / skipped / blocked, for operator verification. | Accepted |
| FR-010 | Before any mutation, a live **preflight** validates: the token identity is kent (target/doomed projects resolve with `owner.username == "kent"`); every target and doomed project matches its expected title and parent id; and `t:habit` resolves to exactly one kent-visible label. Any mismatch aborts fail-loud before mutation. | Accepted |
| FR-011 | A moved task preserves a defined allowlist of writable fields (verified by a post-move readback diff: only `project_id` changed). A task carrying complex state the move cannot safely preserve (assignees, task relations, reminders, attachments, kanban bucket position, sub/parent-task links) is **preflight-blocked and reported**, not silently migrated. | Accepted |

### Non-Functional

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | Every task move uses read-modify-write over a defined writable-field allowlist (title, description, due date, `repeat_after`, `repeat_mode`, priority, done/`done_at`, `hex_color`, `percent_done`, `start_date`, `end_date`, plus `project_id`) — never a blind echo of GET output — because Vikunja POST is partial-replace and zeros unstated fields (#524). A post-move readback verifies only `project_id` changed. | Accepted |
| NFR-002 | The destructive run requires operator-supplied backup evidence: a non-empty `--backup-ref` (Restic snapshot id or ISO timestamp of a `vikunja.db` snapshot ≤24h old, Change-Risk Tier 2), which the helper records verbatim in its applied summary. The helper does not itself validate Restic (honest evidence, not a fabricated check); absent `--backup-ref`, deletions abort. | Accepted |
| NFR-003 | New helper code meets the repository branch-coverage threshold under `pytest --cov-branch`. | Accepted |
| NFR-004 | Every live task enumeration paginates `/tasks/all` at `per_page=50` (Vikunja's cap) until a short page, and includes done tasks; a `null` body is treated as empty; a non-list/non-null body fails loud. | Accepted |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Implemented as a deterministic, idempotent Python helper on the canonical `scripts.common.vikunja_client.VikunjaClient` stdlib boundary (no `requests`), run as `kent` via the `vikunja-api-kent` token. | Accepted |
| C-002 | The live migration is operator-invoked post-merge on office2. This mission ships helper code + tests + the committed manifest + doc updates only — it does not mutate the live Vikunja from the mission. | Accepted |
| C-003 | Inbox is retained: its done tasks stay in place (a done task's project is historical metadata); only the three mis-filed open Inbox tasks are re-homed. | Accepted |
| C-004 | `HABIT_SELECTOR` stays `{project_id: 13}` (Habits retained, still valid); flipping habit identity to the `t:habit` label + the escalation label-fetch strategy is a deliberately deferred future edit, out of scope here. | Accepted |

## Success Criteria

- **SC-001**: All six legacy projects (Everyday, Someday, Personal Growth & Transformation, Household, Goals, Research) are confirmed empty and deleted; the Vikunja sidebar shows only Inbox, the retained topic projects, and the new topic projects.
- **SC-002**: Every migrated task appears in its target project with its original title, due date, recurrence, and labels intact.
- **SC-003**: Every Habits task carries the `t:habit` label, verified in Kent's Vikunja UI.
- **SC-004**: The two test-artifact tasks no longer exist.
- **SC-005**: A second run of the helper reports zero mutations.
- **SC-006**: Escalation and habit queries continue to function after the migration — no code references a deleted project id in a way that raises; the two former Goals tasks are enumerable as escalation candidates.
- **SC-007**: For every moved task, a post-move readback shows only `project_id` changed and all writable fields preserved; any task with unsupported complex state was preflight-blocked and reported rather than migrated.

## Key Entities

- **Task** — a Vikunja task with `id`, `project_id`, `labels`, `due_date`, `repeat_after`, `done`.
- **Project** — a Vikunja project with `id`, `title`, `parent_project_id`, `owner`.
- **Label** — a Vikunja label; the relevant one is `t:habit` (kent-owned, from #715).
- **Routing manifest** — the committed record mapping each task id to its target project (and the habit-label / delete sets), carrying Kent's human-judgment decisions.

## Assumptions

- The target topic-project ids from #716 are stable: Personal 20, Felix / kg-automation 16, Intentional LLC 9 (existing), Habits 13 (existing).
- The `vikunja-api-kent` token remains valid on office2 at `/data/services/openclaw/secrets/vikunja-api-kent`.
- No new tasks are created in the doomed projects between the audit and the live run; if any are, FR-006 catches them.

## Dependencies

- #715 (label taxonomy) — done; `t:habit` exists.
- #716 (topic projects created) — done; target ids known.
- Unblocks #718 (saved filters) — validated against the real post-migration task distribution.
