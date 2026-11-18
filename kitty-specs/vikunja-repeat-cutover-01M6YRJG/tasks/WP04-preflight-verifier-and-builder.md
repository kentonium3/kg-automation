---
work_package_id: WP04
title: Preflight, acceptance verifier, baseline builder
dependencies:
- WP03
requirement_refs:
- FR-009
- FR-010
- FR-013
- SC-004
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: 181ca5bba947a330e22b81a30991e85066b885d3
created_at: '2026-11-09T20:36:53.759585+00:00'
subtasks:
- T020
- T021
- T022
- T023
- T024
phase: WP04 - Preflight, acceptance verifier, baseline builder
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/vikunja/preflight_release_baseline.py
create_intent:
- scripts/vikunja/preflight_release_baseline.py
- scripts/vikunja/verify_release_upgrade.py
- scripts/vikunja/build_release_baseline.py
- tests/deploy/test_vikunja_release_preflight.py
- tests/deploy/test_vikunja_release_acceptance.py
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- scripts/vikunja/preflight_release_baseline.py
- scripts/vikunja/verify_release_upgrade.py
- scripts/vikunja/build_release_baseline.py
- tests/deploy/test_vikunja_release_preflight.py
- tests/deploy/test_vikunja_release_acceptance.py
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

*Preflight, acceptance verifier, baseline builder — FR-009, FR-013, SC-004. Tracking: see #1095; historical route: see #1087.*

- Preflight removes temporary copies on every exit and labels instability inconclusive.
- Acceptance fails every seeded loss while writing aggregates only to restricted private evidence.
- Builder emits exactly the allowed data-free schema, using shared WP03 logic.

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
- Dependencies: WP03. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- Use the builder tests in the acceptance test module; there is no additional owned test file.
- The current unrelated cutover_verify.py is not an upgrade verifier and stays outside ownership.
- Production runtime feasibility remains an operator preflight result, not a claim from local unit tests.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T020 – Implement stable-copy preflight

- **Purpose**: Find qualification failures before an outage without treating preflight as activation evidence.
- **Steps**:
  0. Enforce the contract's 25-second comparison limit and 90-second total budget, both through `PREFLIGHT_OVER_BUDGET`, with a simulated-clock test.
  1. Create scripts/vikunja/preflight_release_baseline.py; CLI takes the release-record path, resolves the bound baseline, and calls WP03 compare.
  2. Use a private working directory beneath the configured service failures root; copy live database/WAL by filesystem reads only, without opening live SQLite.
  3. Apply runbook B3 double-copy/hash stability logic: at most five rounds, retain only an agreeing database/WAL set, then consolidate the private copy. Compare copies from two complete rounds; reject a pair if membership or any corresponding file hash changed.
  4. Call dbsafety.snapshot(data_dir, snap_root, clock=..., pre_version=..., running_image_id=..., deadline=...) at scripts/deploy/vikunja_release/dbsafety.py:544. Set data_dir to the agreeing private copy containing the expected DB basename, and snap_root to a disposable 0700 parent, never release roots.snapshots. Compare its returned db_path; keep snapshot_dir private. Account for WAL appearance/disappearance; never use immutable=1 on live WAL data.
  5. Remove the entire disposable parent and all private input/output copies on every exit, including mismatch, unexpected exception, interruption and consolidation failure. Use try/finally cleanup without masking a failure or leaking its path.
  6. Exit zero prints PREFLIGHT_OK and elapsed consolidation/gate seconds; nonzero prints one stable code only. Five unstable rounds produce PREFLIGHT_COPY_UNSTABLE.
  7. No path, digest, aggregate or private value appears in output; elapsed seconds are the explicit preflight-only contract exception.
  8. Never write a receipt ACTIVATE could consume; a preflight pass does not replace the write-boundary gate.
- **Files**: `scripts/vikunja/preflight_release_baseline.py`, `tests/deploy/test_vikunja_release_preflight.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: An unstable copy is inconclusive and blocks cutover; it is not a baseline mismatch.

### Subtask T021 – Implement acceptance against the durable gate receipt

- **Purpose**: Give Kent a reliable post-upgrade decision with writes still closed.
- **Steps**:
  1. Create scripts/vikunja/verify_release_upgrade.py; CLI takes a private snapshot directory and a stable private post-upgrade copy.
  2. Resolve repository services/vikunja/release.json through an injectable default without adding a third positional argument; call load_bound for the qualified target and exact added IDs. Validate baseline.json against snapshot.json and recomputed snapshot SHA, baseline SHA, release/config and rollback identity. Use WP03 functions; do not expect target-schema facts in the private receipt.
  3. Require all pre IDs remain and exactly the ten reviewed additions are present; require target schema identity.
  4. Require task and repeat counts/hash to equal the receipt and integrity_check to return ok.
  5. Require expected task subscription total, no eligible pair missing, unchanged duplicate excess and retained existing subscription keys/muted choices.
  6. Write aggregate results only into restricted private evidence beneath the snapshot directory using durable/exclusive writing; emit per-check pass/fail codes only.
  7. Run before the disposable write probe; return nonzero for any failure or inability to compute a check.
- **Files**: `scripts/vikunja/verify_release_upgrade.py`, `tests/deploy/test_vikunja_release_acceptance.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: A matching total cannot substitute for preservation and eligible-pair checks.

### Subtask T022 – Build only the committed data-free baseline

- **Purpose**: Provide Claude a reviewed way to derive qualification without exposing rows.
- **Steps**:
  1. Create scripts/vikunja/build_release_baseline.py; CLI accepts consolidated pre-upgrade and post-upgrade copies, a release-record path for reviewed rollback identity, and a new output path.
  2. Call the WP03 build function to obtain previous_version, previous_image_config, sorted unique pre IDs, added IDs and versioned pre/target schema identities.
  3. Require every pre migration retained, additions disjoint and exactly the reviewed ten; do not hardcode a pre-upgrade migration count.
  4. Validate exact output keys and types before creation; refuse counts, repeat hashes, arbitrary metadata, paths, timestamps or any row-derived field.
  5. Write deterministic UTF-8 JSON and a trailing newline create-only; refuse existing destination, symlink or data that fails the data-free validator.
  6. The builder is exercised with synthetic copies here. Claude Opus 5.5 alone runs it against private qualification copies in WP06.
- **Files**: `scripts/vikunja/build_release_baseline.py`, `tests/deploy/test_vikunja_release_acceptance.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: The output artifact contains schema/code facts only; no private aggregates.

### Subtask T023 – Test data-loss, copy races and privacy failures

- **Purpose**: Demonstrate that every claimed acceptance property can fail independently.
- **Steps**:
  1. Create preflight and acceptance test modules owned here; build synthetic SQLite fixtures within tests, never read private copies.
  2. Seed missing/extra migrations, lost task, changed/deleted rule, null tuple fields, corrupt database and target-schema mismatch.
  3. Seed missing eligible subscriptions with equal row total, incorrect total, duplicate growth, preserved duplicates, muted existing rows and dangling creators/assignees.
  4. Test changing database/WAL sets for five rounds, eventual stability, consolidation failure and cleanup on every exit.
  5. Test builder deterministic output, exact-key whitelist, wrong identity, disjoint sets, ten additions and forbidden output fields.
  6. Capture stdout/stderr, result exceptions and evidence-write failure output with path/time/hash/aggregate sentinels; require no leak.
- **Files**: `tests/deploy/test_vikunja_release_preflight.py`, `tests/deploy/test_vikunja_release_acceptance.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Every seeded defect has a correct-upgrade or stable-copy positive control.

### Subtask T024 – Confirm real callers and Python 3.12 CLI behaviour

- **Purpose**: Ensure the new code is used through supported stdlib-only interfaces.
- **Steps**:
  1. Exercise each script via its main function and local subprocess --help/usage paths against temporary synthetic inputs; define clear argparse usage and nonzero invalid-input exits.
  2. Implement operational logic with Python 3.12 standard library only; no sqlite CLI or new package dependency.
  3. Confirm preflight calls load_bound/compare and verifier/builder reuse shared functions, rather than leaving a test-only parallel implementation.
  4. Provide exact CLI usage to WP05: preflight <release-record>; verifier <snapshot-directory> <post-upgrade-copy>; builder <pre-copy> <post-copy> <release-record> <new-output>.
  5. WP05 supplies runbook callers. Test those positional interfaces here, including paths containing spaces and absence of private output.
  6. CI exercises 3.12 and 3.13; test locally available interpreters and report unavailable runtime coverage accurately.
- **Files**: `scripts/vikunja/preflight_release_baseline.py`, `scripts/vikunja/verify_release_upgrade.py`, `scripts/vikunja/build_release_baseline.py`, `tests/deploy/test_vikunja_release_preflight.py`, `tests/deploy/test_vikunja_release_acceptance.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: No host contact or private input access is part of implementation validation.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_release_preflight.py tests/deploy/test_vikunja_release_acceptance.py
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

- Copying a live WAL set can produce false confidence; require agreement and bounded retries.
- Receipt/baseline identity confusion can admit another release; validate all binding fields.
- Builder metadata creep can disclose private facts; use an exact output whitelist.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Inspect seeded equal-total subscription loss and existing duplicate controls.
- Confirm cleanup survives interruption and errors, and that no preflight artifact bypasses ACTIVATE.
- Check all three documented positional CLIs work on Python 3.12 without external tools.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP04 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP04 --to <status>`
- View history and status: `spec-kitty agent tasks status`
