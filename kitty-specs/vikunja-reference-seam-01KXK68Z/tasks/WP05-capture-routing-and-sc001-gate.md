---
work_package_id: WP05
title: '#745 capture routing alignment + SC-001 acceptance gate'
dependencies:
- WP01
- WP03
- WP04
requirement_refs:
- FR-002
- FR-010
- FR-011
- FR-012
- FR-013
tracker_refs: []
planning_base_branch: feat/vikunja-reference-seam
merge_target_branch: feat/vikunja-reference-seam
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-reference-seam. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-reference-seam unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
- T022
phase: Phase 3 - Routing + Gate
assignee: ''
agent: "claude:sonnet:python-pedro:implementer"
agent_profile: python-pedro
role: implementer
model: claude-sonnet-5
shell_pid: "35538"
shell_pid_created_at: "1784146986.845304"
history:
- at: '2026-07-15T17:18:48Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/inbox/route_someday.py
create_intent:
- tests/common/test_sc001_grep.py
execution_mode: code_change
owned_files:
- scripts/inbox/route_someday.py
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- tests/inbox/test_route_someday.py
- tests/common/test_sc001_grep.py
tags: []
---

# Work Package Prompt: WP05 – #745 capture routing alignment + SC-001 acceptance gate

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/vikunja-reference-seam`
- **Final merge target for completed work**: `feat/vikunja-reference-seam`
- **Actual execution workspace is resolved later**: trust the path printed by `spec-kitty agent workflow implement`; do not manually create a different worktree.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Markdown Formatting

Wrap HTML/XML tags in backticks. Use language identifiers in code blocks.

---

## Objectives & Success Criteria

Align `felix-admin-capture`'s routing to the **post-#714 model** (#745) and land the
**SC-001 acceptance grep gate** over the fully-migrated runtime surface. This WP
depends on WP03 + WP04 so the grep runs against a completely migrated codebase.

**Done when:**
- `route_someday` no longer looks up a "Someday" project; a "someday" block becomes
  a task tagged **`q:schedule`** with **no due date**, created in Inbox (or the
  resolved topic project), via the WP01 accessor. Routing-log / dedup behavior is
  preserved.
- The capture **fall-through** target is **Inbox** (id 1), and the capture AGENTS.md
  wording no longer calls "Someday" the safe-fallback bucket.
- Tier-1 labels (project / `f:` / `q:`) are applied on routing where determinable;
  otherwise the item is left in Inbox for the #749 intake loop.
- The **SC-001 grep gate** passes: zero by-title / hardcoded-id runtime resolutions
  remain in the migrated surface (the C-005 exempt `scripts/vikunja/` tools +
  `create_task.py` are excluded).
- `pytest tests/inbox/test_route_someday.py tests/common/test_sc001_grep.py` green.

## Context & Constraints

Read first: **#745** (issue body — the routing-target decisions),
`spec.md` FR-010..FR-013 + SC-001/SC-005 + the SC-001 grep definition,
`plan.md` § capture routing alignment (incl. the label-attach live-probe note),
`quickstart.md` § capture routing, and `docs/design/vikunja-configuration-design.md`
(the `q:schedule` = "important, not date-committed" state).

**C-003:** the `q:schedule` + no-due-date convention is independent of the #725
saved *filter* (which is blocked on Vikunja is-null). Do not depend on #725.
**C-004:** never declare/create a "someday" project.

Existing `route_someday.py` uses `VikunjaClient()` (felix-bot token) and
`PUT /projects/<id>/tasks`. Read it fully before reworking; preserve its CLI
contract (stdout `task_id=<int>`, exit 2 + JSON stderr on failure) unless #745
requires a change (note any change loudly).

## Subtasks & Detailed Guidance

### Subtask T018 – Rework `route_someday` → `q:schedule` + no due date
- **Purpose**: Retire the deleted-project lookup; implement the post-reset "someday" state.
- **Steps**:
  1. **Delete** `find_someday_project` and `SOMEDAY_PROJECT_TITLE` (the by-title
     lookup of a project that no longer exists — the direct #743 cause on this path).
  2. Resolve the destination project via the accessor: default **Inbox**
     (`vikunja_refs.project_id("inbox")`); if the caller/classifier supplies a
     resolved topic project, use that. No live `/projects` listing.
  3. Create the task via the CREATE endpoint `PUT /projects/<id>/tasks` — per
     `[[reference_vikunja_post_partial_replace]]` never `POST /tasks/<id>` (that
     partial-replaces an existing task; it was the root cause of #524) — with **no
     due date** set. (Analysis F2: the original helper called this its "C-006"; this
     spec has no C-006 — cite the endpoint-safety rule directly.)
  4. Attach the **`q:schedule`** label (declared in the WP01 registry) to the created
     task by id — `vikunja_refs.label_id("q:schedule", <token>)` (see T019 for the
     attach-token caveat). "Someday" is now a label state, not a project.
  5. Preserve the description footer (`Source: <note-filename>`) and the
     routing-log / dedup substrate (FR-013).
- **Files**: `scripts/inbox/route_someday.py`, `tests/inbox/test_route_someday.py`.
- **Notes**: Keep the module name `route_someday` (it still routes someday-classified
  blocks). Update the module docstring to describe the new target model.

### Subtask T019 – Apply Tier-1 labels where determinable
- **Purpose**: Populate intake taxonomy at routing time (#745), fail-soft to Inbox.
- **Steps**:
  1. Where the classifier has determined a project / `f:` friction / `q:` quadrant,
     attach the corresponding label(s) via the accessor
     (`vikunja_refs.label_id(...)`). Where not determinable, leave the item in Inbox
     for the #749 intake-validation loop — do **not** guess.
  2. **⚠️ LIVE-PROBE (finding #6 / #715) — resolve before coding the attach:** the
     `q:schedule`/`q:`/`f:` labels are **kent-owned**, and in #715 the **felix-bot
     token got 403 attaching kent-owned labels**. `route_someday` runs under the
     felix-bot `VikunjaClient` today. Probe live (`ssh office2-claude`) whether
     felix-bot can attach `q:schedule` to a task. If it **cannot**, pick one
     (surface the choice in the Activity Log and to the reviewer):
     (a) attach labels using the **kent** token (`vikunja-api-kent`) for the
         label-attach step only; or
     (b) create the task without the label and record the limitation loudly (the
         #749 loop applies labels later).
     Do not silently drop the label (that recreates a taxonomy-never-populated gap).
     `q:schedule` **is declared in the WP01 registry** (analysis F1), so resolve it by
     id via the accessor — do not add it to `vikunja_refs.json` from here (that file
     is WP01-owned). If the live-probe shows felix-bot cannot attach it, that is the
     option (a)/(b) decision above; keep it fail-loud, never silent. The broader
     `f:/q:/t:/loe:` taxonomy remains deferred to #749 — if the classifier determines
     an `f:`/`q:` label not in the registry, route via option (b) (leave for #749).
- **Files**: `scripts/inbox/route_someday.py`, `tests/inbox/test_route_someday.py`.
- **Notes**: This is the one genuinely uncertain seam in the mission — treat the
  probe result as authoritative and document it.

### Subtask T020 – Fix capture AGENTS.md fall-through wording
- **Purpose**: Prompt matches the post-reset model (FR-010).
- **Steps**: In `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (~line 233
  per #745), change the "Someday = safe-fallback bucket" wording so the
  **fall-through / unclassifiable** target is **Inbox** (id 1, native quick-capture),
  and "someday" is described as a `q:schedule` + no-due-date task state, not a
  project. Keep all other capture behavior wording intact.
- **Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`.
- **Notes**: This file deploys via `agent-prompt-sync` post-merge (operational, not
  part of this WP). Agent prompts are not hashed (#621) → no rebaseline. Do not
  exceed the AGENTS.md size guard if one applies to capture (check
  `tests/openclaw` / any `test_agents_md_size` for capture).

### Subtask T021 – Routing tests (SC-005)
- **Purpose**: Lock the post-reset routing behavior.
- **Steps**: In `tests/inbox/test_route_someday.py` (injected `VikunjaClient`):
  - a "someday" block → a created task with the **`q:schedule`** label and **no due
    date**, in Inbox (or the supplied topic project) — SC-005.
  - unclassifiable → Inbox (fall-through).
  - no live `/projects` listing occurs (accessor is used) — assert.
  - routing-log / dedup preserved (existing assertions still pass).
  - the old `find_someday_project` path is gone (a deleted "Someday" project no
    longer errors the route — it never looks it up).
- **Files**: `tests/inbox/test_route_someday.py`.

### Subtask T022 – SC-001 acceptance grep gate
- **Purpose**: Prove the migration is complete — zero remaining ad-hoc runtime resolution.
- **Steps**: Create `tests/common/test_sc001_grep.py` — a test that greps the
  **runtime consumer surface** and asserts **zero** matches for the ad-hoc patterns
  defined in `spec.md` § "SC-001 acceptance grep":
  - Vikunja title-equality resolution against a routed project/label name
    (e.g. `title == "Habits"`, `title == "Inbox"`, `title == "Someday"`,
    `get("title") == MANUAL_OVERRIDE_LABEL` as a *resolution*);
  - integer project-id / label-id literals used as resolution targets
    (e.g. `HABITS_PROJECT_ID = 13`, `= 2`, `project_id: 13`, `DEFAULT_TARGET_PROJECT_ID`);
  - direct `/projects` or `/labels` list-and-filter calls made to resolve a known
    logical reference (not the WP02 validator's single live list; not provisioning tools).
  - **Exclude** the C-005 exempt list: everything under `scripts/vikunja/`
    (`setup_vikunja`, `provision_felix_bot`, `create_taxonomy_labels`,
    `migrate_tasks`, `reconcile_projects`, `create_saved_filters`,
    `validate_felix_bot`, `create_task`) and the WP02 `validate_refs.py` /
    `vikunja_refs_validate.py` (they legitimately list live Vikunja).
  - Scope the grep to `scripts/` runtime consumers; use `pathlib`/`re` in-process
    (no shell-out needed). Make the failure message list each offending file:line so
    a regression is actionable.
- **Files**: `tests/common/test_sc001_grep.py` (new).
- **Notes**: This is the durable regression guard that keeps future code on the seam.
  Tune the allow/deny lists so it is precise (no false positives on the exempt tools,
  no false negatives on a real ad-hoc lookup).

## Test Strategy

- `python3 -m pytest tests/inbox/test_route_someday.py tests/common/test_sc001_grep.py -q`.
- Run the full inbox suite for routing-log/dedup ripple:
  `python3 -m pytest tests/inbox/ -q`.
- The SC-001 grep must be **green only after WP03 + WP04 have merged** (hence the
  dependency) — if it fails, the message names the file:line still to migrate.

## Risks & Mitigations

- **felix-bot can't attach kent-owned labels (#715 403).** Mitigation: the T019
  live-probe + the explicit option (a)/(b) decision — do not assume it works.
- **SC-001 grep false positives** on exempt tools → gate never green. Mitigation:
  precise exclude list (C-005) + file:line failure output for tuning.
- **AGENTS.md size guard** (if capture has one). Mitigation: check
  `tests/openclaw`/size test before enlarging the prompt.

## Integration Verification (mandatory before for_review)

- [ ] `find_someday_project` / `SOMEDAY_PROJECT_TITLE` deleted; no "Someday" project lookup anywhere in capture code.
- [ ] "someday" route produces a `q:schedule` + no-due-date task (SC-005); fall-through = Inbox.
- [ ] Capture AGENTS.md wording matches the post-reset model.
- [ ] SC-001 grep gate passes over the full migrated surface (C-005 excluded).
- [ ] Routing-log / dedup unchanged.

## Review Guidance

- Confirm the label-attach token decision (T019) is explicit and documented, not silently dropped.
- Confirm the SC-001 grep is precise (spot-check it fails when you reintroduce a `title ==` lookup, passes otherwise).
- Confirm no dependence on #725 is-null filtering (C-003).

## Activity Log

> Append new entries at the END, chronological order, UTC `YYYY-MM-DDTHH:MM:SSZ`.

- 2026-07-15T17:18:48Z – system – Prompt created.
- 2026-07-15T20:23:22Z – claude:sonnet:python-pedro:implementer – shell_pid=35538 – Assigned agent via action command
