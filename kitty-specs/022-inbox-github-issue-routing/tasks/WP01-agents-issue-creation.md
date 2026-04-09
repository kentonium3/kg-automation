---
work_package_id: WP01
title: AGENTS.md — Issue Creation Workflow
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-022-inbox-github-issue-routing
base_commit: 6bdced9ac55e7e79edad9c8200d09f0f3c18ff9e
created_at: '2026-04-09T20:49:34.473020+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "23571"
agent: "claude"
history:
- date: '2026-04-09T20:07:16Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
tags: []
---

# WP01: AGENTS.md — Issue Creation Workflow

## Objective

Add GitHub issue routing to the inbox agent's standing orders on office2. This covers: adding the routing table entry, defining trigger phrase detection, title and label inference, the `gh issue create` command, and error handling. After this WP, the agent can detect a GitHub issue trigger and create the issue — but confirmation handling comes in WP02.

## Context

- Agent workspace: `/data/services/openclaw/inbox-agent/` on office2 (`ssh office2-claude`)
- File to modify: `AGENTS.md` in the workspace directory
- The agent already has a routing table in Step 3 with content types and destinations
- The agent already delegates to felix-admin-tasker for Vikunja tasks — the GitHub path is simpler (direct CLI call)
- OpenClaw's bundled `github` skill wraps `gh` CLI, but the agent can also call `gh` directly since it has shell access
- `gh` is authenticated on office2 as kentonium3
- The agent runs on Haiku — instructions must be clear and procedural to avoid the multi-step reasoning failures seen in mission 021
- Repo-side copy at `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` is updated in WP03

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent claude`

---

## Subtask T001: Add GitHub Issue Row to Routing Table

**Purpose**: Add the new content type to the agent's Step 3 classification table so it knows GitHub issue requests are a recognized category.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Read `/data/services/openclaw/inbox-agent/AGENTS.md`
3. Find the routing table in Step 3 (the `| Content type | Destination | Action |` table)
4. Add a new row:

   ```
   | GitHub issue request | GitHub (kentonium3/kg-automation) | Create issue via gh CLI, confirm via WhatsApp |
   ```

5. Place it after "AI automation capability/idea" and before "Unclassifiable" — it should be near the bottom since it's a specialized route

**Validation**:
- [ ] New row appears in routing table
- [ ] Placement is logical (before unclassifiable catch-all)

---

## Subtask T002: Write Trigger Phrase Detection Rules

**Purpose**: Define how the agent recognizes that a content block should become a GitHub issue.

**Steps**:
1. After the routing table section, add a new section: `## GitHub issue creation`
2. Write the trigger detection rules:

   ```markdown
   ## GitHub issue creation

   When a content block contains an explicit GitHub issue trigger phrase,
   create a GitHub issue instead of routing through other paths.

   ### Trigger detection

   A content block is a GitHub issue request ONLY when it contains one of
   these explicit phrases (case-insensitive):
   - "file a github issue"
   - "github issue for"
   - "this is a github issue"
   - "create a github issue"
   - "open a github issue"

   The word "issue" alone is NOT a trigger. It must appear with "github."
   Examples that are NOT triggers:
   - "I had an issue with..." → route as journal/personal
   - "there's an issue in the code" → route as AI automation idea
   - "the issue is that..." → route based on surrounding content

   If a content block contains a GitHub issue trigger AND other content
   (e.g., "Had a great workout. Also, file a github issue for..."),
   split the block: route the non-issue content normally, create a
   GitHub issue from the issue-related portion.
   ```

3. Keep the language procedural and explicit — Haiku needs clear rules, not inference

**Validation**:
- [ ] Trigger phrases listed explicitly
- [ ] Non-trigger examples documented
- [ ] Mixed content splitting described

---

## Subtask T003: Write Title Inference Instructions

**Purpose**: Tell the agent how to generate a clean issue title from voice transcription.

**Steps**:
1. Add a subsection under "GitHub issue creation":

   ```markdown
   ### Title inference

   Generate a concise issue title from the content following the trigger phrase.

   Rules:
   1. Remove the trigger phrase itself ("file a github issue for" → remove)
   2. Distill the remaining content into a clear summary (~60-80 characters max)
   3. Remove voice transcription artifacts: filler words ("um", "like", "you know"),
      false starts, and repetitions
   4. Add the appropriate prefix based on content:
      - Describing a new capability → "Feature: ..."
      - Describing something broken → "Bug: ..."
      - Describing infrastructure/server work → "Infra: ..."
      - Requesting investigation/analysis → "RFC: ..."
      - If unclear, default to "Feature: ..."

   Example:
   - Input: "file a github issue for, um, improving the escalation agent's priority
     threshold logic, it should be configurable instead of hard-coded"
   - Title: "Feature: Configurable escalation priority threshold"
   ```

**Validation**:
- [ ] Title generation rules are clear and procedural
- [ ] Example shows transformation from raw voice to clean title
- [ ] Prefix convention matches existing issue naming

---

## Subtask T004: Write Label Inference Instructions

**Purpose**: Tell the agent how to select the right labels from the known set.

**Steps**:
1. Add a subsection:

   ```markdown
   ### Label inference

   Apply labels from this known set. Never invent labels.

   **Priority + type label** (pick exactly one):

   Determine type first:
   - New capability or enhancement → "feature"
   - Something broken → "bug"
   - Infrastructure/server/config → "infra"
   - Investigation or discussion → "rfc"

   Then determine priority from urgency signals:
   - "urgent", "blocking", "critical", "right now", "asap" → P1
   - "when we get to it", "someday", "nice to have", "low priority" → P3
   - No urgency signal → P2 (default)

   Combine: e.g., P2-feature, P1-bug, P2-infra, P1-rfc

   **Area label** (pick at most one, omit if uncertain):
   - area/infrastructure — office2, Docker, networking, hardware, credentials
   - area/security — hardening, access control, audit
   - area/felix-core — constitution, agent registry, operating modes
   - area/ea — executive assistant capability
   - area/task-intel — Vikunja, task enrichment, escalation
   - area/content — transcription, media processing
   - area/docs — documentation architecture, Obsidian
   - area/biz-ops — Intentional LLC, business

   **Always apply**: `spec: brief`

   Final label set example: `P2-feature`, `area/felix-core`, `spec: brief`
   ```

**Validation**:
- [ ] All valid P-labels listed
- [ ] All valid area labels listed with descriptions
- [ ] Default behavior (P2-feature) clear
- [ ] "spec: brief" always-apply rule stated

---

## Subtask T005: Write gh Issue Create Command and Error Handling

**Purpose**: Define the exact command the agent runs and what to do when it fails.

**Steps**:
1. Add a subsection:

   ```markdown
   ### Creating the issue

   Run this command to create the issue:

   ```bash
   gh issue create \
     --repo kentonium3/kg-automation \
     --title "<inferred title>" \
     --label "<P-label>" --label "<area-label>" --label "spec: brief" \
     --body "<issue body>"
   ```

   If no area label was inferred, omit that `--label` flag.

   **Issue body format**:
   ```
   ## Summary

   <1-2 sentence distilled summary of what's needed and why>

   ## Source

   Captured from inbox note on <date>.

   > <original transcription text, quoted>
   ```

   **After creating**: capture the issue URL from the command output.
   Include it in the processing summary (Step 6 below).

   ### Error handling

   If `gh issue create` fails:
   1. Log the error with action type `github_issue_failed`
   2. Include the failure in the processing summary:
      "⚠️ GitHub issue creation failed: <error message>. Content preserved in inbox."
   3. Set the content block's status to `needs-review` — do NOT discard it
   4. Do NOT retry — Kent will see the failure in the summary

   Common failure modes:
   - "Your credit balance is too low" → API/auth issue, not gh CLI issue. Unlikely for gh.
   - "Bad credentials" / "authentication" → gh auth expired. Report to Kent.
   - Network timeout → transient. Report to Kent.
   ```

**Validation**:
- [ ] Command template is complete and correct
- [ ] Issue body format defined
- [ ] Error handling covers common failure modes
- [ ] Content is never silently lost on failure

---

## Definition of Done

- [ ] AGENTS.md on office2 has the new routing table row
- [ ] Trigger detection section written with explicit rules and examples
- [ ] Title inference section written with rules and example
- [ ] Label inference section written with full label list
- [ ] Issue creation command template and error handling written
- [ ] All instructions are procedural and clear (Haiku-compatible)

## Risks

- **Haiku may struggle with the gh CLI call**: Keep the command as a single template, not multi-step reasoning. If Haiku can't execute it, we'll know from WP03 testing.
- **Label list may be incomplete**: The list was current as of 2026-04-09. New labels added later won't be known to the agent until AGENTS.md is updated.

## Reviewer Guidance

- Read the instructions as if you're Haiku — are they unambiguous? Could you follow them step-by-step?
- Verify the trigger phrase list covers natural voice patterns
- Verify the label list matches `gh label list --repo kentonium3/kg-automation`
- Check that error handling never loses content

## Activity Log

- 2026-04-09T20:49:35Z – claude – shell_pid=23571 – Assigned agent via action command
- 2026-04-09T20:59:41Z – claude – shell_pid=23571 – Ready for review
