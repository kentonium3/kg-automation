---
work_package_id: WP06
title: Enable the gates
dependencies:
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-006
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-adr-first-class-statuses-01M2TVSP
base_commit: cf97254947c9ac9874c1c6ee78025094266b2f25
created_at: '2026-09-18T23:36:07.953656+00:00'
subtasks:
- T026
- T027
- T028
phase: Phase 4 - Gate
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: .githooks/
create_intent: []
execution_mode: code_change
owned_files:
- .githooks/pre-commit
- .github/workflows/docs-ci.yml
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

Make the contract survive `--no-verify`.

## ⚠ Must be last

Enabling a freshness check before the generated outputs exist would block **every commit in this repo**,
including this mission's own. Confirm WP02–WP05 are merged and the tree is clean before starting.

## ⚠ Operator flag — `.github/workflows/` edit

kg-automation's CLAUDE.md says: *"CI: never modify `.github/workflows/` without explicit instruction."*
T027 edits `docs-ci.yml`. This is covered by FR-006, which Kent confirmed in the Intent Summary, but the
edit is called out here so it is visible in review rather than buried in a diff. If the reviewer is not
satisfied that FR-006 authorises it, stop at T026 and surface T027 rather than proceeding.

## Context you need

Verified 2026-09-18: `docs-ci.yml` **already** triggers on `push: [main]`, `pull_request: [main]` and
`workflow_dispatch`. There is **no trigger defect** — an earlier research note claiming otherwise was
wrong and has been corrected (review finding #12). This WP adds a *step*, not a trigger.

The hook currently runs `validate_docs.py` and `validate_architecture_data.py` whole-tree. It does not
check generated-file freshness.

## Subtasks

**T026 — Hook.** Add `generate_doc_standards.py --check` to `.githooks/pre-commit`, after the existing
validators so its failure message is not buried.

**T027 — CI.** Add the same `--check` as a step in the existing `docs-ci.yml` job, ordered relative to
`validate_docs.py`. Do not touch the triggers.

**T028 — Prove the gate.** Deliberately stale a generated file, confirm both the hook and CI fail and
name it; restore. Then confirm `make test` holds the floor (**6490 passed**; #989 is the known
pre-existing failure and is not yours to fix).

## Definition of Done

- A stale generated file fails the hook **and** CI, naming the file.
- A clean tree passes both.
- Suite floor held; full-repo validation green.

## Risks

- The hook is bypassable by design (`--no-verify`); CI is the real gate. If only one can land, land the
  CI step.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
