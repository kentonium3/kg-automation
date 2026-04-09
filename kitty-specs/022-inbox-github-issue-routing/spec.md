# Inbox GitHub Issue Routing

**Feature**: 022-inbox-github-issue-routing
**Mission**: software-dev
**Source**: GitHub issue #146
**Target Branch**: main

---

## Executive Summary

Kent captures system ideas, bugs, and feature requests through voice notes (WisprFlow) alongside personal content. The inbox agent classifies and routes personal content effectively, but system-related items that should become GitHub issues have no routing path — they either get misrouted as Vikunja tasks or flagged for manual review.

This feature adds a GitHub issue routing path triggered by explicit phrases, so Kent can say "file a github issue for improving the escalation threshold logic" in a voice note and have it appear in the issue queue with appropriate labels, ready for prioritization.

Current gaps:

- ❌ No routing path from inbox notes to GitHub issue queue
- ❌ System improvement ideas captured by voice get lost or misrouted
- ❌ No automated label inference for new issues from voice input

---

## Problem Statement

**Current State:**
```
Inbox Content Routing
├─ Action items      → felix-admin-tasker → Vikunja     ✅
├─ Journal entries   → vault journal files               ✅
├─ Health/fitness    → Health-Fitness.md                  ✅
├─ Goal declarations → goal routing                      ✅
├─ AI automation ideas → 07-Resources/kg-automation/     ✅
├─ Unclassifiable   → stays in inbox (needs-review)      ✅
└─ System issues/features/bugs → ???                     ❌
```

**Target State:**
```
Inbox Content Routing
├─ [existing routes unchanged]                           ✅
└─ "File a github issue for..."                          ✅
    ├─ Issue created on kentonium3/kg-automation
    ├─ Title distilled from voice content
    ├─ Area and priority labels inferred
    ├─ spec: brief applied
    └─ Confirmation sent via WhatsApp for review
```

---

## Study These Files First

1. **Inbox agent standing orders**
   - Find: `/data/services/openclaw/inbox-agent/AGENTS.md` on office2
   - Study: the routing table in Step 3 and content classification logic
   - Note: how new content types are added — the GitHub issue type follows this pattern

2. **Tasker delegation pattern**
   - Find: "Task delegation to felix-admin-tasker" section in AGENTS.md
   - Study: how the agent delegates via `openclaw agent --agent` command
   - Note: the issue creation is simpler — direct `gh` CLI call, not inter-agent delegation

3. **Action logging pattern**
   - Find: the action logging table in AGENTS.md
   - Study: existing action types (task_created, task_delegated, etc.)
   - Note: a new action type will be needed for GitHub issue creation

4. **Agent tools**
   - Find: `/data/services/openclaw/inbox-agent/TOOLS.md` on office2
   - Study: how the agent accesses external tools
   - Note: `gh` CLI is available at `/usr/bin/gh`, authenticated as kentonium3

5. **Label taxonomy**
   - Find: existing labels on kentonium3/kg-automation
   - Study: P-label conventions (P0-P3 + type suffix), area/ labels
   - Note: the agent needs to infer from these known labels, not invent new ones

---

## Assumptions

- The trigger phrase is always explicit: "file a github issue", "github issue for", "this is a github issue", or similar clear intent. The agent never infers from generic use of "issue."
- Default target repository is `kentonium3/kg-automation`. The agent recognizes when a request targets a different project and responds that multi-repo is not yet supported.
- `gh` CLI is authenticated on office2 as kentonium3 (confirmed 2026-04-09).
- The inbox agent can execute shell commands (it already does for delegation via `openclaw agent`).
- Kent's WhatsApp reply to the processing summary routes back to the inbox agent through OpenClaw's message routing. The agent handles accept/modify/reject in the same session or a subsequent one.
- Default priority is P2-feature when no urgency signals are present in the text.
- Issue body is a brief summary + original transcription context — not template-formatted. `spec: brief` is applied automatically.
- The GitHub Action for spec lifecycle labels will fire when the issue is created with a P1/P2 label, adding `spec: pending` automatically. The agent does not need to manage spec lifecycle labels beyond `spec: brief`.

---

## Functional Requirements

### FR-001: Detect GitHub Issue Trigger Phrases

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Scan each content block in an inbox note for explicit trigger phrases indicating GitHub issue intent
- Recognized triggers include: "file a github issue", "github issue for", "this is a github issue", "create a github issue", "open a github issue"
- When a trigger is detected, mark the content block for GitHub issue routing
- If a content block contains both a GitHub issue trigger and other content, split them: the issue portion goes to GitHub, the rest routes through existing paths

**Business rules:**
- The word "issue" alone is NOT a trigger — it must be paired with "github"
- Trigger detection must be case-insensitive
- Voice transcription artifacts (filler words, false starts) around the trigger phrase should not prevent detection

**Success criteria:**
- [ ] All listed trigger phrases are reliably detected
- [ ] Generic "issue" mentions do not trigger GitHub routing
- [ ] Mixed content blocks are correctly split

---

### FR-002: Infer Issue Title

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Generate a clear, concise issue title from the content following the trigger phrase
- Title should be a coherent summary, not the raw voice transcription verbatim
- Title should follow existing conventions: "Feature: ...", "Bug: ...", "Infra: ..." prefix based on content type
- Maximum ~80 characters

**Success criteria:**
- [ ] Title reads as a clear description of the issue
- [ ] Title uses appropriate prefix convention
- [ ] Raw transcription artifacts (filler, repetition) are cleaned up

---

### FR-003: Infer Labels

| Field | Value |
|---|---|
| **ID** | FR-003 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Infer the most appropriate area/ label from the content (infrastructure, ea, felix-core, security, docs, task-intel, content, biz-ops)
- Infer the P-level and issue type:
  - Urgency signals ("urgent", "blocking", "critical", "right now") → P1
  - Deferred signals ("when we get to it", "someday", "nice to have") → P3
  - No urgency signal → P2 (default)
  - Content about bugs → P2-bug
  - Content about features/capabilities → P2-feature (or P1/P3 per urgency)
  - Content about infrastructure → P2-infra (or P1/P3 per urgency)
- Apply `spec: brief` to all created issues

**Business rules:**
- The agent must only use labels that exist on the repository — never invent labels
- If the area cannot be determined, omit the area label rather than guessing wrong
- If the type cannot be determined, default to "feature"

**Success criteria:**
- [ ] Area label matches the content domain when domain is clear
- [ ] P-level reflects urgency signals accurately
- [ ] Only existing repository labels are applied
- [ ] `spec: brief` always applied

---

### FR-004: Create the Issue

| Field | Value |
|---|---|
| **ID** | FR-004 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Create a GitHub issue on `kentonium3/kg-automation` using the `gh` CLI
- Issue body contains: a distilled summary paragraph at the top, then the original transcription under a "Source" or "Context" heading
- Apply the inferred labels
- Capture the created issue number and URL for the confirmation message

**Business rules:**
- If `gh` CLI fails (auth expired, network error, rate limit), the agent must log the failure, include it in the processing summary, and mark the content block as `needs-review` so it isn't lost
- The agent must not retry failed issue creation silently — Kent needs to know

**Success criteria:**
- [ ] Issue created with title, body, and labels
- [ ] Issue number and URL captured
- [ ] Failures handled gracefully — content not lost, Kent notified

---

### FR-005: Confirm via WhatsApp and React to Response

| Field | Value |
|---|---|
| **ID** | FR-005 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Include the created issue in the inbox processing summary sent to Kent via WhatsApp
- Show: issue number, title, and proposed labels
- Kent can respond with:
  - Accept ("ok", "good", "yes") → no further action needed
  - Request changes ("change to P1", "add area/security", "wrong area") → agent updates the issue labels
  - Reject ("reject", "cancel", "delete") → agent closes the issue with a comment noting it was rejected from inbox
- Agent must recognize these response intents from natural language, not require exact keywords

**Business rules:**
- If Kent doesn't respond, the issue stands with its initial labels — no timeout action needed
- Label changes must use existing labels only
- The agent must confirm the change was applied ("Updated #147 to P1-feature, area/security")

**Success criteria:**
- [ ] Created issue appears in processing summary with labels
- [ ] Accept, modify, and reject responses handled correctly
- [ ] Label updates confirmed back to Kent
- [ ] Rejected issues closed with explanatory comment

---

### FR-006: Recognize Out-of-Scope Requests

| Field | Value |
|---|---|
| **ID** | FR-006 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- When Kent requests a GitHub issue for a repository other than `kentonium3/kg-automation`, the agent should recognize the request and inform Kent that multi-repo support is not yet available
- When the content doesn't contain enough information to create a meaningful issue, the agent should ask for clarification rather than creating a vague issue

**Success criteria:**
- [ ] Multi-repo requests identified and responded to appropriately
- [ ] Insufficient content flagged rather than creating a useless issue

---

## Non-Functional Requirements

### NFR-001: Zero False Positive Rate

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | High |

Personal tasks, journal entries, and general conversation must never become GitHub issues. The explicit trigger phrase requirement ensures this — the false positive rate should be effectively zero since the trigger is opt-in by Kent.

---

### NFR-002: Issue Creation Reliability

| Field | Value |
|---|---|
| **ID** | NFR-002 |
| **Status** | Proposed |
| **Priority** | High |

When a GitHub issue trigger is detected, the issue must be created or the failure must be reported to Kent. Content must never be silently dropped. Success rate target: 95%+ of triggered requests result in a created issue (failures are network/auth, not agent logic).

---

## Constraints

### C-001: Single Repository

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | Medium |

All issues are created on `kentonium3/kg-automation`. Multi-repo support (Intentional, others) is future work.

### C-002: No Project Board Integration

| Field | Value |
|---|---|
| **ID** | C-002 |
| **Status** | Active |
| **Priority** | Low |

The `gh` token on office2 lacks `project` scope. Created issues are not added to the Felix Roadmap project automatically. Project triage happens separately.

---

## Out of Scope

- ❌ Multi-repo support (future work — notably Intentional project)
- ❌ Duplicate issue detection
- ❌ Template-formatted issue body (issues get `spec: brief`)
- ❌ Adding issues to GitHub project board
- ❌ Interactive voice mode (pending EA-Voice milestone)
- ❌ Automatic `spec: pending` or `spec: ready` management (handled by existing GitHub Action)

---

## User Scenarios & Testing

### Scenario 1: Voice Note with GitHub Issue Trigger

**Actor:** Kent via WisprFlow voice capture
**Input:** "I need to file a github issue for improving the escalation agent's priority threshold logic. Right now it's using a hard threshold but it should be configurable."
**Flow:** Inbox agent scans → detects "file a github issue" → infers title: "Feature: Configurable escalation priority threshold" → infers labels: P2-feature, area/felix-core → creates issue → reports in WhatsApp summary
**Expected outcome:** Issue created with clear title, correct labels, original context in body
**Acceptance:** Issue exists on GitHub with spec: brief label, Kent received confirmation

### Scenario 2: Mixed Content Block

**Actor:** Kent via voice note
**Input:** "Had a great workout this morning, did shoulders and cardio. Also, this is a github issue — the inbox agent should support creating issues for the intentional project too."
**Flow:** Agent splits: workout → Health-Fitness.md, GitHub issue → created on kg-automation noting that multi-repo is not yet supported
**Expected outcome:** Workout routed normally, issue created for the enhancement request
**Acceptance:** Both content blocks routed correctly

### Scenario 3: Kent Rejects an Issue

**Actor:** Kent responding to WhatsApp summary
**Input:** "Reject the issue about threshold logic — I changed my mind"
**Flow:** Agent closes the issue with comment "Rejected from inbox processing"
**Expected outcome:** Issue closed, Kent confirmed
**Acceptance:** Issue state is closed on GitHub

### Scenario 4: Kent Modifies Labels

**Actor:** Kent responding to WhatsApp summary
**Input:** "Change that to P1 and add area/security"
**Flow:** Agent updates issue labels, confirms back
**Expected outcome:** Labels updated on GitHub
**Acceptance:** Issue shows updated labels

### Scenario 5: gh CLI Failure

**Actor:** System — gh auth expired
**Flow:** Agent detects trigger, attempts `gh issue create`, gets auth error → logs failure, includes in processing summary, marks content as needs-review
**Expected outcome:** Kent notified of failure, content preserved for retry
**Acceptance:** No silent data loss, failure visible in summary

### Scenario 6: Generic "Issue" Not Triggered

**Actor:** Kent via voice note
**Input:** "I had an issue with the Wi-Fi today, kept dropping connection"
**Flow:** Agent classifies as journal or personal note → routes normally, NOT to GitHub
**Expected outcome:** No GitHub issue created
**Acceptance:** Content routes through existing path

---

## Key Entities

| Entity | Description |
|---|---|
| Trigger Phrase | Explicit phrase indicating GitHub issue intent ("file a github issue", etc.) |
| Issue Metadata | Inferred title, area label, P-level, and issue type |
| Processing Summary | WhatsApp message delivered to Kent with results including created issues |
| Confirmation Response | Kent's accept/modify/reject reply to the processing summary |

---

## Success Criteria

- Kent can voice-capture a system issue and find it in the GitHub issue queue within one inbox processing cycle
- Inferred titles are coherent summaries, not raw transcription
- Area and priority labels are correct for at least 80% of issues (the confirmation flow catches the rest)
- No personal content is ever routed to GitHub (zero false positives)
- Failed issue creation is always reported to Kent with content preserved
- Kent can accept, modify labels, or reject issues through WhatsApp replies

---

**END OF SPECIFICATION**
