# Agent Identity Header in WhatsApp Messages

**Feature**: 023-agent-identity-whatsapp-header
**Mission**: software-dev
**Source**: GitHub issue #147
**Target Branch**: main

---

## Executive Summary

When Kent receives WhatsApp messages from Felix agents, all messages appear to come from the same source with no indication of which agent sent it or what model produced it. During troubleshooting or when verifying model tiering, Kent has to guess from the message content which agent is speaking.

This feature adds a single identity line at the top of every WhatsApp message from any Felix agent, showing the agent name and model.

Current gaps:

- ❌ WhatsApp messages don't identify which agent sent them
- ❌ No way to tell at a glance if a message is from inbox, habits, escalation, or tasker
- ❌ No visibility into which model produced the message

---

## Problem Statement

**Current State:**
```
WhatsApp message from Felix
├─ Message content              ✅
├─ Which agent sent it          ❌ unknown
└─ Which model was used         ❌ unknown
```

**Target State:**
```
WhatsApp message from Felix
├─ "Sent by felix-admin-capture:haiku"  ✅ identity header (first line)
├─ Message content                       ✅
└─ Agent and model visible at a glance   ✅
```

---

## Study These Files First

1. **All agent AGENTS.md files on office2**
   - Find each agent's workspace under `/data/services/openclaw/`
   - Study the output/summary format sections — where WhatsApp message content is assembled
   - Identify which agents send WhatsApp messages and which only log internally

2. **Agent IDENTITY.md files**
   - Each agent has an IDENTITY.md with its agent ID
   - Confirm the exact agent ID string for each

3. **OpenClaw session metadata**
   - Study `model_change` events in session JSONL files — contains `modelId`
   - Determine whether the agent can read its own model at runtime or if the model should be referenced from standing orders

---

## Assumptions

- The identity header format is: `Sent by <agent-id>:<model-short-name>` (e.g., "Sent by felix-admin-capture:haiku")
- Short model names are used: "haiku" for claude-haiku-4-5, "sonnet" for claude-sonnet-4-6, "opus" for any opus model
- The header is the first line of every WhatsApp message, before any other content
- Every agent that sends WhatsApp messages gets this header — the planning phase discovers the complete list
- The model name can be hardcoded in standing orders (acceptable for v1 since assignments change infrequently) or dynamically detected — the planning phase determines which approach

---

## Functional Requirements

### FR-001: Add Identity Header to All WhatsApp Messages

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Every WhatsApp message from a Felix agent begins with an identity line
- Format: `Sent by <agent-id>:<model-short-name>`
- The header appears as the first line, before any other message content
- Model short names: haiku, sonnet, opus (not full API identifiers)

**Success criteria:**
- [ ] Every WhatsApp-sending agent includes the identity header
- [ ] Agent name is correct for each agent
- [ ] Model name matches the agent's configured model
- [ ] Header is the first line of the message

---

### FR-002: Identify All WhatsApp-Sending Agents

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Discover which agents send WhatsApp messages (known: capture, habits, escalation; uncertain: tasker, health check/main)
- Update every confirmed WhatsApp-sending agent's standing orders
- Document the finding so future agents know they need the header

**Success criteria:**
- [ ] Complete list of WhatsApp-sending agents documented
- [ ] All identified agents updated with the header instruction

---

## Non-Functional Requirements

### NFR-001: No Impact on Message Readability

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | Medium |

The identity header must not clutter the message or reduce readability. A single short line (under 50 characters) followed by a blank line before the message body is the maximum acceptable overhead.

---

## Constraints

### C-001: Model Name Source

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | Low |

If the agent cannot dynamically detect its model at runtime, the model short name may be hardcoded in standing orders. This means model name in the header must be updated whenever the agent's model tier changes. This is an acceptable tradeoff for v1.

---

## Out of Scope

- ❌ Alerting when an unexpected model is detected
- ❌ Historical model usage tracking (#138)
- ❌ Changing agent display names, emojis, or identity cards
- ❌ Adding headers to non-WhatsApp outputs (processing logs, vault files)

---

## User Scenarios & Testing

### Scenario 1: Inbox Processing Summary

**Actor:** felix-admin-capture after inbox run
**Expected message:**
```
Sent by felix-admin-capture:haiku

Inbox processing complete — 2026-04-10
Files scanned: 28 | Unprocessed: 1
...
```
**Acceptance:** First line shows agent name and model

### Scenario 2: Habit Check-in

**Actor:** felix-admin-habits delivering morning check-in
**Expected message:**
```
Sent by felix-admin-habits:sonnet

Morning check-in — Thursday, April 10:
1. Get steps in today
...
```
**Acceptance:** First line identifies habits agent on sonnet

### Scenario 3: Escalation Alert

**Actor:** felix-admin-escalation detecting overdue tasks
**Expected message:**
```
Sent by felix-admin-escalation:sonnet

⚠️ Tasks needing attention:
...
```
**Acceptance:** First line identifies escalation agent

---

## Success Criteria

- Every WhatsApp message Kent receives from a Felix agent starts with the identity header
- Kent can identify the sending agent and model at a glance without reading the message body
- No existing message content is lost or reformatted
- Header adds no more than one line of overhead

---

**END OF SPECIFICATION**
