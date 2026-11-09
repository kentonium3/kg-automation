---
work_package_id: WP03
title: Baseline module and ACTIVATE gate
dependencies:
- WP01
- WP02
requirement_refs:
- C-005
- FR-008
- NFR-001
- NFR-002
- NFR-003
- SC-002
planning_base_branch: fix/vikunja-repeat-cutover
merge_target_branch: fix/vikunja-repeat-cutover
branch_strategy: Planning artifacts for this mission were generated on fix/vikunja-repeat-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/vikunja-repeat-cutover unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-repeat-cutover-01M6YRJG
base_commit: 2cf66811d6b310ba0992046e61bcfc9a50001c96
created_at: '2026-11-09T20:09:26.090030+00:00'
subtasks:
- T013
- T014
- T015
- T016
- T017
- T018
- T019
phase: WP03 - Baseline module and ACTIVATE gate
history:
- at: '2026-11-09T05:00:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/vikunja_release/baseline.py
create_intent:
- scripts/deploy/vikunja_release/baseline.py
- tests/deploy/test_vikunja_release_baseline.py
execution_mode: code_change
model: gpt-6.1-sol
owned_files:
- scripts/deploy/vikunja_release/baseline.py
- scripts/deploy/deploy-vikunja-release-activate.py
- tests/deploy/test_vikunja_release_baseline.py
- tests/deploy/test_deploy_vikunja_release_activate.py
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

*Baseline module and ACTIVATE gate — FR-008, NFR-001, NFR-002, NFR-003, C-005. Tracking: see #1095; historical route: see #1087.*

- Every mismatch fails before release image selection and persists the designed marker error.
- Only the private snapshot is compared; the durable receipt precedes tagging.
- Gate and preflight share the same comparison/build primitives; no private details enter deploy output.

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
- Dependencies: WP01, WP02. Consume predecessor interfaces and fixtures without taking ownership of their files.
- Own only the frontmatter paths. Do not edit another packages surface or any kitty-specs path as part of code implementation.
- Python runtime is 3.12; CI also runs 3.13. New operational logic uses the standard library only.
- Compose remains on office2.local/vikunja:active with pull_policy: never; applied 0033/0034 stay unchanged.
- No host activity is required to implement synthetic tests. Any operational action follows the reviewed runbook and merge authority.
- Codex must never read the private cutover/acceptance directories or any private database copy.
- Use synthetic test data only; private qualification is the Claude-only WP06 boundary.

- Receipt carries private aggregates; committed baseline carries only schema/code-derived qualification facts.
- The build function is a required public interface for WP04, not a second script-specific implementation.
- Keep comparisons parameterized for synthetic fixtures; no host timing claim can be inferred from fake clocks.

## Branch Strategy

- **Strategy**: lane worktree computed by finalize-tasks
- **Planning base branch**: fix/vikunja-repeat-cutover
- **Merge target branch**: fix/vikunja-repeat-cutover

> These fields are populated automatically by spec-kitty agent mission finalize-tasks.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T013 – Load and authenticate the bound baseline

- **Purpose**: Make the reviewed artifact the trust root for gate comparison.
- **Steps**:
  1. Create scripts/deploy/vikunja_release/baseline.py; implement load_bound using WP01 baseline path/digest binding and a repository-root parameter for tests.
  2. Resolve containment under services/vikunja/baselines/, reject escapes including symlinks, read bounded bytes once, hash those bytes and parse the same bytes.
  3. Validate the exact data-free schema: schema_version=1; previous_version/image_config; sorted unique pre/added IDs, disjoint sets; algorithm and lowercase pre/target digests.
  4. Require previous version/config to equal the reviewed release rollback identity; derive version with the same exact ref semantics used by ACTIVATE/rollback.
  5. Missing binding, unreadable bytes, wrong digest, bad schema or inconsistent identity fail with GATE_BASELINE_UNREADABLE; do not print details.
- **Files**: `scripts/deploy/vikunja_release/baseline.py`, `tests/deploy/test_vikunja_release_baseline.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: The old record may load in core without a binding, but the gate must fail closed.

### Subtask T014 – Implement versioned schema identity

- **Purpose**: Compare schema content without depending on SQLite file layout.
- **Steps**:
  1. Implement sqlite-master-sha256-v1 over SELECT type, name, tbl_name, sql FROM main.sqlite_master ORDER BY type COLLATE BINARY, name COLLATE BINARY, tbl_name COLLATE BINARY.
  2. Serialize UTF-8 JSON with sorted keys, compact separators and explicit nulls; exclude rootpage, schema cookie and physical layout.
  3. Preserve SQL text exactly: never lowercase or collapse whitespace in SQL literals or identifiers.
  4. Test before/after consolidation using the dbsafety pattern at `scripts/deploy/vikunja_release/dbsafety.py:544` on synthetic schemas: altered tables, quoted identifiers, indexes, triggers and literals.
  5. Run this matrix on Python 3.12 and 3.13 in CI; a schema discrepancy fails for review rather than being normalized away.
- **Files**: `scripts/deploy/vikunja_release/baseline.py`, `tests/deploy/test_vikunja_release_baseline.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Generate qualified baselines through the same consolidation route the gate observes.

### Subtask T015 – Share comparison, aggregates and data-free build logic

- **Purpose**: Keep gate, preflight, acceptance and builder calculations consistent.
- **Steps**:
  1. Implement compare(snapshot_path, baseline) returning a stable code separately from private aggregate evidence.
  2. Require exact pre-upgrade migration IDs and exact pre-schema identity; noncomputable aggregates return GATE_AGGREGATE_FAILED.
  3. Compute task count and canonical repeat hash over ordered (id, repeats, repeats_from_current_date) tuples with nonempty rules and explicit nulls.
  4. Compute eligible pairs from tasks.id/tasks.created_by_id and task_assignees(task_id,user_id), joined to existing users.id, using UNION. No deleted-task or user-status filter applies. Match subscriptions(entity_type=3, entity_id=task_id, user_id). Expected total is existing task rows plus missing eligible pairs.
  5. Retain muted rows and existing duplicates; duplicate excess is the sum of count minus one for task subscriptions (entity_type=3) grouped by (entity_id,user_id). Expose it for acceptance comparison. Equal totals alone cannot hide missing or substituted eligible pairs.
  6. Expose a build function for WP04: accept consolidated pre/post copies and reviewed rollback identity, return only the data-free qualified baseline schema.
  7. Build derives sorted migration sets and pre/target schema digests; enforce retained pre IDs, disjoint reviewed additions and the qualified ten-addition requirement without hardcoded pre-count.
- **Files**: `scripts/deploy/vikunja_release/baseline.py`, `tests/deploy/test_vikunja_release_baseline.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Private aggregates must never be included in the build result or printed.

### Subtask T016 – Write a durable private baseline receipt

- **Purpose**: Ensure evidence survives before image selection is allowed.
- **Steps**:
  1. Use `scripts/deploy/vikunja_release/dbsafety.py:480` as a durability pattern only; its snapshot validator is not suitable for baseline receipts.
  2. Give the baseline receipt its own strict validator binding snapshot SHA, baseline SHA, release/config, migrations/schema and all private aggregates.
  3. Write baseline.json in the snapshot directory: directory 0700, file 0600, exclusive O_NOFOLLOW creation, complete short writes, file fsync then parent fsync.
  4. Refuse unsafe parents, symlinks, preexisting receipt and malformed evidence; any write, fsync or permission failure is GATE_RECEIPT_WRITE_FAILED.
  5. Test short writes, zero-progress writes, file/parent fsync order, existing paths and crash windows. Do not silently replace a receipt.
- **Files**: `scripts/deploy/vikunja_release/baseline.py`, `tests/deploy/test_vikunja_release_baseline.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: No output may reveal the receipt location or its contents.

### Subtask T017 – Gate ACTIVATE between snapshot persistence and retag

- **Purpose**: Prevent selecting the new image before the restore point is proven.
- **Steps**:
  1. Integrate in `scripts/deploy/deploy-vikunja-release-activate.py:504` immediately after _advance("snapshotted", ...) and before docker tag.
  2. Gate order is load_bound, compare, durable receipt, return; read only the private snapshot and never open live data for writing.
  3. Bound all work by min(30 seconds, remaining outage), including SQLite execution/hash/write time; use deadline-aware work rather than a check only at the end.
  4. Keep total outage 300 seconds and readiness capped at 180/remaining; exhaustion of the overall outage reports ACTIVATE_OUTAGE_DEADLINE.
  5. Do not add marker phases. On gate failure persist phase=snapshotted, failed_phase=retagged, outcome=failed and the stable gate error.
  6. Use existing failure cleanup. With successful cleanup no active tag/container remains; a cleanup failure must be reported without promising absence.
- **Files**: `scripts/deploy/vikunja_release/baseline.py`, `scripts/deploy/deploy-vikunja-release-activate.py`, `tests/deploy/test_vikunja_release_baseline.py`, `tests/deploy/test_deploy_vikunja_release_activate.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Receipt completion and both fsyncs must precede the first tag call.

### Subtask T018 – Scrub every ACTIVATE private detail producer

- **Purpose**: Keep retained deploy output free of snapshot and migration evidence.
- **Steps**:
  1. Remove sensitive snapshot details in `scripts/deploy/deploy-vikunja-release-activate.py:504`, success conversion aggregates and outage detail values.
  2. Inspect `scripts/deploy/deploy-vikunja-release-activate.py:571` and every captured-log emission: no private path, timestamped filename, hash or aggregate may be emitted.
  3. Keep raw logs and aggregate evidence private while emitting stable codes; WP01 already fixes shared run_cli failure paths.
  4. Test stdout, stderr, accumulated detail lines, simulated forwarded failure excerpts and installed reports with recognisable sentinels.
  5. Cover success, ordinary gate failure, unexpected exception, failed cleanup and failed private-log capture.
- **Files**: `scripts/deploy/deploy-vikunja-release-activate.py`, `tests/deploy/test_deploy_vikunja_release_activate.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not treat a permitted emit value as permission to disclose private evidence.

### Subtask T019 – Prove failure ordering, replay and snapshot rollback recovery

- **Purpose**: Make fail-closed behaviour an executable integration contract.
- **Steps**:
  1. Extend Env at `tests/deploy/test_deploy_vikunja_release_activate.py:302` and its synthetic database builder at `tests/deploy/test_deploy_vikunja_release_activate.py:290` with migrations, repeats and subscriptions.
  2. Move historical record loading to WP01 fixture without changing its bytes. Extend each temporary historical happy-path record with a matching synthetic baseline binding and synthetic migration/repeat/subscription schema so it passes the real gate; do not bypass the gate. Add separate explicitly bound repeat-cutover fixtures.
  3. Test each baseline, migration, schema and aggregate mismatch; receipt failure; gate deadline and overall outage deadline.
  4. Use Timing at `tests/deploy/test_deploy_vikunja_release_activate.py:936` and crash injection to prove zero release retag/up calls after any gate failure.
  5. Crash before receipt completion, after receipt durability and before retag, and after retag; replay must refuse unsafe retries.
  6. Drive a gate-failed marker through WP02 rollback prepare/finish using a simulated privileged restore; show exact previous image running.
  7. Prove --recover-pre-snapshot refuses gate failures because their completed phase is snapshotted.
- **Files**: `tests/deploy/test_vikunja_release_baseline.py`, `tests/deploy/test_deploy_vikunja_release_activate.py`.
- **Parallel?**: No; follow the subtask order within this package.
- **Notes**: Do not turn frozen historical tests into an automatic baseline bypass.

## Test Strategy (include only when tests are required)

- Start with the focused regression cases and a same-fixture passing control for each refusal.
- Inject Docker, SSH/process runners and clocks; local tests must not contact a host.
- Database fixtures are synthetic and created only in temporary test directories.
- Capture public stdout/stderr and forwarded/installed-report channels where privacy applies.
- Required focused command:

```bash
python3 -m pytest -q tests/deploy/test_vikunja_release_baseline.py tests/deploy/test_deploy_vikunja_release_activate.py
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

- Synchronous SQLite work can overrun deadlines; include bounded query execution and elapsed-time checks.
- SQLite schema text can change during consolidation; test the actual route on both CI runtimes.
- Cleanup failure is a distinct state; never claim successful absence if cleanup failed.

## Review Guidance

- **Independent reviewer: Claude Sonnet 5.5 for this entire work package.**
- Implementer is Codex gpt-6.1-sol; the implementing model must not review its own change.
- Check the complete owned diff against the subtasks and Definition of Done, including error paths.
- Confirm focused/full test results and any configured compiler diagnostics; do not accept unrun checks as passing.
- Confirm gate error codes: GATE_BASELINE_UNREADABLE, GATE_MIGRATIONS_MISMATCH, GATE_SCHEMA_MISMATCH, GATE_AGGREGATE_FAILED, GATE_RECEIPT_WRITE_FAILED, GATE_DEADLINE.
- Inspect parent fsync and zero tag/up assertions for every failure family.
- Review gate-failed snapshot rollback end to end and public-output sentinels.

## Progress & Status

Progress, history, and status live in the status event log (status.events.jsonl), never in this prompt.
Do not hand-edit a history section here. Use only authoritative workflow commands during execution.

- Record a progress note: `spec-kitty agent tasks add-history WP03 --note "<what you did>"`
- Change WP status: `spec-kitty agent tasks move-task WP03 --to <status>`
- View history and status: `spec-kitty agent tasks status`
