---
affected_files: []
cycle_number: 2
mission_slug: delivery-doctrine-followups-01M8FBH0
reproduction_command:
reviewed_at: '2026-11-27T21:23:16Z'
reviewer_agent: claude
wp_id: WP03
---

# WP03 review feedback, round 2

**Reviewer:** Codex gpt-6.1-sol (read-only), 2026-11-27. **Lead triage:** claude-opus-5-5, which rated these by realistic likelihood (Kent's practicality rule).
**Range:** 32009aa5c..2b598a215. **Codex verdict:** REQUEST CHANGES.

**Round-1 findings:** all three are closed (Codex probes: retry 1/1/1, verify refusals, receipt validation). The `Path.rename` change is accepted by Codex and the lead.

## Fix (one item)

1. **MINOR, fix it: an unrelated reload line counts as confirmation** (`scripts/deploy/deploy-announce-agent-tool-deny.py` ~L583–592 and L629).
   - **Problem:** the journal is read "since patch_started_at" at one-second resolution, so a reload line from just before the patch, or an unrelated later one, can confirm.
   - **Fix:**
     - capture a journal cursor (for example `journalctl --user -u openclaw-gateway.service --show-cursor -n 0`) immediately before the real patch;
     - store it in the receipt, keeping it across retries;
     - read acknowledgements only `--after-cursor` that point.
   - **Tests:** a reload line before the cursor must not confirm; a line after it must. Use one fixture for both.

## Declined, with the reason (no change)

2. **Retry accepts a changed gateway PID** (~L593–600). A restart between apply and retry loads the persisted deny, so the safety property (the tools are denied at runtime) holds. Requiring the same PID on retry would make any unrelated gateway restart (an update, a crash) fail the deploy permanently until someone intervenes, which is worse in normal use. The post-merge canary records the PID/start time and the effective-tools preview. The lead is recording this as an accepted residual. The first apply still fails on a PID change, as before.

The catalog-only success path stays supplementary, as it is now: unchanged.
