---
work_package_id: WP06
title: STAGE change set
dependencies:
- WP05
requirement_refs:
- C-002
- FR-010
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: 6944abdac04a82b0c51da9ea34c442dacf2cb6a2
created_at: '2026-11-09T21:23:51.062042+00:00'
subtasks:
- T030
- T031
- T032
- T033
phase: WP06 - STAGE change set
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: services/vikunja/release.json
create_intent:
- services/vikunja/baselines/v2.7.1-670-420c7bcb75.json
- deploys/queued/vikunja-release-stage.yaml
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- services/vikunja/release.json
- services/vikunja/baselines/v2.7.1-670-420c7bcb75.json
- deploys/queued/vikunja-release-stage.yaml
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

Use the /spk-charter-profile-load skill to load the frontmatter profile and follow its guidance before implementing this prompt.

- **Profile**: implementer-ivan
- **Role**: implementer
- **Agent/tool**: claude
- **Model**: claude-opus-5-5

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

*STAGE change set — FR-010, SC-001, C-002. Tracking: see #1095; historical route: see #1087.*

- Committed baseline is data-free and bound by its exact bytes to the new release record.
- STAGE manifest verifies new release and retained previous image while inventory remains previous.
- PR1 excludes every WP07 path and all private evidence.

### Definition of Done

- Record the `Rebaseline:` line required by the charter on the PR1 merge commit or closing record.
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
- Dependencies: WP05. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- No private values or copy paths are supplied here; the Claude implementer already holds them.
- WP04 builder implementation and its synthetic tests must be reviewed before private execution.
- Creating STAGE metadata does not authorize bypassing Kent/program-lead merge authority.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T030 – Generate the qualified data-free baseline with Claude

- **Purpose**: Obtain real qualification facts without crossing the Codex private-data boundary.
- **Steps**:
  1. Claude Opus 5.5 is the sole implementer for this package; do not reassign it to Codex.
  2. Use the private qualification copies already held by the implementer; their locations, rows, counts, hashes of rows and timestamps must not enter this prompt or git.
  3. Run the reviewed WP04 builder on consolidated pre-upgrade and stable post-upgrade copies with the reviewed release rollback identity.
  4. Create services/vikunja/baselines/v2.7.1-670-420c7bcb75.json; permit only schema_version, previous_version, previous_image_config, pre_upgrade_migration_ids, added_migration_ids and schema_identity.
  5. Require sorted unique disjoint migration sets and the reviewed ten added IDs; require exact previous identity and versioned pre/target schema digests.
  6. Review the artifact against the data-free schema and compare deterministic regeneration privately; exclude all aggregate and path metadata.
  7. Ask the independent Claude Sonnet 5.5 reviewer to verify qualification and whitelist compliance without putting private evidence in review output.
- **Files**: `services/vikunja/baselines/v2.7.1-670-420c7bcb75.json`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not copy database rows, row hashes, private paths, counts or private values into the committed artifact.

### Subtask T031 – Bind the published release and exact rollback identities

- **Purpose**: Make release.json the reviewed trust root for the repeat cutover.
- **Steps**:
  1. Update identity groups in `services/vikunja/release.json:3`; retain the existing schema and stable service settings.
  2. Use i3-office2-packet.md section 13 held by the Claude implementer for release/source/archive/config/index/tag and rollback archive identities and both custody sources.
  3. Target v2.8.0-rrule.2 with previous v2.7.1-670-420c7bcb75; do not invent missing provenance or substitute packet claims for fresh ingress byte verification.
  4. Preserve office2.local/vikunja:active and service/Compose settings; rollback ref/image must name the exact previous deployed image.
  5. Add baseline.path and lowercase SHA256 of the exact committed baseline bytes; load_release and load_bound must validate together.
  6. Do not touch the frozen first-cutover fixture or old successful marker. New release marker absence is an operational precondition.
  7. Keep private qualification evidence out of release.json; custody fields required by the existing public schema use only the reviewed release-artifact metadata.
- **Files**: `services/vikunja/release.json`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: No private copy location or production aggregate belongs in a release record.

### Subtask T032 – Create the queued STAGE manifest

- **Purpose**: Deliver only the inert staging action in PR1.
- **Steps**:
  1. Create deploys/queued/vikunja-release-stage.yaml; use historical manifest structure at `deploys/applied/0033-vikunja-release-stage.yaml:1` without editing that applied record.
  2. Set schema_version v1; name vikunja-release-stage; issue identifier for see #1095; tier 2; entrypoint scripts/deploy/deploy-vikunja-release-stage.py.
  3. Set audited_surface true and expected_baselines [docker-images.txt]; pre verification runs the corresponding helper --dry-run.
  4. Postchecks exactly inspect the new local release tag/config and retained previous ref/image from the new release record.
  5. Set created_at to 2026-11-09T05:00:00Z and created_by to the actual Claude implementer identity; notes are nonempty and at most 2000 characters.
  6. Use issue only, not mission_slug as well. Leave apply_mode, applied_at and rebaseline absent for the deployer.
  7. Notes state running service remains untouched, tagged-import failure cleanup is tag-specific, and no new container or ACTIVATE action occurs here.
- **Files**: `deploys/queued/vikunja-release-stage.yaml`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A manifest is operational on merge; do not include an ACTIVATE manifest or inventory promotion.

### Subtask T033 – Validate the STAGE phase and PR1 boundary

- **Purpose**: Prove PR1 is coherent before it can be merged.
- **Steps**:
  1. Run the full non-live suite and phase-aware tests against the actual STAGE metadata.
  2. Run core baseline, stage, rollback and acceptance tests with the frozen historical fixture unchanged.
  3. Validate the new manifest using the existing manifest schema tests and phase assertions; postchecks must equal release-record identities.
  4. Check the PR1 diff excludes deploys/queued/vikunja-release-activate.yaml and both WP07 inventory paths.
  5. Verify no Compose, historical applied manifests, private evidence or database files enter the change set.
  6. Record reviewed baseline-byte binding and local test outcomes without private values; hand off for PR1 review, not host activation.
  7. Do not open PR2 until STAGE has applied successfully and authorized preflight reports PREFLIGHT_OK within the outage budget.
- **Files**: `services/vikunja/release.json`, `services/vikunja/baselines/v2.7.1-670-420c7bcb75.json`, `deploys/queued/vikunja-release-stage.yaml`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: If real qualification inputs are absent or inconsistent, stop with the missing-input category rather than inventing values.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py tests/deploy/test_vikunja_release_core.py tests/deploy/test_deploy_vikunja_release_stage.py tests/deploy/test_vikunja_release_baseline.py tests/deploy/test_vikunja_release_acceptance.py
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

- The baseline cannot be supplied by Codex; keep execution assigned to Claude Opus 5.5.
- Packet identities are provenance inputs, not evidence that a fresh download was verified.
- An accidentally included ACTIVATE manifest would cut over on merge; inspect exact PR1 paths.

## Review Guidance

- Baseline review inputs, none of them private: the committed JSON, `build_release_baseline.py`, and the migration files of the published tree. Pass: only the contract's fields are present, the ten added IDs match the published tree's new migrations, `release.json` binds the exact bytes, and the rollback identity matches. Do not read private copies. Preflight on Office2 is the real-data proof.
- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Claude Opus 5.5; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Review is by Claude Sonnet 5.5, independent of Claude Opus 5.5 implementation.
- Verify deterministic baseline output has no data-derived aggregate or private metadata.
- Confirm actual STAGE tree passes while inventory still names the previous deployed release.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP06 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP06 --to <status>`
- View history and status: `spec-kitty agent tasks status`
