# Validation Report: Habits and Escalation Agents

**Date**: 2026-04-09T17:50Z

---

## felix-admin-habits (Habits Agent)

### Daily Check-in — **FAIL**

**Test**: Triggered `habits-morning-checkin` cron with Haiku model.

**Sonnet baseline**: Produced a clean formatted check-in in 1 assistant turn:
```
Morning check-in — Thursday, April 9:
1. Get steps in today
2. Read 30 min minimum
3. Evening shoulder PT
Reply with what you've done...
```
Tokens: in=1, out=98, cost=$0.0089

**Haiku result**: Produced 12 assistant turns of reasoning about Vikunja task data but **never delivered a formatted check-in message**. Got stuck trying to infer habit frequencies from task metadata instead of following the standing orders workflow. Never reached the point of sending a message to Kent.

Tokens: in=3, out=859, cost=$0.0085

**Failure mode**: Haiku couldn't follow the multi-step workflow (query Vikunja → determine today's habits → format check-in → deliver). It got lost in data analysis instead of executing the procedure. This is a task-following failure, not a reasoning quality issue.

### Weekly Review — **NOT TESTED**

Daily check-in failed, so the entire habits agent stays on Sonnet. Weekly review (which requires trend reasoning) would be even harder for Haiku. No point testing.

### Verdict: **FAIL — Habits agent stays on Sonnet (pinned)**

The habits agent requires procedural task execution across multiple tool calls with Vikunja API interaction. Haiku cannot reliably execute this workflow. Future split (#141) will separate daily check-in from weekly review, at which point daily may be re-validated on a cheaper model with a simpler prompt.

---

## felix-admin-escalation (Escalation Agent)

### Escalation Detection — **FAIL (false positive)**

**Test**: Triggered `escalation-daily` cron with Haiku model.

**Sonnet baseline** (same day, 12:02 UTC):
- Task 41 (van check, priority 3/high, due today): **Escalated** Level 1 ✅
- Task 42 (lawn contract, priority 2/medium, due today): **Not escalated** (priority < 3, below at-risk threshold) ✅
- Task 24 (priority 0): Filtered out ✅

**Haiku result** (17:49 UTC):
- Task 41 (van check, priority 3/high): **Escalated** Level 1 ✅
- Task 42 (lawn contract, priority 2/medium): **Escalated** Level 1 ⚠️ **FALSE POSITIVE**
- Applied looser threshold than standing orders define

**Failure mode**: Haiku applied a broader escalation threshold (priority >= 2 instead of >= 3 for at-risk). While this is a false positive rather than a false negative (no missed escalations), it means Kent would receive unnecessary alerts. Over time this creates alert fatigue and undermines trust in the escalation system.

**Token usage**: Haiku cost $0.0058 vs Sonnet comparable run.

### Verdict: **FAIL — Escalation agent stays on Sonnet (pinned)**

The escalation agent requires precise threshold application for priority-based filtering. Haiku applied a looser threshold, creating false positives. Given the high consequence of this agent (missed escalations or alert fatigue), it must stay on Sonnet.

---

## Summary

| Agent | Task | Haiku Verdict | Key Finding | Recommendation |
|---|---|---|---|---|
| felix-admin-capture | Inbox scan | **PASS** | All content blocks classified and routed correctly | Move to Haiku |
| felix-admin-habits | Daily check-in | **FAIL** | Couldn't complete multi-step workflow — got stuck reasoning | Stay on Sonnet |
| felix-admin-habits | Weekly review | **NOT TESTED** | Daily failed; weekly would be harder | Stay on Sonnet |
| felix-admin-escalation | Escalation detection | **FAIL** | False positive — applied wrong priority threshold | Stay on Sonnet |

## Final Model Assignment Table

| Agent | Final Model | Policy | Rationale |
|---|---|---|---|
| main | anthropic/claude-sonnet-4-6 | pinned | Orchestrator — no validation needed |
| felix-admin-capture | anthropic/claude-haiku-4-5 | optimizable | PASS — routing accuracy equivalent, 97% cost reduction |
| felix-admin-habits | anthropic/claude-sonnet-4-6 | pinned | FAIL — can't execute multi-step Vikunja workflow on Haiku |
| felix-admin-escalation | anthropic/claude-sonnet-4-6 | pinned | FAIL — false positive on priority threshold |
| felix-admin-tasker | anthropic/claude-sonnet-4-6 | pinned | Complex reasoning — pre-classified, no validation needed |

## Cost Impact

With only `felix-admin-capture` moving to Haiku:
- Inbox: 240 runs/month × ~$0.004 = ~$1/month (was ~$36/month on Sonnet)
- Savings: ~$35/month (~30% reduction from baseline)
- Remaining agents stay on Sonnet: ~$79/month
- **Projected total: ~$80/month** (down from ~$115/month)

This is below the 60% reduction target (NFR-001). The savings are limited because only 1 of 5 agents can move to Haiku. Future improvements:
- #141 (split habits agent) may allow daily check-in on Haiku with a simpler prompt
- Prompt engineering for escalation could make its threshold logic more explicit for cheaper models
- Future cheaper models may handle these workflows better

## All Models Reverted

All agents confirmed reverted to Sonnet after testing. Production is unchanged until WP04 deploys.
