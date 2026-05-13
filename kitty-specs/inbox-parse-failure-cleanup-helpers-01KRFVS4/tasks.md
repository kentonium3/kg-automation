# Tasks: Inbox parse-failure and cleanup helpers

**Mission**: `inbox-parse-failure-cleanup-helpers-01KRFVS4`
**Source**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Source issue**: [#253](https://github.com/kentonium3/kg-automation/issues/253)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/inbox/handle_parse_failures.py` (orchestrates Step 6 — issue file/dedup + marker injection per entry) | WP01 |  | [D] |
| T002 | Create `scripts/inbox/handle_marker_cleanup.py` (orchestrates Step 5a — strip markers per entry) | WP01 | [D] |
| T003 | Create `tests/inbox/test_handle_parse_failures.py` (5 cases — empty / full-success / dedup-hit / partial-failure / stdout-issue-number) | WP01 | [D] |
| T004 | Create `tests/inbox/test_handle_marker_cleanup.py` (3 cases — empty / all-succeed / partial-failure) | WP01 | [D] |
| T005 | Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Step 5a + Step 6 to single-command invocations of the new helpers | WP01 |  | [D] |
| T006 | Mirror T005 edits to `scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl` (keep template + runtime in sync) | WP01 | [P with T005] | [D] |
| T007 | Run local pytest suite — verify 99 existing + 8+ new tests pass | WP01 |  | [D] |

## Work Package WP01 — Implement Step 5a + Step 6 consolidation helpers

**Goal**: Add two orchestrator scripts that consolidate the deterministic loops in AGENTS.md Step 5a and Step 6 into single CLI invocations. Update the agent prompt (and template) to call them. Verify locally before merge.

**Priority**: P2 (per source issue #253).

**Independent test (WP01 review scope)**: Both new helpers exist and have unit tests covering success/empty/partial-failure/dedup paths; `tests/inbox/` runs green; AGENTS.md and AGENTS.md.tmpl Step 5a and Step 6 are each a single command invocation (no multi-line bash recipe).

**Included subtasks (review scope — T001–T007)**:

- [x] T001 Create `scripts/inbox/handle_parse_failures.py` (WP01)
- [x] T002 Create `scripts/inbox/handle_marker_cleanup.py` (WP01) [P]
- [x] T003 Create `tests/inbox/test_handle_parse_failures.py` (WP01) [P]
- [x] T004 Create `tests/inbox/test_handle_marker_cleanup.py` (WP01) [P]
- [x] T005 Update AGENTS.md (WP01)
- [x] T006 Update AGENTS.md.tmpl (WP01) [P with T005]
- [x] T007 Run local pytest suite (WP01)

**Post-merge operator verification (out of WP01 review scope)**:

These steps require office2 SSH against deployed code and must run on `main` after merge, not from an unmerged lane branch (per `docs/design/architecture/change-control.md`). Documented in detail under "Post-Merge Operator Verification" in the WP01 prompt file.

- Deploy via `bash scripts/deploy/deploy-149.sh --apply --backup-confirmed`
- Smoke tests for both new helpers on office2 with `/tmp` fixtures
- SC-003 end-to-end canary — trigger `openclaw cron run 7fa9b299-...` against a synthesized parse_failure note; verify BOTH `inbox_quality_issue_filed`/`_deduped` AND `parse_error_marker_injected` action-log entries fire, and the canary file has the injected callout

**Why the split**: Same lesson from mission #254 (commit b82aac4) — folding operator post-merge work into a review-time DoD creates scoping conflicts at the reviewer gate. T008+ runbook is preserved in the WP prose without blocking the WP01 review.

**Implementation sketch**:

1. T001 + T002 are independent files; `[P]` candidate. Each imports the wrapped library functions from the existing inbox modules (per spec C-003, plan Phase 0 Decision 1). Subprocess-out to `log_action.py` for each emitted action-log entry (plan Phase 0 Decision 4).
2. T003 + T004 are also independent test files; `[P]` candidate. Drive each orchestrator via `subprocess.run` for full CLI surface coverage. Use `pytest.MonkeyPatch` to stub the wrapped functions per scenario.
3. T005 + T006 are mechanically identical edits to two files (AGENTS.md and AGENTS.md.tmpl). Replace Step 5a multi-line bash with a single helper invocation. Replace Step 6.1+6.2 sub-steps with a single helper invocation. Preserve all surrounding prose.
4. T007 runs `python3 -m pytest tests/inbox/ -v`. Expected: 107+ passed (99 existing + 8+ new). Failure stops the WP.

**Parallel opportunities**: T001+T002, T003+T004, T005+T006 are each pairwise-parallel. Sequencing concern: T003/T004 reference T001/T002 imports, so tests should be written after or alongside the helpers. T007 depends on everything else.

**Dependencies**: Builds on #254 (already merged). No inter-WP dependencies.

**Risks (review-scope)**:

- **Import path correctness**: the new helpers must import from `scripts.inbox.inject_parse_error_marker` etc. Verify the existing test structure for the right import style (`sys.path` manipulation in conftest.py).
- **AGENTS.md prose drift**: Step 5a/6 are embedded in a larger flow; the single-command replacement must not break adjacent context (Step 5b/5c, Step 7).
- **AGENTS.md.tmpl drift from AGENTS.md**: C-002 requires identical edits to both. Diff the two files after edits to confirm.
- **Post-merge T008+ may surface unrelated openclaw or sync issues** — operator-owned, not a WP01 review concern.

**Estimated prompt size**: ~450 lines.

## MVP Scope

WP01 is the entire mission. No phase split necessary.

## Next Steps

After WP01 merges, the post-merge operator (you) runs the verification recipe in the WP01 prompt's "Post-Merge Operator Verification" section to confirm haiku 4.5 reliably executes the single-call Step 5a and Step 6 forms.
