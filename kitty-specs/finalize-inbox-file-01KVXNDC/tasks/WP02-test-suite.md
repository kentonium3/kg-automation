---
work_package_id: WP02
title: Test suite
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- NFR-001
- NFR-004
tracker_refs: []
planning_base_branch: feat/finalize-inbox-file
merge_target_branch: feat/finalize-inbox-file
branch_strategy: Planning artifacts for this mission were generated on feat/finalize-inbox-file. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/finalize-inbox-file unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
phase: Phase 2 - Verification
assignee: ''
agent: claude
history:
- at: '2026-06-24T20:35:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: tests/inbox/test_finalize_inbox_file.py
create_intent:
- tests/inbox/test_finalize_inbox_file.py
execution_mode: code_change
model: ''
owned_files:
- tests/inbox/test_finalize_inbox_file.py
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP02 – Test suite

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter (`python-pedro`), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match.

---

## Objectives & Success Criteria

Deliver `tests/inbox/test_finalize_inbox_file.py` proving all eight enumerated
scenarios for the WP01 helper, run hermetically against a tmp vault.

Done when `pytest tests/inbox/test_finalize_inbox_file.py -v` is green and covers
scenarios 1–8 from the CLI contract, including atomicity, idempotency, and error
surfacing.

## Context & Constraints

- Helper under test: `scripts/inbox/finalize_inbox_file.py` (WP01).
- CLI contract / test matrix: `kitty-specs/finalize-inbox-file-01KVXNDC/contracts/finalize_inbox_file.cli.md`.
- Spec acceptance scenarios: `kitty-specs/finalize-inbox-file-01KVXNDC/spec.md`.
- **Pattern reference (read first)**: `tests/inbox/conftest.py` (reuse fixtures)
  and `tests/inbox/test_atomic_write_perms.py` (the established atomic-write /
  permission-denied test pattern). Point the helper at a tmp vault via the same
  registry-path env override the helper honors.
- Tests must be hermetic and portable (macOS dev + Linux CI).

## Branch Strategy

- **Strategy**: planning/base + merge target `feat/finalize-inbox-file`. Execution
  worktree allocated per lane at `/spec-kitty.implement`.

## Subtasks & Detailed Guidance

### T007 — Hermetic test harness
- **Purpose**: tmp vault with `01-Inbox/` + `02-Inbox-Processed/`, a `paths.json`
  pointing at it, and the registry env override set.
- **Steps**: build a fixture (reuse `conftest.py` where possible) that creates the
  dirs + a minimal `paths.json`; helper to write an inbox file with given
  frontmatter/body; helper to invoke the script (subprocess or import-and-call)
  and capture exit code + stdout + stderr.
- **Files**: `tests/inbox/test_finalize_inbox_file.py`.

### T008 — Happy / already-finalized / partial-recovery [P]
- Scenario 1: unprocessed → status processed, in processed dir, one log line,
  JSON stdout, exit 0.
- Scenario 2: run twice → second run no-op, no duplicate log line, exit 0.
- Scenario 3: pre-move file + set status + omit log line → run appends only the
  log line, exit 0.

### T009 — Permission-denied (file + dir) [P]
- Scenario 4: make the inbox file (or its dir) unwritable → exit 2, `OSError` on
  stderr, original file not corrupted/half-written.
- Scenario 5: make the processed dir unwritable → exit 2, `OSError` on stderr.
- Use `os.chmod`; skip/guard if running as root (perms not enforced).

### T010 — Missing frontmatter / malformed YAML [P]
- Scenario 6: file with no frontmatter → exit 1.
- Scenario 7: file with malformed YAML frontmatter → exit 1.

### T011 — Cross-filesystem rename rejected [P]
- Scenario 8: simulate `EXDEV` (e.g., monkeypatch `os.rename` to raise
  `OSError(errno.EXDEV, ...)`) → exit 2, no copy fallback (assert no duplicate in
  the processed dir).

### T012 — Idempotency / no-duplicate-log assertion
- **Purpose**: NFR-002. Run the helper 3× on the same file; assert exactly one log
  line, stable end state, exit 0 each time.

## Definition of Done

- [ ] All 8 scenarios covered and green.
- [ ] Idempotency (3× run) asserted.
- [ ] Hermetic (tmp vault, env override) and portable; root-guarded perm tests.
- [ ] Reuses `conftest.py` fixtures and the `test_atomic_write_perms.py` pattern.

## Risks

- Portable simulation of permission-denied and cross-FS rename across macOS/Linux.
- Root in CI defeating chmod-based perm tests — guard with a skip.

## Reviewer Guidance

- Confirm every contract scenario maps to a test. Confirm the cross-FS test
  asserts no copy fallback. Confirm no-duplicate-log on re-run. Confirm tests do
  not touch the real vault (env override in effect).
