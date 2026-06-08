---
affected_files: []
cycle_number: 2
mission_slug: vikunja-client-and-habits-weekly-report-01KTKSFT
reproduction_command:
reviewed_at: '2026-06-08T17:28:38Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
review_artifact_override_at: "2026-06-08T18:06:53Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP03"
review_artifact_override_reason: "merge complete (f5625171)"
---

**Issue 1 (blocking)**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md:259` contradicts the weekly helper failure contract defined at lines 150-164. The weekly workflow requires a `Weekly report unavailable: <reason>` WhatsApp message, but the later Tailscale section groups morning and weekly failures together and instructs the agent to reply `IDLE`. A network failure could therefore silently suppress the required failure render, violating the contract and NFR-002. Split the lane-specific behavior explicitly: morning helper failure replies `IDLE`; weekly helper failure emits the contract's failure render; reply-workflow failures follow Step 4.

WP04 depends on WP03 and must rebase after the corrected WP03 commit is available.
