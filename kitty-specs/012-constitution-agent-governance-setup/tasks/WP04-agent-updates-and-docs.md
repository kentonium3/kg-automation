---
work_package_id: WP04
title: Agent Standing Orders & Documentation
lane: planned
dependencies: []
requirement_refs:
- FR-014
- FR-017
- FR-019
- FR-020
- FR-021
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T013, T014, T015, T016, T017]
history:
- date: '2026-04-01T22:12:34Z'
  event: created
  agent: claude
priority: P1
---

# WP04: Agent Standing Orders & Documentation

## Implementation Command

```bash
spec-kitty implement WP04 --base WP01
```

Depends on WP01 — needs the constitution to exist for the AGENTS.md preamble reference.

## Objective

Update both agents' standing orders with a constitution preamble, write the governance runbook, and update architecture documentation. All changes to existing files are additive only (C-004).

## Context

- **Spec**: FR-017 (standing orders), FR-019 (runbook), FR-020 (service-inventory), FR-021 (openclaw-ops)
- **Plan**: Standing Order Updates section, Implementation Sequence steps 8-10
- **Constraint C-004**: Modifications to existing agent standing orders are additive only — no rewriting of standing orders that are already working

## Subtask T013: Update felix-admin-capture AGENTS.md

**Purpose**: Add a governance preamble to the capture agent's standing orders referencing the constitution.

**File**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Change**: PREPEND the following preamble before the existing content. Do NOT modify any existing content.

**Preamble format:**

```markdown
## Governance

**Autonomy Level**: Assisted (Level 1) — registered 2026-04-01 (F012)
**Constitution**: This agent operates under the [Felix Constitution](../../../../docs/constitution/FELIX-CONSTITUTION.md).
**Registry**: [Agent Registry](../../../../docs/constitution/AGENT-REGISTRY.md)

Standing orders below supplement the constitution. Where these standing orders are ambiguous, the constitution is the tiebreaker. These standing orders do not override the constitution.

---

```

**Critical rule (C-004)**: The existing content of AGENTS.md must remain UNCHANGED. Only prepend the preamble. Verify by diffing — the only change should be new lines at the top.

**Validation**:
- [ ] Preamble appears at the top of AGENTS.md
- [ ] All existing content is unchanged (diff shows only additions)
- [ ] Relative path to constitution resolves correctly
- [ ] Autonomy level stated as "Assisted (Level 1)"

## Subtask T014: Update felix-admin-habits AGENTS.md

**Purpose**: Same as T013 but for the habits agent.

**File**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`

**Change**: PREPEND the same governance preamble format. Adjust nothing in the existing content.

**Preamble** is identical to T013 — same autonomy level, same constitution reference, same tiebreaker statement.

**Validation**:
- [ ] Preamble appears at the top of AGENTS.md
- [ ] All existing content is unchanged
- [ ] Relative path to constitution resolves correctly

## Subtask T015: Write felix-governance.md Runbook

**Purpose**: Create the operational runbook for Felix governance at `docs/handbooks/felix-governance.md`.

**File**: `docs/handbooks/felix-governance.md`

**Required sections (FR-019):**

### 1. Reading the Constitution and Registry

- Where to find the constitution: `docs/constitution/FELIX-CONSTITUTION.md`
- Where to find the registry: `docs/constitution/agent-registry.json` (authoritative), `docs/constitution/AGENT-REGISTRY.md` (human-readable)
- What each document contains and when to consult it

### 2. Autonomy Level Promotion Procedure

Step-by-step procedure:
1. Verify the agent has been at its current level for minimum 30 days
2. Review the agent's activity logs for the period (path: `~/second-brain/agents/logs/`)
3. Assess reliability: consistent successful operation, no unresolved errors, no scope violations
4. Decision: Kent makes the explicit decision to promote
5. Update `agent-registry.json`: change `autonomy_level`, append to `transition_history` with direction `"promotion"`
6. Update `AGENT-REGISTRY.md` to match
7. Update the agent's AGENTS.md preamble with new autonomy level
8. Deploy updated files to office2
9. Commit changes with message format: `chore: promote <agent-name> to <level> (F###)`

**Minimum evidence for promotion:**
- Assisted → Observed: 30+ days at Assisted, no unresolved errors, no scope violations, consistent daily operation
- Observed → Autonomous: 30+ days at Observed, demonstrated ability to self-correct, no incidents requiring demotion

### 3. Autonomy Level Demotion Procedure

Step-by-step:
1. Kent decides to demote (no minimum time, any reason)
2. Update `agent-registry.json`: change `autonomy_level`, append to `transition_history` with direction `"demotion"`
3. Update `AGENT-REGISTRY.md`
4. Update the agent's AGENTS.md preamble
5. Deploy to office2
6. Commit with: `chore: demote <agent-name> to <level> — <brief reason>`

**Common demotion triggers:**
- Unexpected behavior or errors
- Agent code was modified (new code starts at Assisted)
- Security concern
- Kent's judgment (no further justification required)

### 4. New Agent Registration Procedure

1. Create agent workspace: `scripts/openclaw/agents/<agent-name>/` with AGENTS.md, SOUL.md, IDENTITY.md, TOOLS.md, USER.md
2. Add governance preamble to AGENTS.md (Assisted by default)
3. Add entry to `agent-registry.json` with `autonomy_level: "assisted"` and initial `transition_history`
4. Update `AGENT-REGISTRY.md`
5. Update `service-inventory.json` with agent deployment details and `autonomy_level` field
6. Deploy to office2
7. Verify the agent operates within the governance framework from its first run

### 5. Activity Surfacing

- Delivery: Obsidian notes at `~/second-brain/notes/00-System/agent-activity/`
- Critical alerts: WhatsApp (when enabled)
- Cadence: Daily digest at 7:00 PM ET
- Time window: Rolling 24 hours
- Behavior varies by autonomy level:
  - Assisted/Observed: all activity surfaced (routine as counts, flagged/error/security elevated)
  - Autonomous: only exceptions surfaced
  - Critical alerts: always, at every level
- Intelligence layer: `scripts/openclaw/observation/summarize.py`
- Cron: daily at 7:00 PM ET on office2

### 6. Constitution Violation Handling

When an agent acts outside its defined scope or violates a constitutional directive:
1. Identify the violation (from activity logs or direct observation)
2. Demote the agent to Assisted immediately (see demotion procedure)
3. Investigate root cause: was it a standing order ambiguity? A code bug? A malicious input?
4. Fix the root cause (new feature spec if standing orders need clarification)
5. Document the incident in the agent's transition history
6. Agent remains at Assisted until Kent explicitly promotes it again

**Frontmatter:**

```yaml
---
title: Felix Governance Runbook
doc_type: handbook
status: active
---
```

**Validation**:
- [ ] All 6 sections present and complete
- [ ] Promotion procedure includes minimum evidence requirements
- [ ] Demotion procedure emphasizes no minimum time
- [ ] New agent registration includes all steps
- [ ] Activity surfacing section documents delivery mechanism rationale
- [ ] Constitution violation handling includes demotion and investigation steps

## Subtask T016: Update service-inventory.json

**Purpose**: Add `autonomy_level` field to each agent entry and set `updated_by` to `"F012"`.

**File**: `docs/design/architecture/data/service-inventory.json`

**Changes:**
1. Find each agent entry in the `services` or `agents` section
2. Add `"autonomy_level": "assisted"` to each agent's config
3. Update the top-level or agent-level `updated_by` field to `"F012"`

**Important**: Read the file first to understand its current structure. Do not blindly add fields — place them where they fit the existing schema.

**Validation**:
- [ ] Both agent entries have `autonomy_level: "assisted"`
- [ ] `updated_by` includes `"F012"`
- [ ] JSON is valid (parse it)
- [ ] No other fields accidentally modified

## Subtask T017: Update openclaw-ops.md

**Purpose**: Add references to the new constitution and registry documents.

**File**: `docs/handbooks/openclaw-ops.md`

**Changes**: Add a section (or update existing governance references) pointing to:
- `docs/constitution/FELIX-CONSTITUTION.md` — authoritative governance document
- `docs/constitution/AGENT-REGISTRY.md` — agent registry (human-readable)
- `docs/constitution/agent-registry.json` — agent registry (machine-readable)
- `docs/handbooks/felix-governance.md` — governance operational runbook

**Placement**: Near the existing ClawHub policy section or in a new "Governance" section.

**Validation**:
- [ ] All four document references added
- [ ] Existing content unchanged (additive only)
- [ ] References use correct relative paths

## Definition of Done

- [ ] felix-admin-capture AGENTS.md has governance preamble, existing content unchanged
- [ ] felix-admin-habits AGENTS.md has governance preamble, existing content unchanged
- [ ] `docs/handbooks/felix-governance.md` exists with all 6 required sections
- [ ] `docs/design/architecture/data/service-inventory.json` has autonomy_level fields and F012 attribution
- [ ] `docs/handbooks/openclaw-ops.md` references constitution and registry
- [ ] All files committed to target branch

## Risks

| Risk | Mitigation |
|------|-----------|
| AGENTS.md preamble conflicts with existing content | C-004 requires additive-only. Diff before committing to verify no existing lines changed. |
| service-inventory.json schema unknown | Read file first. Place autonomy_level where it fits existing structure. |
| Relative paths in AGENTS.md preamble don't resolve | Verify by counting directory levels from agent dir to docs/constitution/ |

## Reviewer Guidance

- **CRITICAL**: Diff both AGENTS.md files — verify ONLY additions, zero modifications to existing content
- Verify governance runbook covers all 6 sections from FR-019
- Verify service-inventory.json changes are minimal and targeted (only autonomy_level + updated_by)
- Verify openclaw-ops.md references use correct paths
- Check that autonomy level is consistently "Assisted" / "assisted" (markdown uses title case, JSON uses lowercase)
