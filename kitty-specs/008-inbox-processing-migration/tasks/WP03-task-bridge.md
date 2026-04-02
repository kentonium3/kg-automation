---
work_package_id: WP03
title: Standing Orders — Vikunja Task Bridge
dependencies: [WP02]
requirement_refs:
- C-002
- C-004
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- FR-014
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 008-inbox-processing-migration-WP02
base_commit: 98c0596263a548f4520100bb66ca26b3e0136121
created_at: '2026-03-31T03:09:09.346708+00:00'
subtasks: [T011, T012, T013, T014, T015, T016]
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
authoritative_surface: kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md/
execution_mode: code_change
mission_id: 01KN5QX3WJGAVA67AVPSBGXX96
owned_files:
- kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md
wp_code: WP03
---

# WP03: Standing Orders — Vikunja Task Bridge

## Implementation Command

```bash
spec-kitty implement WP03 --base WP02
```

## Objective

Create the Research project in Vikunja, then add standing orders to AGENTS.md
for the Vikunja task bridge: task items create tasks in the Inbox project,
research requests create tasks in the Research project, with identity label
inference, duplicate detection, and error handling.

## Context

- **AGENTS.md**: Created in WP02 with routing table. This WP adds the task bridge section.
- **Vikunja API skill**: `~/.openclaw/skills/vikunja-api/SKILL.md` on office2 — already deployed (F007)
- **API contract reference**: `kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md`
- **Current Vikunja projects**: Inbox (id=1), Goals (id=11), plus others. Research does not exist yet.
- **Identity labels**: personal (id=1), intentional (id=2), metalcasework (id=3)

## Subtask Guidance

### T011: Create Research Project in Vikunja

**Purpose**: Research requests need a dedicated project.

**Steps**:
1. Create the project via API:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"title\": \"Research\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/projects'
   ```
2. Verify it appears:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects' | python3 -c "
   import json,sys
   for p in json.load(sys.stdin):
       if p['title'] == 'Research': print(f'Research project: id={p[\"id\"]}')"
   ```
3. Note the ID for reference (but the agent will resolve by name at runtime)

**Validation**:
- [ ] Research project exists in Vikunja
- [ ] Accessible via API with the stored token

### T012: Task Bridge Section — Task Items to Inbox Project

**Purpose**: Teach the agent to create Vikunja tasks for action items.

**Steps**:
1. Add a "Task Bridge" section to AGENTS.md (after the routing table)
2. Document the workflow:
   ```markdown
   ## Task Bridge — Vikunja Task Creation

   When you classify a content block as `type: task` (an action item), create
   a real Vikunja task using the vikunja_api skill.

   ### For action items (type: task)

   1. Read the vikunja_api skill: `cat ~/.openclaw/skills/vikunja-api/SKILL.md`
   2. Resolve the "Inbox" project by name
   3. Resolve the appropriate identity label by name
   4. Check for duplicates (search Inbox project for same title)
   5. If no duplicate: create the task with title, identity label, and
      description referencing the source note
   6. Log the created task in the processing log

   Task description format:
   "Source: Inbox YYYY-MM-DD HHmm.md — [brief context from the note]"
   ```

**Validation**:
- [ ] Workflow references vikunja_api skill (not raw curl commands)
- [ ] Inbox project resolved by name
- [ ] Source reference included in description
- [ ] Steps are clear enough for the agent to follow autonomously

### T013: Identity Label Inference Rules

**Purpose**: Teach the agent how to infer the correct identity label.

**Steps**:
1. Add label inference rules to the task bridge section:
   ```markdown
   ### Identity label inference

   Every task MUST have an identity label. Infer from context:

   - **intentional**: Business content, consulting, client work, Intentional LLC,
     marketing, thought leadership, revenue generation
   - **metalcasework**: Metal casework venture, fabrication, ecommerce research
   - **personal**: Everything else — personal errands, health, family, general life

   When ambiguous, default to **personal**. It is better to assign personal
   and let Kent re-label than to guess wrong on a business label.
   ```

**Validation**:
- [ ] All three labels covered with clear criteria
- [ ] Default to personal when ambiguous

### T014: Duplicate Task Detection

**Purpose**: Prevent creating duplicate tasks.

**Steps**:
1. Add duplicate detection to the task bridge:
   ```markdown
   ### Duplicate detection

   Before creating a task, search the target project for an existing task
   with the same title (using the vikunja_api skill's duplicate check).
   If an exact match exists, do NOT create a new task. Log it as
   "already exists" in the processing log with the existing task ID.
   ```

**Validation**:
- [ ] Search-before-create documented
- [ ] Duplicate logged, not silently skipped

### T015: Research Request Routing

**Purpose**: Route research requests to the Research project.

**Steps**:
1. Add a research request subsection:
   ```markdown
   ### For research requests (type: research-request)

   1. Resolve the "Research" project by name
   2. Resolve the appropriate identity label
   3. Check for duplicates in the Research project
   4. Create the task with:
      - Title: the research question or topic
      - Identity label: inferred from context
      - Description: "Source: Inbox YYYY-MM-DD HHmm.md — Research request"
   5. Log the created task in the processing log under "Research tasks created"
   ```

**Validation**:
- [ ] Research project referenced by name (not Inbox)
- [ ] Same label inference and duplicate detection as regular tasks

### T016: Task Creation Error Handling

**Purpose**: Ensure task creation failures are logged, never dropped.

**Steps**:
1. Add error handling to the task bridge:
   ```markdown
   ### Error handling for task creation

   If Vikunja is unreachable or task creation fails:
   - Log the failure in the processing log under "Items flagged"
   - Include the error message and the task that could not be created
   - Continue processing remaining inbox files — do not abort the run
   - NEVER silently drop a task creation failure

   If the vikunja_api skill is not available:
   - Log the error and continue processing other content types
   - Flag all task/research items as "task creation unavailable" in the log
   ```

**Validation**:
- [ ] Failure logged, not silently dropped
- [ ] Processing continues after task creation failure
- [ ] Skill unavailability handled

## Definition of Done

- [ ] Research project exists in Vikunja
- [ ] AGENTS.md task bridge section covers task items and research requests
- [ ] Identity label inference rules documented
- [ ] Duplicate detection documented
- [ ] Error handling documented
- [ ] Deploy updated AGENTS.md to office2

## Risks

- **Research project already exists**: Check before creating. If it exists,
  skip creation.
- **vikunja_api skill not readable from agent**: The agent needs to
  `cat ~/.openclaw/skills/vikunja-api/SKILL.md` to learn the API. Verify
  this path is accessible from the felix-admin-capture agent's context.

## Activity Log

- 2026-03-31T03:09:09Z – claude-code – shell_pid=68877 – lane=doing – Assigned agent via workflow command
- 2026-03-31T03:11:15Z – claude-code – shell_pid=68877 – lane=for_review – Ready for review: Research project created in Vikunja (id=12), task bridge section added to AGENTS.md with task/research routing, identity label inference, duplicate detection, and error handling. Deployed to office2.
- 2026-03-31T03:11:58Z – claude-code – shell_pid=69648 – lane=doing – Started review via workflow command
- 2026-03-31T03:12:25Z – claude-code – shell_pid=69648 – lane=approved – Review passed: Research project created (id=12), task bridge covers action items and research requests with vikunja_api skill references, identity label inference with safe personal default, duplicate detection, and error handling. 13KB within bootstrap limit. Deployed to office2.
