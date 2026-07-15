---
work_package_id: WP04
title: Migrate sync consumers (private set + felix:ignore label)
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-005
- FR-006
tracker_refs: []
planning_base_branch: feat/vikunja-reference-seam
merge_target_branch: feat/vikunja-reference-seam
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-reference-seam. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-reference-seam unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
phase: Phase 2 - Migration
assignee: ''
agent: "claude:sonnet:python-pedro:implementer"
agent_profile: python-pedro
role: implementer
model: claude-sonnet-5
shell_pid: "98269"
shell_pid_created_at: "1784139360.469166"
history:
- at: '2026-07-15T17:18:48Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/sync/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/sync/diff.py
- scripts/sync/classify.py
- tests/sync/test_diff.py
- tests/sync/test_classify.py
tags: []
---

# Work Package Prompt: WP04 – Migrate sync consumers (private set + felix:ignore label)

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

Move the two **sync** runtime consumers onto the seam: the `PRIVATE_PROJECT_IDS`
project set and the `felix:ignore` manual-override **label**. `felix:ignore` is the
one label with a live runtime consumer today (the `f:/q:/t:/loe:` taxonomy labels
have no runtime id-consumer — deferred to #749, FR-006).

**Done when:**
- `scripts/sync/diff.py`'s private-project set is sourced from
  `vikunja_refs.private_project_ids()` (empty today, so behavior unchanged) rather
  than a bare module `frozenset()`.
- `scripts/sync/classify.py` resolves `felix:ignore` through
  `vikunja_refs.label_id("felix:ignore", <token>)` in the correct per-token
  namespace; the `title == MANUAL_OVERRIDE_LABEL` resolution is removed (the
  `[NO FELIX]` title-prefix override behavior is preserved separately).
- A deleted/renamed `felix:ignore` reference **fails loud** (accessor raises), not a
  silent classify-miss (SC-002 / #743 guard).
- `pytest tests/sync/test_diff.py tests/sync/test_classify.py` is green.

## Context & Constraints

Read first: `plan.md` (§ private-project set, § runtime call-site migration),
`spec.md` FR-002/FR-005/FR-006, WP01's accessor contract, and
`[[reference_vikunja_label_ownership_model]]` (the #715 two-token model — labels are
per-user).

**Label reality (finding #6):** `felix:ignore` is `owner_token: kent` in the
registry. The classify path *reads/filters* labels on shared tasks — that works for
felix-bot (it 403'd only on *attaching* kent-owned labels, not reading them). So
label **resolution** here is fine; confirm the token the sync classifier runs under
and pass it to `label_id`.

Constraints: C-001; no behavior change to private filtering (empty set today);
stdlib + existing modules. Grep `scripts/sync/` for how `diff.py` threads
`private_project_ids` into `cycle`/`emit` — you are changing only the **default
source** in `diff.py`, not the threading.

## Subtasks & Detailed Guidance

### Subtask T015 – Migrate `PRIVATE_PROJECT_IDS` onto the registry
- **Purpose**: Give the privacy set one declared home (finding #4).
- **Steps**:
  1. In `scripts/sync/diff.py`, replace the module-level
     `PRIVATE_PROJECT_IDS: frozenset[int] = frozenset()` default so it derives from
     `vikunja_refs.private_project_ids()` (empty today → identical behavior).
  2. Keep the function parameter `private_project_ids` and its threading through
     `diff`/`cycle`/`emit` unchanged — callers may still override via the driver's
     config surface. Only the **default** now comes from the registry.
  3. Preserve the exact filtering semantics at the `task.get("project_id") in
     private_project_ids` check.
- **Files**: `scripts/sync/diff.py`, `tests/sync/test_diff.py`.
- **Notes**: If evaluating `private_project_ids()` at import time is awkward (import
  order / registry load), resolve it inside the function default path rather than a
  module constant — keep it network-free and lazy if needed.

### Subtask T016 – Migrate `felix:ignore` label resolution (per-token)
- **Purpose**: Resolve the manual-override label through the seam, not by title.
- **Steps**:
  1. In `scripts/sync/classify.py`, replace the `label.get("title") ==
     MANUAL_OVERRIDE_LABEL` comparison with a resolution via
     `vikunja_refs.label_id("felix:ignore", <token>)`, comparing task label **ids**
     to the resolved id (the robust, rename-proof check).
  2. Determine the token the classifier runs under (grep the sync driver / config;
     it reads Kent's tasks, so likely the `kent`-scoped or felix-bot read token) and
     pass it. If the label id cannot be resolved (unprovisioned/undeclared), let the
     `VikunjaRefError` propagate — do **not** silently treat the task as
     non-override (that would be the #743 class).
  3. **Preserve** the `MANUAL_OVERRIDE_TITLE_PREFIX` (`[NO FELIX]`) title-prefix
     override — that is a task-*title* heuristic, unrelated to label resolution;
     leave it exactly as-is.
- **Files**: `scripts/sync/classify.py`, `tests/sync/test_classify.py`.
- **Notes**: If the live task labels only carry titles (not ids) in the sync
  payload, resolve by mapping the registry id back through the fetched label list —
  but prefer id comparison. Verify against the actual sync fetch shape (grep
  `scripts/sync/fetch.py`).

### Subtask T017 – Sync tests + #743 fail-loud regression guard
- **Purpose**: Lock behavior + the fail-loud contract.
- **Steps**:
  - `test_diff.py`: private filtering unchanged with the empty default; overriding
    the set still filters (parametrized).
  - `test_classify.py`: a task carrying the resolved `felix:ignore` id → classified
    as manual-override; the `[NO FELIX]` prefix path still works; and a
    **deleted/undeclared** `felix:ignore` reference makes classification **raise**
    (SC-002) rather than silently returning "not overridden".
- **Files**: `tests/sync/test_diff.py`, `tests/sync/test_classify.py`.

## Test Strategy

- `python3 -m pytest tests/sync/test_diff.py tests/sync/test_classify.py -q`.
- Run the broader sync suite to catch threading ripple:
  `python3 -m pytest tests/sync/ -q` (cycle/emit should be untouched; if a shared
  fixture needs a one-line update, record the out-of-map rationale).

## Risks & Mitigations

- **Sync payload carries label titles, not ids** → id comparison misses.
  Mitigation: verify the fetch shape (T016 note); map through the fetched list if
  needed.
- **Wrong token** → label not found → over-eager fail-loud. Mitigation: confirm the
  classifier's token from the driver config before wiring.
- **Import-time registry load ordering.** Mitigation: lazy resolution inside the
  function path.

## Integration Verification (mandatory before for_review)

- [ ] `title == MANUAL_OVERRIDE_LABEL` label resolution is removed; id-based resolution via the accessor is in.
- [ ] `[NO FELIX]` title-prefix override behavior preserved.
- [ ] Private filtering behavior identical (empty default) and still override-able.
- [ ] Deleted `felix:ignore` reference fails loud (tested).

## Review Guidance

- Confirm `felix:ignore` resolves in the correct token namespace (#715).
- Confirm the private-set threading through cycle/emit is untouched — only the default source moved.

## Activity Log

> Append new entries at the END, chronological order, UTC `YYYY-MM-DDTHH:MM:SSZ`.

- 2026-07-15T17:18:48Z – system – Prompt created.
- 2026-07-15T18:16:55Z – claude:sonnet:python-pedro:implementer – shell_pid=98269 – Assigned agent via action command
