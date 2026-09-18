---
work_package_id: WP02
title: Generator with conditional schema and sentinel bootstrap
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-adr-first-class-statuses-01M2TVSP
base_commit: cf97254947c9ac9874c1c6ee78025094266b2f25
created_at: '2026-09-18T22:31:17.654669+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Foundation
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: tooling/scripts/
create_intent:
- tooling/scripts/generate_doc_standards.py
- tests/docs_standards/test_generator.py
execution_mode: code_change
owned_files:
- tooling/scripts/generate_doc_standards.py
- docs/design/standards/frontmatter.schema.json
- docs/design/standards/doc-standards.md
- tests/docs_standards/test_generator.py
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

Derive both unenforced copies of the status taxonomy from the enforced source, so they cannot drift again.

## Context you need

Read `contracts/generator-contract.md` in full — it is the specification for this WP.

Three files define status today and only `allowed-values.json` is enforced. The other two had already
drifted before this mission started (`active` was live and missing from both). Hand-maintenance is the
defect; generation is the fix.

## Subtasks

**T006 — Skeleton with two modes.** Default writes the derived regions and exits 0. `--check` writes
nothing and exits non-zero if any derived region differs, naming each stale file. `--check` is what CI
runs (WP06).

**T007 — Conditional JSON Schema.** ⚠ **Blocking design point (review finding #2).** A flat
`status.enum` **cannot** express doc_type-scoped sets — a union would permit `active` on an ADR, and the
default set would reject `superseded`. Emit conditional schema (`if doc_type == decision / then / else`).
Test both the accept and the reject path. Preserve all unrelated schema content byte-for-byte.

**T008 — Sentinel bootstrap.** ⚠ **The contract as written is circular (review finding #6)**:
`doc-standards.md` has no sentinels, the generator must fail when they are absent, and generated files
may have no other writer. Resolve with an explicit one-time bootstrap mode. Afterwards enforce strictly:
exactly one ordered start/end pair; reject duplicate, reversed, nested or partial pairs **without writing**.

**T009 — Region-scoped write.** Replace only the region between
`<!-- GENERATED:status-list START -->` and `<!-- GENERATED:status-list END -->`. Hand-written prose
outside it is never touched.

**T010 — Tests.** Idempotency (second run stages no diff), determinism (source order, not sorted),
prose-outside-sentinels survives regeneration, and every sentinel edge case from T008.

**T011 — Bootstrap for real.** Insert the sentinels and generate fresh outputs. After this the two
copies are build output.

## Definition of Done

- Running the generator twice produces **no staged diff** on the second run (NFR-001).
- `--check` fails on a hand-mutated copy and names it.
- A doc_type-scoped schema accepts `superseded` on a `decision` doc and rejects `active` on one.
- Sentinel misuse fails loudly without writing.

## Risks

- Do not sort the status values. Source order keeps the diff reviewable (contract invariant 5).
- `doc-standards.md` is part generated, part prose. Writing outside the region is a defect.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
