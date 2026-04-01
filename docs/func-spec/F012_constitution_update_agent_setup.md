---
title: "F012: Constitution Update and Minimal Agent Setup"
doc_type: func-spec
status: draft
feature: F012
---

# F012: Constitution Update and Minimal Agent Setup

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

Two agents are running on office2 (felix-admin-capture, felix-admin-habits)
but neither has been formally registered under the Felix governance framework.
There is no constitution document, no formal gate assignment, no Observation
Mode mechanism, and no skill-authoring skill. As the system grows, each new
agent will make up its own conventions unless the governance framework is
established now.

This feature formalizes the rules all Felix agents operate under, registers
the two existing agents at Gate 1, implements Observation Mode as a lightweight
WhatsApp delivery mechanism, and creates the skill-authoring skill so future
agents can write skills that conform to project standards.

Current gaps:
- ❌ No Felix constitution document — four governance directives are captured
  in specs but never formalized as authoritative operational documents
- ❌ Two running agents with no formal gate registration
- ❌ Observation Mode described in F010 stub but not implemented
- ❌ No skill-authoring skill — agents given skill-writing capability have
  no standards document to follow
- ❌ ClawHub community skill constraint documented in openclaw-ops.md but
  not encoded in any agent's standing orders

This spec delivers the constitution document, gate registration for existing
agents, Observation Mode delivery, the skill-authoring skill, and the
ClawHub constraint in agent standing orders.

---

## Problem Statement

**Current State:**
```
Felix governance
└── ❌ No constitution document in repo
└── ❌ Four directives exist only as spec comments
└── ❌ No gate registry — agents are running but ungated
└── ❌ Observation Mode: defined but not implemented
└── ❌ Skill-authoring skill: not written
└── ❌ ClawHub constraint: in openclaw-ops.md but not in agent standing orders

Deployed agents
└── felix-admin-capture (F008)
│   └── Implicitly at Gate 1 but not formally registered
└── felix-admin-habits (F009)
    └── Implicitly at Gate 1 but not formally registered
```

**Target State:**
```
Felix governance
└── ✅ docs/constitution/FELIX-CONSTITUTION.md — authoritative governance doc
└── ✅ docs/constitution/AGENT-REGISTRY.md — gate assignments for all agents
└── ✅ Observation Mode delivering daily WhatsApp summaries for both agents
└── ✅ Skill-authoring skill at scripts/openclaw/skills/skill-author/SKILL.md
└── ✅ ClawHub constraint encoded in relevant agent standing orders

Deployed agents
└── felix-admin-capture — formally registered at Gate 1
└── felix-admin-habits — formally registered at Gate 1
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **All existing agent standing orders to understand current conventions**
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — the most
     complete set of agent standing orders in the system; the constitution
     must not contradict anything working well here
   - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — habit agent
     standing orders
   - Both agents' SOUL.md and IDENTITY.md files — understand the agent
     identity model before formalizing it

2. **All places the four directives and constraints are currently documented**
   - `docs/handbooks/openclaw-ops.md` — ClawHub constraint documented here
   - `docs/diagnostics/security-incidents/2026-03-31-whatsapp-pairing-and-axios.md`
     — security incident that reinforces the need for formal governance
   - The F010 stub (now F012 stub) — Observation Mode requirements captured here

3. **How OpenClaw agents currently receive standing orders**
   - Study the SOUL.md / AGENTS.md / IDENTITY.md / TOOLS.md structure across
     deployed agents to understand the format before writing the constitution
     and agent registry documents
   - The constitution must integrate with how OpenClaw loads agent context,
     not fight it

---

## Functional Requirements

### FR-1: Felix Constitution Document

**What it must do:**
- Create a formal Felix constitution at `docs/constitution/FELIX-CONSTITUTION.md`
  that authoritatively defines the four governance directives, Observation Mode,
  the gate model, the privacy boundary, and the ClawHub constraint
- The constitution must be written so it can be included by reference in any
  future agent's standing orders — concise, unambiguous, actionable

**The four directives (must all be formalized):**

**Directive 1 — Narrow scope:**
Every agent has one clearly defined responsibility. Agents do not expand their
scope without a spec and Kent's explicit approval. If asked to do something
outside defined scope, the agent stops and alerts Kent rather than attempting it.

**Directive 2 — Earned autonomy (three-gate model):**
- Gate 1 (Human In The Middle): Agent proposes actions and confirms with Kent
  before executing. All new agents start here.
- Gate 2 (Human Monitored): Agent executes autonomously but reports all actions.
  Requires demonstrated reliable Gate 1 performance (minimum 30 days).
- Gate 3 (Autonomous): Agent executes and reports exceptions only. Requires
  demonstrated reliable Gate 2 performance (minimum 30 days).
- Gate advancement requires Kent's explicit decision — never automatic.
- Gate regression (demotion) can happen at any time and for any reason.

**Directive 3 — Central action logging:**
Every agent action must be logged with: agent name, action type, target,
outcome, timestamp, and autonomy gate level. Logs are the audit trail.
Nothing happens without a log entry. If logging fails, the action is
considered unexecuted and must be retried.

**Directive 4 — Safety parameters and clear boundaries:**
Agents stop and alert Kent when:
- Asked to do something outside their defined scope
- Encountering an error they cannot resolve
- Receiving ambiguous input they cannot interpret confidently
- Detecting a potential security or safety concern
Agents never fail silently. Every failure produces an observable output.

**Business rules:**
- The constitution is version-controlled in the repo
- Changes to the constitution require a spec and Kent's approval
- All agent AGENTS.md files must reference the constitution and declare
  compliance with it
- The constitution is the tiebreaker when agent standing orders are ambiguous

**Success criteria:**
- [ ] `docs/constitution/FELIX-CONSTITUTION.md` exists and contains all
  four directives, the gate model, privacy boundary, ClawHub constraint,
  and Observation Mode definition
- [ ] Document is version-stamped (v1.0, date)
- [ ] Document is concise enough to be included by reference in agent
  standing orders without bloating their context

---

### FR-2: Agent Registry

**What it must do:**
- Create `docs/constitution/AGENT-REGISTRY.md` as the authoritative record
  of all deployed Felix agents, their current gate, their scope, and their
  gate history
- Register felix-admin-capture and felix-admin-habits at Gate 1
- Define the format for gate transition events so future gate advancements
  are recorded consistently

**Registry entry format (per agent):**
```
Agent: felix-admin-capture
Team: SuperAdmin (B)
Scope: Obsidian inbox processing — classifies notes, routes to vault,
       creates Vikunja tasks
Current gate: Gate 1 (Human In The Middle)
Deployed: F008 (2026-03-31)
Gate history:
  2026-03-31 — Registered at Gate 1 (F012)
```

**Business rules:**
- Every deployed agent must have a registry entry
- Gate transitions are appended to history — never edited in place
- The registry is the source of truth for gate status; service-inventory.json
  records deployment details; these are complementary not redundant

**Success criteria:**
- [ ] `docs/constitution/AGENT-REGISTRY.md` exists with entries for
  felix-admin-capture and felix-admin-habits
- [ ] Each entry includes: agent name, team, scope, current gate, deploy
  feature, and gate history
- [ ] Format is consistent and extensible for future agents

---

### FR-3: Observation Mode — Audit Logging and Activity Surfacing

**Two distinct concerns — both required:**

**Concern 1 — Audit logging (mandatory, non-negotiable):**
Every agent in Observation Mode must write a structured activity log after
every run. This is not optional and cannot be disabled. The log is the
canonical audit trail — the source of truth for what the agent did.

Log location: `/home/kgale/second-brain/agents/logs/` (already established)
Log format: per the existing processing log format in felix-admin-capture
Log content per run:
- Agent name, date, run time
- Count and description of each action taken
- Any items flagged (needs-review, potential-goals, errors)
- Any failures, with error detail

**Concern 2 — Activity surfacing (delivery mechanism is an open decision):**
The audit log exists but requires Kent to seek it out. Observation Mode
requires that activity be pushed to Kent in a practical, consumable form.
The delivery mechanism is a planning phase decision — not locked to WhatsApp.

Candidate delivery mechanisms (planning phase evaluates and recommends one):

- **WhatsApp summary** — brief digest after each run; practical for short
  summaries but limited for content-heavy reports; works well if the summary
  stays under 5-6 lines
- **Email digest** — daily or per-run email with more room for content;
  suitable when action volume is high or summaries require context;
  requires email integration (not yet built)
- **Dashboard** — a lightweight web page served on office2 (Tailscale-only)
  showing system status, agent activity stream, and flagged items in real
  time; accessible from Mac and iPhone via Tailscale; no content length
  constraints; best for ongoing situational awareness; requires a small
  web service to be built or an existing tool evaluated
- **Log file surfaced via Obsidian** — the log is already written to
  `agents/logs/`; if that directory were included in Obsidian Sync,
  logs would appear on Mac and iPhone without any additional delivery
  mechanism; lowest implementation cost but requires Kent to navigate to
  the file rather than receiving a push notification

**Planning phase must:**
1. Evaluate each candidate mechanism against: implementation cost, content
   volume likely from current agents, accessibility on Mac and iPhone,
   and whether critical alerts can always be surfaced regardless of setting
2. Recommend one mechanism (or a combination) with rationale
3. Identify what infrastructure (if any) needs to be built
4. Propose a fallback if the primary mechanism cannot be implemented in F012

**Business rules (apply regardless of delivery mechanism):**
- Observation Mode is ON by default for all new agents
- Kent turns off routine activity surfacing explicitly, per agent
- Critical alerts (failures, security concerns, errors) are ALWAYS surfaced
  regardless of whether routine Observation Mode is enabled or disabled —
  this cannot be turned off
- Observation Mode state (on/off per agent) persists across agent restarts
- Observation Mode for existing agents starts as of F012 deployment

**Intelligence layer — what gets surfaced is not the raw log:**
The full log contains everything for audit and investigation. What gets
surfaced to Kent is an AI-consolidated, filtered, and summarized view
that answers the question: "What do I actually need to know?"

The intelligence layer must:
- **Filter by significance** — routine successful actions that require no
  attention ("processed 2 notes, created 3 tasks") are summarized as a
  count, not listed individually
- **Elevate what matters** — flagged items, errors, unexpected behavior,
  potential-goals, and security concerns are surfaced with enough detail
  to act on, not buried in counts
- **Consolidate across runs** — for agents that run multiple times per day
  (felix-admin-capture runs 3×), the surfaced summary covers all runs in
  the period, not one message per run
- **Apply time windowing** — the planning phase must define the surfacing
  cadence (per-run, daily digest, or on-demand query) and how long
  activity remains in the surfaced window before it ages out
- **Point to the source** — every surfaced summary includes a reference
  to the full log for investigation if needed

**The planning phase must also decide:**
- Surfacing cadence: immediate (per-run), batched (daily digest at a set
  time), or on-demand (Kent queries "what happened today?")
- Time window: how much history is included in a single surfaced view
  (last run, last 24 hours, since last time Kent acknowledged)
- Retention: how long the surfaced view remains accessible before archiving
- Whether the intelligence layer is applied by the agent itself at run
  time, or by a separate summarization step that reads the logs

**Example of what surfaced output looks like vs. raw log:**
```
Raw log (audit trail):
  09:15 — Read Inbox 2026-04-01 0712.md (1,200 words)
  09:15 — Classified block 1: health content → 03-Health/Conditioning.md
  09:15 — Updated 03-Health/Conditioning.md (appended 180 words)
  09:16 — Classified block 2: task → Vikunja Inbox
  09:16 — Created Vikunja task #234 "Schedule car repair" (personal)
  09:16 — Classified block 3: aspirational goal → potential-goal
  09:16 — Flagged: "I want to do a triathlon" missing date and evidence
  09:17 — Marked Inbox 2026-04-01 0712.md as processed

Surfaced summary (intelligence layer):
  Inbox — Apr 1 (3 runs)
  Routine: 4 notes processed, 6 tasks created, 2 vault updates
  ⚠ 1 potential-goal needs your attention:
    "I want to do a triathlon" — missing date and evidence
    Source: Inbox 2026-04-01 0712.md
  Full log: agents/logs/inbox-processing-2026-04-01.md
```

**Business rules (apply regardless of delivery mechanism):**
- Observation Mode is ON by default for all new agents
- Kent turns off routine activity surfacing explicitly, per agent
- Critical alerts (failures, security concerns, errors) are ALWAYS surfaced
  regardless of whether routine Observation Mode is enabled or disabled —
  this cannot be turned off
- Observation Mode state (on/off per agent) persists across agent restarts
- Observation Mode for existing agents starts as of F012 deployment
- The full audit log is always written regardless of surfacing settings

**Success criteria:**
- [ ] Both agents write a structured activity log after every run
- [ ] Surfaced output is an AI-consolidated digest, not the raw log
- [ ] Routine successful actions summarized as counts
- [ ] Flagged items, errors, and alerts elevated with actionable detail
- [ ] Multi-run agents consolidated into a single periodic digest
- [ ] Critical alerts always surface regardless of routine setting
- [ ] Kent can disable routine surfacing per agent
- [ ] Observation Mode state persists across restarts
- [ ] Delivery mechanism, cadence, and time window decisions documented
  in governance runbook with rationale

---

### FR-4: ClawHub Constraint in Agent Standing Orders

**What it must do:**
- Add the ClawHub community skill constraint to the standing orders of any
  agent that has — or could in the future have — skill management capability
- For current agents, this means adding it as a standing constraint in their
  AGENTS.md so it is part of their operational context

**The constraint (exact wording to include):**

> Community skills from ClawHub require Kent's explicit approval before
> installation. Present the full SKILL.md and any supporting files for
> review. Never self-approve a community skill installation regardless of
> autonomy gate level. This constraint does not expire and applies even
> at Gate 3 (Autonomous).

**Business rules:**
- The constraint must appear in the constitution (FR-1) as the authoritative
  statement and in any agent's standing orders where it is relevant
- It is not necessary to add it to agents with no skill management capability
  (felix-admin-capture and felix-admin-habits do not install skills)
- The planning phase must determine which currently deployed agents need this
  in their standing orders and add it accordingly

**Success criteria:**
- [ ] ClawHub constraint present in FELIX-CONSTITUTION.md
- [ ] Any agent capable of skill management has it in AGENTS.md
- [ ] The constraint wording is consistent between constitution and agent files

---

### FR-5: Skill-Authoring Skill

**What it must do:**
- Write and deploy a skill-authoring skill at
  `scripts/openclaw/skills/skill-author/SKILL.md` that teaches any agent
  how to write OpenClaw skills conforming to kg-automation project standards
- Deploy the skill to office2 alongside the other OpenClaw skills

**What the skill-authoring skill must encode:**
- The OpenClaw SKILL.md format: required frontmatter fields (name, description,
  version), document structure, how skills are invoked
- Project-specific conventions:
  - Credentials always read from the credential store — never in skill code
  - No hardcoded IDs — resolve by name at runtime
  - Error handling: every error path returns a structured, typed response;
    never fail silently; halt-on-ambiguity (the FR-5 pattern from F007)
  - Identity label required on every task created
  - Logging: every significant action logged so the calling agent can report it
- The ClawHub community skill review constraint
- How to write skills that are narrow in scope (one responsibility)
- Pattern references: point to the Whisper skill (F003) and Vikunja API
  skill (F007) as the canonical examples in this project

**Business rules:**
- The skill-authoring skill is itself a SKILL.md document, not an agent
  standing orders document
- It must be updated whenever project conventions change — it is a living
  document
- Any agent given skill-writing capability must have the skill-authoring
  skill in its context before writing a new skill

**Success criteria:**
- [ ] `scripts/openclaw/skills/skill-author/SKILL.md` exists and covers
  all required content
- [ ] Skill deployed to office2 alongside other skills
- [ ] Skill references the Whisper and Vikunja API skills as pattern examples
- [ ] A hypothetical agent reading only this skill could write a compliant
  new skill without additional guidance

---

### FR-6: Update Existing Agent Standing Orders

**What it must do:**
- Update the AGENTS.md for both deployed agents to reference the constitution
  and declare compliance with it
- Add a header or preamble section to each agent's AGENTS.md stating:
  - The agent's current gate level
  - A reference to FELIX-CONSTITUTION.md as the governing document
  - That the agent's specific standing orders supplement but do not override
    the constitution

**Success criteria:**
- [ ] felix-admin-capture AGENTS.md references the constitution
- [ ] felix-admin-habits AGENTS.md references the constitution
- [ ] Both agents' gate levels documented in their standing orders
- [ ] Both agents' updated workspace files deployed to office2

---

### FR-7: Operations Runbook

**What it must do:**
- Create `docs/handbooks/felix-governance.md` covering:
  - How to read the constitution and agent registry
  - How to advance an agent's gate level (what evidence is required, who decides)
  - How to register a new agent
  - How to enable/disable Observation Mode
  - How to handle a constitution violation (agent acting outside scope)

**Success criteria:**
- [ ] Runbook exists at `docs/handbooks/felix-governance.md`
- [ ] Covers gate advancement procedure with minimum evidence requirements
- [ ] Covers new agent registration procedure

---

## Architecture Documentation Updates

F012 adds no new services, ports, or credentials.

### Markdown Updates Required

| File | Change |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Update updated_by to F012; add gate field to each agent entry |
| `docs/handbooks/openclaw-ops.md` | Add reference to FELIX-CONSTITUTION.md and AGENT-REGISTRY.md |

**Success criteria:**
- [ ] service-inventory.json updated with `updated_by: "F012"` and gate
  field on each agent entry

---

## Out of Scope

- ❌ Security review agent — the adversarial security agent captured in the
  F012 stub is a significant feature in its own right. It will be specced
  as a separate feature after F012 establishes the governance framework it
  would operate within.
- ❌ Gate 2 or Gate 3 advancement for any agent — neither agent has the
  operating history to qualify; this is Gate 1 registration only
- ❌ Full daily briefing (F015) — Observation Mode in this feature is a
  lightweight interim mechanism; the full briefing comes later
- ❌ Cross-agent routing (the main OpenClaw router for WhatsApp) — that
  comes with the broader agent team configuration in future features
- ❌ Modifications to existing agent behavior — constitution compliance is
  additive (add a preamble), not a rewrite of standing orders that are
  already working

---

## Success Criteria

**Complete when:**

### Constitution and Registry
- [ ] FELIX-CONSTITUTION.md exists, complete, version-stamped
- [ ] AGENT-REGISTRY.md exists with both agents at Gate 1

### Observation Mode
- [ ] Both agents deliver daily WhatsApp summaries
- [ ] Disabling routine summaries works via WhatsApp
- [ ] Failures always surface regardless of routine summary state

### Skill-Authoring Skill
- [ ] Skill written, deployed to office2
- [ ] Self-contained — sufficient to write a compliant new skill

### Agent Updates
- [ ] Both agents' AGENTS.md reference the constitution
- [ ] Updated workspace files deployed to office2

### Documentation
- [ ] `docs/handbooks/felix-governance.md` complete
- [ ] Architecture docs updated

---

## Architecture Principles

### Constitution First, Standing Orders Second

The constitution defines the rules that apply to all agents universally.
Agent standing orders define how a specific agent operates within those
rules. Standing orders supplement the constitution — they do not override
it. When a standing order conflicts with the constitution, the constitution
wins.

### Gate 1 Is the Default and a Feature, Not a Limitation

Gate 1 (Human In The Middle) is not a restriction imposed on untrustworthy
agents — it is the appropriate posture for any agent that has not yet
demonstrated reliable autonomous behavior. Every agent starts here because
it is the correct starting point, not because of distrust. Gate 1 is also
where Observation Mode generates the most value: knowing what the agent
did while it is still confirming each action builds the track record needed
for future gate advancement.

### Observation Mode Is Not Logging

The processing log is a file written for audit purposes. Observation Mode
is a push notification to Kent. They serve different consumers: logs are
for investigation; Observation Mode summaries are for awareness. Both are
necessary. The processing log is the source of truth; the Observation Mode
summary is the digest.

---

## Constitutional Compliance

✅ **Self-referential**: This spec creates the constitutional document that
future features reference. The constitution itself must comply with the
principles it encodes — it should be narrow in scope, versioned, and
changeable only through the defined process.

✅ **No credentials**: No new credentials introduced.

✅ **Docs adjacent**: All governance documents are committed alongside the
operational changes to agent standing orders.

---

## Risk Considerations

**Risk: Constitution contradicts working agent behavior**
- If the constitution imposes requirements that conflict with what
  felix-admin-capture or felix-admin-habits are already doing successfully,
  we risk breaking working agents.
- Mitigation: FR-1 explicitly requires reading existing agent standing
  orders before writing the constitution. The constitution formalizes
  patterns already working — it does not impose new ones on existing agents.

**Risk: Activity surfacing delivery mechanism requires infrastructure not yet built**
- Email requires an email integration. A dashboard requires a web service.
  Obsidian Sync for agent logs requires adding logs to the sync scope.
  WhatsApp has content length constraints. No mechanism is free.
- Mitigation: Planning phase evaluates all four candidates and recommends
  the one with the best cost/value trade-off given current infrastructure.
  The audit log (Concern 1) is always implemented regardless of which
  surfacing mechanism is chosen — so the worst case is Kent checks logs
  manually while a better surfacing mechanism is built in a later feature.

**Risk: Skill-authoring skill becomes stale quickly**
- If project conventions change after F012, the skill-authoring skill
  will be out of date.
- Mitigation: The constitution designates a responsible update process.
  The skill is version-stamped. Any feature that changes project
  conventions must update the skill-authoring skill in the same PR.

---

## Notes for Implementation

**Sequence within F012:**
1. Read all existing agent standing orders first (AGENTS.md, SOUL.md)
2. Write the constitution — ensure it formalizes what is already working
3. Write the agent registry with both agents at Gate 1
4. Write the skill-authoring skill
5. Update both agents' AGENTS.md to reference the constitution
6. Implement Observation Mode (discovering the correct OpenClaw mechanism)
7. Deploy updated agent workspace files to office2
8. Write the governance runbook
9. Update architecture docs

**Skill-authoring skill primary pattern references:**
- `scripts/openclaw/skills/whisper/SKILL.md` — the simplest existing skill,
  good format reference
- `scripts/openclaw/skills/vikunja-api/SKILL.md` — the most complete skill,
  covers error handling, credential access, and structured outputs

**Constitution location rationale:**
- `docs/constitution/` is a new directory. It keeps governance documents
  separate from handbooks (operational) and func-specs (implementation).
  The constitution is neither — it is foundational. A dedicated directory
  signals its status.

---

**END OF SPECIFICATION**
