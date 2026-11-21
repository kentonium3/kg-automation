---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:52:55Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP07
---

# WP07 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Preview cannot count historical windows | scripts/habits/query_active_habits_weekly.py:199 | Production server d7e202228 searches after max(server now, due_date), so moving the anchor before a completed reporting window still returns future occurrences. Filtering those produces 0 scheduled days and suppresses real completions. The fake previews conceal this behavior. | Use a historical evaluation mechanism; return unknown when preview cannot evaluate the window. Add server-faithful tests.

2. MAJOR | Evaluation refusals become zero scheduled days | scripts/habits/query_active_habits_weekly.py:206 | The response reason is ignored. Black-box probes with occurrences=[] and reason=evaluation_failed or anchor_beyond_horizon both return 0, violating the requirement against guessed zeroes. | Validate the reason and completeness of the answer; return None for evaluation refusals and incomplete results.

3. MAJOR | YAML fallback rewrites frozen history | scripts/sync/cleanup.py:271 | A valid quoted "habits" key triggers library serialization. An in-memory probe confirmed that pruning removes comments and changes operations indentation, violating C-005’s byte-preservation requirement. | Preserve the original operations bytes on every supported path, or refuse unsupported layouts before writing. Test fallback layouts containing operations.

4. MINOR | Final habit cannot be pruned | scripts/sync/cleanup.py:263 | Removing the sole entry leaves “habits:” parsing as None, while verification expects []. The function raises ValueError and leaves the deleted task in the schedule; sync subsequently removes its cache entry. | Emit an explicit empty sequence when pruning the final item, and add a regression test.

Tests: focused suite 814 passed. Full suite collected 10,290 tests but stalled near 72%; interrupted without a completed result. No failure was reported before interruption.

Checklist: dead code PASS; synthetic fixtures PASS; silent empty returns FAIL; FR test coverage PASS; frozen committed surface PASS; locked decisions FAIL; shared-file coordination PASS; production fragility FAIL.

VERDICT: REJECT
## Required
- Fix 1 (orchestrator ruling, within FR-012 scope): the server's preview cannot evaluate past windows. Count daily and weekly-by-day (interval 1, no COUNT/UNTIL) locally as now; for any other rule return None (unknown) for a window that ends at or before now; use preview only for a window wholly in the future, and verify the server semantics you rely on (cite d7e202228 lines). Server-faithful tests: a fake preview that, like the real one, only returns occurrences after max(now, anchor).
- Fix 2: honour reason/completeness; evaluation refusals and incomplete answers -> None.
- Fix 3: never library-serialise a file containing operations:; refuse unsupported layouts before writing (or preserve the original operations bytes exactly). Test it.
- Fix 4: emit an explicit empty sequence when pruning the last habit; regression test.
