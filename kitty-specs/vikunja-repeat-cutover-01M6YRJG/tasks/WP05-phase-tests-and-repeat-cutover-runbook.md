---
work_package_id: WP05
title: Phase-aware change-set tests and repeat-cutover runbook
dependencies:
- WP04
requirement_refs:
- C-001
- C-003
- C-004
- FR-010
- FR-012
- FR-014
- NFR-004
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: fa8f7a8a166ee296d139a482328750e296f48f6b
created_at: '2026-11-09T21:01:15.075046+00:00'
subtasks:
- T025
- T026
- T027
- T028
- T029
phase: WP05 - Phase-aware change-set tests and repeat-cutover runbook
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: tests/deploy/test_vikunja_cutover_change_set.py
create_intent: []
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- tests/deploy/test_vikunja_cutover_change_set.py
- tests/deploy/test_vikunja_release_consistency.py
- docs/runbooks/vikunja-release-cutover.md
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

*Phase-aware change-set tests and repeat-cutover runbook — FR-012, NFR-004, C-001, C-003, C-004. Tracking: see #1095; historical route: see #1087.*

- Focused tests pass on the current tree and synthetic STAGE/ACTIVATE trees.
- Invalid queued ACTIVATE always fails; inventory promotion is required only in ACTIVATE.
- Runbook documents the new callers, recovery distinction, safe tagged cleanup and complete candidate packaging.

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
- Dependencies: WP04. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- Read the prior runbook as history, not as authority for new first-install assumptions.
- Exact public manifest schema issue fields are machine identifiers; narrative citations use the requested see form.
- This package owns tests/runbook only; WP06 owns release/STAGE and WP07 owns ACTIVATE/inventory.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T025 – Make route tests explicitly phase-aware

- **Purpose**: Keep tests valid before STAGE, during STAGE and during ACTIVATE.
- **Steps**:
  0. Classify the tree: ACTIVATE phase when a queued or applied ACTIVATE manifest names the current release (including STAGE applied with ACTIVATE queued); STAGE phase when `release.json` carries a release with no such manifest; historical otherwise, identified only by manifest 0034.
  1. Refactor mutable release loading/resolution at `tests/deploy/test_vikunja_cutover_change_set.py:68` and `tests/deploy/test_vikunja_cutover_change_set.py:72` into root/manifest-parameterized helpers.
  2. Identify historical ACTIVATE explicitly as 0034-vikunja-release-activate.yaml, its historical issue identity and exact frozen-record postchecks; never select history merely because it sorts last.
  3. Keep the historical Compose reversal tests starting at `tests/deploy/test_vikunja_cutover_change_set.py:104` explicitly historical and keep applied 0033/0034 unchanged.
  4. Current tree: historical manifests and inventory must still pass against the frozen first-cutover record.
  5. STAGE tree: require current release and baseline binding plus current STAGE identities, while inventory describes the rollback/previous deployed release.
  6. ACTIVATE tree: require a current-release queued or applied ACTIVATE with exact container/version postchecks and promoted inventory.
  7. An invalid queued ACTIVATE must fail in place: no fallback to valid applied history, including malformed YAML, wrong release, missing checks or wrong audit fields.
  8. Reuse `tests/deploy/test_vikunja_cutover_change_set.py:150` and replace repeat CUTOVER_PATHS with WP07 three paths; retain historical path set separately.
  9. Add temporary-tree positive and negative cases for all three phases, queued/applied forms, stale manifests, missing binding and premature inventory promotion.
- **Files**: `tests/deploy/test_vikunja_cutover_change_set.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Ship these tests before WP06 mutates the release record; they must pass on the current tree.

### Subtask T026 – Derive current rollback-version expectations

- **Purpose**: Keep consistency checks reusable across cutovers.
- **Steps**:
  1. Change `tests/deploy/test_vikunja_release_consistency.py:76` to derive the expected version from the current reviewed rollback ref.
  2. Compare both ACTIVATE and rollback helpers to that independent expected value; normalize an unprefixed tag to v exactly as specified.
  3. Retain a separate frozen historical v2.4.0 case and add a synthetic rrule/commit-suffixed rollback ref case.
  4. Preserve shared activation.lock and systemd/Compose argv consistency checks; no Compose edit is allowed.
- **Files**: `tests/deploy/test_vikunja_release_consistency.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not use one helper as the only oracle for the other helper.

### Subtask T027 – Document repeat-cutover operation and recovery

- **Purpose**: Remove first-cutover assumptions from executable current instructions.
- **Steps**:
  1. Update introduction/custody/roots and candidate sections around `docs/runbooks/vikunja-release-cutover.md:106` and the first-cutover prerequisites.
  2. Clearly label retained first-cutover conversions and applied manifests as historical; no completed repeat conversion or fixed migration-count requirement may rerun.
  3. Document previous release retained, existing active/Compose/roots allowed, only new custody/candidate/snapshot destinations create-only and only the new release marker required absent.
  4. Sequence PR1, STAGE applied, notification disposition, Restic backup at most 24 hours old, paused Felix crons and felix-vikunja-sync.timer, preflight pass/timing, one-line lead handoff, PR2 and acceptance with writes closed. Proceed if only Kent can be notified, or mail is off and nothing reacts; ask Kent if others could be notified or an automation cannot be paused.
  5. Use WP04 exact CLI interfaces; explain inconclusive unstable preflight and require PREFLIGHT_OK and fitting consolidation/gate timing before any outage. Require the acceptance verifier with writes closed before the disposable write probe.
  6. Document private gate/receipt placement in operational terms and stable codes; no private snapshot locations or aggregate values in committed examples.
  7. Distinguish failed or unfinished started/stopped marker recovery from snapshotted gate failure: the latter uses rollback --prepare/privileged restore/--finish.
  8. Require exact pre_version/hash and conservative write-loss acknowledgement. Kent controls privileged restore, browser acceptance and ACCEPT/ROLLBACK.
  9. Document tagged-import cleanup: inspect the specific imported tag identity, remove only that tag when authorized, retain local release/rollback keeper refs and containers; never blindly remove by image ID.
  10. Preserve residual crash-after-retag risk, cleanup-failure reporting and no-blind-retry instructions.
- **Files**: `docs/runbooks/vikunja-release-cutover.md`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Verified runbook edit anchors: docs/runbooks/vikunja-release-cutover.md:106 (preconditions), :128 (candidate), :211 (ingress), :289 (STAGE assembly), :394 (STAGE verify), :413 (host readiness/preflight), :448 (ACTIVATE assembly), :484 (gate/output), :543 (acceptance), :793 (crash risk), :827 (rollback), :991 (pre-snapshot recovery), :1115 (cancel/retry), :1185 (tagged cleanup), :1213 (codes). Keep examples value-free for private evidence; public identities derive from release.json.

### Subtask T028 – Package every repeat-cutover dependency in the candidate

- **Purpose**: Ensure offline candidate execution has the same code and baseline as reviewed.
- **Steps**:
  1. Update the candidate archive command at docs/runbooks/vikunja-release-cutover.md:157 to include baseline.py, the bound baseline artifact, preflight, acceptance verifier and baseline builder alongside existing package files. The existing shared-package inclusion already covers baseline.py; verify this rather than duplicating it.
  2. Include any newly required package/module files and the release record; preserve create-only candidate handling.
  3. Update obsolete five-path PR descriptions: PR1 carries everything except WP07 paths; PR2 has exactly its manifest and two inventory paths.
  4. Document exact diff/path-set verification during PR assembly; constants/existence tests alone do not prove PR contents.
  5. Use phase-test temporary trees or focused assertions to check required candidate inclusions without running host commands.
- **Files**: `docs/runbooks/vikunja-release-cutover.md`, `tests/deploy/test_vikunja_cutover_change_set.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Candidate packaging must not include private copies or their receipts.

### Subtask T029 – Validate docs and the complete phase test matrix

- **Purpose**: Make the revised instructions and phases reviewable before STAGE metadata changes.
- **Steps**:
  0. FR-014: check `docs/INDEX.md` and roadmap status for affected entries, update any you find (out-of-map if needed, with a one-line rationale), and record in the WP history if none was affected.
  1. Run focused phase and consistency tests on the untouched current release tree; temporary-tree cases represent STAGE and ACTIVATE.
  2. Run python3 tooling/scripts/validate_docs.py and resolve issues within the owned runbook.
  3. Run the full non-live suite; preserve still-valid historical first-cutover tests.
  4. Check all links/commands and issue citations; use only see #1095 or see #1087 in authored prose and no mentions.
  5. Report current/STAGE/ACTIVATE matrix evidence and doc validation separately from future host verification.
- **Files**: `tests/deploy/test_vikunja_cutover_change_set.py`, `tests/deploy/test_vikunja_release_consistency.py`, `docs/runbooks/vikunja-release-cutover.md`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not change unrelated documentation or historical applied records to make validation pass.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py tests/deploy/test_vikunja_release_consistency.py
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

- Latest-applied fallback can silently validate history; current queued invalidity is an unconditional failure.
- Premature inventory promotion misstates running production; gate it on ACTIVATE phase.
- Historical conversion commands can be mistaken for current steps; label and separate them clearly.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Inspect temporary-tree negative cases, especially invalid queued ACTIVATE with valid history present.
- Confirm no Compose modification and unchanged applied 0033/0034.
- Review candidate inclusions and recovery instructions together with the code interfaces.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP05 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP05 --to <status>`
- View history and status: `spec-kitty agent tasks status`
