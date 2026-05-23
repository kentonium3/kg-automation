---
affected_files: []
cycle_number: 5
mission_slug: main-verbatim-passthrough-01KSATRP
reproduction_command:
reviewed_at: '2026-05-23T17:29:55Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: The `Heartbeats` compression removed concrete standing-order rules, which violates WP01's requirement to preserve all rules while trimming. In the base file, this section explicitly preserved the default heartbeat prompt constraint (`Do not infer or repeat old tasks from prior chats`) and required timestamp tracking in `memory/heartbeat-state.json`; both are absent from the new compressed section. Restore these rules in terse form while keeping `scripts/openclaw/agents/main/AGENTS.md` under 14,000 bytes.

Evidence:
- Base: `scripts/openclaw/agents/main/AGENTS.md` included the default heartbeat prompt with "Do not infer or repeat old tasks from prior chats."
- Base: the same section required "Track your checks in `memory/heartbeat-state.json`" with `lastChecks` state.
- Current: the compressed `Heartbeats` section does not preserve either rule.

Suggested fix: Add one compact sentence under `## 💓 Heartbeats - Be Proactive!`, for example: "Do not infer or repeat old tasks from prior chats; track periodic checks in `memory/heartbeat-state.json` (`lastChecks`)." Re-run the existing `wc -c` and grep validations after the edit.
