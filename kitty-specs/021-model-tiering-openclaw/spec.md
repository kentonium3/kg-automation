# Model Tiering for OpenClaw Agents

**Feature**: 021-model-tiering-openclaw
**Mission**: software-dev
**Source**: GitHub issue #135 (parent: #137 AI Token Cost Optimization)
**Target Branch**: main

---

## Executive Summary

All 12 OpenClaw cron agents run claude-sonnet-4-6 regardless of task complexity, costing ~$4/day (~$115/month projected). API credits exhausted on 2026-04-09 after hitting the $35 self-imposed spend limit. Routine tasks like inbox scanning, habit check-ins, and health checks consume the same expensive model as complex reasoning tasks.

This feature implements per-agent model selection so each agent runs on the least expensive model that meets its quality requirements, targeting 60-80% monthly cost reduction.

Current gaps:

- ❌ No per-agent model selection — every agent uses the global default (Sonnet)
- ❌ Routine classification tasks use the same model as complex reasoning
- ❌ No documented model assignment policy for new agents
- ❌ No quality validation that cheaper models meet task requirements

---

## Problem Statement

**Current State (ALL SONNET):**
```
OpenClaw Agent Fleet — Model Assignment
├─ Inbox scan (×8/day)        → claude-sonnet-4-6  ❌ overkill
├─ Habit morning check-in     → claude-sonnet-4-6  ❌ overkill
├─ Habit weekly review         → claude-sonnet-4-6  ❌ overkill
├─ Escalation detection        → claude-sonnet-4-6  ⚠️ may be appropriate
├─ Health check (×2/day)       → claude-sonnet-4-6  ❌ overkill
└─ Model config                → agents.defaults.model (global)
                                  No per-agent override ❌
```

**Target State (TIERED):**
```
OpenClaw Agent Fleet — Model Assignment
├─ Inbox scan (×8/day)        → claude-haiku-4-5   ✅ pattern matching
├─ Habit morning check-in     → claude-haiku-4-5   ✅ structured Q&A
├─ Habit weekly review         → claude-haiku-4-5   ✅ structured Q&A
├─ Escalation detection        → [haiku or sonnet]  ✅ validated choice
├─ Health check (×2/day)       → claude-haiku-4-5   ✅ status checks
└─ Model config                → per-agent override  ✅ documented
                                  Default = haiku    ✅ safe default
```

**Cost projection:**
- Current: ~$4/day, ~$115/month (all Sonnet)
- Target: ~$0.40–$1.60/day, ~$12–$48/month (mostly Haiku)
- Haiku is ~10-20x cheaper per token than Sonnet

---

## Study These Files First

Before implementation, planning phase MUST read and understand:

1. **OpenClaw agent configuration**
   - Find `openclaw.json` on office2 (`ssh office2-claude`)
   - Study the `agents.defaults.model` setting and per-agent config structure
   - Determine whether OpenClaw supports per-agent model override or only a global default
   - If no per-agent override exists, identify the mechanism to add one

2. **Agent registry and governance**
   - Find `docs/constitution/AGENT-REGISTRY.md`
   - Find `docs/design/architecture/data/agent-registry.json`
   - Study how agents are registered — model assignment must be documented here

3. **OpenClaw agent workspace files**
   - Find agent workspace directories on office2
   - Study `IDENTITY.md`, `SOUL.md`, `AGENTS.md` files per `docs/runbooks/openclaw-agent-setup.md`
   - Determine where model selection is configured per agent (workspace-level vs global)

4. **Current cron configuration**
   - Find cron jobs on office2 that invoke OpenClaw agents
   - Map each cron job to its agent and invocation frequency
   - This establishes the baseline for cost modeling

---

## Assumptions

- OpenClaw supports some mechanism for per-agent model selection (config override, env var, or wrapper). If it does not, a minimal workaround is in scope.
- Haiku (claude-haiku-4-5) is available on the same API key and endpoint used by OpenClaw today.
- The Anthropic API returns token usage in response metadata that can be used for cost projection validation.
- Agent workspace files on office2 are accessible via `ssh office2-claude`.
- Spec-kitty merges create merge commits directly to main — no PR-based CI triggers will fire.

---

## Functional Requirements

### FR-001: Discover OpenClaw Model Configuration Mechanism

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Determine whether OpenClaw supports per-agent model selection
- If yes, document the configuration syntax
- If no, identify the minimal change to enable it (wrapper script, env var, config override)

**Success criteria:**
- [ ] Per-agent model selection mechanism is identified and documented
- [ ] Mechanism is validated on one test agent before fleet-wide rollout

---

### FR-002: Classify Agents by Model Tier

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Assign each active agent to a model tier based on task complexity
- Tier 1 (Haiku): routine classification, structured Q&A, status checks
- Tier 2 (Sonnet): complex reasoning, date math + priority inference, multi-step analysis
- Document the classification rationale for each agent

**Business rules:**
- Default tier for new agents MUST be Haiku unless explicitly justified
- Escalation detection requires quality validation before tier assignment — do not assume
- Any agent handling user-facing content generation stays on Sonnet minimum

**Success criteria:**
- [ ] Every active agent has a documented tier assignment with rationale
- [ ] Tier assignments are recorded in the agent registry

---

### FR-003: Validate Haiku Quality for Routine Tasks

| Field | Value |
|---|---|
| **ID** | FR-003 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Run Haiku against representative inputs for each Tier 1 candidate agent
- Compare output quality to Sonnet baseline
- Establish pass/fail criteria: does Haiku produce acceptable routing/classification/responses?

**Business rules:**
- Quality validation must happen BEFORE switching any agent to Haiku in production
- If Haiku fails quality for a specific agent, that agent stays on Sonnet with documented justification
- Validation uses real production inputs, not synthetic test cases

**Success criteria:**
- [ ] Each Tier 1 candidate tested with at least 3 representative inputs
- [ ] Pass/fail documented per agent
- [ ] Any failures result in agent remaining on Sonnet with rationale recorded

---

### FR-004: Deploy Tiered Model Configuration

| Field | Value |
|---|---|
| **ID** | FR-004 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Update OpenClaw configuration to assign validated model tiers to each agent
- Set global default model to Haiku (safe default for future agents)
- Ensure configuration survives OpenClaw restarts

**Success criteria:**
- [ ] Each agent runs on its assigned model tier
- [ ] Global default is Haiku
- [ ] Configuration persists across OpenClaw restart
- [ ] All agents functional after change (verified via health check or manual trigger)

---

### FR-005: Establish Model Assignment Policy

| Field | Value |
|---|---|
| **ID** | FR-005 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- Document the tiering policy: when to use Haiku vs Sonnet vs Opus
- Add model assignment as a required field in agent registration
- Define the process for changing an agent's tier (requires quality validation)

**Success criteria:**
- [ ] Model assignment policy documented in agent registry or runbook
- [ ] Agent registration checklist includes model tier selection
- [ ] Policy specifies what validation is required to change a tier

---

### FR-006: Establish Monthly Cost Target

| Field | Value |
|---|---|
| **ID** | FR-006 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- Define a monthly API spend target based on projected tiered usage
- Document the target and the assumptions behind it
- Provide a simple way to check current spend against target

**Business rules:**
- Cost target must account for current agent count AND planned additions (#131 escalation delegation)
- Target should include headroom for occasional Sonnet escalation

**Success criteria:**
- [ ] Monthly cost target documented with calculation basis
- [ ] Target accounts for planned agent fleet growth

---

## Non-Functional Requirements

### NFR-001: Cost Reduction Target

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | High |

Monthly API spend must decrease by at least 60% compared to the all-Sonnet baseline (~$115/month). Target range: $12–$48/month.

---

### NFR-002: No Quality Degradation for Routine Tasks

| Field | Value |
|---|---|
| **ID** | NFR-002 |
| **Status** | Proposed |
| **Priority** | High |

Agents switched to Haiku must produce outputs of equivalent functional quality to their Sonnet baseline. Inbox routing accuracy, habit check-in interaction quality, and health check reporting must not degrade.

---

### NFR-003: Configuration Durability

| Field | Value |
|---|---|
| **ID** | NFR-003 |
| **Status** | Proposed |
| **Priority** | Medium |

Model tier assignments must persist across OpenClaw restarts and service updates. No manual reconfiguration should be required after routine maintenance.

---

## Constraints

### C-001: No Observability Scope

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | High |

Per-agent token usage tracking, dashboards, and budget alerting are out of scope. Those are tracked in #138.

---

### C-002: No Mid-Session Model Escalation

| Field | Value |
|---|---|
| **ID** | C-002 |
| **Status** | Active |
| **Priority** | Medium |

This feature assigns a fixed model tier per agent. Dynamic escalation (start on Haiku, escalate to Sonnet mid-session if task is complex) is a future optimization, not in scope.

---

### C-003: Change Control Tier

| Field | Value |
|---|---|
| **ID** | C-003 |
| **Status** | Active |
| **Priority** | High |

OpenClaw configuration changes on office2 are Tier 2 (application config) per the change risk taxonomy. A recent Restic backup must be confirmed before modifying. Agent workspace files are Tier 3 (logic/workflow).

---

## Out of Scope

- ❌ Per-agent token usage tracking and dashboards — #138
- ❌ Budget threshold alerting and notifications — #138
- ❌ Mid-session model escalation (start Haiku, escalate to Sonnet) — future optimization
- ❌ OpenTelemetry integration — #124
- ❌ Spend limit changes on Anthropic console — manual decision for Kent

---

## User Scenarios & Testing

### Scenario 1: Routine Inbox Scan on Haiku

**Actor:** Inbox scan cron job (runs 8x/day)
**Flow:** Cron triggers OpenClaw → agent starts with Haiku model → processes inbox items → routes content correctly
**Expected outcome:** Inbox items classified and routed with same accuracy as Sonnet baseline
**Acceptance:** Compare routing decisions on 3+ real inbox batches between Haiku and Sonnet

### Scenario 2: Escalation Detection Tier Validation

**Actor:** Escalation detection cron job (runs 1x/day)
**Flow:** Agent processes pending tasks → evaluates priority, due dates, blocking status → flags escalations
**Expected outcome:** Agent correctly identifies items requiring escalation, with no missed high-priority items
**Acceptance:** Test with 3+ real task snapshots including known escalation triggers

### Scenario 3: New Agent Registration

**Actor:** Developer adding a new OpenClaw agent
**Flow:** Follow agent registration process → select model tier → document justification → deploy
**Expected outcome:** New agent defaults to Haiku; policy is clear on when Sonnet is justified
**Acceptance:** Registration checklist includes model tier; default is Haiku

### Scenario 4: Configuration Survives Restart

**Actor:** System after OpenClaw restart or office2 reboot
**Flow:** Service restarts → agents resume on their assigned model tiers
**Expected outcome:** No agents revert to global default or wrong model
**Acceptance:** Restart OpenClaw, verify each agent's model assignment

---

## Architecture Documentation Impact

This feature changes deployed service configuration on office2.

### JSON Updates Required

| File | Change |
|---|---|
| `data/agent-registry.json` | Add `model` field to each agent entry with tier assignment |
| `data/service-inventory.json` | Update OpenClaw entry to note tiered model configuration |

### Markdown Updates Required

| File | Change |
|---|---|
| `AGENT-REGISTRY.md` | Add model tier column to agent table |
| `service-inventory.md` | Note tiered model config in OpenClaw entry |

### No Changes Required

- `network-topology.json` — no port/IP changes
- `credential-manifest.json` — no new credentials
- `data-flows.json` — no new data flows
- `hardware-inventory.json` — no hardware changes

---

## Risk Considerations

**Risk: Haiku produces plausible but incorrect outputs for some agents**
- Inbox misrouting could cause missed escalations or lost content
- Mitigation: quality validation on real inputs before switching; keep escalation detection on Sonnet if validation is ambiguous

**Risk: OpenClaw doesn't support per-agent model override**
- May require wrapper scripts or config restructuring
- Mitigation: FR-001 discovers this first; planning phase determines the minimal viable workaround

**Risk: Cost savings less than projected**
- Token counts may not scale linearly with model choice if Haiku produces more verbose outputs
- Mitigation: FR-006 establishes cost target based on actual Haiku token usage from validation runs, not theoretical projections

---

## Key Entities

| Entity | Description |
|---|---|
| Agent | An OpenClaw agent with a specific task role and cron schedule |
| Model Tier | Classification (Tier 1 = Haiku, Tier 2 = Sonnet) determining which LLM an agent uses |
| Agent Registry | Machine-readable JSON + narrative markdown documenting all agents and their configurations |
| OpenClaw Config | `openclaw.json` on office2 containing global and per-agent settings |

---

## Success Criteria

### Model Configuration
- [ ] Per-agent model selection is operational in OpenClaw
- [ ] Global default model is Haiku
- [ ] All routine agents (inbox, habits, health) run on Haiku
- [ ] Complex agents (escalation, tasker) run on validated tier

### Quality
- [ ] Haiku quality validated per agent before production switch
- [ ] No degradation in inbox routing accuracy
- [ ] No degradation in habit check-in interaction quality
- [ ] Health checks produce equivalent output on Haiku

### Cost
- [ ] Monthly cost target defined and documented
- [ ] Projected savings of 60-80% vs all-Sonnet baseline

### Documentation
- [ ] Agent registry updated with model assignments
- [ ] Model assignment policy documented for future agents
- [ ] Architecture docs updated per change control protocol

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study OpenClaw configuration on office2 → determine per-agent model override mechanism
- Study agent workspace files → understand where model selection lives
- Study cron job definitions → map invocation frequency for cost modeling
- Study Anthropic API pricing → confirm current Haiku vs Sonnet token costs

**Key Patterns to Copy:**
- Agent registration pattern (runbook) → extend with model tier field
- Health check agent → use as first Haiku validation candidate (simplest task, lowest risk)

**Focus Areas:**
- FR-001 (discovery) must complete before FR-002–FR-004 can proceed
- FR-003 (validation) is the quality gate — do not skip or abbreviate
- Escalation detection agent is the hardest tier decision — may need dedicated validation

---

**END OF SPECIFICATION**
