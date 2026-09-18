---
work_package_id: WP04
title: ADR authoring template
dependencies:
- WP01
requirement_refs:
- FR-007
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
created_at: '2026-09-18T18:45:00Z'
subtasks:
- T018
- T019
phase: Phase 2 - Enforcement
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: docs/_templates/
create_intent:
- tests/docs_standards/test_adr_template.py
execution_mode: code_change
owned_files:
- docs/_templates/decision.md
- tests/docs_standards/test_adr_template.py
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

New ADRs must conform at creation, rather than being migrated later.

## Context you need

`docs/_templates/decision.md` is the actual ADR authoring template and it was **missed entirely** in the
first decomposition (review finding #9). It currently emits `doc_type: reference` and has no decision log
section, so an ADR created from it today would violate the contract the moment it is written.

The template is Templater-driven — note that a Templater expression is currently leaking into the
`doc_type` field across the repo (tracked separately as **#988**). Do not fix #988 here; just make this
one template emit the right values.

## Subtasks

**T018 — Fix the template.** It must emit `doc_type: decision`, a status valid for that doc_type
(`draft`), and an empty decision log section:

```markdown
## Decision log

*No entries.*
```

It must **not** emit a body `Status:` line — frontmatter is authoritative (FR-007, Kent 2026-09-18).

**T019 — Regression test.** Assert over the rendered/template content that a new ADR conforms: correct
`doc_type`, a permitted status, decision-log section present, no body `Status:` line.

## Definition of Done

- A document created from the template passes WP03's validation unmodified.
- The test fails if any of the four properties regress.

## Risks

- Do not restructure the template beyond these fields. Its prose is an authoring aid others rely on.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
