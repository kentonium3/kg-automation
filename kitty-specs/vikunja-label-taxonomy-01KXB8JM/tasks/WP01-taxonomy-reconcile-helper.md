---
work_package_id: WP01
title: Taxonomy reconcile helper + tests + design-doc colors
dependencies: []
requirement_refs:
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
- NFR-001
- NFR-002
- NFR-003
tracker_refs: []
planning_base_branch: feat/vikunja-label-taxonomy
merge_target_branch: feat/vikunja-label-taxonomy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-label-taxonomy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-label-taxonomy unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
- T008
agent: claude:opus:reviewer-renata:reviewer
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/
create_intent:
- scripts/vikunja/create_taxonomy_labels.py
- tests/vikunja/test_create_taxonomy_labels.py
execution_mode: code_change
owned_files:
- scripts/vikunja/create_taxonomy_labels.py
- tests/vikunja/test_create_taxonomy_labels.py
- docs/design/vikunja-configuration-design.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries, and initialization declaration, then proceed.

## Objective

Ship a single deterministic, idempotent helper —
`scripts/vikunja/create_taxonomy_labels.py` — that reconciles the live Vikunja
label set toward the canonical 12-label taxonomy (`f:`/`q:`/`t:`/`loe:`) and,
behind an explicit backup-gated flag, deletes the 3 legacy labels. Add a full
mocked-client test suite (`tests/vikunja/test_create_taxonomy_labels.py`), and
add the color column to the design doc's label tables so
`docs/design/vikunja-configuration-design.md` remains the single taxonomy
authority.

The **live run is NOT part of this WP** — it is a post-merge operational step
(see `quickstart.md`). This WP produces code + tests + the doc edit only.

## Context (read these first)

- **Authoritative behavior contract**: `kitty-specs/vikunja-label-taxonomy-01KXB8JM/contracts/create_taxonomy_labels.md` — the CLI, the reconcile steps, idempotency, and every failure mode. This is binding; implement to it exactly.
- **Data model + canonical taxonomy table (titles + colors + dimensions)**: `kitty-specs/vikunja-label-taxonomy-01KXB8JM/data-model.md`. The 12 titles/colors and the invariants (INV-1..INV-8) are the source of truth for the constants.
- **API + gotcha decisions**: `kitty-specs/vikunja-label-taxonomy-01KXB8JM/research.md` (R-01..R-08).
- **The client you build on**: `scripts/common/vikunja_client.py` — `VikunjaClient` with `.get/.put/.delete`, leading-slash paths, typed exceptions (`VikunjaAuthError`, `VikunjaNotFoundError`, `VikunjaBadRequestError`, `VikunjaServerError`, `VikunjaTimeoutError`), empty body → `{}`. Do NOT add a new HTTP path (no `requests`).
- **Config**: `scripts/common/vikunja_config.py::get_vikunja_base_url()`; the token defaults to `VikunjaClient.DEFAULT_TOKEN_PATH`. Passing `base_url=None, token=None` makes `VikunjaClient` resolve both canonically on office2.
- **Proven label-create pattern (endpoint evidence)**: `scripts/vikunja/setup_vikunja.py::create_labels` — create is `PUT /labels` with body `{"title", "hex_color"}`.
- **Test-mock pattern to mirror**: `tests/habits/test_query_active_habits_weekly.py` and `tests/vikunja/test_create_task.py` show how VikunjaClient is faked/mocked in this repo. `tests/conftest.py` installs a **global urlopen guard** — your tests must make NO real network calls (inject a fake client; never construct a real `VikunjaClient` that hits the wire).
- **Invocation form**: the helper runs as `python3 -m scripts.vikunja.create_taxonomy_labels` from the repo root (namespace packages; `scripts/` has no `__init__.py` and does not need one — mirror `create_task.py`). office2 is `python3`-only.

### Canonical taxonomy (copy EXACTLY from data-model.md — titles + colors)

Friction (gradient): `f:1-flow`=`4caf50`, `f:2-growth`=`fbc02d`, `f:3-edge`=`fb8c00`, `f:4-overload`=`e53935`.
Eisenhower (blue): `q:do`=`1565c0`, `q:schedule`=`1e88e5`, `q:delegate`=`42a5f5`, `q:eliminate`=`90caf9`.
Type: `t:habit`=`8e24aa`. LOE (gray): `loe:s`=`bdbdbd`, `loe:m`=`757575`, `loe:l`=`424242`.
Legacy to delete: `personal`, `intentional`, `Duplicate`.

---

### Subtask T001 — Declare taxonomy + legacy constants

**Purpose**: the single in-code source of truth for what must exist / be removed.

**Steps**:
1. In `scripts/vikunja/create_taxonomy_labels.py`, declare the 12 taxonomy labels as an ordered structure of `(title, hex_color, dimension)` — e.g. a list of small dataclasses or `(title, color, dimension)` tuples. Colors are bare 6-hex strings (no `#`), lower-case, exactly per the table above.
2. Declare `LEGACY_TITLES = ["personal", "intentional", "Duplicate"]`.
3. Add a `normalize_color(value)` helper: strip a leading `#`, lower-case. Use it on both declared and server-returned colors so comparison is form-independent (R-04).
4. Add a `normalize_title` if needed for matching — titles are matched **exactly** (case-sensitive) per the design doc; do not lower-case titles (e.g. `Duplicate` is capitalized). "Normalized" for the dedup map means the exact title string as the key.
5. Module docstring: state it is the deterministic layer (Directive 6), that create = `PUT /labels`, and that the live run is operator-invoked post-merge.

**Do NOT**: read files or hit the network at import time. Pure constants + tiny pure helpers.

### Subtask T002 — Paginated listing + duplicate-title detection

**Purpose**: build an accurate live view that surfaces duplicates instead of hiding them (FR-009, FR-010, INV-6).

**Steps**:
1. `list_labels(client) -> dict[str, list[dict]]`: page `client.get("/labels", params={"per_page": "50", "page": str(n)})` starting at page 1, accumulating until a page returns fewer than 50 items (or empty). Build `{title: [label, ...]}` — a **list** per title (do not collapse duplicates).
2. Each label dict retains at least `id`, `title`, `hex_color`.
3. Provide a small accessor to detect duplicates: any title whose list length > 1.

**Edge cases**: empty instance → `{}`. A title appearing 3× → list of 3.

### Subtask T003 — Create pass

**Purpose**: create missing taxonomy labels; never falsely pass on a wrong color (FR-001, FR-002, FR-007, FR-011, INV-7).

**Steps**:
1. For each taxonomy entry, look up its title in the live map:
   - **absent** → `client.put("/labels", json={"title": title, "hex_color": color})`; capture the new id from the response; record `ReconcileOutcome(title, "created", id)`.
   - **present, 1 match, color matches** (`normalize_color(existing) == normalize_color(declared)`) → record `already-present` + existing id.
   - **present, 1 match, color differs** → record `color-mismatch` + existing id; flag the run for non-zero exit. Do NOT attempt to update the color (out of scope — see contract "Color correction").
   - **present, >1 match (duplicate)** → record `duplicate-title` with all ids; flag non-zero exit; do NOT create or mutate.
2. Collect the title→id map for all 12 taxonomy titles (from created ids + existing ids).

### Subtask T004 — Delete pass (gated, destructive)

**Purpose**: remove the 3 legacy labels safely (FR-005, FR-006, C-002, INV-6, INV-8).

**Steps**:
1. The delete pass runs only when `--delete-legacy` is set. If `--delete-legacy` is set but `--backup-confirmed <ref>` is absent → print a clear error and exit non-zero BEFORE any mutation.
2. For each legacy title present in the live map, delete **every** id that matches (handles the duplicate `Duplicate` case): `client.delete(f"/labels/{id}")`; record `deleted` per id.
3. Legacy title absent → `already-absent`.
4. On `VikunjaNotFoundError` during a delete (concurrent/stale), re-list; if the title is now absent → `already-absent`; if still present → fail (inconsistent view), non-zero exit (INV-8).
5. Without `--delete-legacy`, any present legacy label is `skipped-no-flag` (reported, not deleted).

### Subtask T005 — CLI + reporting + exit codes

**Purpose**: the operator entrypoint (FR-003, FR-007, FR-008, contract CLI table).

**Steps**:
1. `argparse` with: `--delete-legacy` (flag), `--backup-confirmed <str>`, `--dry-run` (flag), `--json` (flag), `--base-url <str>`, `--token <str>`, `--token-file <path>`.
2. Construct `VikunjaClient(base_url=args.base_url, token=<resolved>)` — pass `None` to fall back to canonical defaults. If `--token-file`, read it; else `--token`; else default.
3. `--dry-run`: compute the plan (would-create / would-delete / would-skip) from the live listing WITHOUT any `put`/`delete`; print it; exit 0.
4. Normal run: create pass → (optional) delete pass → assemble outcomes.
5. Output:
   - Default: a readable per-label outcome table + the title→id map + (if deleting) the echoed `backup_confirmed` ref.
   - `--json`: a JSON object `{"outcomes": [...], "label_id_map": {...}, "backup_confirmed": <ref or null>}` on stdout.
6. **Exit code**: `0` only if every taxonomy label is present with a correct color and all requested deletes succeeded; **non-zero** if any `duplicate-title`, `color-mismatch`, refused delete, or surfaced `VikunjaError`. Surface (do not swallow) client exceptions with a clear message.

### Subtask T006 — Design-doc color column

**Purpose**: keep the design doc the single taxonomy authority (post-plan finding #1).

**Steps**:
1. In `docs/design/vikunja-configuration-design.md`, add a **Color (hex)** column to each of the four label tables (Friction, Eisenhower, Type, LOE), filling the exact values from the table above.
2. Do NOT change any title, dimension, or narrative text — colors are additive only.
3. Keep the markdown tables valid (Docs CI validates). This file is a dual-purpose Obsidian doc — do not add `#`-anchor links.

### Subtask T007 — Tests: create / idempotency / fidelity

**Purpose**: prove the additive paths + guard drift (NFR-001, NFR-002, INV-1, INV-7, FR-010/FR-011).

Write `tests/vikunja/test_create_taxonomy_labels.py` using a **fake client** (a small class or `unittest.mock` double exposing `get`/`put`/`delete` with the real signatures and leading-slash paths). No real network. Cover:
1. **create-from-empty**: fake `get /labels` returns `[]` → all 12 `PUT /labels` issued with correct `{title, hex_color}` bodies; outcomes all `created`; title→id map has 12 entries; exit 0.
2. **skip-existing**: fake returns some taxonomy labels already present with correct colors → those `already-present`, the rest `created`; 0 redundant puts on the present ones.
3. **idempotent re-run**: fake returns ALL 12 present with correct colors → 0 puts, all `already-present`, exit 0 (NFR-002).
4. **color-mismatch**: a present taxonomy label with a different color → `color-mismatch`, non-zero exit, no put (INV-7, FR-011).
5. **duplicate-title**: a taxonomy title present twice → `duplicate-title` with both ids, non-zero exit, no mutation (FR-010).
6. **fidelity assertion**: the 12 declared titles == the design-doc taxonomy set, and the declared colors match the values documented in data-model/design-doc (assert against a literal expected set in the test so drift fails loudly, INV-1).
7. **pagination**: fake `get` returns 50 then a short page → helper requests page 2 and stops (proves the `per_page`≤50 loop).

### Subtask T008 — Tests: delete / failure-modes / dry-run

**Purpose**: prove the destructive + error paths (FR-005/FR-006, INV-8, NFR-001).

Cover:
1. **delete refused without backup ref**: `--delete-legacy` and no `--backup-confirmed` → non-zero exit, NO `delete` calls.
2. **delete with backup ref**: `--delete-legacy --backup-confirmed X` → each present legacy id deleted; `backup_confirmed` echoed in JSON.
3. **delete-all-matches**: legacy title present twice → both ids deleted.
4. **delete-404 re-list**: `delete` raises `VikunjaNotFoundError`; on re-list the title is absent → `already-absent`, no crash; and the still-present variant → fail (INV-8).
5. **skipped-no-flag**: legacy present, no `--delete-legacy` → `skipped-no-flag`, no delete.
6. **failure modes**: fake `get` raises `VikunjaTimeoutError` / `VikunjaAuthError` / `VikunjaServerError` → surfaced, non-zero exit, no false success claim.
7. **dry-run**: `--dry-run --delete-legacy --backup-confirmed dry-run` → plan printed, zero `put`/`delete` calls, exit 0.

## Branch Strategy

Planning artifacts were generated on `feat/vikunja-label-taxonomy`. This WP is
implemented in its computed lane worktree (from `lanes.json` after
finalize-tasks) and merges back into `feat/vikunja-label-taxonomy`. The
`feat → main` merge and the live office2 run happen after mission merge +
post-merge Codex review — not in this WP.

## Test Strategy

- All tests are offline (fake client). `make test` must stay green (the pre-push gate runs it).
- Put the fake client in the test module (or reuse an existing fixture pattern from `tests/vikunja/` / `tests/habits/`). Assert on the exact paths (`/labels`, `/labels/{id}`), methods (`get`/`put`/`delete`), and `PUT /labels` body shape — this is the mock-fidelity guard (research R-07).

## Definition of Done

- [ ] `scripts/vikunja/create_taxonomy_labels.py` implements the full contract (create + gated delete + dry-run + json + exit codes).
- [ ] All 8 subtasks' behaviors implemented; every failure mode in the contract handled.
- [ ] `tests/vikunja/test_create_taxonomy_labels.py` covers every path above; `make test` green.
- [ ] Design-doc label tables carry the color column with exact values; Docs CI green.
- [ ] Fidelity test asserts constants == design-doc taxonomy (titles + colors).
- [ ] No real network in tests; no new third-party dependency; module runs via `-m` form.

## Risks / Reviewer Guidance

- **Reviewer**: verify create = `PUT /labels` (not POST); titles matched case-sensitively (`Duplicate` stays capitalized); colors normalized on compare; delete gated on BOTH `--delete-legacy` AND `--backup-confirmed`; duplicate-title and color-mismatch both force non-zero exit; the mock mirrors the real `VikunjaClient` surface (leading-slash paths, `.put` for create). Confirm the fidelity test would actually fail if a title/color drifted (not a tautology). Confirm zero real network calls.
- **Gotcha**: `VikunjaClient` paths need a leading slash; `per_page` caps at 50; `hex_color` returns without `#`.
