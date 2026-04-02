---
work_package_id: WP06
title: Architecture & Registry Updates
dependencies: [WP03]
requirement_refs:
- C-008
- FR-024
- FR-025
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T028, T029, T030, T031]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files: [docs/constitution/AGENT-REGISTRY.md, docs/design/architecture/service-inventory.md, docs/design/architecture/data/service-inventory.json]
---

# WP06: Architecture & Registry Updates

## Objective

Register felix-admin-tasker in the agent registry and update architecture documentation (service inventory markdown and JSON) to reflect the new agent, its cron jobs, and data flows.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent (FR-024, FR-025)
- **Standing requirement from CLAUDE.md**: Any feature that changes deployed services must update `docs/design/architecture/` and `docs/design/architecture/data/`
- **Existing files to update**:
  - `docs/constitution/AGENT-REGISTRY.md` — read for current format and entries
  - `docs/design/architecture/service-inventory.md` — read for current agent entries (felix-admin-capture, felix-admin-habits)
  - `docs/design/architecture/data/service-inventory.json` — read for JSON structure

### Implementation command

```bash
spec-kitty implement WP06 --base WP03
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP03 (must know agent details for registry)
- **Can run in parallel with**: WP04, WP05

---

## Subtask T028: Register felix-admin-tasker in AGENT-REGISTRY.md

**Purpose**: Add the new agent to the official agent registry per Felix Constitution requirements.

**Steps**:
1. Read `docs/constitution/AGENT-REGISTRY.md` — understand current format
2. Add entry for felix-admin-tasker:
   ```markdown
   ### felix-admin-tasker

   | Field | Value |
   |---|---|
   | **Registered** | 2026-04-02 |
   | **Feature** | F013 |
   | **Autonomy Level** | Assisted (Level 1) |
   | **Scope** | Task structuring and enrichment — transforms raw task descriptions into fully structured Vikunja tasks |
   | **Does NOT handle** | Inbox processing, habit tracking, briefings, calendar, email |
   | **Constitution** | Felix Constitution v1.0 |
   | **Skills** | task-intelligence, vikunja-api |
   | **Cron** | Incomplete task detection: `0 */4 * * *` |
   ```

3. Add to the autonomy history table (if one exists):
   ```markdown
   | Date | Agent | From | To | Reason | Decided by |
   |---|---|---|---|---|---|
   | 2026-04-02 | felix-admin-tasker | — | Assisted (Level 1) | Initial registration (F013) | Kent |
   ```

**Validation**:
- [ ] Entry added with correct format matching existing entries
- [ ] Autonomy level set to Assisted (Level 1)
- [ ] Scope and negative scope documented
- [ ] Feature reference (F013) included

---

## Subtask T029: Update service-inventory.md

**Purpose**: Add felix-admin-tasker to the architecture service inventory markdown.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md` — find the OpenClaw agents section
2. Add felix-admin-tasker entry following the pattern of felix-admin-capture and felix-admin-habits:
   ```markdown
   ### Felix Admin Tasker

   | Field | Value |
   |---|---|
   | Type | OpenClaw agent (sub-agent of the gateway) |
   | Feature | F013 |
   | Purpose | Task intelligence — transforms raw tasks into structured Vikunja entries |
   | Workspace | /data/services/openclaw/tasker-agent/ |
   | Skills | task-intelligence, vikunja-api |
   | Autonomy | Assisted (Level 1) |
   | Trigger | Delegation from felix-admin-capture, cron (incomplete detection), manual |
   ```

3. Add cron job entry to the Scheduled Jobs section:
   ```markdown
   | Incomplete Task Detection | Every 4 hours (0 */4 * * *) | felix-admin-tasker | Poll Inbox for flat tasks |
   ```

**Validation**:
- [ ] Entry follows format of existing agent entries
- [ ] Cron job added to scheduled jobs table
- [ ] Workspace path is correct

---

## Subtask T030: Update service-inventory.json

**Purpose**: Add felix-admin-tasker to the machine-readable service inventory.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json` — understand current structure
2. Add agent entry following the pattern of existing agents:
   ```json
   {
     "name": "felix-admin-tasker",
     "type": "openclaw-agent",
     "feature": "F013",
     "purpose": "Task intelligence — transforms raw tasks into structured Vikunja entries",
     "workspace": "/data/services/openclaw/tasker-agent/",
     "skills": ["task-intelligence", "vikunja-api"],
     "autonomy_level": "assisted",
     "triggers": ["delegation", "cron", "manual"],
     "updated_by": "F013"
   }
   ```

3. Add cron job entry:
   ```json
   {
     "name": "task-detection",
     "schedule": "0 */4 * * *",
     "agent": "felix-admin-tasker",
     "action": "detect_incomplete",
     "updated_by": "F013"
   }
   ```

4. Ensure JSON is valid after updates (no trailing commas, proper nesting)

**Validation**:
- [ ] JSON is valid (parseable)
- [ ] Agent entry follows existing structure
- [ ] Cron entry follows existing structure
- [ ] `updated_by` field set to "F013"

---

## Subtask T031: Define Cron Job Specifications

**Purpose**: Document the cron job specifications clearly for deployment.

**Steps**:
1. In the service-inventory.md, add a deployment note for the cron setup:
   ```markdown
   **Cron setup command** (run on office2):
   ```bash
   openclaw cron add \
     --name "task-detection" \
     --cron "0 */4 * * *" \
     --agent felix-admin-tasker \
     --session isolated \
     --message '{"action": "detect_incomplete"}' \
     --no-deliver
   ```

2. Document cron timing rationale:
   - Every 4 hours = 6 runs per day
   - Balances detection speed vs. polling overhead
   - Not too frequent (avoids redundant checks) but catches tasks within half a workday
   - Configurable: adjust via `openclaw cron update` if 4 hours is too frequent/infrequent

**Validation**:
- [ ] Cron command is copy-paste ready
- [ ] Timing rationale documented
- [ ] Adjustment procedure noted

---

## Definition of Done

- [ ] felix-admin-tasker registered in AGENT-REGISTRY.md at Assisted (Level 1)
- [ ] service-inventory.md updated with agent and cron entries
- [ ] service-inventory.json updated with agent and cron entries (valid JSON)
- [ ] Cron job specifications documented with setup command
- [ ] All entries follow existing format conventions

## Risks

- **JSON validation**: service-inventory.json must remain valid. Validate after editing.
- **Format drift**: Existing entries may have evolved since last feature. Match current format, not a remembered format.

## Reviewer Guidance

- Verify JSON is valid (run through a JSON linter)
- Compare new entries against existing ones for format consistency
- Check that autonomy level matches AGENT-REGISTRY.md
- Verify workspace path matches plan.md
- Confirm cron schedule matches plan.md (every 4 hours)
