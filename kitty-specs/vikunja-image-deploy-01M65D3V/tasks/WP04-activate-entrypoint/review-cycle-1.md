---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:14:34Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP04
---

# WP04 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 HIGH, 2 MEDIUM, 1 LOW)

1. **HIGH — Overall deadlines are not enforced across inspections.** `scripts/deploy/deploy-vikunja-release-activate.py:382–388,474–498`: image/container inspections each receive an independent 30-second timeout. `_untag_active()` also uses a removal timeout calculated before its first inspection. Cleanup can consequently take roughly 200 seconds despite its 120-second budget; the 35-second reserve is insufficient. Cutover inspections similarly escape the remaining outage budget. Pass the shared deadline through every subprocess and recalculate immediately before each call.

2. **MEDIUM — Failed success replay is not read-only.** `scripts/deploy/deploy-vikunja-release-activate.py:327,535,549`: reconciliation failures attach `detail_private`, while `--apply` supplies a private-log root to `core.run_cli()`. That writes a new log through `core.py:290,304`. Wrong-version or inspection failures can therefore write files on every five-minute retry. Replay must suppress filesystem logging, and tests must check filesystem changes alongside Docker verbs.

3. **MEDIUM — Failure tests miss consequential partial effects.** `tests/deploy/test_deploy_vikunja_release_activate.py:795–807`: the cleanup-down failure test first fails `up` before creating a container, so teardown fails while already stopped. It never establishes the promised no-container result for a running rejected release. The fake also raises timeouts before applying effects (`:180–185`), leaving partial starts untested. Deadline tests (`:838–858`) advance commands beyond their supplied timeouts rather than exercising realistic cumulative exhaustion. Add partially completed operations, crash/replay boundaries, and aggregate-budget assertions.

4. **LOW — Durable phase evidence lags the documented stop boundary.** `scripts/deploy/deploy-vikunja-release-activate.py:393–400`: `stopped` is recorded only after untagging and inspections. A crash between successful `down` and untag leaves `started`, contrary to R-21’s recovery description. Replay still refuses safely, but the marker does not identify that boundary accurately.

I found no rollback-image retag path violating INV-1. The normal snapshot path enforces INV-2’s required order. Preconditions, `v2.4.0` handling, Compose arguments, output sanitization, mode dispatch, and committed executable mode appear consistent with the supplied authority. Crash-after-retag behavior retains R-21’s accepted residual risk.

Static review only; the test suite was not run. No files changed and no network, SSH, or Docker calls were made.

**REQUEST CHANGES**
