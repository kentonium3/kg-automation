---
affected_files: []
cycle_number: 1
mission_slug: crash-loop-unit-alerting-01M858E8
reproduction_command:
reviewed_at: '2026-11-23T23:39:15Z'
reviewer_agent: codex
wp_id: WP03
---

# WP03 review feedback, cycle 1

Reviewer: Codex CLI, model gpt-6.1-sol, read-only sandbox, 2026-11-23. The implementer was Claude Opus 5.5. Verdict: REJECT. The orchestrator ran the tests: 97 WP tests passed and 595 tests/canary passed.

1. **MAJOR — [crash_loop_readers.py:183](/home/kgale/repos/kg-automation/.worktrees/crash-loop-unit-alerting-01M858E8-lane-c/scripts/canary/crash_loop_readers.py:183): Deadline overruns can return healthy.** The deadline is checked before commands, but successful completion and parsing are never checked afterward. Read-only reproduction: an empty enumeration returning at 7 seconds under a 6-second budget produced `complete=True`, `elapsed_ms=7000`. R-13 and the scope-health contract require deadline overruns to be incomplete. **Fix:** check the deadline after commands and before every successful scope return, including empty-enumeration paths. Add tests for successful final commands and empty enumerations returning after expiry; existing tests only catch overruns through a subsequent command or exception.

2. **MAJOR — [crash_loop_readers.py:434](/home/kgale/repos/kg-automation/.worktrees/crash-loop-unit-alerting-01M858E8-lane-c/scripts/canary/crash_loop_readers.py:434): Duplicate container state keys are accepted.** Reconciliation checks container IDs, but observations are keyed downstream by container **name**. Two distinct requested IDs with `"/same"` both pass, yielding two `container:same` observations with different generations and counters. This creates ambiguous state and can lose coverage. Name changes during enumeration/inspection also make this a race worth handling. **Fix:** reject duplicate normalized names across all returned records before policy exclusion. Add a test using distinct valid IDs sharing one name and assert an incomplete scope.

3. **MINOR — [crash_loop_readers.py:435](/home/kgale/repos/kg-automation/.worktrees/crash-loop-unit-alerting-01M858E8-lane-c/scripts/canary/crash_loop_readers.py:435): Container-name validation only rejects emptiness.** A malformed name such as `"/bad name"` passes and becomes a watched identity, contrary to R-13’s explicit malformed-name failure rule. **Fix:** validate the Docker name shape before exclusion, including the leading slash and allowed name characters. Add malformed-name cases beyond empty/non-string values, including an excluded-policy record.

VERDICT: REJECT
