---
work_package_id: WP01
title: Vikunja project + legacy-filter reconciliation helper + tests + design-doc
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- C-005
- C-006
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
- FR-012
- FR-013
- FR-014
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-005
tracker_refs:
- kentonium3/kg-automation#716
planning_base_branch: feat/vikunja-restructure-projects
merge_target_branch: feat/vikunja-restructure-projects
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-restructure-projects. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-restructure-projects unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
agent: "claude"
shell_pid: "13817"
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/
create_intent:
- scripts/vikunja/reconcile_projects.py
- tests/vikunja/test_reconcile_projects.py
execution_mode: code_change
owned_files:
- scripts/vikunja/reconcile_projects.py
- tests/vikunja/test_reconcile_projects.py
- docs/design/vikunja-configuration-design.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity,
boundaries, and initialization declaration, then proceed.

## Objective

Ship a single deterministic, idempotent helper —
`scripts/vikunja/reconcile_projects.py` — that reconciles the live Vikunja
project structure toward the canonical topic-project layout (additive: creates
missing projects **as kent**, verifies Inbox) and, behind an explicit
backup-gated flag, deletes the five legacy saved filters. Add a full
mocked-client test suite (`tests/vikunja/test_reconcile_projects.py`), and update
the Project Structure section of `docs/design/vikunja-configuration-design.md` so
it matches the final agreed structure.

The **live run is NOT part of this WP** — it is a post-merge operational step
(see `quickstart.md`). This WP produces code + tests + the doc edit only.

## Context (read these first — binding)

- **Spec**: `kitty-specs/vikunja-restructure-projects-01KXBS2P/spec.md` — FR/NFR/C, success criteria, edge cases. Implement to it exactly.
- **API + CLI behavior contract**: `kitty-specs/vikunja-restructure-projects-01KXBS2P/contracts/vikunja-api.md` — endpoints, owner enforcement, the CLI exit-code table. Binding.
- **Data model + reconcile invariants**: `kitty-specs/vikunja-restructure-projects-01KXBS2P/data-model.md` — the target project set, match key, invariants 1–7, pagination/null handling, partial-failure report.
- **Research decisions (R-01..R-07)**: `kitty-specs/vikunja-restructure-projects-01KXBS2P/research.md` — the filter-id derivation, the `/user`-is-401 finding, the owner-based enforcement, pagination, title readback.
- **Post-plan review resolutions**: `kitty-specs/vikunja-restructure-projects-01KXBS2P/contracts/post-plan-review-resolutions.md` — the 10 hardening findings you must honor.
- **The client you build on**: `scripts/common/vikunja_client.py` — `VikunjaClient` with `.get/.put/.delete`, **leading-slash paths** (`/projects`, `/filters/{id}`), typed exceptions. Do NOT add a new HTTP path (no `requests`).
- **Config**: `scripts/common/vikunja_config.py::get_vikunja_base_url()`.
- **Sibling helper to mirror in shape/style**: `scripts/vikunja/create_taxonomy_labels.py` (the #715 reconcile helper) — same `reconcile()`-at-function-boundary + CLI-wrapper structure, same backup-gate pattern, same `--json` summary. **Reuse its conventions; do not copy label logic.**
- **Test-mock pattern**: `tests/vikunja/test_create_taxonomy_labels.py` and `tests/vikunja/test_create_task.py`. `tests/conftest.py` installs a **global urlopen guard** — tests must make NO real network calls (inject a fake client).
- **Invocation form**: `python3 -m scripts.vikunja.reconcile_projects` from repo root (namespace packages; no `__init__.py`). office2 is `python3`-only.

## Canonical target structure (desired state)

Create if absent (owner must be kent), matching only active, correctly-parented,
kent-owned projects:

| Title | Parent | Note |
|-------|--------|------|
| `Inbox` | top-level | verify exists (kent's, id 1) — never recreate |
| `Felix / kg-automation` | top-level | create |
| `Clients` | top-level | create (folder, no tasks) — must resolve to exactly one active top-level kent project before children |
| `PointerHealth` | `Clients` | create under resolved Clients id |
| `spec-kitty` | `Clients` | create under resolved Clients id |
| `Personal` | top-level | create |

Legacy saved filters to delete (derive live; ids are environment-specific):
`Today`, `Upcoming`, `Overdue`, `Goals`, `Completed`. Derive each from its
negative-id pseudo-project (`filter_id = -pseudo_id - 1`), title-readback, then
`DELETE /filters/{id}`. **Never** touch `Favorites` (`-1`).

## Subtasks

### T001 — Token loading + paginated, owner-scoped project fetch

**Purpose**: Read projects as kent, safely.

- `--token-file` defaults to `/data/services/openclaw/secrets/vikunja-api-kent`.
  Read the token from that file only; **never** fall back to `VikunjaClient`'s
  default token path (felix-bot). Missing/blank file → abort (exit 1) with a
  clear message naming the credential.
- Build the `VikunjaClient` with that token and the config base URL.
- Fetch projects with pagination: `GET /projects?per_page=50&page=N` until an
  empty batch. Normalize a `null` body to `[]` (the #715 quirk).
- Return only entries with `owner.username == "kent"` for matching purposes,
  but keep the raw negative-id pseudo-projects (needed for filter derivation;
  their owner is kent too, except Favorites `-1` whose owner is null).

**Files**: `scripts/vikunja/reconcile_projects.py`.

### T002 — Reconcile-plan builder (match + ambiguity + derivation)

**Purpose**: Compute what to create/delete without mutating.

- **Match key**: a target resolves against candidates that are
  `owner.username == "kent"` AND `is_archived == false` AND
  `parent_project_id == expected_parent`. Zero matches → create; exactly one →
  reuse id; **more than one, or a collision with an archived/wrong-parent/
  wrong-owner project → raise/abort fail-loud** (do not create a duplicate,
  do not bind to the wrong project). `Clients` must resolve to exactly one
  active top-level kent project before its children are planned.
- Build `projects_to_create` ordered so `Clients` precedes `PointerHealth` and
  `spec-kitty`.
- Build `filters_to_delete`: from negative-id pseudo-projects with `id <= -2`
  (excludes Favorites `-1`) whose title ∈ the legacy set; record
  `filter_id = -id - 1`.
- The plan MUST NOT contain any project delete (assert this; invariant 3).

**Files**: same helper.

### T003 — Create pass + owner assertion + verify Inbox

**Purpose**: Additively create the missing projects, proving kent ownership.

- Verify Kent's `Inbox` exists (owner kent, top-level); do not recreate. If
  absent, that is a hard error (Inbox is native) — report, do not create.
- For each `projects_to_create`: `PUT /projects` with
  `{"title", "parent_project_id"}` (0 for top-level; resolved Clients id for
  children). Resolve Clients' id from the create response before creating its
  children.
- **Assert each create response's `owner.username == "kent"`**; if not, abort
  fail-loud (wrong token despite the path).

**Files**: same helper.

### T004 — Filter-delete pass (backup-gated, readback, never -1)

**Purpose**: Remove the five legacy filters, safely and only when authorized.

- Gate: the delete pass runs only when BOTH `--delete-legacy` AND a non-blank
  `--backup-confirmed <ref>` are given. `--delete-legacy` without a non-blank
  ref → exit 2 **before any mutation**.
- For each `filters_to_delete`: `GET /filters/{filter_id}`, confirm the returned
  title equals the intended legacy title AND the pseudo id is not `-1`; only
  then `DELETE /filters/{filter_id}`.
- Never derive or delete a filter for `Favorites`.

**Files**: same helper.

### T005 — CLI entrypoint (flags, exit codes, dry-run, json, summary)

**Purpose**: Operator surface with defined semantics.

- Flags: `--token-file` (default kent secret), `--delete-legacy`,
  `--backup-confirmed <ref>`, `--dry-run`, `--json`.
- Modes/exit codes (per `contracts/vikunja-api.md`): default = create-only pass
  (no filter deletes); `--delete-legacy --backup-confirmed <ref>` = also delete;
  `--dry-run` = compute + print plan, no mutation, exit 0; exit 2 when
  `--delete-legacy` lacks a non-blank ref; exit 1 on any API error/inconsistency;
  exit 0 on success.
- Emit a human-readable summary (created / verified / deleted / skipped) and,
  with `--json`, a machine summary. On a mid-run failure, the summary reports
  which operations completed vs were skipped (invariant 4 / NFR-005).
- Wrap all API calls so any typed `VikunjaError` (or unexpected exception)
  aborts with exit 1 and a descriptive message; no partial run reports success.

**Files**: same helper.

### T006 — Tests (≥90% coverage, fully mocked)

Cover, with an injected fake client (no network):

- Idempotency: converged state → zero create/delete calls (NFR-001).
- Ambiguity abort: duplicate/archived/wrong-parent title → fail-loud, no create (FR-014).
- Owner enforcement: create response with `owner != kent` → abort; matching ignores a felix-bot-owned `Inbox` (id 14).
- Pagination: a create-target and a legacy filter on page 2 are found; `null` body → `[]`.
- Filter path: readback mismatch → no delete; derivation works for a non-`1..5` id; Favorites (`-1`) never targeted.
- Backup gate: `--delete-legacy` without ref → exit 2, no mutation; with ref → deletes.
- Partial failure: API error after one successful create → exit 1, summary shows completed vs skipped.
- No project-delete: assert the plan/execution never calls `DELETE /projects`.

**Files**: `tests/vikunja/test_reconcile_projects.py`.

### T007 — Update the design doc

**Purpose**: Keep `docs/design/vikunja-configuration-design.md` the single
authority.

- Update the **Project Structure** section to the final agreed structure:
  retained projects (`Metal Casework`, `CT-90day`, `Habits`), the created
  topic projects, and the `Clients` parent/child hierarchy.
- Correct the pseudo-view vs native-filter description: `Today`, `Upcoming`,
  `Overdue`, `Completed`, `Goals` are negative-id saved filters (removed here);
  `Favorites` is native. Note that task migration + task-bearing-project deletion
  are #717.

**Files**: `docs/design/vikunja-configuration-design.md`.

## Branch Strategy

Planning base: `feat/vikunja-restructure-projects`. Final merge target:
`feat/vikunja-restructure-projects`. Execution worktrees are allocated per
computed lane from `lanes.json`; implement in your assigned lane worktree, not
the primary checkout.

## Definition of Done

- `scripts/vikunja/reconcile_projects.py` implements T001–T005 to the contract.
- `tests/vikunja/test_reconcile_projects.py` passes with ≥90% coverage, no
  network calls.
- `docs/design/vikunja-configuration-design.md` Project Structure section updated.
- `python3 -m scripts.vikunja.reconcile_projects --dry-run --help` works from repo root.
- No project-delete path anywhere; Favorites never targeted; owner enforced.
- Repo test gate green (`make test` or the project's pytest invocation).

## Risks / reviewer guidance

- **Highest severity**: any path that could delete/mutate a task-bearing project
  or project id 13. Reviewer: grep the diff for `DELETE /projects` / `delete(` on
  a project id — must be absent.
- Owner-scoped matching must ignore felix-bot's `Inbox` (id 14) — verify the test
  encodes a felix-bot-owned project in the fixture.
- Filter ids are environment-specific — verify tests use a non-`1..5` derived id.
- Backup gate must refuse before mutation — verify exit 2 with no `DELETE` issued.
- Do not construct a real `VikunjaClient` that hits the wire in tests.

## Activity Log

- 2026-07-12T18:47:09Z – claude – shell_pid=9643 – Assigned agent via action command
- 2026-07-12T18:59:10Z – claude – shell_pid=9643 – Moved to for_review
- 2026-07-12T18:59:32Z – claude – shell_pid=13817 – Started review via action command
