---
work_package_id: WP02
title: Standing Orders — Routing and Vault Operations
lane: "approved"
dependencies: [WP01]
requirement_refs:
- C-001
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- NFR-001
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 008-inbox-processing-migration-WP01
base_commit: c419b9c0eda3b6802fdf24b2fff4bfd66f37b679
created_at: '2026-03-31T03:02:43.919668+00:00'
subtasks: [T006, T007, T008, T009, T010]
agent: claude-code
shell_pid: '68445'
reviewed_by: "Kent Gale"
review_status: "approved"
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
---

# WP02: Standing Orders — Routing and Vault Operations

## Implementation Command

```bash
spec-kitty implement WP02 --base WP01
```

## Objective

Write the AGENTS.md file with standing orders that define the core inbox
processing workflow: content classification, routing table, vault-writer
standards, privacy boundary, edge case handling, and processing log format.

This is the most critical deliverable — it defines what the agent does on
every run.

## Context

- **Source of truth for behavior**: `~/second-brain/.claude/skills/inbox-processor/SKILL.md` (read locally)
- **Vault-writer standards**: `~/second-brain/.claude/skills/vault-writer/SKILL.md` (read locally)
- **Deploy target**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` → deployed to `/data/services/openclaw/inbox-agent/AGENTS.md`
- **Vault path on office2**: `/home/kgale/second-brain/vault/`
- **Standing orders format**: See OpenClaw standing orders docs — AGENTS.md is auto-injected every session
- **CRITICAL**: Read the inbox-processor and vault-writer SKILL.md files in FULL before writing. They are the specification.

## Subtask Guidance

### T006: Routing Table Section

**Purpose**: Encode the complete content classification routing table from
inbox-processor SKILL.md.

**Steps**:
1. Read `~/second-brain/.claude/skills/inbox-processor/SKILL.md` in full
2. Create `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
3. Begin with a standing orders header explaining the agent's authority:
   ```markdown
   # AGENTS.md — Standing Orders: Inbox Processing

   ## Authority

   You are authorized to process Kent's Obsidian inbox autonomously.
   This document defines your complete processing workflow.

   ## Processing Workflow

   ### Step 1: Scan the inbox

   Read all `.md` files in `/home/kgale/second-brain/vault/00-Inbox/`.
   Filter to files where frontmatter contains `status: unprocessed`.
   Skip files with `status: processed` or `status: needs-review`.
   ```

4. Replicate the FULL routing table from inbox-processor — every content
   type and destination. Use the correct office2 vault paths (no `Notes/`):

   | Content type | Destination |
   | --- | --- |
   | Values, beliefs, principles | `01-Constitution/Values.md` |
   | Goal — new or update | `01-Constitution/Goals-MOC.md` |
   | Vision, aspiration, future state | `01-Constitution/Vision.md` |
   | Life story, biography | `01-Constitution/Life-Narrative.md` |
   | Identity statement | `01-Constitution/Identity.md` |
   | Personal brand | `01-Constitution/Personal-Brand.md` |
   | Growth/transformation | `02-Growth/` |
   | Health/fitness | `03-Health/` |
   | Consulting/Intentional | `04-Business/Intentional/` |
   | Acquisition/deal | `04-Business/Acquisition/` |
   | Metal casework | `04-Business/Metal-Casework/` |
   | Financial | `05-Finance/` |
   | Journal reflection | `06-Journal/` |
   | Book/resource/tool | `07-Resources/` |
   | Task/action item | Create Vikunja task (see task bridge section) |
   | Research request | Create Vikunja task in Research project |
   | AI automation idea | `07-Resources/kg-automation/` |
   | Unclassifiable | Leave in 00-Inbox, set `status: needs-review` |

5. Note the change from the original: task items and research requests now
   create Vikunja tasks instead of just logging. The routing table entry
   should reference the task bridge section (written in WP03).

**Validation**:
- [ ] Every content type from inbox-processor SKILL.md is present
- [ ] All vault paths use office2 paths (no `Notes/` prefix)
- [ ] Task and research entries reference the task bridge section

### T007: Vault-Writer Standards Section

**Purpose**: Encode the file operation standards from vault-writer SKILL.md.

**Steps**:
1. Read `~/second-brain/.claude/skills/vault-writer/SKILL.md` in full
2. Add a "File Operation Standards" section covering:
   - Frontmatter standard (required fields: domain, type, updated, status, tags)
   - File naming conventions (Title-Case-With-Hyphens, journal format, inbox format)
   - Creating new notes (check for existing, apply frontmatter, wikilinks, source)
   - Updating canonical documents (01-Constitution/) — integrate, don't overwrite
   - Cross-linking with wikilinks
   - Transform voice dumps (clean filler, preserve meaning, structure for destination)
3. State that all paths are relative to `/home/kgale/second-brain/vault/`

**Validation**:
- [ ] Frontmatter standard matches vault-writer
- [ ] File naming conventions documented
- [ ] Canonical document update rules included
- [ ] Voice dump transformation guidance included

### T008: Privacy Boundary Section

**Purpose**: Encode the absolute privacy rule.

**Steps**:
1. Add a prominent "Privacy — Absolute Rule" section:
   ```markdown
   ## Privacy — Absolute Rule

   **NEVER** read, process, route to, reference, or log any content in or
   from `02-Growth/_private/`. If inbox content mentions private growth work,
   route only to `02-Growth/` public files or `02-Growth/_bridge.md`.
   Never log or reference `_private/` contents. This rule has no exceptions.
   ```

**Validation**:
- [ ] Privacy boundary stated prominently
- [ ] Matches the rule in inbox-processor and vault-writer SKILL.md files

### T009: Edge Case Handling Section

**Purpose**: Encode edge case handling from inbox-processor.

**Steps**:
1. Add an "Edge Cases" section covering:
   - **Empty inbox files**: Mark `status: processed`, note in log
   - **Multi-domain content**: Create primary note in most relevant domain,
     add wikilinks from other locations. Do not duplicate content.
   - **Content that updates existing goals**: Check Goals-MOC.md first,
     update in place if exists
   - **Shared content (Facebook posts, emails)**: Treat as source material,
     extract and route. Reference with `source:` frontmatter.
   - **Unclassifiable content**: Set `status: needs-review`, explain in log

**Validation**:
- [ ] All edge cases from inbox-processor SKILL.md are covered

### T010: Processing Log Format Section

**Purpose**: Define the processing log output.

**Steps**:
1. Add a "Processing Log" section:
   - Location: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
   - If multiple runs per day, append with a time-stamped section header
   - Format from vault-writer SKILL.md:
     ```markdown
     ---
     domain: resources
     type: log
     updated: YYYY-MM-DD
     status: reference
     ---

     # Inbox processing log — YYYY-MM-DD HH:MM

     ## Files processed
     - `Inbox YYYY-MM-DD HHmm.md` — [brief description]

     ## Actions taken
     - [what was created/updated, with wikilinks]

     ## Tasks created
     - [Vikunja tasks with project, label, source]

     ## Items flagged
     - [needs-review, potential-goals, errors]

     ## Summary
     - Files processed: N
     - Notes created: N
     - Notes updated: N
     - Tasks created: N
     - Research tasks created: N
     - Goals routed: N
     - Items flagged: N
     ```
2. State: the processing log is the audit trail. Every action must be logged.
   Every error must be logged. Nothing happens silently.

**Validation**:
- [ ] Log location and format match vault-writer SKILL.md
- [ ] All sections present (files, actions, tasks, flags, summary)
- [ ] "Nothing happens silently" principle stated

## Definition of Done

- [ ] AGENTS.md exists at `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- [ ] Full routing table replicated from inbox-processor SKILL.md
- [ ] Vault-writer standards encoded
- [ ] Privacy boundary prominent and absolute
- [ ] Edge cases covered
- [ ] Processing log format defined
- [ ] Deploy to office2 and verify agent can read it:
  ```bash
  ssh office2-claude "cat > /data/services/openclaw/inbox-agent/AGENTS.md" \
    < scripts/openclaw/agents/felix-admin-capture/AGENTS.md
  ```

## Risks

- **AGENTS.md size**: With the full routing table, standards, and edge cases,
  this file may approach the 20,000 character bootstrap limit. Monitor size.
  If too large, move reference tables to TOOLS.md (also auto-injected).
- **Behavioral drift**: The standing orders must match inbox-processor behavior
  exactly. Any deviation is a bug, not an improvement.

## Activity Log

- 2026-03-31T03:02:44Z – claude-code – shell_pid=67468 – lane=doing – Assigned agent via workflow command
- 2026-03-31T03:04:56Z – claude-code – shell_pid=67468 – lane=for_review – Ready for review: AGENTS.md with full routing table, vault-writer standards, privacy boundary, edge cases, processing log format, and task bridge placeholder. Deployed to office2 and verified agent reads it correctly.
- 2026-03-31T03:07:20Z – claude-code – shell_pid=68445 – lane=doing – Started review via workflow command
- 2026-03-31T03:08:27Z – claude-code – shell_pid=68445 – lane=approved – Review passed: AGENTS.md faithfully replicates all 18 routing entries from inbox-processor, vault-writer standards, Felix goal declaration format, privacy boundary, 5 edge cases, and processing log format. 11KB within 20K bootstrap limit. Deployed and verified on office2.
