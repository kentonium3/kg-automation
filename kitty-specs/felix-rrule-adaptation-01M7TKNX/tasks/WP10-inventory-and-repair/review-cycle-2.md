---
affected_files: []
cycle_number: 2
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T00:24:00Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP10
---

# WP10 review feedback — cycle 2

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | UI reconciliation counts as Felix-write attribution | scripts/vikunja/rule_inventory.py:335 | The parser accepts synthetic escalation rows with source="reconcile" and habit rows with source="vikunja-ui". Real reconciliation code appends these without writing to Vikunja. Probes classify missing unlimited rules as lost, enabling automatic repair of intentional UI removals. | Require positive write provenance; exclude synthetic/UI reconciliation records and test against both real reconciliation paths.

2. MAJOR | Intake requested values masquerade as executed changes | scripts/vikunja/rule_inventory.py:359 | Intake's applied map includes project/due_date even when those values already match. A real apply_line probe changed only labels, made zero task-body writes, yet this parser attributed a write and classified the missing rule as lost. | Use evidence of executed task-field mutations; conservatively exclude ambiguous historical records. Add regression tests for unchanged project/due values combined with label changes.

VERDICT: REJECT
## Required (last cycle before arbiter)
- Positive write provenance only: exclude escalation source=reconcile (and any synthesized record), habit source=vikunja-ui / reconcile records; for intake require evidence the task body was actually PATCHed (e.g. a recorded field_changes/patched set, not the requested applied map) — if historical intake records carry no such evidence, treat them as non-attribution. Regression tests against the real writers' record shapes (escalation reconcile_completions, habits reconcile, intake apply_line with label-only change).
