---
affected_files: []
cycle_number: 2
mission_slug: remove-escalation-v1-parity-01KT4VTD
reproduction_command:
reviewed_at: '2026-06-03T02:26:09Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: `docs/design/architecture/data/data-flows.json` still contains the `escalation-event-write-vikunja` flow as a deprecated entry. T009 and the reviewer guidance require this flow to be removed from the architecture data, not retained with deprecated status. Remove the `escalation-event-write-vikunja` entry entirely and regenerate/update `docs/design/architecture/data-flows.md` so the markdown view reflects the JSON state.

**Issue 2**: `docs/runbooks/escalation-ops.md` still contains phantom-subscription operator guidance at lines 211-214. T008 requires phantom-subscription operator guidance to be deleted, and its validation grep should return zero matches for `phantom subscription`. Reword or remove that hard-fail triage bullet so the runbook describes JSONL-native recovery without the removed phantom-subscription detector.
