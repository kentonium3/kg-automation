---
work_package_id: WP01
title: Release and archive compatibility
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- SC-001
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: 1263962949f8f6f34f5bc6bd5e7ea47e0e625108
created_at: '2026-11-09T19:33:53.804246+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: WP01 - Release and archive compatibility
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/vikunja_release/core.py
create_intent:
- tests/deploy/fixtures/vikunja_first_cutover_release.json
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- scripts/deploy/vikunja_release/core.py
- scripts/deploy/deploy-vikunja-release-stage.py
- tests/deploy/test_vikunja_release_core.py
- tests/deploy/test_vikunja_release_readiness.py
- tests/deploy/test_deploy_vikunja_release_stage.py
- tests/deploy/test_vikunja_stage_release_archive.py
- tests/deploy/fixtures/vikunja_first_cutover_release.json
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

*Release and archive compatibility — FR-001, FR-002, FR-003. Tracking: see #1095; historical route: see #1087.*

- Both gzip and historical tar records pass only with pinned bytes and verified identities.
- Conflicting imported tags are rejected before any load; historical no-container/no-Compose STAGE behaviour stays intact.
- Historical tests consume the frozen fixture, and shared CLI failures disclose no private log location.

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
- Dependencies: none. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- Owned source excludes the ingress helper because inspection showed no suffix or compression restriction there.
- Its test file is owned because its hardcoded historical destination and mutable release loader must change.
- Freeze the fixture once; later WPs consume it read-only.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T001 – Accept rrule versions and refuse malformed suffixes

- **Purpose**: Unblock the published release without broadening version acceptance arbitrarily.
- **Steps**:
  1. Extend _VERSION_RE at `scripts/deploy/vikunja_release/core.py:119` with an explicit -rrule.[0-9]+ alternative; retain existing plain and commit-suffixed releases.
  2. Exercise release loading at `scripts/deploy/vikunja_release/core.py:450` and allowlisted version emission at `scripts/deploy/vikunja_release/core.py:158`.
  3. Use readiness tests `tests/deploy/test_vikunja_release_readiness.py:44` and `tests/deploy/test_vikunja_release_readiness.py:96` to verify exact rrule readiness without editing readiness.py.
  4. Reject empty/non-numeric counters, extra suffix components, trailing garbage, wrong separators and arbitrary prereleases; include positive controls.
- **Files**: `scripts/deploy/vikunja_release/core.py`, `tests/deploy/test_vikunja_release_core.py`, `tests/deploy/test_vikunja_release_readiness.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not accept a version prefix through a partial regex match.

### Subtask T002 – Parse gzip after pinning the original archive bytes

- **Purpose**: Accept the published transport format while preserving the byte trust boundary.
- **Steps**:
  1. Change tar parsing in `scripts/deploy/vikunja_release/core.py:688` from r: to r:*; preserve one-open-handle ordering in `scripts/deploy/vikunja_release/core.py:708`.
  2. Check compressed-file size and SHA256 before parsing. Rewind that same descriptor; never hash decompressed or recompressed bytes.
  3. Extend archive builders at `tests/deploy/test_vikunja_release_core.py:554` and `tests/deploy/test_deploy_vikunja_release_stage.py:83` with gzip variants.
  4. Retain handle-swap protection at `tests/deploy/test_vikunja_release_core.py:775`; cover corrupt gzip, changed compressed bytes, size/hash mismatch and parser errors.
- **Files**: `scripts/deploy/vikunja_release/core.py`, `tests/deploy/test_vikunja_release_core.py`, `tests/deploy/test_deploy_vikunja_release_stage.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: No extraction, prescan or second path-open may precede or replace pin verification.

### Subtask T003 – Verify tagged Docker imports and preflight collisions

- **Purpose**: Prevent docker load from silently replacing unrelated references.
- **Steps**:
  1. Validate and return manifest RepoTags from `scripts/deploy/vikunja_release/core.py:708`; accept the historical untagged shape and validate every supplied reference.
  2. Use verified embedded references in `scripts/deploy/deploy-vikunja-release-stage.py:109` to refuse conflicting tags before docker load; inspection errors are failures, not absence.
  3. Extend `scripts/deploy/deploy-vikunja-release-stage.py:232` for Loaded image: <reference> as well as Loaded image ID: <digest>; resolve each reported identity and require the pinned config.
  4. Retain all image fact checks in `scripts/deploy/deploy-vikunja-release-stage.py:246` and the activation lock; rename misleading loaded-untagged diagnostics and docstrings.
  5. Test tagged/untagged success, mixed output, wrong identity/reference, empty output, conflicting RepoTags, inspection failure, reapply and retained rollback/local keeper refs.
  6. Do not add cleanup by image ID. Import may already have created tags when verification fails; report a stable diagnostic for reviewed tag-only cleanup.
- **Files**: `scripts/deploy/vikunja_release/core.py`, `scripts/deploy/deploy-vikunja-release-stage.py`, `tests/deploy/test_vikunja_release_core.py`, `tests/deploy/test_deploy_vikunja_release_stage.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Docker import itself mutates embedded tags; checking only after load is too late.

### Subtask T004 – Validate an optional baseline binding shape

- **Purpose**: Keep historical release records valid while enabling a bound repeat-cutover baseline.
- **Steps**:
  1. Extend RELEASE_SCHEMA at `scripts/deploy/vikunja_release/core.py:400` and `scripts/deploy/vikunja_release/core.py:450` for optional baseline with exactly path and sha256.
  2. Require a repository-relative contained path under services/vikunja/baselines/ and a lowercase 64-hex digest. Reject absolute paths, traversal, escaping resolutions and unknown nested keys.
  3. Keep all existing required fields and unknown-key refusal intact; do not make baseline mandatory for historical records.
  4. Test absent binding, valid binding, malformed object/types, uppercase digest, traversal and symlink escape. Leave baseline-byte hashing and parsing to WP03.
- **Files**: `scripts/deploy/vikunja_release/core.py`, `tests/deploy/test_vikunja_release_core.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Optional does not mean a present but malformed binding is accepted.

### Subtask T005 – Make shared CLI failures emit stable codes only

- **Purpose**: Close the public private-log location leak for ordinary and unexpected failures.
- **Steps**:
  0. Out-of-map edit, rationale: same contract as this change. Update the `private_log=` assertions in `tests/deploy/test_deploy_vikunja_release_activate.py` (about lines 725, 889, 1189 and 1269) to the new output, so the full suite stays green when this package lands. WP03 owns the rest of that file.
  1. Update `scripts/deploy/vikunja_release/core.py:267`: retain private detail capture but remove private_log and timestamped filenames from failure output.
  2. Revise public-path expectations at `tests/deploy/test_vikunja_release_core.py:339` and `tests/deploy/test_vikunja_release_core.py:359`.
  3. Seed distinctive private path, timestamp, hash and aggregate sentinels in Fail.detail_private and unexpected exception messages.
  4. Assert stdout/stderr and simulated forwarded excerpts contain only stable failure codes; private files still contain diagnostic evidence with restrictive modes.
  5. Cover private-log creation failure as well as absent private_root; avoid masking the original stable error.
- **Files**: `scripts/deploy/vikunja_release/core.py`, `tests/deploy/test_vikunja_release_core.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not rely on emit allowlisting: absolute paths and timestamps are currently allowed values.

### Subtask T006 – Freeze the first-cutover record and isolate historical tests

- **Purpose**: Prevent WP06 release changes from breaking valid historical route coverage.
- **Steps**:
  1. Create tests/deploy/fixtures/vikunja_first_cutover_release.json from the current committed record at `services/vikunja/release.json:3`; retain public release metadata only.
  2. Point historical core _record at `tests/deploy/test_vikunja_release_core.py:51`, stage Env at `tests/deploy/test_deploy_vikunja_release_stage.py:192` and ingress env at `tests/deploy/test_vikunja_stage_release_archive.py:165` to the frozen fixture.
  3. Fix stage resolver ambiguity at `tests/deploy/test_deploy_vikunja_release_stage.py:63`: historical assertions use explicit applied 0033 and the frozen record, not whichever queued manifest is newest.
  4. Update the historical ingress destination assertion at `tests/deploy/test_vikunja_stage_release_archive.py:662`; keep explicit current-record shape checks separate.
  5. Ingress source was checked: `scripts/vikunja/stage_release_archive.py:109` is extension-neutral and `scripts/vikunja/stage_release_archive.py:374` hashes opaque bytes. No stage_release_archive.py source change is needed or owned.
  6. Use explicit synthetic repeat-cutover records for new behaviour; keep readiness historical controls and add rrule controls without mutable-release assumptions.
- **Files**: `tests/deploy/fixtures/vikunja_first_cutover_release.json`, `tests/deploy/test_vikunja_release_core.py`, `tests/deploy/test_vikunja_release_readiness.py`, `tests/deploy/test_deploy_vikunja_release_stage.py`, `tests/deploy/test_vikunja_stage_release_archive.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not alter the existing archive-shape fixtures or historical applied manifests.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_release_core.py tests/deploy/test_vikunja_release_readiness.py tests/deploy/test_deploy_vikunja_release_stage.py tests/deploy/test_vikunja_stage_release_archive.py
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

- An imported tag collision can destroy a prior binding; preflight all validated RepoTags.
- Compressed-byte pinning can regress through a reopen; retain the same-handle race tests.
- Core schema changes affect all callers; preserve strict validation and absent-baseline compatibility.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Inspect both branches of run_cli and injected log-write failures.
- Confirm no image-ID deletion or unreviewed tag overwrite exists.
- Check historical manifest tests select applied 0033 explicitly and do not compare it with a later release.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP01 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP01 --to <status>`
- View history and status: `spec-kitty agent tasks status`
