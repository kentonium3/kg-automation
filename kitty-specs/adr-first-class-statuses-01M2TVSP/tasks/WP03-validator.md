---
work_package_id: WP03
title: Scoped validation and decision-log checks
dependencies:
- WP01
- WP02
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
created_at: '2026-09-18T18:45:00Z'
subtasks:
- T012
- T013
- T014
- T015
- T016
- T017
phase: Phase 2 - Enforcement
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: tooling/scripts/
create_intent:
- tests/docs_standards/test_validator_scoping.py
- tests/docs_standards/test_decision_log.py
execution_mode: code_change
owned_files:
- tooling/scripts/validate_docs.py
- tests/docs_standards/test_validator_scoping.py
- tests/docs_standards/test_decision_log.py
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

Enforce the contract with messages an author can act on — without widening what the validator walks.

## Context you need

`validate_docs.py` gates every commit. It does two unrelated jobs with **different scopes**, and
conflating them is dangerous:

- **Frontmatter validation** uses `SKIP_DIRS`, which excludes `kitty-specs/`, `.kittify/`, `.agents/`,
  `.claude/`, `.codex/`, `dist/`.
- **Secret scanning** uses the deliberately narrower `SECRET_SCAN_SKIP_DIRS` and **does** scan
  `kitty-specs/`. A 2026-04-08 key leak went unnoticed for a month because the secret scanner reused
  `SKIP_DIRS`; the comment at line 104 records that.

## Subtasks

**T012 — Scoped status enforcement.** Resolve the permitted set via `doc_taxonomy.py` (WP01) keyed on
the document's `doc_type`. No JSON parsing here.

**T013 — Actionable messages.** Name the file, the offending value, the `doc_type`, and the permitted
set for that `doc_type`. Scoped to status-membership failures; structural and generation failures get
their own message shapes (review finding #13).

**T014 — Decision-log validation.** Per `contracts/decision-log-contract.md`: section presence, table
shape, `Type` in vocabulary, ISO date, and `superseded-by` ⇔ `status: superseded` consistency. Both
grammars are valid — the empty form (`*No entries.*`, no table) and the populated form. Applies to every
`doc_type: decision` document, which is ADRs **and** RFCs.

**T015 — Scope assertion.** ⚠ **Read this carefully (review finding #10).** The rule is **never
frontmatter-validate** those trees — *not* "never walk" them. Assert that `front_matter()` is never
invoked for a path under a skipped dir, and in the same test assert that **secret scanning still covers
`kitty-specs/`**. A test that disabled secret coverage would be worse than the bug being fixed.

**T016 — A negative test per promised check.** Every check named in T014 needs a failing case.

**T017 — Full-repo run green.** `python3 tooling/scripts/validate_docs.py` over the whole tree.

## Definition of Done

- An ADR-only status on a runbook is rejected, naming both the doc_type and its permitted set.
- `active` on a `decision` document is rejected; `superseded` is accepted.
- Every decision-log check has a negative test.
- Secret scanning of `kitty-specs/` provably still happens.
- Full-repo validation passes; `make test` holds the **6490** floor (#989 is pre-existing, not yours).

## Risks

- WP05 has not run yet, so the corpus still carries `doc_type: reference` on ADRs. Enforcement that
  assumes migration has happened will fail the repo-wide run. Keep T012 keyed on actual frontmatter.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
