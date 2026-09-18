---
work_package_id: WP01
title: Taxonomy data and fail-closed loader
dependencies: []
requirement_refs:
- FR-004
- FR-005
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
created_at: '2026-09-18T18:45:00Z'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: tooling/scripts/
create_intent:
- tooling/scripts/doc_taxonomy.py
- tests/docs_standards/__init__.py
- tests/docs_standards/test_doc_taxonomy.py
execution_mode: code_change
owned_files:
- docs/design/standards/allowed-values.json
- tooling/scripts/doc_taxonomy.py
- tests/docs_standards/__init__.py
- tests/docs_standards/test_doc_taxonomy.py
role: implementer-ivan
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this file, load your assigned profile:

```
/ad-hoc-profile-load implementer-ivan
```

Do not begin implementation until the profile is loaded. It carries the identity, boundaries, and
governance scope you are working under.

## Objective

Make `docs/design/standards/allowed-values.json` express **doc_type-scoped** status sets, and give every
consumer a single loader that **fails closed** rather than guessing.

## Why this is first

This file gates every commit in the repo through `.githooks/pre-commit`. Everything else depends on its
shape. Nothing here changes enforcement behaviour — that is WP03 — so this WP is safe to land alone.

## Context you need

- `docs/design/standards/allowed-values.json` — the only enforced source (`validate_docs.py:56`).
- The current loader accepts **top-level list values only** and, on malformed JSON, prints a warning and
  **continues on built-in fallbacks**. That is unsafe once this file is authoritative (review finding #7).
- Decided status sets (`data-model.md` → DocStatus):
  - `decision`: `draft`, `proposed`, `approved`, `superseded`, `deprecated`
  - everything else: `draft`, `proposed`, `in_review`, `approved`, `deprecated`, `archived`, `active`

## Subtasks

**T001 — Add `status_by_doc_type`.** Keep the existing `status` array as the default for every doc_type
that does not opt in, and add `status_by_doc_type: {"decision": [...]}` consulted first. Backward
compatible on purpose: the current validator reads only `status` and must keep working until WP03.

**T002 — New `tooling/scripts/doc_taxonomy.py`.** One shared loader returning the permitted status set
for a given `doc_type`. Both `validate_docs.py` (WP03) and the generator (WP02) consume it. No consumer
may parse the JSON itself.

**T003 — Fail closed.** Missing file, malformed JSON, a non-list value, an empty set, duplicate entries,
or a `status_by_doc_type` key that is not a valid `doc_type` must all **raise**, not warn-and-continue.
Removing the existing silent fallback is the point of this subtask.

**T004 — Tests.** One negative test per malformed shape in T003, plus a positive load. Put them in
`tests/docs_standards/`.

**T005 — Prove no behaviour change.** Run `python3 tooling/scripts/validate_docs.py` over the whole repo
and confirm it still passes. This WP must not start rejecting documents.

## Definition of Done

- `allowed-values.json` carries both keys; the default set is unchanged in content.
- `doc_taxonomy.py` raises on every malformed shape, with a message naming the file and the problem.
- Tests cover each failure mode; `make test` holds the floor (**6490 passed**; see the known
  pre-existing failure in #989 — do not treat it as yours).
- Repo-wide `validate_docs.py` still passes.

## Risks

- **Do not** replace `status` with a map. The pre-commit hook reads it on every commit; a shape the
  current code cannot parse blocks all work in the repo until WP03 lands.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
