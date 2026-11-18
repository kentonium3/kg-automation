---
work_package_id: WP07
title: ACTIVATE change set
dependencies:
- WP06
requirement_refs:
- C-006
- C-007
- FR-011
- FR-014
- SC-005
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: 693e6473f76013207b608306e6d9d7622f894028
created_at: '2026-11-09T21:38:51.176879+00:00'
subtasks:
- T034
- T035
- T036
phase: WP07 - ACTIVATE change set
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: deploys/queued/vikunja-release-activate.yaml
create_intent:
- deploys/queued/vikunja-release-activate.yaml
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- deploys/queued/vikunja-release-activate.yaml
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
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

*ACTIVATE change set — FR-011, SC-002, SC-003, SC-005, C-001, C-002, C-006, C-007. Tracking: see #1095; historical route: see #1087.*

- ACTIVATE and inventory share exact current identities; Compose retains active/never.
- PR2 has exactly the three owned paths and opens only after applied STAGE and passing preflight.
- Review, merge authority and post-cutover acceptance remain independent and explicit.

### Definition of Done

- Record the `Rebaseline:` line required by the charter on the PR2 merge commit or closing record.
- Done means prepared, tested in the ACTIVATE tree state and reviewed inside the mission. It does not wait for STAGE to apply; opening PR2 does (plan D5).
- Every listed subtask is complete within this packages owned files, except the steps marked as PR-assembly steps, which run under the quickstart sequence after this WP is done.
- Required focused tests pass, and the full non-live suite is green before handoff.
- No production rows, aggregate values, private copy locations or snapshot evidence enter committed output.
- Claude Sonnet 5.5 has independent review evidence and significant findings are fixed.
- Report commands and results honestly; synthetic tests are not host acceptance.

## Context & Constraints

- Mission: kitty-specs/vikunja-repeat-cutover-01M6YRJG/spec.md; design: plan.md; rationale: research.md.
- Contract: kitty-specs/vikunja-repeat-cutover-01M6YRJG/contracts/baseline-and-gate.md; state: data-model.md; operator order: quickstart.md.
- The concrete steps below are the implementation handoff; requirement IDs refer to this mission.
- Source anchors were verified on the drafting tree; prerequisite edits may shift line numbers, so use the named symbols.
- Dependencies: WP06. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- No new tests are owned here: phase-aware tests ship in WP05 before this data-only change.
- This packages focused verification executes existing tests against the real ACTIVATE metadata.
- Do not add mission artifacts to the PR2 code path set; mission workflow records follow their own authoritative process.
- ACTIVATE metadata is prepared under this package, while production acceptance remains an operator decision.
- No production row, count, snapshot path or private value belongs in manifest notes or inventory.
- Any fail-closed gate result preserves the snapshot recovery route established in WP02/WP03.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T034 – Create the queued ACTIVATE manifest

- **Purpose**: Separate the production cutover decision from inert staging.
- **Steps**:
  1. Create deploys/queued/vikunja-release-activate.yaml; use the validated schema structure at `deploys/applied/0034-vikunja-release-activate.yaml:1` without modifying history.
  2. Set schema_version v1, name vikunja-release-activate, issue identifier for see #1095, tier 2 and entrypoint scripts/deploy/deploy-vikunja-release-activate.py.
  3. Set audited_surface true and expected_baselines [docker-images.txt]; pre verification invokes the ACTIVATE helper --dry-run.
  4. Derive exact postchecks using the format in `tests/deploy/test_vikunja_cutover_change_set.py:150`: container config ID and exact API version from the current release record.
  5. Set created_at to 2026-11-09T05:00:00Z, actual creator identity and concise nonempty notes at most 2000 characters; omit apply_mode/applied_at/rebaseline.
  6. Use issue only, not mission_slug too; machine issue identity belongs to see #1095.
  7. Notes cover snapshot gate before retag, 300-second outage bound, no blind retry, cleanup-failure reporting and crash-after-retag risk.
  8. State interrupted started/stopped recovery versus snapshotted rollback prepare/finish; preserve old successful marker and keep private evidence out of commands/notes.
  9. At PR assembly, after this WP is done and outside its completion check: open PR2 only after applied STAGE and passing authorized preflight; merge by Kent, the program lead or the core worker under Kent's delegation.
- **Files**: `deploys/queued/vikunja-release-activate.yaml`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: ACTIVATE executes on merge; local green tests alone do not satisfy the PR2 opening condition.

### Subtask T035 – Promote machine inventory and narrative together

- **Purpose**: Describe the deployed target only in the ACTIVATE change set.
- **Steps**:
  1. Update only the Vikunja entry and relevant provenance in `docs/design/architecture/data/service-inventory.json:7`.
  2. Keep image selection office2.local/vikunja:active and pull_policy never; update notes for target release/source/archive/config and exact retained rollback identity.
  3. Preserve unrelated services and existing provenance history; use see #1095 for new issue citations.
  4. Update the Vikunja summary row at `docs/design/architecture/service-inventory.md:18` and image-selection detail at `docs/design/architecture/service-inventory.md:202`.
  5. Keep JSON authoritative and narrative consistent with current release.json; distinguish prior first-cutover history clearly.
  6. No Compose, port, unit, runtime-user or service-data location changes are part of this package.
  7. Do not promote inventory during STAGE or claim verified production outcomes before actual application.
- **Files**: `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Restrict inventory edits to Vikunja and necessary top-level change provenance.

### Subtask T036 – Validate ACTIVATE and prove the exact PR2 diff

- **Purpose**: Ensure the second PR contains only the authorized activation surfaces.
- **Steps**:
  1. Run phase-aware tests against the actual ACTIVATE state; repeat full non-live suite and documentation validation.
  2. Use WP05 temporary-tree cases as negative controls for wrong-release ACTIVATE and mismatched inventory.
  3. At PR assembly, after this WP is done and outside its completion check: inspect the actual PR2 base-to-head path list and require set equality with this packages three owned paths.
  4. Expected set: deploys/queued/vikunja-release-activate.yaml; docs/design/architecture/data/service-inventory.json; docs/design/architecture/service-inventory.md.
  5. Do not substitute CUTOVER_PATHS constants or existence checks for the actual diff; reject extra and missing paths.
  6. At PR assembly, after this WP is done and outside its completion check: confirm PR1 code/tests/release/baseline/STAGE are already present, rather than copying them into PR2.
  7. At PR assembly, after this WP is done and outside its completion check: require evidence STAGE applied and preflight passed; report stable codes/timing category without private aggregates or paths.
  8. At PR assembly, after this WP is done and outside its completion check: after application, keep writes closed through reviewed verifier and browser acceptance; Kent decides ACCEPT or ROLLBACK and automation resume.
- **Files**: `deploys/queued/vikunja-release-activate.yaml`, `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: If the exact diff differs, correct PR assembly rather than widening this packages owned set.

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

- Premature PR2 creation can trigger a cutover before qualification; require applied STAGE and preflight evidence.
- Inventory drift can conceal wrong image identity; compare both views with release.json.
- A constant path set is not diff evidence; inspect the actual PR2 range during assembly.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Reviewer is Claude Sonnet 5.5; verify independence from Codex implementation.
- Require exact three-path diff evidence, unchanged Compose and preserved historical manifests.
- Check gating/rollback evidence from earlier WPs and operator prerequisites before recommending merge.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP07 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP07 --to <status>`
- View history and status: `spec-kitty agent tasks status`
