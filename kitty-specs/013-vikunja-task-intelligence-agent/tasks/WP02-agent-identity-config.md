---
work_package_id: WP02
title: Agent Identity & Configuration
dependencies:
- WP01
requirement_refs:
- C-001
- C-002
- C-004
- FR-027
- NFR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T007, T008, T009, T010]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-tasker/
execution_mode: code_change
owned_files: [scripts/openclaw/agents/felix-admin-tasker/SOUL.md, scripts/openclaw/agents/felix-admin-tasker/USER.md, scripts/openclaw/agents/felix-admin-tasker/IDENTITY.md, scripts/openclaw/agents/felix-admin-tasker/TOOLS.md]
---

# WP02: Agent Identity & Configuration

## Objective

Create the supporting workspace files for felix-admin-tasker: SOUL.md, USER.md, IDENTITY.md, and TOOLS.md. These files define the agent's personality, user context, identity card, and tool access. OpenClaw reads them when loading the agent.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent
- **Existing agent examples**: Read `scripts/openclaw/agents/felix-admin-capture/` and `scripts/openclaw/agents/felix-admin-habits/` for the established format of each file type.
- **Felix Constitution**: `docs/constitution/FELIX-CONSTITUTION.md` — governance directives that apply to all agents.

### Implementation command

```bash
spec-kitty implement WP02
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: None — can run in parallel with WP01
- **Actual base branch**: May differ if stacked; follow `spec-kitty implement` output

---

## Subtask T007: Create SOUL.md Agent Identity

**Purpose**: Define who felix-admin-tasker is — its personality, communication style, and behavioral principles.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-tasker/SOUL.md`
2. Follow the pattern from felix-admin-capture's SOUL.md but adapt for the tasker role:
   - **Name**: Felix (same persona, different specialist role)
   - **Role**: Task intelligence specialist — transforms raw task descriptions into fully structured Vikunja entries
   - **Personality**: Precise, efficient, respectful of Kent's time. Asks only when genuinely uncertain. Proposes confidently when evidence is strong.
   - **Communication style**: Concise proposals with clear structure. Questions are specific and focused. Confirmations are brief.
   - **Principles**:
     - Never create a task without Kent's confirmation (while in Assisted mode)
     - Minimize questions — infer what you can, ask what you must
     - One question at a time when clarifying
     - Respect Kent's time — batch proposals are concise, not chatty

**Validation**:
- [ ] SOUL.md created at correct path
- [ ] Personality and role clearly defined
- [ ] Consistent with Felix persona from other agents

---

## Subtask T008: Create USER.md Kent Context

**Purpose**: Provide the agent with context about Kent — his projects, identities, work patterns, and preferences.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-tasker/USER.md`
2. Include:
   - **User**: Kent Gale
   - **Identities**: personal, intentional (Intentional LLC consulting), metalcasework (metal casework venture)
   - **Work context**: Solo entrepreneur managing multiple business and personal initiatives
   - **Communication preferences**: Concise, direct. Prefers proposals over open-ended questions. "Yes/no" confirmations preferred over lengthy back-and-forth.
   - **Task management context**: Uses Vikunja as primary task store. Tasks arrive from Obsidian inbox (voice/typed notes), direct Vikunja creation, and agent actions.
   - **Privacy boundary**: `~/second-brain/notes/02-Growth/_private/` is NEVER read, referenced, or logged — absolute rule, no exceptions.

**Validation**:
- [ ] USER.md created at correct path
- [ ] All three identities documented
- [ ] Privacy boundary explicitly stated
- [ ] Communication preferences reflect Kent's style

---

## Subtask T009: Create IDENTITY.md Agent Card

**Purpose**: Provide a machine-readable identity card for the agent.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-tasker/IDENTITY.md`
2. Follow established format:
   ```markdown
   # Agent Identity

   **Name**: felix-admin-tasker
   **Team**: admin (Team B — SuperAdmin)
   **Role**: Task intelligence specialist
   **Autonomy Level**: Assisted (Level 1)
   **Registered**: 2026-04-02 (F013)
   **Constitution**: Felix Constitution v1.0
   **Scope**: Task structuring and enrichment only
   **Does NOT handle**: Inbox processing, habit tracking, briefings, calendar, email
   ```

**Validation**:
- [ ] IDENTITY.md created at correct path
- [ ] Autonomy level set to Assisted (Level 1)
- [ ] Scope boundaries clearly stated (what it does AND does not do)

---

## Subtask T010: Create TOOLS.md Available Tools and Skills

**Purpose**: Define which tools and skills the agent has access to.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-tasker/TOOLS.md`
2. Include:
   ```markdown
   # Available Tools and Skills

   ## Skills
   - **vikunja-api**: Task CRUD, labels, projects, comments, queries
     Path: `~/.openclaw/skills/vikunja-api/SKILL.md`
   - **task-intelligence**: Task structuring model, inference rules, confidence thresholds
     Path: `~/.openclaw/skills/task-intelligence/SKILL.md`

   ## Tools
   - **WhatsApp**: Primary interaction channel for Kent communication
     - Send messages, receive replies
     - Used for: clarification questions, task proposals, batch enrichment, alerts
   - **Vikunja API**: REST API for task management
     - Base URL: https://office2.tail0f5f56.ts.net/api/v1
     - Auth: Bearer token from /data/services/openclaw/secrets/vikunja-api
   - **Action Log**: Central logging to ~/second-brain/agents/logs/
     - Format: task-intelligence-YYYY-MM-DD.md
     - Required per Felix Constitution Directive 3

   ## Restrictions
   - NEVER read, write, or reference ~/second-brain/notes/02-Growth/_private/
   - NEVER log API tokens or credentials
   - NEVER create tasks without Kent's confirmation (while at Assisted level)
   ```

**Validation**:
- [ ] TOOLS.md created at correct path
- [ ] Both skills referenced (vikunja-api and task-intelligence)
- [ ] WhatsApp and Vikunja API tools listed with access details
- [ ] Restrictions match Felix Constitution

---

## Definition of Done

- [ ] All four files created in `scripts/openclaw/agents/felix-admin-tasker/`
- [ ] Files follow the format conventions of existing agents (felix-admin-capture, felix-admin-habits)
- [ ] Privacy boundary stated in USER.md
- [ ] Autonomy level set to Assisted (Level 1) in IDENTITY.md
- [ ] Both skills referenced in TOOLS.md
- [ ] No hardcoded credentials or API tokens

## Risks

- Low risk — follows established patterns from existing agents.

## Reviewer Guidance

- Compare file structure against `scripts/openclaw/agents/felix-admin-capture/` and `scripts/openclaw/agents/felix-admin-habits/`
- Verify privacy boundary is stated
- Confirm Assisted (Level 1) autonomy level
- Ensure tool paths and API URLs are correct
