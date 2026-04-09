---
work_package_id: WP02
title: AGENTS.md — Confirmation, Logging, and Tools
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
history:
- date: '2026-04-09T20:07:16Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md
tags: []
---

# WP02: AGENTS.md — Confirmation, Logging, and Tools

## Objective

Complete the GitHub issue routing workflow by adding the WhatsApp confirmation flow, out-of-scope handling, action logging types, and TOOLS.md GitHub reference. After this WP, the agent has complete instructions for the entire issue lifecycle: detect → create → confirm → react.

## Context

- WP01 added the creation workflow to AGENTS.md on office2
- This WP adds the confirmation/response handling section after WP01's creation section
- TOOLS.md at `/data/services/openclaw/inbox-agent/TOOLS.md` needs a GitHub section
- The inbox agent's processing summary is delivered via WhatsApp — Kent replies to it
- OpenClaw routes WhatsApp replies back to the originating agent
- Repo-side copies updated in WP03

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent claude`

---

## Subtask T006: Write Confirmation Response Handling

**Purpose**: Define how the agent includes created issues in the WhatsApp summary and handles Kent's responses.

**Steps**:
1. SSH to office2, edit AGENTS.md
2. Add after the "Creating the issue" section from WP01:

   ```markdown
   ### Processing summary format

   When one or more GitHub issues were created during this run, include them
   in the processing summary under a "GitHub Issues" heading:

   ```
   **GitHub Issues Created:**
   - #<number>: <title> — labels: <P-label>, <area-label>, spec: brief
     <URL>
   ```

   If multiple issues were created, list each on its own line.

   ### Handling Kent's response

   Kent may reply to the processing summary with instructions about the
   created issue(s). Recognize these response intents:

   **Accept** (no action needed):
   - "ok", "good", "yes", "looks good", "fine", "perfect"
   - No response at all (silence = acceptance, issue stands as-is)

   **Modify labels**:
   - "change to P1", "make it P1", "upgrade priority"
   - "add area/security", "wrong area, should be infrastructure"
   - "change to bug", "this is actually a bug not a feature"
   - Parse the intent and run:
     ```bash
     gh issue edit <number> --repo kentonium3/kg-automation \
       --remove-label "<old-label>" --add-label "<new-label>"
     ```
   - Confirm back: "Updated #<number>: now P1-bug, area/security"

   **Reject**:
   - "reject", "cancel", "delete", "never mind", "remove it"
   - Close the issue:
     ```bash
     gh issue close <number> --repo kentonium3/kg-automation \
       --comment "Rejected from inbox processing per Kent's request."
     ```
   - Confirm back: "Closed #<number>."

   If Kent's response is ambiguous (can't determine accept/modify/reject),
   ask for clarification: "I created #<number> (<title>). Would you like
   to keep it as-is, change the labels, or reject it?"
   ```

**Validation**:
- [ ] Summary format shows issue number, title, labels, URL
- [ ] Accept, modify, and reject intents documented with examples
- [ ] gh commands for modify and reject are correct
- [ ] Ambiguous response handling included

---

## Subtask T007: Write Out-of-Scope Handling

**Purpose**: Define how the agent responds when a request is beyond its current capability.

**Steps**:
1. Add a subsection:

   ```markdown
   ### Out-of-scope requests

   **Multi-repo requests**: If Kent says "file a github issue on intentional"
   or names any repo other than kg-automation, respond:
   "I can currently only create issues on kentonium3/kg-automation.
   Multi-repo support isn't available yet. I've noted the request in
   the processing summary — you can create the issue manually."
   Route the content block to `needs-review` status.

   **Insufficient content**: If the trigger phrase is present but the content
   after it is too vague to create a meaningful issue (e.g., "file a github
   issue for... that thing we talked about"), respond:
   "I detected a GitHub issue request but couldn't determine what the issue
   should be about. The note is preserved in the inbox for manual review."
   Set status to `needs-review`.
   ```

**Validation**:
- [ ] Multi-repo handling documented with example
- [ ] Insufficient content handling documented
- [ ] Content preserved in both cases (not discarded)

---

## Subtask T008: Add GitHub Issue Action Types to Logging Table

**Purpose**: Register new action types so processing logs capture GitHub issue events.

**Steps**:
1. Find the action logging table in AGENTS.md (the `| Action type | Description | Category |` table)
2. Add these rows:

   ```
   | `github_issue_created` | GitHub issue created from inbox content | routine |
   | `github_issue_failed` | GitHub issue creation failed | error |
   | `github_issue_updated` | Issue labels updated per Kent's request | routine |
   | `github_issue_rejected` | Issue closed per Kent's rejection | routine |
   | `github_issue_out_of_scope` | Issue request was out of scope | flagged |
   ```

3. Also add a context field:

   ```
   | `github_issue_number` | int | When a GitHub issue is created or updated |
   | `github_issue_url` | string | When a GitHub issue is created |
   ```

**Validation**:
- [ ] All 5 action types added to logging table
- [ ] Context fields added for issue number and URL
- [ ] Categories are consistent with existing patterns (routine/error/flagged)

---

## Subtask T009: Add GitHub Section to TOOLS.md

**Purpose**: Document the GitHub tool availability and label reference for the agent.

**Steps**:
1. Edit `/data/services/openclaw/inbox-agent/TOOLS.md` on office2
2. Add a new section after the Vikunja API section:

   ```markdown
   ## GitHub

   - **CLI**: `gh` (authenticated as kentonium3)
   - **Skill**: `github` (OpenClaw bundled)
   - **Default repo**: `kentonium3/kg-automation`
   - **Multi-repo**: NOT supported yet — only kg-automation

   ### Available Labels

   **Priority + type** (pick one):
   P1-feature, P2-feature, P3-candidate, P1-infra, P2-infra, P1-bug, P2-bug, P1-rfc, P2-debt

   **Area** (pick at most one):
   area/infrastructure, area/security, area/felix-core, area/ea, area/task-intel, area/content, area/docs, area/biz-ops

   **Always apply**: `spec: brief`
   ```

**Validation**:
- [ ] GitHub section added to TOOLS.md
- [ ] Label list matches AGENTS.md label inference section (from WP01)
- [ ] Multi-repo limitation noted

---

## Definition of Done

- [ ] Confirmation response handling written in AGENTS.md (accept/modify/reject)
- [ ] Out-of-scope handling written (multi-repo, insufficient content)
- [ ] Action logging types added to table (5 new types + 2 context fields)
- [ ] TOOLS.md has GitHub section with label reference
- [ ] All instructions are procedural and Haiku-compatible

## Risks

- **Haiku may not parse natural language responses reliably**: Keep the response intent examples broad and include an ambiguity fallback
- **Label list in TOOLS.md and AGENTS.md could drift**: Both are maintained manually — note in TOOLS.md that AGENTS.md is authoritative

## Reviewer Guidance

- Verify the gh commands for label modification and issue closing are syntactically correct
- Confirm the response intent examples cover Kent's natural communication style
- Check that TOOLS.md label list matches AGENTS.md label list exactly

## Activity Log

- 2026-04-09T21:01:11Z – unknown – Ready for review
