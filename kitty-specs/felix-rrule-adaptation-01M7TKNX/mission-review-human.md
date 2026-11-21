# Mission Review: felix-rrule-adaptation-01M7TKNX (kg-automation#1111)

**Reviewer**: Claude Sonnet (profile reviewer-renata) | **Date**: 2026-11-21
**Branch/HEAD**: fix/felix-rrule-adaptation @ 1f579a1c | **Baseline**: 68d66c05 | **Build**: 06af0c52e
**Scope**: mission-level fidelity, live-caller trace, locked decisions, security. Not a line-by-line code review (two Codex passes cover that). Read-only; `spec-kitty review` deliberately not run.

## Verdict: PASS WITH NOTES (releasable to main)

No BLOCKER or MAJOR findings. All 12 WPs are `done` in the reduced `status.json`. Every shipped module has a live production caller, and the write surface is closed behind the new gates. Only process and wording items remain.

## Gate results
- Gate 1 (tests/contract/): not applicable. No such directory exists in kg-automation.
- Gate 2 (architectural): the two new guards, `tests/architectural/test_no_retired_repeat_fields.py` and `test_agent_docs_no_direct_task_writes.py`, pass. Targeted run of those plus `tests/common/test_vikunja_client_v2.py`, `tests/habits/test_habits_rule_roundtrip.py`, `tests/habits/test_schedule_check_live.py`, `tests/vikunja`, `tests/escalation` and `tests/intake/test_apply_reply_rule_roundtrip.py`: **1253 passed**. The full suite was not rerun, as instructed.
- Gate 3 (cross-repo E2E): not applicable to this repo.
- Gate 4 (issue matrix): see M1.

## Traces that held
- **Write surface closed.** Every Vikunja task write outside the client goes through `patch_task`, which is a v2 merge patch, refuses keys outside `WRITABLE_TASK_FIELDS`, refuses nested nulls, and refuses `repeat: None` together with `done` (vikunja_client.py:641-700). The call sites are:
  - scripts/habits/record_completion.py:278
  - scripts/habits/sweeper.py:773
  - scripts/habits/set_due_dates.py:151
  - scripts/escalation/record_completion.py:273
  - scripts/intake/apply_reply.py:444
  - scripts/vikunja/migrate_tasks.py:826
  - scripts/vikunja/migrate_date_only_due_dates.py:117
  - scripts/vikunja/update_task.py:272
  - scripts/vikunja/rule_repair.py (the only user of `_allow_null`)
- **The v1 fallback is guarded.** `update_task_fields` (vikunja_client.py:515) is a full echo that raises `ValueError` on a rule or reminder change. No caller outside the client uses it.
- **Remaining v1 writes cannot touch the rule.** They are label PUT/DELETE (apply_reply.py:480/488, route_someday.py:166), task create in route_someday.py:218, and deletes in migrate_tasks.py:887. I found no raw-HTTP task writer outside the client.
- **No stale rule fields.** `repeat_after`/`repeat_mode` survive only in comments, the schedule_loader rejection message and frozen history (NFR-001). The architectural guard enforces this.
- **Live entry points exist** for every new module:
  - manage_habit is imported by the sweeper and the morning list, and is named in the habits agent doc.
  - update_task, preview_rule, rule_inventory and rule_repair appear in the agent skill docs and `docs/runbooks/vikunja-task-repair.md`.
  - `check_live` is reachable via `schedule_loader --check-live`, documented at habits-ops.md:742.
  - migrate_schedule is deleted, with its tests.
- **Repair gating (FR-021/022, NFR-005).**
  - `--apply` acts on status `lost` only. `removed`, `ended`, `changed` and `progressed` need an explicit `--task-id N --accept-changed` (rule_repair.py:100-103, 443-466).
  - Each write is preceded by a snapshot of the task as read, written with `O_EXCL` at mode 600 under a 0700 directory (rule_repair.py:172-184, 504).
  - Each write is confirmed by readback, and a `mismatch` or `unknown` outcome stops the run and prints the restore command.
  - Nothing writes Vikunja without the gates.
- **Sweeper (FR-004/024/026).** It skips paused habits through the single `is_paused` predicate, using a live v2 read (sweeper.py:819). It refuses and alerts on a habit with no rule (sweeper.py:661). I found no deploy manifest or unit change that re-enables the timer. The service and timer files are unchanged, so re-enable stays Kent's post-deploy go.
- **Token handling.** No token is printed or logged in the new scripts. Snapshot and run directories are 0700/0600. The only broad `except Exception` handlers are a cosmetic field (rule_repair.py:761) and sweeper safety nets that record errors (sweeper.py:998, 1323). I found no silent empty-result returns.
- **Architecture docs (FR-023).** data-flows.json, service-inventory.json, mutation-surfaces.json and credential-manifest.json were updated. No `deploys/queued` manifest was added, which is correct per the spec's own correction.

## FR/NFR/SC trace summary
- FR-001 to FR-020 and FR-025/026 trace to shipped code with live callers. Dedicated round-trip tests exist (habits, escalation, intake, sync, vikunja), plus the shared v2 factory (NFR-002 depends on this).
- FR-021/022 code and tooling are shipped (rule_inventory.py, rule_repair.py). Their live runs are post-deploy and deferred, with 4 DEFERRED matrix rows. This is known and accepted.
- FR-023 is shipped (docs and data). FR-024, SC-001 to SC-004 and NFR-004 are post-deploy and deferred. The inventory and repair outcomes belong on #1111.
- FR-025/026 are not in the acceptance matrix (a known tool gap). They are covered by `tests/vikunja/test_update_task.py`, `tests/habits/test_manage_habit.py`, `tests/habits/test_paused_habits_excluded.py` and the architectural doc guard.
- SC-005 and NFR-001 are enforced by tests and the architectural guard.

## Findings

All are **MINOR**.

- **M1 (process)** `kitty-specs/felix-rrule-adaptation-01M7TKNX/issue-matrix.json`, row `#1111`: verdict is `in-mission` and the title is the unfilled placeholder `<fill at WP-implementation time>`. The tool treats `in-mission` as non-terminal at `done`. In practice #1111 legitimately stays open until the post-deploy phases finish. Recommendation: record it as `deferred-with-followup` with an evidence_ref naming the post-deploy steps and #1118, and fill the title. Metadata only, no code effect.
- **M2 (traceability)** `acceptance-matrix.json` evidence strings cite ephemeral lane-worktree paths such as `.worktrees/...-lane-k/scripts/...` and `...-lane-j/...`. These stop resolving after worktree cleanup. Recommendation: note the repo-relative paths in the follow-up record. FR-025/026 are also absent, which is already known.
- **M3 (SC-001 operability)** The "schedule drift check on each day" has no scheduler. `check_live` runs only by hand through `schedule_loader --check-live` (schedule_loader.py:481, habits-ops.md:742). This is acceptable for the 7-day post-deploy verification, since Kent or the verifier runs it. Do not add machinery for it now.
- **M4 (cache lag)** The morning list applies the pause filter on sync-cache data (query_active_habits_v2.py:256), while the sweeper uses a live read. A habit paused within one sync poll could show once in a morning list. The sweeper does not auto-skip it. Improbable and low impact.
- **M5 (wording, already known)**
  - scripts/escalation/record_completion.py:37 and 39 say "felix-bot", but the runtime token is the kent user's (ADR-0007).
  - docs/design/process-flows/habits.md:239 describes the `unresolved` state.
- **M6 (note, no action)** `scripts/habits/phase3-schedule.yaml` is frozen history. The comment at line 133 correctly points at `--check-live`.

## Locked decisions and drift
- No non-goal invasion found. The migrate_schedule retirement is the specified FR-018 scope. The frozen YAML history is kept, and references were updated.
- FR-025 deliberately refuses due-date changes on recurring tasks (the series anchor). The sweeper does use `due_date` PATCH, as FR-004 specifies. These are consistent.
- No new Vikunja write bypasses `patch_task`, `update_task_fields` or `end_series`, so the "no write without gates" requirement is honoured.

## Retrospective
`retrospective.yaml` exists in the mission dir and was captured at consolidate (commit 21fdef1f). Recommended next steps are `spec-kitty retrospect summary` and `spec-kitty agent retrospect synthesize --mission felix-rrule-adaptation-01M7TKNX` (dry-run).
