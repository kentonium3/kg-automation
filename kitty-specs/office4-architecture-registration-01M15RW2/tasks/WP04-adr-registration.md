---
work_package_id: WP04
title: Register ADR 0008 in the index surfaces
dependencies:
- WP02
requirement_refs:
- FR-010
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
- T019
phase: Phase 2 - Discoverability
history:
- at: '2026-08-29T04:12:16Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/adr/README.md
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- docs/design/architecture/adr/README.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
- docs/design/architecture/README.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Register ADR 0008

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Make ADR 0008 discoverable from every surface that indexes or points at ADRs.

Done when the per-file loop in [quickstart.md](../quickstart.md) step 5 passes for **all
four** files, and `validate_docs.py` exits 0.

## Context & Constraints

- **Depends on WP02** — you need the ADR's final filename to exist.
- **The four files are not equivalent.** Measured ADR references
  ([research.md](../research.md) R-7, [contracts](../contracts/architecture-data-payloads.md) C-6):

  | File | "adr" hits | What to do |
  |---|---|---|
  | `docs/design/architecture/adr/README.md` | 5 | **The ADR Index.** Add a 0008 row to its table |
  | `docs/INDEX.md` | 14 | Add 0008 to the ADR list (around lines 63–74) |
  | `docs/DEVELOPER_PORTAL.md` | 0 | **No ADR surface.** Add a single pointer |
  | `docs/design/architecture/README.md` | 0 | **No ADR surface.** Add a single pointer |

- **Do not invent an ADR list** in the two zero-hit files. A pointer to the ADR index is the
  whole job there. #909 named those two and missed the actual index — that error is corrected
  here, not repeated.

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T015 – Add the 0008 row to the ADR index

- **File**: `docs/design/architecture/adr/README.md` — **the required target.** Omitting it
  leaves the index showing 0001–0007 forever.
- **Steps**: read its existing table (title, status, date columns) and append a 0008 row in
  exactly that shape. Status `Accepted`, date matching the ADR's own `**Date**`.

### Subtask T016 – Add 0008 to `docs/INDEX.md`

- **Steps**: find the ADR list (around lines 63–74) and add 0008 in the established format,
  with whatever Divio type annotation its siblings carry.

### Subtask T017 – Add a pointer to `DEVELOPER_PORTAL.md`

- ⚠️ **Lines 138–210 are a GENERATED block**, delimited by
  `<!-- begin:runbook-filter (generated; do not edit) -->`. `validate_docs.py` (lines
  266–289) runs a drift check and **fails the commit** with "Developer portal runbook-filter
  block is stale" if it is hand-edited. **Put your pointer outside that block.**
- **Steps**: add one line in a sensible orientation section — a pointer to the ADR index and
  a one-clause note that ADR 0008 records the three-machine model. This is an onboarding
  sitemap; a new reader should learn the machine boundary exists.

### Subtask T018 – Add a pointer to `docs/design/architecture/README.md`

- **Steps**: its tables are Documents / Data Files / Schema Contracts. Add a pointer to the
  ADR index (`adr/README.md`) naming 0008, in whichever table or prose section fits. Do not
  create a new ADR table.

### Subtask T019 – Verify registration

- **Steps**:

  ```bash
  for f in docs/design/architecture/adr/README.md docs/INDEX.md \
           docs/DEVELOPER_PORTAL.md docs/design/architecture/README.md; do
    grep -q "0008-three-machine-model" "$f" || { echo "MISSING in $f"; exit 1; }
  done; echo "OK: registered in all four"
  ```

- Then `python3 tooling/scripts/validate_docs.py` — must exit 0. If it reports the portal
  block stale, you edited inside the generated region; move your pointer out.
- **Do not** substitute `grep -l "0008" a b c` — `grep -l` exits 0 if *any* file matches,
  so it would pass on `docs/INDEX.md` alone, and `"0008"` is a loose token.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Editing inside the portal's generated block | T017 names the exact delimiter and line range |
| Inventing an ADR list where none exists | Pointer only in the two zero-hit files |
| Leaving the real ADR index stale | T015 is the required target, checked by T019 |
| A weak check that passes on one file | T019 loops per-file on the real artifact name |

## Review Guidance

- Confirm `adr/README.md`'s table now has a 0008 row consistent with its siblings.
- Confirm the `DEVELOPER_PORTAL.md` diff is entirely **outside** lines 138–210.
- Confirm the two pointer files gained a pointer, not a fabricated ADR list.
- Confirm the T019 loop passes for all four and `validate_docs.py` is clean.

## Activity Log

- 2026-08-29T04:12:16Z – system – Prompt created.
