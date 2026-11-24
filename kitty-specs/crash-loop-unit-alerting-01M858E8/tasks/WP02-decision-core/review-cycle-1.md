---
affected_files: []
cycle_number: 1
mission_slug: crash-loop-unit-alerting-01M858E8
reproduction_command:
reviewed_at: '2026-11-23T23:41:58Z'
reviewer_agent: codex
wp_id: WP02
---

# WP02 review feedback, cycle 1

Reviewer: Codex CLI, model gpt-6.1-sol, read-only sandbox, 2026-11-23. The implementer was Claude Opus 5.5. Verdict: REJECT. The orchestrator ran the tests: 47 WP tests passed and 545 tests/canary passed.

1. **MAJOR — `scripts/canary/crash_loop.py:346–349`: re-reminds can reuse the original burst indefinitely until its baseline expires.**  
   With `(minute, count) = (0,0), (16,39)`, followed by +1 every 16 minutes, minute 384 emits `reremind`: the original baseline yields Δ=62, m=26, bound=53. Every post-alert interval fails the crossing rule, yet each rise prevents clearing.

   This follows the literal R-05/INV-CL-4 algorithm, but exposes a **design gap against FR-007’s persistence intent**: historical evidence becomes a “still crash-looping” page without a fresh proven crossing.

   **Fix:** require the re-remind proof’s `baseline_at >= episode.last_alert_utc`. Preserve ordinary history and initial-alert proof selection; revise the authoritative design accordingly. Add the 39-restart sequence as a regression test, asserting no reminder and no advancement of `last_alert_utc`, followed by a fresh qualifying burst that does remind. The existing negative test at `tests/canary/test_crash_loop.py:267` starts with only five restarts and misses this case.

2. **MINOR — `tests/canary/test_crash_loop.py:651`: clock precedence lacks a regression test.**  
   The test changes time and count but preserves boot ID and generation. Moving the reboot check before the clock check would therefore escape this test, violating INV-CL-9.

   **Fix:** at equal and backward timestamps, combine a changed boot ID, changed container generation, and decreased counter. Assert unchanged unit state, no events, and only `clock_skipped` incremented.

The remaining invariant trace checks out: first sight, reset suppression, silent boot closure, clear-once with history rebasing, ignore handling, incomplete-scope preservation, removal, purity, and delivery-independent decisions. The applicable rounds 1–4 sequences produce the specified results, including dense sampling, clear replay prevention, delayed reboot observation, dominance replacement, and retention of all in-window entries. The property test uses independently generated restart timestamps and is non-vacuous; it does not establish reminder freshness.

The declared deviations are acceptable: observation-derived aggregate dates and alert timestamps preserve determinism; `None` boot ID fails safely to unknown; `ValueError` suits internal contract violations; reset-clear deltas match the revised model; holding-proof-only `peak_delta` is reasonable evidence bookkeeping. Production code changes stay within WP02’s owned files; additional diff entries are workflow metadata. No prohibited credential reads, journal access, or shell execution appear in the decision core.

Tests were assessed statically; the reported 47/545 passing results were supplied by the orchestrator.

VERDICT: REJECT

Orchestrator ruling: finding 1 is accepted. The design addendum is recorded in data-model.md INV-CL-4 and research.md R-05 (commit 6423d21): a re-remind proof uses only baselines with baseline_at >= episode.last_alert_utc.
