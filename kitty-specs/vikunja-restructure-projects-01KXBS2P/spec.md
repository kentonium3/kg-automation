# Feature Specification: Vikunja Project Restructure

**Mission**: vikunja-restructure-projects-01KXBS2P
**Status**: Draft
**Source**: [kentonium3/kg-automation#716](https://github.com/kentonium3/kg-automation/issues/716) (part of Vikunja configuration reset epic #714)
**Authoritative design**: `docs/design/vikunja-configuration-design.md`

## Purpose

Establish Vikunja's canonical topic-project structure and remove the legacy
ad-hoc saved filters, as an **additive-only** operation. Task migration and the
deletion of task-bearing projects are explicitly out of scope (they are
handled by issue #717, which requires human judgment). This mission is
therefore self-contained: it can complete without waiting on #717.

## User Scenarios & Testing

### Primary scenario — establish the canonical structure

**Actor**: Kent (via a Felix operator running the reconciliation helper).
**Trigger**: The helper is run against the live Vikunja instance with the
kent-owned API token.
**Happy path**:
1. The helper reads the current project list.
2. It verifies `Inbox` exists (it does — id 1) and does not recreate it.
3. It creates the missing topic projects: `Felix / kg-automation`, `Clients`
   (parent), `PointerHealth` and `spec-kitty` (both under `Clients`), and
   `Personal`.
4. It deletes the legacy saved filters (`Today`, `Upcoming`, `Overdue`,
   `Goals`, `Completed`), leaving the native `Favorites` view untouched.
5. It reports the reconciliation summary (created / verified / deleted /
   skipped) and exits 0.
6. Kent opens Vikunja and sees the new projects in the sidebar under his own
   account, with `Clients` as a parent containing `PointerHealth` and
   `spec-kitty`.

### Idempotency scenario — safe re-run

**Trigger**: The helper is run a second time with no intervening changes.
**Outcome**: Every target project already exists and every legacy filter is
already gone, so the helper performs zero create/delete operations, reports
"no changes", and exits 0. No duplicate projects or filters are ever created.

### Exception — destructive delete without backup confirmation

**Trigger**: The helper is asked to delete legacy filters without the
`--backup-confirmed` flag.
**Outcome**: The helper refuses the delete pass, exits non-zero, and prints
the Tier-2 Restic backup requirement. The additive (create) work may still be
performed; deletion is gated.

### Exception — API error mid-run

**Trigger**: Vikunja returns an auth failure or 4xx/5xx during any operation.
**Outcome**: The helper aborts immediately with a clear message and a non-zero
exit. It never reports success on a partial run.

### Edge cases

- **Empty label/project responses**: Vikunja returns JSON `null` (not `[]`)
  for empty collections (per the #715 finding). The helper must treat `null`
  as an empty list, not error.
- **Saved-filter delete endpoint unknown**: `GET /api/v1/filters` returned
  `Not Found` during the audit. The working delete path must be confirmed
  against the live API before the delete path is exercised; if no API delete
  is available on this Vikunja version, the helper documents a manual UI
  fallback and skips the automated filter delete (the additive work still
  proceeds).
- **Per-user object scoping**: objects created by the felix-bot token are
  invisible in Kent's UI (#715). All objects here must be created with the
  kent-owned token so they appear in Kent's account.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Create topic project `Felix / kg-automation` if absent. | Draft |
| FR-002 | Create parent project `Clients` (holds no tasks of its own) if absent. | Draft |
| FR-003 | Create sub-project `PointerHealth` under `Clients` if absent. | Draft |
| FR-004 | Create sub-project `spec-kitty` under `Clients` if absent. | Draft |
| FR-005 | Create catch-all project `Personal` if absent. | Draft |
| FR-006 | Verify `Inbox` exists; do not create a duplicate. | Draft |
| FR-007 | Delete the legacy saved filters `Today`, `Upcoming`, `Overdue`, `Goals`, `Completed`; leave the native `Favorites` view untouched. | Draft |
| FR-008 | Reconciliation is idempotent: a second run with no intervening changes performs no create/delete operations. | Draft |
| FR-009 | All created projects (and any filter operations) are performed with the kent-owned token so objects are owned by and visible to Kent. | Draft |
| FR-010 | Do not delete or modify any task-bearing project; do not touch the `Habits` project (id 13) or its crons. | Draft |
| FR-011 | Update `docs/design/vikunja-configuration-design.md` so its Project Structure section reflects the final agreed structure (retained projects, corrected pseudo-view vs native-filter distinction). | Draft |
| FR-012 | Emit a human-readable reconciliation summary (created / verified / deleted / skipped) on completion. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Idempotency is verified by test: a second reconciliation issues zero create/delete API calls. | 0 mutating calls on second run | Draft |
| NFR-002 | Fail-loud: any API error aborts with a non-zero exit and a descriptive message; no partial run reports success. | Non-zero exit on any API error | Draft |
| NFR-003 | Automated test coverage for the helper meets the repository gate. | ≥ 90% line coverage | Draft |
| NFR-004 | Destructive operations (filter deletion) are gated behind an explicit backup-confirmation flag. | Delete refused without `--backup-confirmed` | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Build on the canonical stdlib `VikunjaClient` (`scripts/common/vikunja_client.py`), not the older `requests`-based setup scripts. | Draft |
| C-002 | Use the `vikunja-api-kent` token (kent-owned, all-perms) for all operations — required for project/filter config and Kent-visible ownership (#715 two-token model). | Draft |
| C-003 | The helper lives in `scripts/vikunja/` and is invoked in `python3 -m scripts.vikunja.<module>` form. | Draft |
| C-004 | No project deletions in this mission — all project deletions and task migration are deferred to #717. | Draft |
| C-005 | The saved-filter delete endpoint must be verified against the live Vikunja API before implementing the delete path; if unavailable, document a manual UI fallback and skip the automated delete. | Draft |
| C-006 | This is a Tier-2 (Application/State) change: confirm a recent Restic backup before the filter-delete pass. | Draft |

## Success Criteria

- **SC-001**: The five new projects appear in Kent's Vikunja sidebar with the
  exact names, and `Clients` shows `PointerHealth` and `spec-kitty` as
  sub-projects.
- **SC-002**: `Inbox` is present and not duplicated.
- **SC-003**: The five legacy saved filters no longer appear in Kent's
  sidebar; `Favorites` remains.
- **SC-004**: Re-running the helper makes no changes (idempotent).
- **SC-005**: No task-bearing project was deleted, and the `Habits` project
  plus its daily/weekly prompts continue to function unchanged.
- **SC-006**: `docs/design/vikunja-configuration-design.md` matches the live
  structure.

## Key Entities

- **Project** — Vikunja project. Relevant fields: `id`, `title`,
  `parent_project_id` (0 = top-level), `is_archived`. Target projects are
  matched by `title`.
- **Saved filter** — Vikunja saved filter, surfaced in the API as a
  negative-id pseudo-project. Legacy instances (`Today`, `Upcoming`,
  `Overdue`, `Goals`, `Completed`) are removed here; the canonical six
  replacement filters are created in #718.
- **`t:habit` label** — created in #715 (not created here). Referenced only to
  note that habit identity moves to this label in #717; the `Habits` project
  (id 13) is left intact by this mission.

## Assumptions

- The live project audit (2026-07-12) is current: `Inbox` (1) exists;
  task-bearing projects to be deleted later hold ~27 tasks (out of scope here);
  `Metal Casework` (10) and `CT-90day` (7) are empty and retained.
- The `vikunja-api-kent` token is provisioned on office2
  (`/data/services/openclaw/secrets/vikunja-api-kent`) and registered in the
  credential manifest (done in #715).
- The legacy saved filters carry no data that must be preserved before
  deletion (they are views, not task containers); the canonical replacements
  are #718's responsibility.

## Dependencies

- **#715 (label taxonomy)** — DONE. Provides the `vikunja-api-kent` token and
  the `t:habit` label.
- **#717 (task migration)** — downstream. Consumes the new projects created
  here; owns all project deletions and task moves.
- **#718 (saved filters)** — downstream. Creates the six canonical filters
  after this mission removes the legacy ones.

## Out of Scope

- Migrating any tasks between projects (→ #717).
- Deleting any task-bearing project: `Everyday`, `Someday`, `Personal Growth &
  Transformation`, `Household`, `Goals`, `Research` (→ #717).
- Attaching `t:habit` labels to `Habits` tasks or repointing habit crons (→
  #717 / future Felix integration).
- Creating the canonical replacement saved filters (→ #718).
