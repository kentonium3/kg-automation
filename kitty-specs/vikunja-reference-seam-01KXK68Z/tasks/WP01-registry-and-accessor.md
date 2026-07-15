---
work_package_id: WP01
title: Registry data file + typed fail-loud accessor
dependencies: []
requirement_refs:
- FR-001
- FR-003
- FR-007
- FR-008
- FR-009
- NFR-001
- NFR-003
tracker_refs: []
planning_base_branch: feat/vikunja-reference-seam
merge_target_branch: feat/vikunja-reference-seam
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-reference-seam. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-reference-seam unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
assignee: ''
agent_profile: python-pedro
role: implementer
model: claude-sonnet-5
shell_pid_created_at: "1784138601.440592"
agent: "claude:sonnet:python-pedro:implementer"
shell_pid: "93693"
history:
- at: '2026-07-15T17:18:48Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/common/vikunja_refs
create_intent:
- scripts/common/vikunja_refs.json
- scripts/common/vikunja_refs.py
- tests/common/test_vikunja_refs.py
execution_mode: code_change
owned_files:
- scripts/common/vikunja_refs.json
- scripts/common/vikunja_refs.py
- tests/common/test_vikunja_refs.py
tags: []
---

# Work Package Prompt: WP01 – Registry data file + typed fail-loud accessor

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/vikunja-reference-seam`
- **Final merge target for completed work**: `feat/vikunja-reference-seam`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` decides the lane workspace path and records the lane branch. Trust the path printed by `spec-kitty agent workflow implement`; do not manually create a different worktree.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Markdown Formatting

Wrap HTML/XML tags in backticks. Use language identifiers in code blocks.

---

## Objectives & Success Criteria

Build the **foundation** of the reference seam: one declared registry data file and
a typed accessor that resolves logical Vikunja project/label names to identities
with **zero network I/O** and **fail-loud** semantics. Every other WP imports this.

**Done when:**
- `scripts/common/vikunja_refs.json` declares all post-#714-reset projects + the
  `felix:ignore` label, using the `{kind, value}` selector shape, with
  `title`/`owner`/`provisioned` fields and an (initially empty) `private_projects` list.
- `scripts/common/vikunja_refs.py` exposes `project_id`, `project_title`,
  `selector`, `label_id`, `private_project_ids`, and a `VikunjaRefError`, all
  network-free and memoized.
- Resolution **never** returns `None`/`0`/empty to signal "not found" — it raises
  `VikunjaRefError` for undeclared names, declared-but-unprovisioned (`value:
  null`) refs, and wrong-kind accessor calls.
- `pytest tests/common/test_vikunja_refs.py` is green and asserts no network call
  occurs on any accessor path (injected loader).

## Context & Constraints

Read these mission artifacts before editing — they are authoritative:
- `kitty-specs/vikunja-reference-seam-01KXK68Z/data-model.md` — the registry
  schema (selector shape, `provisioned` flag, `private_projects`), the accessor
  interface, and the invariants.
- `kitty-specs/vikunja-reference-seam-01KXK68Z/contracts/vikunja-refs.contract.md`
  — the exact success/failure behavior each accessor must honor.
- `docs/design/vikunja-configuration-design.md` — **C-004**: the locked post-reset
  names. The registry must not diverge from this document, and must **not** declare
  a "someday" project (deleted by design) nor felix-bot's own Inbox (id 14, C-002).

Constraints:
- **C-001**: Felix-side code only. Do not create/rename/delete any Vikunja config.
- **NFR-001**: zero network on any accessor call. **NFR-003**: stdlib only (plus
  the existing `scripts/common/vikunja_client.py` / `vikunja_config.py` if needed —
  but the accessor itself needs neither for the hot path).
- Follow `docs/design/helper-script-conventions.md` (library tier): pure,
  importable, no I/O on the hot path, typed errors.

Grep the codebase for import conventions before writing imports (per
`[[feedback_wp_prompts_grep_codebase]]`): other `scripts/common/` modules use
`from __future__ import annotations` and are imported as
`from scripts.common import vikunja_refs`.

## Subtasks & Detailed Guidance

### Subtask T001 – Seed the registry JSON from live post-reset ids
- **Purpose**: Declare the single source of truth for every runtime project/label reference.
- **Steps**:
  1. Create `scripts/common/vikunja_refs.json` with top-level keys:
     `schema_version` (1), `source_of_truth`
     (`"docs/design/vikunja-configuration-design.md"`), `last_verified_utc`
     (`"2026-07-15T00:00:00Z"`), `projects`, `labels`, `private_projects` (`[]`).
  2. **Projects** — one entry per locked post-reset project. Each entry:
     `{ "name": <snake_lower>, "selector": {"kind": "project_id", "value": <int|null>},
     "title": <Vikunja title>, "owner": "kent", "provisioned": <bool> }`.
     Seed at minimum: `inbox` (id 1), `habits` (id 13), `personal` (Personal),
     `felix_kg_automation` (Felix / kg-automation), `clients` (Clients),
     `pointerhealth` (PointerHealth), `spec_kitty` (spec-kitty),
     `metal_casework` (Metal Casework), `ct_90day` (CT-90day). Use the concrete
     ids from `docs/design/vikunja-configuration-design.md`; any project whose id
     you cannot confirm gets `"value": null, "provisioned": false` (a declared but
     unprovisioned ref — do **not** guess an id).
  3. **Labels** — declare the **two** labels with a live runtime consumer this
     mission: `felix:ignore` (sync manual-override, WP04) and **`q:schedule`** (the
     capture "someday" state, WP05 / FR-011). Each:
     `{ "name": "<felix:ignore|q:schedule>", "selector": {"kind": "label", "value": <int|null>},
     "title": "<title>", "owner_token": "kent" }`. Do **not** declare the rest of the
     `f:/q:/t:/loe:` taxonomy — deferred to #749 (spec FR-006). (Analysis finding F1:
     `q:schedule` is seeded here, in the registry's owning WP, so WP05 attaches it by
     id rather than editing this file cross-WP.)
  4. `private_projects`: empty list (no private project exists today; the mechanism
     lives here for when one does — finding #4).
- **Files**: `scripts/common/vikunja_refs.json` (new).
- **Notes / LIVE-PROBE (design-phase-research discipline)**: Before locking ids,
  confirm the live post-reset values against office2 (`ssh office2-claude`) —
  especially **Habits = 13** (this branch's `reconcile_completions.py` still reads
  2; main fixed it to 13) and the **`felix:ignore` + `q:schedule` label ids + owning
  token** (finding #6; felix-bot could not *attach* kent-owned labels in #715, but
  *reads* them — WP05 handles the attach-token question). If you cannot live-probe in
  this workspace, seed the known values (inbox=1,
  habits=13) and mark anything unconfirmed `null`/`provisioned:false`; the WP02
  validator will surface drift. Record what you confirmed in the Activity Log.

### Subtask T002 – `VikunjaRefError` + memoized no-network loader
- **Purpose**: One typed error + a single registry load, cached, with no network.
- **Steps**:
  1. In `scripts/common/vikunja_refs.py`, define
     `class VikunjaRefError(Exception)` — the single typed failure surface.
  2. Implement a module-level loader that reads `vikunja_refs.json` from a path
     resolved relative to the module file (`Path(__file__).with_name("vikunja_refs.json")`),
     parses it once, and **memoizes** (module-level cache or `functools.lru_cache`).
     Validate shape on load: required top-level keys present, each project/label
     entry well-formed, selector `kind` ∈ {`project_id`, `label`}; raise
     `VikunjaRefError` on a malformed registry (fail-loud at load, not at call).
  3. Provide an **injectable loader seam** for tests: e.g. an internal
     `_load_registry(path=None)` plus a way for tests to substitute an in-memory
     dict (a module-level override or a `set_registry_for_test` hook) so unit tests
     never read the real file and never touch the network.
- **Files**: `scripts/common/vikunja_refs.py` (new).
- **Notes**: No `import requests`, no `VikunjaClient` on this path — loading is pure
  file/JSON. Assert this in tests (T005).

### Subtask T003 – Project accessors (fail-loud)
- **Purpose**: The runtime project resolution surface.
- **Steps**: Implement, all reading only the memoized registry:
  - `project_id(name: str) -> int` — returns the int from a `project_id` selector.
    Raise `VikunjaRefError` if: `name` undeclared; selector `kind == "label"`
    (wrong accessor); or `provisioned is False` / `value is None`
    (**"declared but unprovisioned"** — distinct message, FR-009).
  - `project_title(name: str) -> str` — the declared title; raise if undeclared.
  - `selector(name: str) -> dict` — the raw `{kind, value}` copy (for the
    vikunja_scope selector layer, WP03); raise if undeclared.
- **Files**: `scripts/common/vikunja_refs.py`.
- **Notes**: Error messages must name the logical name and the reason so a caller
  log is actionable (this is the #743 fix — loud, not silent). Return copies of
  mutable structures so callers cannot mutate module state.

### Subtask T004 – Label + private accessors (fail-loud)
- **Purpose**: Per-token label resolution + the private-project set derivation.
- **Steps**:
  - `label_id(name: str, owner_token: str) -> int` — resolve within the label's
    `owner_token` namespace. Raise `VikunjaRefError` if undeclared, unprovisioned,
    or if `owner_token` does not match the declared owner (per-token, #715 / FR-006).
  - `private_project_ids() -> frozenset[int]` — resolve each name in
    `private_projects` via `project_id(...)` and return the frozenset (empty today).
    A listed-but-undeclared/unprovisioned name raises (fail-loud).
- **Files**: `scripts/common/vikunja_refs.py`.

### Subtask T005 – Accessor unit tests (injected loader, no network)
- **Purpose**: Lock the contract from `contracts/vikunja-refs.contract.md`.
- **Steps**: In `tests/common/test_vikunja_refs.py`, using an **injected in-memory
  registry** (never the real file, never the network), cover:
  - `project_id("inbox") == <seeded id>`; `project_title`/`selector` return declared values.
  - undeclared name → `VikunjaRefError`; unprovisioned (`value: null`) → `VikunjaRefError`
    with the "unprovisioned" message; `project_id` on a `label`-kind selector → raise.
  - `label_id("felix:ignore", "kent")` resolves; wrong `owner_token` → raise;
    undeclared label → raise.
  - `private_project_ids()` returns the resolved frozenset (test with a seeded
    private name; and empty when the list is empty).
  - **No network / no file read on the hot path**: assert via a loader that would
    raise if the network/file were touched (e.g. monkeypatch the real loader to blow
    up, inject the in-memory registry, confirm accessors still work).
- **Files**: `tests/common/test_vikunja_refs.py` (new).
- **Notes**: If `tests/common/` lacks an `__init__.py` and sibling test packages
  have one, add it (per `[[reference_pytest_test_package_init]]`) — check first.

## Test Strategy

- Run: `python3 -m pytest tests/common/test_vikunja_refs.py -q` from repo root.
- All Vikunja effects injected; **no live network**. Aim for full branch coverage
  of the fail-loud paths (they are the point of the mission).

## Risks & Mitigations

- **Seeding a wrong id** → silent mis-route later. Mitigation: live-probe (T001);
  anything unconfirmed is `null`/`provisioned:false`, and WP02's validator confirms
  reality on every run.
- **Duplicate "Inbox" (id 1 vs felix-bot id 14)**: registry pins id 1, owner
  `kent`; never declare id 14 (C-002).
- **Accidental network import** defeating NFR-001: keep the accessor import graph
  free of `vikunja_client`; the T005 no-network test guards this.

## Integration Verification (mandatory before for_review)

- [ ] `from scripts.common import vikunja_refs` imports with no network/side effects.
- [ ] Every accessor fail path raises `VikunjaRefError` (no `None`/empty returns).
- [ ] Field names + error semantics match `data-model.md` and the contract.
- [ ] Tests verify the *contract* (spec/contract behavior), not just the implementation.

## Review Guidance

- Confirm the registry JSON matches `docs/design/vikunja-configuration-design.md`
  (no "someday" project; no felix-bot Inbox; selector shape used, not bare ints).
- Confirm unprovisioned vs undeclared produce **distinct** loud errors (FR-009).
- Confirm no network on the hot path (NFR-001) is actually tested.

## Activity Log

> Append new entries at the END, chronological order, UTC `YYYY-MM-DDTHH:MM:SSZ`.

- 2026-07-15T17:18:48Z – system – Prompt created.
- 2026-07-15T17:38:04Z – claude:sonnet:python-pedro:implementer – shell_pid=85299 – Assigned agent via action command
- 2026-07-15T17:51:11Z – claude:sonnet:python-pedro:implementer – shell_pid=85299 – Ready for review (moved from primary checkout per known #710 lane-vs-primary stale-event-log SOP)
- 2026-07-15T17:51:35Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=89485 – Started review via action command
- 2026-07-15T17:56:06Z – user – Moved to planned
- 2026-07-15T17:56:45Z – claude:sonnet:python-pedro:implementer – shell_pid=91217 – Started implementation via action command
- 2026-07-15T18:00:38Z – claude:sonnet:python-pedro:implementer – shell_pid=91217 – Fixes for cycle-1 findings applied (39 tests, ruff clean, 5aac3b5c)
- 2026-07-15T18:00:50Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=92475 – Started review via action command
- 2026-07-15T18:03:33Z – user – Moved to planned
- 2026-07-15T18:03:52Z – claude:sonnet:python-pedro:implementer – shell_pid=93693 – Started implementation via action command
