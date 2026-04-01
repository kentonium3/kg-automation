---
work_package_id: WP01
title: Constitution & Agent Registry
lane: "approved"
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 7281c5dcc60eead8b6ebb5677e38ef714ca7bad3
created_at: '2026-04-01T22:21:07.998156+00:00'
subtasks: [T001, T002, T003, T004]
agent: claude
shell_pid: '58964'
reviewed_by: "Kent Gale"
review_status: "approved"
history:
- date: '2026-04-01T22:12:34Z'
  event: created
  agent: claude
priority: P0
---

# WP01: Constitution & Agent Registry

## Implementation Command

```bash
spec-kitty implement WP01
```

No dependencies — this is the foundation WP.

## Objective

Create the Felix constitution document and dual-format agent registry (JSON + Markdown) that formalize the governance framework all agents operate under. Register both existing agents at Assisted (Level 1).

This WP is the foundation — every other WP references the constitution or registry. Get it right.

## Context

- **Spec**: `kitty-specs/012-constitution-agent-governance-setup/spec.md` (FR-001 through FR-007)
- **Plan**: `kitty-specs/012-constitution-agent-governance-setup/plan.md`
- **Data Model**: `kitty-specs/012-constitution-agent-governance-setup/data-model.md` (registry schema)
- **Research**: `kitty-specs/012-constitution-agent-governance-setup/research.md` (Decision 9: autonomy level nomenclature)

**Critical constraint (NFR-005)**: The constitution must formalize patterns already working in existing agents. It must NOT impose new operational requirements that contradict current behavior. Read existing standing orders first.

## Subtask T001: Read Existing Agent Standing Orders

**Purpose**: Understand current conventions before writing the constitution. The constitution formalizes what works — it does not invent new rules.

**Files to read (all under `scripts/openclaw/agents/`):**

| File | What to look for |
|------|-----------------|
| `felix-admin-capture/AGENTS.md` | Standing orders structure, workflow, error handling patterns, privacy rules, logging behavior |
| `felix-admin-capture/SOUL.md` | Voice principles, writing style |
| `felix-admin-capture/IDENTITY.md` | Identity model (name, creature, vibe, emoji) |
| `felix-admin-capture/TOOLS.md` | Tool access, paths, credentials pattern |
| `felix-admin-capture/USER.md` | User context model |
| `felix-admin-habits/AGENTS.md` | Same analysis for habits agent |
| `felix-admin-habits/SOUL.md` | Voice consistency check |
| `felix-admin-habits/IDENTITY.md` | Identity model consistency |
| `felix-admin-habits/TOOLS.md` | Tool access pattern consistency |
| `felix-admin-habits/USER.md` | User context consistency |

**What to extract for the constitution:**
- Common patterns across both agents (these become constitutional directives)
- Privacy boundary enforcement (how it's currently stated)
- Error handling patterns (how agents currently handle failures)
- Logging behavior (what's logged, where, format)
- Scope enforcement (how agents limit themselves)
- Credential access patterns (how agents use the credential store)

**Validation**: Before writing T002, confirm that the four directives from the spec (narrow scope, earned autonomy, central action logging, safety parameters) are consistent with what you observe in the existing standing orders. If any directive contradicts observed behavior, flag it — do not silently override.

## Subtask T002: Write FELIX-CONSTITUTION.md

**Purpose**: Create the authoritative governance document at `docs/constitution/FELIX-CONSTITUTION.md`.

**Create directory first**: `docs/constitution/` (new directory)

**Document structure** (from data-model.md):

1. **Preamble** — purpose statement, version (v1.0), date, change process (requires spec + Kent's approval)

2. **Directive 1: Narrow Scope** — every agent has one defined responsibility. No scope expansion without a spec and Kent's approval. If asked to do something outside scope: stop and alert Kent.

3. **Directive 2: Earned Autonomy** — the autonomy level model:
   - **Assisted (Level 1)**: Agent proposes actions, Kent confirms before execution. All new agents start here.
   - **Observed (Level 2)**: Agent executes autonomously, all activity surfaced to Kent. Requires 30+ days at Assisted + Kent's explicit decision.
   - **Autonomous (Level 3)**: Agent executes autonomously, only exceptions surfaced. Requires 30+ days at Observed + Kent's explicit decision.
   - Promotion: requires Kent's explicit decision + minimum time at current level. Never automatic.
   - Demotion: can happen at any time for any reason (unexpected behavior, code modification, Kent's judgment). No minimum time required.

4. **Directive 3: Central Action Logging** — every agent action logged with: agent name, action type, target, outcome, timestamp, and autonomy level. Logs are the audit trail. If logging fails, the action is unexecuted and must be retried.

5. **Directive 4: Safety Parameters** — agents stop and alert Kent when: outside scope, unresolvable error, ambiguous input, potential security concern. Never fail silently.

6. **Privacy & Communication Boundaries** (extensible section):
   - Current boundary: `~/second-brain/notes/02-Growth/_private/` — never read, written, referenced, or logged by any agent under any circumstance. No exceptions.
   - Future boundaries placeholder: "As Felix gains outbound communication capabilities (email, calendar, messaging), additional PII and communication rules will be added to this section."
   - Make it clear this section is designed to grow.

7. **ClawHub Community Skill Constraint**:
   > Community skills from ClawHub require Kent's explicit approval before installation. Present the full SKILL.md and any supporting files for review. Never self-approve a community skill installation regardless of autonomy level. This constraint does not expire and applies even at Autonomous (Level 3).

8. **Activity Surfacing** — behavior per autonomy level:
   - All levels: mandatory structured activity log after every run (audit trail)
   - Assisted/Observed: daily digest includes all activity (routine as counts, flagged/error/security elevated)
   - Autonomous: daily digest includes only exceptions (flagged/error/security)
   - Critical alerts (errors, security): always surfaced at every level, no exceptions
   - The intelligence layer determines what Kent needs to know — agents write logs, they don't control surfacing

9. **Amendment Process** — constitution changes require a feature spec and Kent's approval. Version-stamped. Changes committed to version control.

**Style requirements (NFR-001):**
- Written for AI agent consumption — clear, unambiguous, actionable
- No implied context — every rule must be explicit
- Concise enough to be included by reference without bloating agent context (FR-002)
- Use numbered directives and named sections for easy referencing

**Validation**:
- [ ] All four directives present and complete
- [ ] Autonomy level model uses correct terminology (assisted/observed/autonomous, NOT gate)
- [ ] Privacy boundary stated as absolute with no exceptions
- [ ] ClawHub constraint exact wording included
- [ ] Activity surfacing behavior defined per autonomy level
- [ ] Version stamp: v1.0, date
- [ ] Amendment process defined
- [ ] No contradiction with existing agent standing orders (verified via T001)

## Subtask T003: Write agent-registry.json

**Purpose**: Create the machine-readable authoritative agent registry at `docs/constitution/agent-registry.json`.

**Schema** (from data-model.md):

```json
{
  "version": "1.0",
  "updated": "2026-04-01",
  "updated_by": "F012",
  "agents": {
    "felix-admin-capture": {
      "team": "SuperAdmin (B)",
      "scope": "Obsidian inbox processing — classifies notes, routes to vault, creates Vikunja tasks",
      "autonomy_level": "assisted",
      "deployed_feature": "F008",
      "registered": "2026-04-01",
      "transition_history": [
        {
          "date": "2026-04-01",
          "autonomy_level": "assisted",
          "direction": "registration",
          "reason": "Initial registration under Felix governance framework (F012)",
          "decided_by": "Kent Gale"
        }
      ]
    },
    "felix-admin-habits": {
      "team": "SuperAdmin (B)",
      "scope": "Daily habit check-ins, completion recording, and pattern reporting",
      "autonomy_level": "assisted",
      "deployed_feature": "F009",
      "registered": "2026-04-01",
      "transition_history": [
        {
          "date": "2026-04-01",
          "autonomy_level": "assisted",
          "direction": "registration",
          "reason": "Initial registration under Felix governance framework (F012)",
          "decided_by": "Kent Gale"
        }
      ]
    }
  }
}
```

**Validation**:
- [ ] Valid JSON (parse it)
- [ ] Both agents present with correct scope descriptions
- [ ] Both at `assisted`
- [ ] Transition history has `direction: "registration"` entries
- [ ] `updated_by` is `"F012"`

## Subtask T004: Write AGENT-REGISTRY.md

**Purpose**: Create the human-readable narrative view at `docs/constitution/AGENT-REGISTRY.md`, consistent with the JSON registry.

**Format per agent:**

```markdown
## felix-admin-capture

**Team**: SuperAdmin (B)
**Scope**: Obsidian inbox processing — classifies notes, routes to vault, creates Vikunja tasks
**Current Autonomy Level**: Assisted (Level 1)
**Deployed**: F008 (2026-03-31)
**Registered**: F012 (2026-04-01)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-01 | Assisted | Registration | Initial registration under Felix governance framework (F012) | Kent Gale |
```

**Include a header** explaining that `agent-registry.json` is the authoritative record and this file is the human-readable view.

**Validation**:
- [ ] Both agents present with entries matching JSON
- [ ] Transition history matches JSON entries
- [ ] Header states JSON is authoritative

## Definition of Done

- [ ] `docs/constitution/FELIX-CONSTITUTION.md` exists, complete, version-stamped v1.0
- [ ] `docs/constitution/agent-registry.json` exists, valid JSON, both agents at Assisted
- [ ] `docs/constitution/AGENT-REGISTRY.md` exists, consistent with JSON
- [ ] Constitution does not contradict existing agent standing orders
- [ ] Constitution uses "autonomy level" / "assisted" / "observed" / "autonomous" terminology throughout (never "gate")
- [ ] Privacy & Communication Boundaries section is extensible
- [ ] All files committed to target branch

## Risks

| Risk | Mitigation |
|------|-----------|
| Constitution contradicts existing agent behavior | T001 requires reading all agent files first. Flag contradictions before writing. |
| Registry schema incomplete | data-model.md provides complete schema with field types and validation rules |
| Terminology drift (gate vs. autonomy level) | Use search-and-verify after writing to ensure no "gate" references remain |

## Reviewer Guidance

- Verify constitution directives match the four directives in `docs/func-spec/F012_constitution_update_agent_setup.md` (FR-1 section)
- Verify registry entries match agent details in `docs/design/architecture/data/service-inventory.json`
- Verify constitution is concise enough for agent context inclusion (FR-002) — aim for under 200 lines
- Verify privacy boundary wording is absolute — no wiggle room
- Verify ClawHub constraint wording matches the exact text from the spec

## Activity Log

- 2026-04-01T22:21:08Z – claude – shell_pid=55885 – lane=doing – Assigned agent via workflow command
- 2026-04-01T22:24:26Z – claude – shell_pid=55885 – lane=for_review – Ready for review: Constitution, JSON registry, and Markdown registry created. 116-line constitution covers all four directives, autonomy levels, privacy boundary, ClawHub constraint, and activity surfacing rules. No gate terminology. No contradictions with existing agent standing orders.
- 2026-04-01T22:34:06Z – claude – shell_pid=58964 – lane=doing – Started review via workflow command
- 2026-04-01T22:34:49Z – claude – shell_pid=58964 – lane=approved – Review passed: constitution complete with all directives, correct autonomy terminology, extensible privacy, ClawHub exact wording. Registry valid JSON + consistent markdown.
