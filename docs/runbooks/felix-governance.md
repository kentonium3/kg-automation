---
title: Felix Governance Runbook
doc_type: runbook
audience: humans
status: approved
---

# Felix Governance Runbook

This runbook defines operational procedures for governing Felix agents under
the Felix Constitution. All governance actions — promotions, demotions,
registrations, and violation handling — follow the procedures documented here.

## 1. Reading the Constitution and Registry

The governance framework consists of three authoritative documents:

- **Felix Constitution**: `docs/constitution/FELIX-CONSTITUTION.md`
  The top-level governance document. Defines autonomy levels, operating
  principles, boundaries, and the authority model. Consult this when
  resolving ambiguities in agent standing orders or when evaluating
  whether an agent action is within scope.

- **Agent Registry (machine-readable)**: `docs/constitution/agent-registry.json`
  The authoritative record of all registered agents, their current autonomy
  level, deployment details, and transition history. This is the source of
  truth for agent state.

- **Agent Registry (human-readable)**: `docs/constitution/AGENT-REGISTRY.md`
  A markdown view of the registry for quick reference. Must stay in sync
  with the JSON file. When they disagree, the JSON file wins.

**When to consult each document:**

| Situation | Document |
|-----------|----------|
| Is this action within the agent's scope? | Constitution |
| What autonomy level is this agent at? | agent-registry.json |
| What are this agent's standing orders? | The agent's AGENTS.md |
| How do I promote/demote/register an agent? | This runbook |

## 2. Autonomy Level Promotion Procedure

Promotions increase an agent's autonomy level. They require evidence of
reliable operation and are never automatic.

### Steps

1. **Verify minimum time at current level.** The agent must have been at its
   current autonomy level for a minimum of 30 consecutive days. Check the
   `transition_history` in `agent-registry.json` for the date of the last
   transition.

2. **Review the agent's activity logs.** Logs are stored at
   `~/second-brain/agents/logs/`. Review the full 30-day period for:
   - Consistent successful operation (daily runs completing without error)
   - No unresolved errors or failures
   - No scope violations (actions outside standing orders)
   - No constitution violations

3. **Assess reliability.** The agent must demonstrate:
   - Consistent daily operation without manual intervention
   - Correct handling of edge cases
   - No incidents that required demotion or manual correction

4. **Kent makes the explicit decision to promote.** Promotion is never
   automatic, never suggested by the agent, and never triggered by a timer.
   Kent decides.

5. **Update `agent-registry.json`:**
   - Change the `autonomy_level` field to the new level
   - Append a new entry to `transition_history` with:
     - `date`: today's date (YYYY-MM-DD)
     - `from`: previous level
     - `to`: new level
     - `direction`: `"promotion"`
     - `reason`: brief justification
     - `decided_by`: `"kent"`

6. **Update `AGENT-REGISTRY.md`** to reflect the new autonomy level.

7. **Update the agent's AGENTS.md preamble** with the new autonomy level
   text (e.g., change "Assisted (Level 1)" to "Observed (Level 2)").

8. **Deploy updated files to office2.** Copy the updated AGENTS.md to the
   agent's workspace on office2.

9. **Commit changes** with message format:
   `chore: promote <agent-name> to <level>`

### Minimum Evidence for Promotion

| Transition | Minimum Time | Evidence Required |
|------------|-------------|-------------------|
| Assisted to Observed | 30+ days at Assisted | No unresolved errors, no scope violations, consistent daily operation |
| Observed to Autonomous | 30+ days at Observed | Demonstrated ability to self-correct, no incidents requiring demotion, reliable independent operation |

## 3. Autonomy Level Demotion Procedure

Demotions decrease an agent's autonomy level. They can happen at any time,
for any reason, with no minimum time requirement.

### Steps

1. **Kent decides to demote.** No minimum time, no evidence threshold, no
   appeal process. Kent's judgment is sufficient.

2. **Update `agent-registry.json`:**
   - Change the `autonomy_level` field to the new (lower) level
   - Append a new entry to `transition_history` with:
     - `date`: today's date (YYYY-MM-DD)
     - `from`: previous level
     - `to`: new level
     - `direction`: `"demotion"`
     - `reason`: brief explanation
     - `decided_by`: `"kent"`

3. **Update `AGENT-REGISTRY.md`** to reflect the new autonomy level.

4. **Update the agent's AGENTS.md preamble** with the new autonomy level.

5. **Deploy updated files to office2.**

6. **Commit changes** with message format:
   `chore: demote <agent-name> to <level> — <brief reason> (#NNN)`

### Common Demotion Triggers

- Unexpected behavior or errors in agent operation
- Agent code was modified (new or changed code starts at Assisted)
- Security concern (real or suspected)
- Kent's judgment (no further justification required)

## 4. New Agent Registration Procedure

Every new agent must be registered before its first run.

### Steps

1. **Create the agent workspace** in the repo:
   `scripts/openclaw/agents/<agent-name>/`
   Include the standard agent files:
   - `AGENTS.md` — standing orders (with governance preamble)
   - `SOUL.md` — voice and personality
   - `IDENTITY.md` — identity and role
   - `TOOLS.md` — available tools and skills
   - `USER.md` — user context

2. **Add the governance preamble** to the new agent's AGENTS.md. All new
   agents start at Assisted (Level 1) by default.

3. **Add an entry to `agent-registry.json`** with:
   - `agent_id`: unique identifier
   - `name`: human-readable name
   - `autonomy_level`: `"assisted"`
   - `registered`: today's date
   - `registered_by`: the GitHub issue number (e.g., "#42")
   - `purpose`: what the agent does
   - `standing_orders`: path to AGENTS.md
   - `transition_history`: initial entry with direction `"registration"`

4. **Update `AGENT-REGISTRY.md`** with the new agent's details.

5. **Update `service-inventory.json`** with the agent's deployment details
   and `autonomy_level` field.

6. **Deploy to office2.** Copy agent files to the workspace directory and
   configure the OpenClaw cron schedule if applicable.

7. **Verify the agent operates within the governance framework** from its
   first run. Check the first activity log for correct behavior.

## 5. Activity Surfacing

Agents surface their activity through structured reporting so Kent maintains
visibility into what the system is doing.

### Delivery Channels

- **Primary**: Obsidian notes at `~/second-brain/notes/00-System/agent-activity/`
- **Critical alerts**: WhatsApp (when enabled in dm_policy)

### Cadence

- **Daily digest**: 7:00 PM ET, covering the rolling 24-hour period
- **Critical alerts**: Immediately, at any time

### Behavior by Autonomy Level

| Level | Routine Activity | Flagged/Error/Security |
|-------|-----------------|----------------------|
| Assisted (Level 1) | All activity surfaced (routine as counts) | Elevated — full detail |
| Observed (Level 2) | All activity surfaced (routine as counts) | Elevated — full detail |
| Autonomous (Level 3) | Only exceptions surfaced | Elevated — full detail |
| Critical alerts | Always surfaced | Always surfaced |

At Assisted and Observed levels, every action the agent takes is visible in
the daily digest. Routine actions (successful inbox processing, habit check-ins)
appear as counts. Flagged items, errors, and security events are elevated with
full detail.

At Autonomous level, only exceptions are surfaced. If everything ran normally,
the digest says so briefly. Errors and security events are always elevated
regardless of level.

Critical alerts bypass the daily cadence entirely and are delivered immediately
via WhatsApp (when enabled).

### Infrastructure

- **Intelligence layer**: `scripts/openclaw/observation/summarize.py`
- **Cron schedule**: Daily at 7:00 PM ET on office2
- **Log source**: `~/second-brain/agents/logs/`

## 6. Issue Tracking

Issues, bugs, feature requests, and infrastructure work are tracked on
GitHub using a structured label taxonomy, milestones, and a project board.

**GitHub Project**: [Felix Roadmap](https://github.com/users/kentonium3/projects/1)

### Issue lifecycle

1. **Triage**: New issues receive a P-label (priority + type) and one or
   more area/ labels (domain). See `docs/runbooks/repo-governance.md` for
   the full label taxonomy.
2. **Milestone assignment**: Issues are assigned to the appropriate
   capability milestone (e.g., Platform-Production-Ready, EA-Calendaring).
3. **Project board**: Issues are added to the Felix Roadmap project for
   visibility across Board, Table, and Roadmap views.
4. **Feature implementation**: Issues that require spec-kitty feature
   development are linked to the corresponding feature spec (e.g., F019).
5. **Closure**: Issues are closed when the implementing feature is merged
   or the issue is otherwise resolved.

### Creating issues

Use the `gh` CLI:

```bash
gh issue create --repo kentonium3/kg-automation \
  --title "<Type>: <Description>" \
  --label "<P-label>,<area-label>" \
  --milestone "<Milestone>"
```

See `docs/runbooks/repo-governance.md` for full details including how to
add issues to the project board.

## 7. Constitution Violation Handling

When an agent acts outside its defined scope or violates a constitutional
directive, follow this procedure immediately.

### Steps

1. **Identify the violation.** Sources:
   - Activity logs (daily digest or direct inspection)
   - Direct observation during interactive sessions
   - Unexpected system state (files modified outside scope, tasks created
     incorrectly, etc.)

2. **Demote the agent to Assisted immediately.** Follow the demotion
   procedure in Section 3. Do not wait for investigation results. The
   demotion is precautionary.

3. **Investigate root cause.** Determine what happened:
   - Was it a standing order ambiguity? (The standing orders were unclear
     and the agent made a reasonable but incorrect interpretation.)
   - Was it a code bug? (The agent logic has a defect.)
   - Was it a malicious or unexpected input? (External data caused the
     agent to behave incorrectly.)
   - Was it a scope creep? (The agent took an action not covered by its
     standing orders at all.)

4. **Fix the root cause.** Depending on the finding:
   - Standing order ambiguity: Create a new feature spec to clarify the
     standing orders.
   - Code bug: Fix the bug through the normal feature/fix workflow.
   - Malicious input: Add input validation or guardrails.
   - Scope creep: Tighten standing orders to explicitly exclude the
     problematic action.

5. **Document the incident** in the agent's `transition_history` in
   `agent-registry.json`. The demotion entry's `reason` field should
   reference the violation and the resolution.

6. **Agent remains at Assisted** until Kent explicitly promotes it again
   following the promotion procedure in Section 2. The 30-day minimum
   timer resets from the demotion date.
