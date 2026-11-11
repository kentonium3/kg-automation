---
work_package_id: WP01
title: Migration count from reviewed inputs
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- NFR-001
- NFR-002
- C-001
- C-002
- C-003
- C-004
- FR-007
planning_base_branch: fix/vikunja-migration-count
merge_target_branch: fix/vikunja-migration-count
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-migration-count. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-migration-count unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1
history:
- at: '2026-11-11T00:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/vikunja_release/
create_intent:
- services/vikunja/releases/v2.7.1-670-420c7bcb75.json
- services/vikunja/releases/v2.8.0-rrule.2.json
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- scripts/deploy/vikunja_release/baseline.py
- scripts/vikunja/build_release_baseline.py
- scripts/vikunja/verify_release_upgrade.py
- tests/deploy/test_vikunja_release_baseline.py
- tests/deploy/test_vikunja_release_acceptance.py
- tests/deploy/test_vikunja_cutover_change_set.py
- services/vikunja/releases/v2.7.1-670-420c7bcb75.json
- services/vikunja/releases/v2.8.0-rrule.2.json
- docs/runbooks/vikunja-release-cutover.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP01 – Migration count from reviewed inputs

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the profile in the frontmatter, then follow its guidance before reading the rest of this prompt.

- **Profile**: `implementer-ivan`
- **Role**: `implementer`
- **Agent/tool**: `codex` (gpt-6.1-sol). Reviewer: Claude Sonnet 5.5.

---

## Objective

Implement plan D-1 to D-5 (`plan.md`). Spec FR-001 to FR-006, NFR-001, NFR-002, C-001, C-002. Every gate stays fail-closed.

## Subtasks

- **T001 Builder (D-1, D-5).** `baseline.build(pre, post, record, *, expected_added, deadline=None)`: reject a non-`int` or `bool` `expected_added`, or a negative one, as `BUILD_BASELINE_INVALID`. Raise `GATE_MIGRATIONS_MISMATCH` unless the pre set is a subset of the post set and `len(added) == expected_added`. `build_release_baseline.py` takes a required `--expected-added-count N`; a missing or bad value is `BUILD_BASELINE_USAGE` (exit 2). Remove its own `!= 10`.
- **T002 Verifier (D-2).** Remove `len(facts["added_migration_ids"]) != 10` from `verify_release_upgrade.py`. Leave every other binding.
- **T003 History and change-set tests (D-3).** Create `services/vikunja/releases/v2.7.1-670-420c7bcb75.json` and `v2.8.0-rrule.2.json`. Each holds identity fields only, with no paths: `release_version`, `source_revision`, `archive` sha256 and size, `image` config_digest and index_digest, `rollback` ref and image_id, rollback archive sha256 and size, `stage_issue` and `activate_issue`. The issues are `#1087`/`#1087` for the first, from the frozen record the test already uses, and `#1095`/`#1095` for rrule.2, from current `release.json`. Change `test_vikunja_cutover_change_set.py` to select the predecessor from those records, failing closed on no match or more than one. Take the current change set's issue from its manifests, and keep the frozen 0033 and 0034 checks. Add the fixture-tree tests listed in D-3.
- **T004 Tests (D-1, D-2, D-4).** In `test_vikunja_release_baseline.py` and `test_vikunja_release_acceptance.py`, with synthetic SQLite fixtures:
  - build with 10 and with 0;
  - a count mismatch and a lost ID, each writing no output;
  - CLI usage errors: missing, negative, non-integer and boolean counts;
  - an equal-schema zero-addition fixture matching `.2 → .3`, whose acceptance passes, and fails on an extra ID and on a lost predecessor ID;
  - the existing 10-ID acceptance, unchanged;
  - a zero-migration gate compare: `baseline.compare` on a snapshot equal to a baseline with `added_migration_ids: []` returns no code, and preflight on it passes.

  Red-first: show the 0-migration build and acceptance tests failing on the unmodified code.
- **T005 Runbook and doc sync (D-4, FR-007).** Check the architecture JSON and its markdown view, `INDEX` and the roadmap for entries describing the Vikunja release route's migration count. Update any that are affected; otherwise record that none was, in the commit message. Update the builder command near line 112 and the text at line 409. Say how N is established: the migration IDs added in the Vikunja source between the rollback and release source revisions, recorded in the packet and checked against the rehearsal's observed difference.
- **T006 Verify.** `.venv/bin/python -m pytest -q tests/deploy`, then the full suite `.venv/bin/python -m pytest -q --ignore=docs/archive -p no:cacheprovider`, then `.venv/bin/python tooling/scripts/validate_docs.py`.

## Definition of Done

All tests green, including the new 10 and 0 cases and every mismatch case; no applied manifest, committed baseline or `release.json` changed; only owned files changed.

## Reviewer Guidance

Claude Sonnet 5.5 reviews. Confirm no gate weakened (C-002), the predecessor selection cannot pass a wrong rollback identity, and the history records match the actual released records.

## Branch Strategy

Planning branch and final merge target: `fix/vikunja-migration-count`.

Implementation command: `spec-kitty agent action implement WP01 --agent codex --mission vikunja-migration-count-01M75P4M`
