# Contract: operator smoke runbook shape

**Deliverable**: `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`
**Authored by**: implementation WP (per plan IC-13)
**Run by**: operator (Kent), post-deploy
**Owner of regression coverage**: SC-001, SC-002, SC-005, SC-006

## Required sections

1. **Pre-conditions** — what must be true before running smoke
2. **DM round-trips** — one checkbox per subagent + calendar clarification round-trip
3. **Non-DM checks** — doc-auditor `last-tick.json`, scheduled-flow observations
4. **24h observation window** — what to watch passively
5. **Decision criteria** — when to mark mission complete vs file regression bug
6. **Verification record** — initials + timestamps per check

## DM coverage matrix

| Subagent | Test DM | Expected behavior | Success criterion |
|---|---|---|---|
| `felix-admin-habits` | "mark habits 1, 3, 5 complete" (or appropriate-for-today phrasing) | Confirmation reply listing the habits marked | SC-001 (the bug's originating regression) |
| `felix-admin-capture` | A WhatsApp message that should be inbox-routed (Kent picks one matching current inbox usage) | Inbox classification + Vikunja task creation + structured reply | SC-005 |
| `felix-admin-tasker` | "what's on my list today" | Task list reply | SC-005 |
| `felix-admin-escalation` | (path TBD by operator — escalation triggers are domain-specific) | Escalation reply | SC-005 |
| `felix-admin-calendar` (NEW) | "schedule a 30-min check-in tomorrow at 2pm" | Either event created (success envelope acknowledged in chat) OR clarification asked | SC-002 |
| `felix-admin-calendar` clarification round-trip | Reply to clarification prompt with the missing info | Event created | SC-002 (round-trip variant) |

## Non-DM coverage matrix

| Surface | Check | Cadence |
|---|---|---|
| `felix-doc-auditor` driver | `last-tick.json` freshness < 1h | Once post-deploy, then 24h |
| Morning checkin | Fires at 7am ET, delivers normal message | Next morning |
| IDLE pings | Fire on normal cadence | 24h observation |
| Periodic digests | Fire on schedule (per `service-inventory.json`) | 24h observation |
| journal | Zero `truncating in injected context` warnings for `agent:main:*` | 24h observation |
| Audit baselines | Post-rebaseline, audit log clean | Next audit cycle (~24h) |

## Decision criteria

| Outcome | Action |
|---|---|
| All checks pass within 24h | Mark mission complete; merge commit footer includes `Rebaseline: completed at <ts>` |
| One subagent DM fails | File regression bug citing this runbook + observed symptom; do NOT mark mission complete; consider rollback |
| Truncation warning observed | File bug; possibly indicates main/AGENTS.md tightening was insufficient or another section grew |
| Scheduled outbound flow misses | File bug citing service-inventory.json schedule and observed time |
| doc-auditor `last-tick.json` stale | NOT a regression caused by this mission (separate substrate); note observation but do not block mission |
| Rebaseline omitted | Audit alerts fire next day. Operator catches up by running canonical command and adding the footer to merge commit retroactively. |

## What this contract is NOT

- NOT a synthetic-message injector. No automated subagent invocation. Per `feedback_live_integration_tests`.
- NOT a substitute for the deploy script's automated checks. The deploy script's pytest + journal-grep run independently; this runbook adds the behavioral layer that scripts can't verify.
- NOT a free-form QA exploration. Each row is a check with a binary outcome.
