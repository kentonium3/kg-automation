---
work_package_id: WP02
title: Validate felix-bot — side-channel validation harness before cutover
dependencies: []
requirement_refs:
- FR-004
- FR-015
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-bot-vikunja-provisioning-01KRT3N4
base_commit: b89c2c9c9e8ab0642aad7e7a2155e48b52884920
created_at: '2026-05-17T05:18:13.168362+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
shell_pid: "71341"
agent: "codex:gpt-4o:python-reviewer:reviewer"
history:
- action: drafted
  agent: claude
  timestamp: '2026-05-17T05:15:00Z'
authoritative_surface: scripts/vikunja/validate_felix_bot.py
execution_mode: code_change
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
owned_files:
- scripts/vikunja/validate_felix_bot.py
- tests/vikunja/test_validate_felix_bot.py
tags: []
---

# WP02 — Validate felix-bot side-channel

## Objective

Implement `scripts/vikunja/validate_felix_bot.py` — the second-phase helper of ADR-0002 Phase 1 (issue #304). The helper exercises felix-bot's API token end-to-end via a side-channel script BEFORE the production secrets file is rotated. Verifies project access for all 12 real projects, writes a sample comment on a throwaway task and asserts attribution, then cleans up. Also includes a rollback-procedure smoke test mode (FR-015) so the recovery path is proven before it is needed.

This helper is the GATE that decides whether Phase 3 (cutover via swap_vikunja_secrets.py) can proceed. Failure here means no production disruption.

## Context

- **Spec section**: FR-004 (full validation flow), FR-015 (rollback smoke test), NFR-001 (5-minute timing budget) in [spec.md](../spec.md).
- **Design rationale**: [research.md](../research.md) R-004 (validation comment target = throwaway task), R-005 (atomic operations), R-006 (operator-driven).
- **API contracts**: See [contracts/vikunja-api-endpoints.md](../contracts/vikunja-api-endpoints.md) sections C-2 (list projects), C-6 (create task), C-7 (add comment), C-8 (read comments), C-9 (delete comment), C-10 (delete task).
- **Token source**: This helper authenticates as felix-bot using the token captured by WP01's `--token-output-file`. The helper is invoked AFTER WP01's `provision_felix_bot.py` completes and BEFORE WP03's `swap_vikunja_secrets.py` runs.
- **Existing helper convention**: Same as WP01 — match `felix-file-issue.py` patterns.

## Branch strategy

Planning branch: `main`. Final merge target: `main`. Execution worktree allocated per computed lane in `lanes.json` after task finalization.

## Subtask guidance

### T006 — argparse + token file reading + identity gate

**Purpose**: Establish the helper's CLI and the felix-bot identity gate.

**Steps**:

1. Write the docstring header — explain what the helper does and its role in the mission flow (gate before swap).
2. Implement argparse with:
   - `--token-file` (required) — path to file containing felix-bot's API token (the file written by WP01)
   - `--target-project-id` (default `13`, type=int) — project ID for the throwaway task probe; default is Habits
   - `--vikunja-base-url` (default `https://office2.tail0f5f56.ts.net/api/v1/`)
   - `--expected-project-count` (default `12`, type=int) — assert this many projects are accessible to felix-bot
   - `--rollback-smoke-test` (boolean flag) — run only the rollback-procedure smoke test, no live writes
   - `--dry-run` (boolean flag) — no network calls
3. Implement an identity gate:
   - Confirm `--token-file` exists, is mode 600, is owned by the current user, contains a non-empty token
   - If any check fails, exit 2 with explicit message
4. Read the token into memory; do not echo it anywhere.

**Files**:
- `scripts/vikunja/validate_felix_bot.py` (new, ~80 lines for this subtask)

**Validation**:
- `python3 scripts/vikunja/validate_felix_bot.py --help` displays the argparse interface
- Missing required arg exits 2
- Token file with wrong permissions exits 2
- Empty token file exits 2

### T007 — Project access verification (read all 12 with felix-bot token)

**Purpose**: Confirm felix-bot has read access to all 12 real Vikunja projects per the share grants made in WP01.

**Steps**:

1. Implement `verify_project_access(token, base_url, expected_count) -> dict`:
   - GET `{base_url}/projects?per_page=50` with felix-bot bearer token
   - Filter to real projects (`id > 0 AND is_archived != True`)
   - Assert count == `expected_count` (default 12). If less, exit 1 with explicit message listing what's missing.
   - Return summary `{"accessible_project_ids": [...], "count": N}`
2. Print a per-project log line so the operator sees what's accessible: `OK project_id=N title="..."`
3. This step takes seconds, not minutes. Logs help the operator see progress.

**Files**:
- `scripts/vikunja/validate_felix_bot.py` (~40 added lines)

**Validation**:
- Unit test mocks `GET /projects` returning exactly 12 real projects; helper proceeds.
- Unit test mocks returning 11 real projects; helper exits 1 with the specific missing project IDs noted (caller can investigate which share grant didn't apply).
- Unit test mocks 401 (token rejected); helper exits 1 with "felix-bot token rejected — share grants may not have applied" message.

### T008 — Throwaway task creation + sample comment + readback + cleanup

**Purpose**: The core attribution probe. Creates a fresh throwaway task, writes a `[Felix-Validation]` comment, reads it back, asserts `created_by.username == felix-bot`, then cleans up both the comment and the task.

**Steps**:

1. Implement `validate_attribution(token, base_url, target_project_id) -> dict`:
   - Compute a timestamp string (ISO 8601, UTC) for the task title and comment text uniqueness.
   - **Create throwaway task**: PUT `{base_url}/projects/{target_project_id}/tasks` with `{"title": "felix-bot validation probe <iso8601>"}`. Capture task_id.
   - Verify the task's `created_by.username == 'felix-bot'`. If not, exit 1 immediately (this is the first attribution signal — if it's wrong here, abort).
   - **Write comment**: PUT `{base_url}/tasks/{task_id}/comments` with `{"comment": "[Felix-Validation] felix-bot can write to this task — <iso8601>"}`. Capture comment_id.
   - Verify the comment's `author.username == 'felix-bot'`. If not, exit 1.
   - **Read back comments**: GET `{base_url}/tasks/{task_id}/comments`. Find the comment by id. Confirm `created_by.username == 'felix-bot'`.
   - **Cleanup**: DELETE the comment, DELETE the task. Cleanup failure is logged as a WARN but does NOT fail validation (best-effort per contract C-9, C-10).
2. Return a summary structure that includes the task_id, comment_id, all three attribution checks (task-creation, comment-write, comment-readback), and cleanup status.

**Files**:
- `scripts/vikunja/validate_felix_bot.py` (~80 added lines)

**Validation**:
- Unit test mocks the full happy-path sequence; all three attribution checks pass.
- Unit test mocks task creation returning `created_by.username='kent'`; helper exits 1 immediately (this would be a Vikunja bug or share-grant bug).
- Unit test mocks comment write returning `author.username='kent'`; helper exits 1.
- Unit test mocks comment-readback returning the felix-bot-authored comment; helper passes.
- Unit test mocks cleanup DELETE returning 404; helper logs WARN but exits 0.
- Unit test mocks dry-run; no network calls; returns mock summary.

### T009 — Rollback smoke test mode (FR-015)

**Purpose**: Per FR-015, the rollback procedure must be proven executable in under 5 minutes BEFORE it is needed. This subtask implements a symbolic exercise of the rollback path without modifying production state.

**Steps**:

1. Implement `rollback_smoke_test(secrets_path, bak_path) -> dict`:
   - This mode is triggered by `--rollback-smoke-test` flag.
   - Verify that `bak_path` (e.g., `vikunja-api.kent-pre-felix-bot.bak`) does NOT yet exist (Phase 3 has not run yet — backing up before is wrong).
   - Verify that `secrets_path` exists and is the current secrets file.
   - Simulate (not execute) the rollback steps:
     - "Would copy {bak_path} → {secrets_path}" (does not actually copy)
     - "Would restart openclaw-gateway"
     - "Would invoke sample agent + verify kent attribution"
   - Time the simulated path. Each step has an explicit timing model (e.g., file copy ~1s, systemctl restart ~5s, verification ~10s).
   - Output a SUMMARY line confirming total simulated time < 5 min per NFR-003.
2. The smoke test runs in seconds (it does no I/O). Its purpose is to confirm the runbook's rollback procedure is well-formed and traceable.

**Files**:
- `scripts/vikunja/validate_felix_bot.py` (~40 added lines)

**Validation**:
- Unit test invokes helper with `--rollback-smoke-test`; helper does NOT make any HTTP calls; emits SUMMARY confirming simulated rollback is < 5 min.
- Unit test invokes smoke test in a state where the `.bak` file exists (Phase 3 already done); helper exits 1 with explicit message (rollback smoke test before swap is the only legitimate use).

### T010 — Pytest tests for validate_felix_bot.py

**Purpose**: Comprehensive unit test coverage for the helper.

**Steps**:

1. Create `tests/vikunja/test_validate_felix_bot.py`.
2. Test categories:
   - **Argparse validation**: missing/invalid args; `--help` works
   - **Identity gate**: missing token file, wrong-permission file, empty file all exit 2
   - **Project access verification**: 12 returned, 11 returned (exit 1), 401 (exit 1)
   - **Attribution probe**: full happy path; task-creation attribution wrong; comment-write attribution wrong; cleanup soft-fail
   - **Rollback smoke test**: happy path; .bak already exists (exit 1)
   - **Dry-run**: full path with no network calls
3. Aim for ~12-15 tests.

**Files**:
- `tests/vikunja/test_validate_felix_bot.py` (new, ~250 lines)

**Validation**:
- `pytest tests/vikunja/test_validate_felix_bot.py -v` passes all tests
- No live network calls

## Test strategy

Pytest with subprocess invocation + mocked `urllib.request.urlopen`. Same pattern as WP01.

## Definition of Done

- [ ] `scripts/vikunja/validate_felix_bot.py` exists and is executable
- [ ] `tests/vikunja/test_validate_felix_bot.py` exists with ≥12 passing tests
- [ ] `python3 scripts/vikunja/validate_felix_bot.py --help` works
- [ ] All argparse args from T006 implemented
- [ ] Identity gate rejects bad token files
- [ ] Project access verification asserts expected count, lists accessible projects
- [ ] Attribution probe creates throwaway task, writes/reads/deletes comment, asserts felix-bot at three checkpoints
- [ ] Cleanup is best-effort (warn but don't fail)
- [ ] Rollback smoke test runs without network IO and emits a < 5min simulated timing
- [ ] `SUMMARY:` line emitted at end of validation run
- [ ] Dry-run skips network calls entirely
- [ ] Pytest suite passes
- [ ] No third-party dependencies

## Risks

- **Felix-bot share grant incomplete**: If WP01's share verification missed an edge case, this helper catches it via T007's expected_count check.
- **Throwaway task pollution on cleanup failure**: Worst case is a single stale task in the Habits project. Operator can manually delete via UI. Documented in helper output.
- **Race during target task creation**: If two operators run validate concurrently (shouldn't happen), each creates its own throwaway task with a different timestamp; no collision.

## Reviewer guidance (for Codex review)

- Verify the helper actually checks attribution at three distinct points: task creation, comment write, comment readback. All three must pass for validation success.
- Verify the cleanup DELETE calls are inside try/except — failure to delete should be a WARN, not an error.
- Verify the `--rollback-smoke-test` mode does ZERO network calls (mock-able assertion).
- Verify token is never logged or echoed.
- Confirm `expected_project_count` default is 12 and the off-by-one logic correctly handles 11 vs 13.
- Verify the timestamp in the throwaway task's title is uniqueness-sufficient (ISO 8601 with seconds resolution).
- Verify SUMMARY line format is parseable by the runbook.

## Implementation command

```bash
spec-kitty agent action implement WP02 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent <tool>:<model>:<profile>:<role>
```

## Review command

```bash
spec-kitty agent action review WP02 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent codex:gpt-4o:python-reviewer:reviewer
```

## Activity Log

- 2026-05-17T05:18:15Z – claude:opus-4-7:python-implementer:implementer – shell_pid=64199 – Assigned agent via action command
- 2026-05-17T05:24:09Z – claude:opus-4-7:python-implementer:implementer – shell_pid=64199 – Ready for review — validate_felix_bot.py (625 lines) + test_validate_felix_bot.py (481 lines, 19 passing tests). Stdlib only; identity gate, project-count gate, three-checkpoint attribution probe, FR-015 rollback smoke test, dry-run all covered.
- 2026-05-17T05:24:58Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=66639 – Started review via action command
- 2026-05-17T05:32:38Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=66639 – Moved to planned
- 2026-05-17T05:33:11Z – claude:opus-4-7:python-implementer:implementer – shell_pid=70044 – Started implementation via action command
- 2026-05-17T05:36:26Z – claude:opus-4-7:python-implementer:implementer – shell_pid=70044 – Cycle 2 — addressed Codex blocking finding: strict created_by.username at write+readback; 2 new regression tests added; existing 19 tests still pass.
- 2026-05-17T05:38:03Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=71341 – Started review via action command
