---
affected_files: []
cycle_number: 1
mission_slug: crash-loop-unit-alerting-01M858E8
reproduction_command:
reviewed_at: '2026-11-24T00:04:36Z'
reviewer_agent: codex
wp_id: WP04
---

# WP04 review feedback, cycle 1

Reviewer: Codex CLI gpt-6.1-sol (read-only, 2026-11-23); implementer Claude Opus 5.5. Codex verdict: APPROVE with 3 MINOR findings. **Orchestrator decision: changes requested.** All three MINORs are cheap and real, and the first one is needed for R-14's 7-day acceptance evidence.

- **MINOR — scripts/canary/run.py:587:** Unverified-rise evidence omits the period and required bound explicitly required by research R-05. The interval preserves timestamps and counts, but neither the evidence nor extra fields record `proof.bound`. **Fix:** include `period_seconds`, `m`, and `bound` in the evidence; assert their values in the unverified-rise test.

- **MINOR — tests/canary/test_run_crash_loop.py:599:** Scope-failure coverage stops at first-seen `unknown`. It does not verify persistent-unknown paging, dedup suppression, or recovery through the enabled stage. **Fix:** add successive ticks before and after the dedup window, followed by a healthy reading; assert WARN/INFO emissions and persisted scope entries.

- **MINOR — tests/canary/test_run_crash_loop.py:317:** The save-failure case uses a first-seen baseline with no crash-loop emission. It therefore cannot detect reversed emit/save ordering or prove that a successful emission followed by failed persistence repeats next tick, as R-07 requires. **Fix:** seed a baseline, trigger a crossing, fail the save after observing emission, then verify unchanged persisted state and repeat emission.

