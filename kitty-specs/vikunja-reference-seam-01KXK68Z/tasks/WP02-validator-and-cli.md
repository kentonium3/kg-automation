---
work_package_id: WP02
title: Drift / unreachable validator + CLI
dependencies:
- WP01
requirement_refs:
- FR-004
- NFR-002
tracker_refs: []
planning_base_branch: feat/vikunja-reference-seam
merge_target_branch: feat/vikunja-reference-seam
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-reference-seam. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-reference-seam unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
phase: Phase 1 - Foundation
assignee: ''
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
agent_profile: python-pedro
role: implementer
model: claude-sonnet-5
shell_pid: "31245"
shell_pid_created_at: "1784146350.973112"
history:
- at: '2026-07-15T17:18:48Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/common/vikunja_refs_validate.py
create_intent:
- scripts/common/vikunja_refs_validate.py
- scripts/vikunja/validate_refs.py
- tests/common/test_vikunja_refs_validate.py
- tests/vikunja/test_validate_refs.py
execution_mode: code_change
owned_files:
- scripts/common/vikunja_refs_validate.py
- scripts/vikunja/validate_refs.py
- tests/common/test_vikunja_refs_validate.py
- tests/vikunja/test_validate_refs.py
tags: []
---

# Work Package Prompt: WP02 – Drift / unreachable validator + CLI

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

Build the **reality-vs-registry honesty check**: an on-demand validator that lists
live Vikunja once and reports every declared reference that is missing, drifted, or
unprovisioned — plus a distinct **unreachable** state — and fails loud (non-zero
exit) on any finding. This is what keeps the committed ids from silently rotting
(the #743 class).

**Done when:**
- `scripts/common/vikunja_refs_validate.py` exposes a **pure** `validate(...)` over
  injected live data returning `list[ValidationFinding]` (empty == clean).
- `scripts/vikunja/validate_refs.py` is a CLI that lists live Vikunja in **≤2**
  round trips, prints findings, exits 0 when clean and non-zero on any finding, and
  emits a single `unreachable` finding + non-zero exit when Vikunja can't be listed.
- `pytest tests/common/test_vikunja_refs_validate.py tests/vikunja/test_validate_refs.py`
  is green.

## Context & Constraints

Read first:
- `data-model.md` → the `ValidationFinding` shape and the finding kinds
  (`missing` | `id_drift` | `title_drift` | `unprovisioned` | `unreachable`).
- `contracts/vikunja-refs.contract.md` → the Validator table, incl. the reachable
  vs unreachable exit behavior.
- WP01's `scripts/common/vikunja_refs.py` — the validator reads the declared
  registry through it (do not re-parse the JSON yourself; import the accessor /
  loader). WP02 owns a **separate** module (`vikunja_refs_validate.py`) so it does
  not overlap WP01's `owned_files`.

Constraints: **NFR-002** (≤2 live list calls); pure `validate()` (all live data
injected — no network inside `validate`, the CLI does the I/O); stdlib + existing
`VikunjaClient` only; fail-loud.

Grep for how existing `scripts/vikunja/` CLIs shape argparse + exit codes + the
`{"error": ..., "detail": ...}` stderr envelope (e.g. `route_someday.py`,
`create_saved_filters.py`) and match that convention.

## Subtasks & Detailed Guidance

### Subtask T006 – `validate()` pure function → findings
- **Purpose**: The deterministic, testable core of drift detection.
- **Steps**:
  1. In `scripts/common/vikunja_refs_validate.py`, define the finding structure
     (a small dataclass or typed dict) matching `data-model.md`:
     `kind`, `ref_type` (`project`|`label`), `name`, `detail`.
  2. Implement
     `validate(live_projects, live_labels_by_token) -> list[ValidationFinding]`:
     - `live_projects`: iterable of `{id, title}` (as returned by `GET /projects`).
     - `live_labels_by_token`: `{token: [{id, title}, ...]}`.
     - For each declared **project**: if `provisioned` is False / `value` is null →
       `unprovisioned` finding; else find the live project whose `title` == declared
       `title`: none → `missing`; found but id ≠ declared value → `id_drift`; a live
       project with the declared id but a different title → `title_drift`.
     - For each declared **label**: same logic within its `owner_token`'s list.
     - Return every finding (do not stop at the first).
  3. Read the declared entries via the WP01 accessor/loader (import it).
- **Files**: `scripts/common/vikunja_refs_validate.py` (new).
- **Notes**: `validate` performs **no** network I/O — all live data is a parameter.
  This is what makes it unit-testable with injected fixtures.

### Subtask T007 – CLI `validate_refs.py` (live listing, exit codes, unreachable)
- **Purpose**: The operator-facing on-demand check.
- **Steps**:
  1. In `scripts/vikunja/validate_refs.py`, build a `VikunjaClient`, list live
     projects (`GET /projects`) and labels once per relevant token — **≤2 list
     round trips total** (NFR-002). (Only the `kent` token is needed today since
     `felix:ignore` is `owner_token: kent`.)
  2. Call `validate(...)` with the fetched data; print findings in a readable form
     (one line per finding: kind, ref_type, name, detail).
  3. **Exit codes**: `0` when findings is empty ("registry OK"); **non-zero** when
     any finding is present.
  4. **Unreachable path**: if listing raises (network/auth/`VikunjaError`/
     `ConnectionError`), emit a **single** `unreachable` finding and exit non-zero
     as "could not validate" — a state the operator must read as *distinct* from
     "registry clean" (do not swallow it into exit 0). Use the stderr error envelope
     convention for the detail.
  5. Support the mandatory `-m` invocation form:
     `python3 -m scripts.vikunja.validate_refs` (per `[[feedback_helper_m_invocation_form]]`).
- **Files**: `scripts/vikunja/validate_refs.py` (new).
- **Notes**: This is the only place that touches the network in WP02. Keep the
  live-list count at ≤2 and assert it in tests via an injected client spy.

### Subtask T008 – Validator unit tests
- **Purpose**: Lock the finding taxonomy + the unreachable contract.
- **Steps**: 
  - `tests/common/test_vikunja_refs_validate.py`: injected live data producing each
    finding kind (`missing`, `id_drift`, `title_drift`, `unprovisioned`) and the
    clean (empty) case; label findings within a token namespace.
  - `tests/vikunja/test_validate_refs.py`: CLI exit `0` on clean, non-zero on a
    finding; **unreachable** (client raises) → single `unreachable` finding +
    non-zero exit; assert **≤2** list calls via a spy/mock client.
- **Files**: `tests/common/test_vikunja_refs_validate.py`,
  `tests/vikunja/test_validate_refs.py` (both new).
- **Notes**: Check for `__init__.py` needs in `tests/vikunja/`
  (`[[reference_pytest_test_package_init]]`).

## Test Strategy

- `python3 -m pytest tests/common/test_vikunja_refs_validate.py tests/vikunja/test_validate_refs.py -q`.
- No live network — inject `live_projects` / a fake client.

## Risks & Mitigations

- **Confusing unreachable with clean** — the exact bug the mission guards against.
  Mitigation: the dedicated `unreachable` finding + a test that fails if exit 0 is
  ever returned on a listing error.
- **>2 list calls** creeping in (e.g. per-label fetch). Mitigation: fetch all
  labels for the token in one call; assert call count in T008.

## Integration Verification (mandatory before for_review)

- [ ] `validate()` is pure (no network) and returns all findings in one pass.
- [ ] CLI exit codes: 0=clean, non-zero=findings, non-zero+`unreachable` on listing failure.
- [ ] ≤2 live list round trips (asserted).
- [ ] Findings shape matches `data-model.md`.

## Review Guidance

- Verify the unreachable path is genuinely distinct (exit code + finding), not folded into "clean".
- Verify the validator reads declared entries through WP01's accessor (single source), not a re-parse.

## Activity Log

> Append new entries at the END, chronological order, UTC `YYYY-MM-DDTHH:MM:SSZ`.

- 2026-07-15T17:18:48Z – system – Prompt created.
- 2026-07-15T18:16:16Z – claude:sonnet:python-pedro:implementer – shell_pid=98269 – Assigned agent via action command
- 2026-07-15T20:12:45Z – claude:sonnet:python-pedro:implementer – shell_pid=98269 – Validator + CLI; 17 tests; uses public declared_projects/declared_labels (5c7ade0d); rebased on WP01 additions
- 2026-07-15T20:12:58Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=31245 – Started review via action command
