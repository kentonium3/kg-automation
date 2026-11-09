---
work_package_id: WP02
title: Rollback correctness
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
- FR-006
- FR-007
- SC-003
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: f7af1e8359945afb88f29ddbfa8019be36aef4ca
created_at: '2026-11-09T19:51:41.078008+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
phase: WP02 - Rollback correctness
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/vikunja_release/dbsafety.py
create_intent: []
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- scripts/deploy/vikunja_release/dbsafety.py
- scripts/vikunja/rollback_release.py
- tests/deploy/test_vikunja_release_db.py
- tests/deploy/test_vikunja_rollback.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

Use the /spk-charter-profile-load skill to load the frontmatter profile and follow its guidance before implementing this prompt.

- **Profile**: implementer-ivan
- **Role**: implementer
- **Agent/tool**: codex
- **Model**: gpt-6.1-sol

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- Check the review_ref field in the status event log through the authoritative task-status command.
- Address all returned feedback before completion; it is part of this packages implementation scope.
- Record progress through the workflow history command, never by editing prompt status or history.

---

## Review Feedback

*If this WP was returned from review, its feedback reference appears in the status event log.*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks. Use language identifiers on fenced code blocks.

---

## Objectives & Success Criteria

*Rollback correctness — FR-004, FR-005, FR-006, FR-007. Tracking: see #1095; historical route: see #1087.*

- A correct RRULE snapshot restore succeeds and wrong hash or exact version fails before image mutation.
- Both crash windows recover through the previous image running under both locks.
- Repetition edits count as writes; subscription backfill stays included and privately labelled.

### Definition of Done

- Every listed subtask is complete within this packages owned files.
- Required focused tests pass, and the full non-live suite is green before handoff.
- No production rows, aggregate values, private copy locations or snapshot evidence enter committed output.
- Claude Sonnet 5.5 has independent review evidence and significant findings are fixed.
- Report commands and results honestly; synthetic tests are not host acceptance.

## Context & Constraints

- Mission: kitty-specs/vikunja-repeat-cutover-01M6YRJG/spec.md; design: plan.md; rationale: research.md.
- Contract: kitty-specs/vikunja-repeat-cutover-01M6YRJG/contracts/baseline-and-gate.md; state: data-model.md; operator order: quickstart.md.
- The concrete steps below are the implementation handoff; requirement IDs refer to this mission.
- Source anchors were verified on the drafting tree; prerequisite edits may shift line numbers, so use the named symbols.
- Dependencies: WP01. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- Consume WP01 fixture read-only; no edits to its JSON or other WPs tests.
- Recovery does not broaden rollback privilege: Kent retains privileged restore and acknowledgement.
- The old successful marker is history and must remain untouched.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T007 – Replace the obsolete rollback schema criterion

- **Purpose**: Accept a proven restore of an already-RRULE database.
- **Steps**:
  1. Change `scripts/deploy/vikunja_release/dbsafety.py:755`: retain no-container, active-tag, sidecar and restored-hash checks.
  2. Require restored hash == recorded snapshot SHA and snapshot pre_version == the exact rollback version supplied by the caller.
  3. Remove the blanket is_migrated refusal in that guard; reverse `tests/deploy/test_vikunja_release_db.py:564` expectations for matching RRULE restores.
  4. Add missing/wrong pre_version failures paired with a passing same-hash RRULE restore; prove no tag/start follows a refusal.
- **Files**: `scripts/deploy/vikunja_release/dbsafety.py`, `tests/deploy/test_vikunja_release_db.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A schema column alone cannot identify whether a snapshot is the qualified previous release.

### Subtask T008 – Require exact pre_version before tag or start

- **Purpose**: Remove broad version fallback from rollback safety.
- **Steps**:
  1. Remove _FALLBACK_VERSION_RE at `scripts/vikunja/rollback_release.py:130` and fallback logic in `scripts/vikunja/rollback_release.py:613`.
  2. Validate pre_version before `scripts/vikunja/rollback_release.py:696` can tag or start; pass the reviewed version through finish and rollback_guard.
  3. Derive the expected rollback version consistently from the reviewed rollback ref; do not introduce an unowned release schema field.
  4. Replace the fallback expectation at `tests/deploy/test_vikunja_rollback.py:720` with absent/wrong refusal and exact-version readiness cases.
  5. Test both v-prefixed and unprefixed reviewed ref tags according to the existing rollback_version helper.
- **Files**: `scripts/vikunja/rollback_release.py`, `tests/deploy/test_vikunja_rollback.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A readiness refusal after starting the wrong image is too late.

### Subtask T009 – Recover unfinished pre-snapshot markers under both locks

- **Purpose**: Provide the supported route after a process dies before snapshot phase persistence.
- **Steps**:
  1. Extend `scripts/vikunja/rollback_release.py:795` and `scripts/vikunja/rollback_release.py:827` for failed pre-snapshot markers and unfinished started/stopped markers (outcome=None).
  2. Validate release version, config, rollback image and exact pre-version from marker versus current record; do not require a snapshot or inspect schema to decide eligibility.
  3. Acquire both existing deployer and activation locks before mutable state checks and hold through recovery; main at scripts/vikunja/rollback_release.py:918 already owns this lock order.
  4. Allow active absent or resolving to the previous image only; refuse new/foreign image, unexpected containers and malformed/foreign markers.
  5. Refuse snapshotted and all later phases even if the snapshot exists or the marker outcome is unfinished.
  6. Extend Recover at `tests/deploy/test_vikunja_rollback.py:1004` and write_marker at `tests/deploy/test_vikunja_rollback.py:1049`; reverse unfinished stopped refusal.
  7. Simulate death during snapshot and between Compose down and active-tag removal; drive recovery through exact previous-version readiness and previous image running.
- **Files**: `scripts/vikunja/rollback_release.py`, `tests/deploy/test_vikunja_rollback.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A partial snapshot is not authorization for a retagged/new-image recovery.

### Subtask T010 – Count repeats edits and label backfill privately

- **Purpose**: Keep the acknowledged write-loss estimate conservative.
- **Steps**:
  1. Remove repeats from MIGRATION_OWNED_COLUMNS at `scripts/vikunja/rollback_release.py:338` while retaining exclusions for completed legacy conversion columns.
  2. Extend private evidence from `scripts/vikunja/rollback_release.py:394` and prepare to label subscription backfill as included.
  3. Never subtract subscription-backfill changes from acknowledged writes; preserve existing net-row accounting semantics.
  4. Use _with at `tests/deploy/test_vikunja_rollback.py:878` for existing-rule edits and subscription additions, with unchanged controls.
- **Files**: `scripts/vikunja/rollback_release.py`, `tests/deploy/test_vikunja_rollback.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: The receipt describes a conservative net difference, not an exact event log.

### Subtask T011 – Remove private DB safety reporting

- **Purpose**: Prevent private snapshot evidence entering retained deploy output.
- **Steps**:
  1. Remove private-copy/receipt record_installed emissions in snapshot at `scripts/deploy/vikunja_release/dbsafety.py:544`; preserve actual private writes and durability.
  2. Review all dbsafety detail output for paths, hashes, counts and timestamps derived from private copies.
  3. Keep private rollback evidence available to the authorized operator, without forwarding it into installed reports or deploy detail lines.
  4. Seed sentinel locations, digest, count and timestamp values; assert public stdout/stderr and captured installed reports exclude them.
  5. Cover ordinary exceptions, unexpected failures and cleanup branches, including a private-log-write failure.
- **Files**: `scripts/deploy/vikunja_release/dbsafety.py`, `tests/deploy/test_vikunja_release_db.py`, `tests/deploy/test_vikunja_rollback.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Deleting an installed-report emission must not delete or weaken snapshot persistence.

### Subtask T012 – Adopt the frozen fixture and reverse obsolete expectations

- **Purpose**: Keep historical coverage independent of the mutable STAGE record.
- **Steps**:
  1. Point rollback module fixture loading and Scenario at `tests/deploy/test_vikunja_rollback.py:204` to WP01 frozen first-cutover release data.
  2. Reuse DB fixture builders `tests/deploy/test_vikunja_release_db.py:70` and `tests/deploy/test_vikunja_release_db.py:564` with synthetic rows only.
  3. Reverse schema-based rollback rejection, old fallback acceptance, unfinished-marker rejection and repeats/WAL schema rejection where obsolete.
  4. Keep sidecar, hash, Docker-state, lock-contention and post-snapshot phase refusal coverage.
  5. Add explicit repeat-cutover records so exact pre-version behaviour is tested against both historical and next-release refs.
- **Files**: `tests/deploy/test_vikunja_release_db.py`, `tests/deploy/test_vikunja_rollback.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A negative test needs a matching positive control; do not simply delete old safety assertions.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_release_db.py tests/deploy/test_vikunja_rollback.py
```

- Before review run the full non-live suite; for documentation changes also run the validator:

```bash
python3 -m pytest -q --ignore=docs/archive
python3 tooling/scripts/validate_docs.py
```

- Runtime matrix: .github/workflows/test-ci.yml runs Python 3.12 and 3.13 with make test.
- No separate compiler/typecheck command is configured for these Python surfaces in that CI workflow; pytest does not imply static typecheck coverage.
- Do not introduce a new typechecker dependency for this mission. If required CI checks change, run and report the configured checks.
- Keep tests in owned files; data-only WPs execute the predecessor-owned phase tests without editing them.

## Risks & Mitigations

- Starting an image before version validation risks irreversible incompatibility; assert call order.
- An unfinished marker is admissible only in started/stopped, with exact identity checks and both locks.
- Gate failure after snapshot must continue to require snapshot restore, handled in WP03 integration tests.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Review through-running crash tests, not only eligibility helper tests.
- Check wrong/missing pre_version produces zero tag and Compose up calls.
- Confirm subscription backfill is labelled and never deducted.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP02 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP02 --to <status>`
- View history and status: `spec-kitty agent tasks status`
