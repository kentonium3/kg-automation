# Implementation Plan: Agent Identity Header in WhatsApp Messages

**Branch**: `main` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/023-agent-identity-whatsapp-header/spec.md`
**Source Issue**: #147

## Summary

Add a `Sent by <agent-id>:<model-short-name>` identity header as the first line of every WhatsApp message from Felix agents. This is a standing-orders-only change — update each agent's AGENTS.md output format section to prepend the header.

## Technical Context

**Platform**: office2 via `ssh office2-claude`
**Change control**: Tier 3 (agent prompts) — no backup required
**Approach**: Hardcode agent ID and model short name in each agent's standing orders. Dynamic detection is unnecessary since model assignments change infrequently and are documented in the agent registry.

## Research Findings

All WhatsApp-sending agents identified through live discovery:

| Agent | Agent ID | Model | Short Name | WhatsApp Delivery |
|---|---|---|---|---|
| Inbox | felix-admin-capture | claude-haiku-4-5 | haiku | Cron delivery to +16179300916 |
| Habits | felix-admin-habits | claude-sonnet-4-6 | sonnet | Cron delivery to +16179300916 |
| Escalation | felix-admin-escalation | claude-sonnet-4-6 | sonnet | Cron delivery to +16179300916 |
| Tasker | felix-admin-tasker | claude-sonnet-4-6 | sonnet | Direct WhatsApp messages to Kent |
| Health Check | main | claude-sonnet-4-6 | sonnet | Cron delivery to +16179300916 |

**5 agents total.** All need the header.

## Implementation Approach

For each agent:
1. Read the AGENTS.md on office2
2. Find the output/summary format section
3. Add an instruction: "Begin every WhatsApp message with: `Sent by <agent-id>:<model-short-name>`" followed by a blank line before the message body
4. The agent ID and model short name are hardcoded — update them if model tier changes

**Model short name mapping:**
- `anthropic/claude-haiku-4-5` → `haiku`
- `anthropic/claude-sonnet-4-6` → `sonnet`

**No research.md needed** — all agents identified, all model assignments known from mission 021.

## Files Modified

### On office2

```
/data/services/openclaw/inbox-agent/AGENTS.md        ← felix-admin-capture:haiku
/data/services/openclaw/habits-agent/AGENTS.md       ← felix-admin-habits:sonnet
/data/services/openclaw/escalation-agent/AGENTS.md   ← felix-admin-escalation:sonnet
/data/services/openclaw/tasker-agent/AGENTS.md       ← felix-admin-tasker:sonnet
```

The `main` agent (health checks) needs investigation — it may use a built-in skill or workspace-level instructions. Planning phase discovered it delivers to WhatsApp but its output format may be controlled differently.

### In kg-automation repo

```
scripts/openclaw/agents/felix-admin-capture/AGENTS.md
scripts/openclaw/agents/felix-admin-habits/AGENTS.md
scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
```

## Branch Contract

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **true**

---

**PLAN COMPLETE** — Ready for `/spec-kitty.tasks --mission 023-agent-identity-whatsapp-header`
