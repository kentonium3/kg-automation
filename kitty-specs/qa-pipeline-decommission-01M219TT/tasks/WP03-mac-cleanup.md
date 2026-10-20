---
work_package_id: WP03
title: Mac cleanup
dependencies: []
requirement_refs:
- FR-009
planning_base_branch: feat/970-qa-decommission
merge_target_branch: feat/970-qa-decommission
branch_strategy: Planning artifacts for this mission were generated on feat/970-qa-decommission. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/970-qa-decommission unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
phase: Phase 1 - Mac
history:
- timestamp: '2026-09-08T20:30:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/decommission/mac/
create_intent:
- scripts/decommission/mac/cleanup.sh
execution_mode: planning_artifact
lane: planned
owned_files:
- scripts/decommission/mac/**
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP03 – Mac cleanup

Read first: `../spec.md` User Story 4 + edge cases, `../research.md` D-8,
`../contracts/teardown-verification.md` (M-01..M-08).

- **T010 `scripts/decommission/mac/cleanup.sh`**: targets exactly
  `~/repos/teamspace-qa-scratch`, `~/repos/teamspace-qa-scratch2`,
  `~/teamspace-qa-harness`, `~/teamkitty-qa`, `~/teamkitty-qa-harness`, plus
  QA-classified entries inside `~/Documents/spec-kitty/`. Behavior:
  1. Take the `~/repos/spec-kitty-qa` protection snapshot (HEAD +
     `status --porcelain` hash) BEFORE anything else; refuse to proceed if the
     path is missing.
  2. Inventory every target: what it contains, git repo or not; a git repo
     with unpushed commits or dirty tree → REFUSE that path, record, continue
     with the rest (M-08).
  3. `~/Documents/spec-kitty/`: list entries, classify QA vs non-QA with a
     stated criterion per entry, write the inventory file BEFORE removal
     (M-06); delete only QA-classified entries.
  4. Delete approved targets; re-verify M-01..M-07; print tri-state lines.
  Never run with HOME unset (assert `$HOME` non-empty and a directory —
  Engineering Principle 15). `--dry-run` mode prints decisions only.
- **T011** run it (dry-run, review, then real), save the inventory/evidence
  output to `kitty-specs/qa-pipeline-decommission-01M219TT/research/mac-cleanup-evidence.md`,
  including the M-07 before/after snapshot equality proof. Any REFUSED path is
  surfaced in the WP completion notes for Kent, not silently skipped.

Definition of done: M-01..M-08 all pass or are explicitly REFUSED-and-surfaced;
evidence file committed; `~/repos/spec-kitty-qa` provably untouched.
