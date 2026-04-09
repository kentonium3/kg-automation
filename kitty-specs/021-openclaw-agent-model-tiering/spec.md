# OpenClaw Agent Model Tiering

**Feature**: 021-openclaw-agent-model-tiering
**Mission**: software-dev
**Source**: GitHub issue #135 (parent: #137 AI Token Cost Optimization)
**Target Branch**: main

---

## Executive Summary

The OpenClaw agent fleet on office2 runs every agent on the same LLM regardless of task complexity. Routine tasks that require only pattern matching or structured data collection use the same expensive model as agents that perform multi-step reasoning. This caused API credits to exhaust on 2026-04-09.

This feature introduces per-agent model selection so that each agent runs on the least expensive model that meets its quality requirements. Agents whose tasks involve reasoning, trend analysis, or orchestration remain on a higher-capability model. The agent registry gains a new attribute indicating whether each agent is pinned to a specific model or eligible for cost optimization.

Current gaps:

- ❌ All agents share one global model setting — no per-agent selection
- ❌ Routine agents consume the same resources as complex reasoning agents
- ❌ No policy governs which model a new agent should use
- ❌ No registry attribute distinguishes pinned agents from optimizable ones
- ❌ No quality validation process exists before changing an agent's model

---

## Problem Statement

**Current State:**
```
OpenClaw Agent Fleet
├─ Inbox scan (×8/day)        → same model as everything else  ❌
├─ Habit daily check-in       → same model                     ❌
├─ Habit weekly review         → same model                     ⚠️ (needs Sonnet — does trend reasoning)
├─ Escalation detection        → same model                     ⚠️ (may be appropriate)
├─ Health check (×2/day)       → same model                     ❌
├─ OpenClaw main agent         → same model                     ⚠️ (orchestrator — needs Sonnet)
└─ Configuration               → single global default, no per-agent override
```

**Target State:**
```
OpenClaw Agent Fleet
├─ Inbox scan (×8/day)        → cheapest viable model          ✅
├─ Habit daily check-in       → cheapest viable model          ✅
├─ Habit weekly review         → higher-capability model        ✅ (trend reasoning validated)
├─ Escalation detection        → validated model assignment     ✅
├─ Health check (×2/day)       → cheapest viable model          ✅
├─ OpenClaw main agent         → higher-capability model        ✅ (orchestrator pinned)
└─ Configuration               → per-agent model override       ✅
                                  registry tracks pinned vs optimizable ✅
```

---

## Study These Files First

Before implementation, planning phase MUST read and understand:

1. **OpenClaw agent configuration**
   - Find `openclaw.json` on office2 (`ssh office2-claude`)
   - Study the global model default and any per-agent config structure
   - Determine whether per-agent model override is supported natively
   - If not, identify the minimal mechanism to enable it

2. **Agent registry and governance**
   - Find `docs/constitution/AGENT-REGISTRY.md`
   - Find `docs/design/architecture/data/agent-registry.json`
   - Understand current registry schema — new fields will be added

3. **OpenClaw agent workspace files**
   - Find agent workspace directories on office2
   - Study `IDENTITY.md`, `SOUL.md`, `AGENTS.md` per `docs/runbooks/openclaw-agent-setup.md`
   - Determine where model selection lives per agent (workspace-level vs global)

4. **Current cron configuration**
   - Map each cron job to its agent and invocation frequency
   - This establishes the cost baseline for savings projection

---

## Assumptions

- OpenClaw has some mechanism (native or extensible) for per-agent model selection. If it does not, a minimal workaround is in scope for this feature.
- The cheaper model is available on the same API key and endpoint currently used by OpenClaw.
- The Anthropic API returns token usage in response metadata usable for cost validation.
- Agent workspaces on office2 are accessible via `ssh office2-claude`.
- The spend limit has been raised to $100 (confirmed 2026-04-09), providing budget for live validation runs.
- The habit weekly review agent performs trend reasoning, pattern detection, and recommendations — it is NOT a routine task and should not be assumed to work on a cheaper model without validation.
- The OpenClaw main agent is the orchestrator and must remain on a higher-capability model.

---

## Functional Requirements

### FR-001: Discover Per-Agent Model Configuration Mechanism

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Determine whether OpenClaw supports per-agent model selection natively
- If supported, document the configuration syntax and any constraints
- If not supported, identify and implement the minimal viable mechanism to enable it
- Validate the mechanism works by changing one test agent's model and confirming it takes effect

**Success criteria:**
- [ ] Per-agent model selection mechanism is identified and documented
- [ ] Mechanism validated on one agent before fleet-wide rollout
- [ ] If a workaround was needed, the approach is documented for OpenClaw maintainer awareness

---

### FR-002: Classify Each Agent by Task Complexity

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Review each active agent's task description, prompt complexity, and expected reasoning depth
- Assign a tier: routine (cheap model candidate) or complex (higher-capability model)
- Document the rationale for each classification

**Business rules:**
- Agents performing classification, structured data collection, or status reporting are routine candidates
- Agents performing trend analysis, multi-step reasoning, priority inference, or orchestration are complex
- The habit weekly review is complex (confirmed: does trend reasoning and recommendations)
- The OpenClaw main agent is complex (orchestrator)
- The escalation detection agent requires dedicated validation — do not pre-assign

**Success criteria:**
- [ ] Every active agent has a documented complexity classification with rationale
- [ ] Classifications distinguish between "confirmed routine," "confirmed complex," and "needs validation"

---

### FR-003: Validate Cheaper Model Quality for Routine Candidates

| Field | Value |
|---|---|
| **ID** | FR-003 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- For each routine candidate, run the cheaper model against representative production inputs
- Compare outputs to the current model's baseline for functional equivalence
- Establish clear pass/fail for each agent: does the cheaper model produce acceptable results?
- For the escalation detection agent specifically, test with inputs that include known escalation triggers to verify none are missed

**Business rules:**
- Validation must happen BEFORE any agent is switched in production
- If a candidate fails, it stays on the current model with documented justification
- Validation uses real production inputs from recent agent runs, not synthetic cases
- At least 3 representative inputs per agent candidate

**Success criteria:**
- [ ] Each routine candidate tested with 3+ real inputs
- [ ] Pass/fail documented per agent with specific quality observations
- [ ] Failed candidates remain on current model with rationale recorded
- [ ] Escalation detection agent validated with known escalation triggers

---

### FR-004: Deploy Tiered Configuration

| Field | Value |
|---|---|
| **ID** | FR-004 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Update agent configurations to assign validated model tiers
- Set the global default to the cheapest viable model (safe default for new agents)
- Verify all agents function correctly after the change
- Ensure configuration persists across service restarts

**Success criteria:**
- [ ] Each agent runs on its assigned model
- [ ] Global default is the cheapest viable model
- [ ] Configuration persists across restart (verified by restarting and checking)
- [ ] All agents produce expected outputs in their first post-change run

---

### FR-005: Add Model Attributes to Agent Registry

| Field | Value |
|---|---|
| **ID** | FR-005 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- Add model-related fields to each agent's registry entry
- Include: assigned model, whether the agent is pinned to that model or eligible for optimization, and the rationale
- The design of "pinned vs optimizable" depends on what OpenClaw supports (discovered in FR-001) — if OpenClaw allows dynamic model selection, the attribute enables it; if not, it's a documentation-only policy flag for now

**Business rules:**
- Orchestrator and complex reasoning agents should be pinned
- Routine agents should be marked as optimizable
- Any future agent registration must include model assignment

**Success criteria:**
- [ ] Agent registry JSON includes model assignment and pin/optimize attribute per agent
- [ ] Agent registry markdown matches JSON
- [ ] Agent setup runbook updated to require model tier selection during registration

---

### FR-006: Establish Monthly Cost Target

| Field | Value |
|---|---|
| **ID** | FR-006 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- Calculate projected monthly cost based on actual tiered configuration (not theoretical)
- Use token counts from the validation runs (FR-003) and cron frequency to project monthly spend
- Document the target and its assumptions
- Account for planned agent fleet growth (e.g., #131 escalation delegation)

**Success criteria:**
- [ ] Monthly cost target documented with calculation showing per-agent contribution
- [ ] Target is based on actual validation run data, not estimates
- [ ] Target includes headroom for fleet growth and occasional higher-tier usage

---

## Non-Functional Requirements

### NFR-001: Cost Reduction

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | High |

Monthly API spend must decrease by at least 60% compared to the all-Sonnet baseline of ~$115/month. Target range: $12–$48/month.

---

### NFR-002: No Quality Degradation

| Field | Value |
|---|---|
| **ID** | NFR-002 |
| **Status** | Proposed |
| **Priority** | High |

Agents switched to a cheaper model must produce outputs of equivalent functional quality. No missed inbox routing, no missed escalation triggers, no degraded health check reporting. Quality is measured by comparison to recent production outputs on the current model.

---

### NFR-003: Configuration Durability

| Field | Value |
|---|---|
| **ID** | NFR-003 |
| **Status** | Proposed |
| **Priority** | Medium |

Model tier assignments must persist across service restarts and routine maintenance. No manual reconfiguration required after reboot.

---

## Constraints

### C-001: Observability Is Out of Scope

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | High |

Per-agent token tracking, dashboards, and budget alerting are separate (#138). This feature assigns models and validates quality — it does not build monitoring.

---

### C-002: No Mid-Session Model Escalation

| Field | Value |
|---|---|
| **ID** | C-002 |
| **Status** | Active |
| **Priority** | Medium |

Each agent gets a fixed model assignment. Dynamic escalation within a session (start cheap, escalate if complex) is a future optimization not in scope.

---

### C-003: Change Control Compliance

| Field | Value |
|---|---|
| **ID** | C-003 |
| **Status** | Active |
| **Priority** | High |

OpenClaw configuration changes are Tier 2 (application config) per the change risk taxonomy. Recent Restic backup must be confirmed before modifying. Agent workspace changes are Tier 3 (logic/workflow).

---

## Out of Scope

- ❌ Per-agent token usage tracking and dashboards (#138)
- ❌ Budget threshold alerting and notifications (#138)
- ❌ Mid-session model escalation (start cheap, escalate dynamically)
- ❌ OpenTelemetry integration (#124)
- ❌ Spend limit management on Anthropic console
- ❌ Model selection linked to autonomy level (selection is task-complexity based)

---

## User Scenarios & Testing

### Scenario 1: Routine Agent Running on Cheaper Model

**Actor:** Inbox scan cron job (runs 8×/day)
**Flow:** Cron triggers agent → agent starts on cheaper model → processes inbox items → routes content
**Expected outcome:** Items classified and routed with same accuracy as current model
**Acceptance:** Side-by-side comparison on 3+ real inbox batches shows equivalent routing decisions

### Scenario 2: Complex Agent Remains on Higher-Capability Model

**Actor:** Habit weekly review (runs 1×/week)
**Flow:** Cron triggers agent → agent starts on higher-capability model → analyzes week's habit data → produces trend analysis and recommendations
**Expected outcome:** Trend reasoning, pattern detection, and recommendations are coherent and actionable
**Acceptance:** Agent produces output comparable to current quality; no regression in reasoning depth

### Scenario 3: Escalation Detection Validation

**Actor:** Escalation detection agent (runs 1×/day)
**Flow:** Agent evaluates pending tasks for priority, due dates, blocking status → flags items needing escalation
**Expected outcome:** All genuine escalation triggers are detected; no false negatives on high-priority items
**Acceptance:** Tested against 3+ real task snapshots including known escalation triggers; zero missed escalations

### Scenario 4: New Agent Registration with Model Policy

**Actor:** Developer registering a new OpenClaw agent
**Flow:** Follow registration process → policy requires model tier selection → developer documents rationale → default is cheapest viable model
**Expected outcome:** New agents don't silently use an expensive model; policy is clear and enforced through documentation
**Acceptance:** Agent setup runbook includes model tier step; registry entry includes model attributes

### Scenario 5: Configuration Survives Restart

**Actor:** office2 after reboot or OpenClaw service restart
**Flow:** Service restarts → agents resume → each uses its assigned model
**Expected outcome:** No agents revert to a different model than assigned
**Acceptance:** Restart OpenClaw, trigger one agent from each tier, verify model used matches registry

### Scenario 6: Validation Failure Handling

**Actor:** Agent that fails quality validation on cheaper model
**Flow:** Validation shows unacceptable output quality → agent stays on current model → failure documented with rationale
**Expected outcome:** No agent is downgraded without passing validation; failures are visible in the registry
**Acceptance:** Registry shows "pinned" status with validation failure rationale for any agent that didn't pass

---

## Architecture Documentation Impact

### JSON Updates Required

| File | Change |
|---|---|
| `data/agent-registry.json` | Add `model`, `model_policy` (pinned/optimizable), and `model_rationale` fields per agent |
| `data/service-inventory.json` | Update OpenClaw entry to note tiered model configuration |

### Markdown Updates Required

| File | Change |
|---|---|
| `AGENT-REGISTRY.md` | Add model tier and policy columns to agent table |
| `service-inventory.md` | Note tiered model config in OpenClaw entry |

### No Changes Required

- `network-topology.json` — no port/IP changes
- `credential-manifest.json` — no new credentials
- `data-flows.json` — no new data flows
- `hardware-inventory.json` — no hardware changes

---

## Risk Considerations

**Risk: Cheaper model produces plausible but incorrect outputs**
- Inbox misrouting could cause missed content or misdirected escalations
- Mitigation: FR-003 requires live validation with real inputs before any production switch; failed agents stay on current model

**Risk: OpenClaw doesn't support per-agent model override natively**
- Could require wrapper scripts, env var injection, or config restructuring
- Mitigation: FR-001 discovers this first and implements a minimal workaround if needed; workaround is documented for OpenClaw maintainer awareness

**Risk: Cost savings less than projected**
- Cheaper models may produce more tokens (verbose output) partially offsetting per-token savings
- Mitigation: FR-006 bases cost targets on actual token counts from validation runs, not theoretical estimates

**Risk: Escalation detection agent misses a genuine escalation on cheaper model**
- High consequence — missed escalation could delay critical task response
- Mitigation: Dedicated validation with known escalation triggers; if any doubt, agent stays pinned to current model

**Risk: Configuration drift after manual changes or updates**
- Model assignments could be overwritten by OpenClaw updates or manual intervention
- Mitigation: NFR-003 requires restart durability; registry is the source of truth for what each agent should run

---

## Key Entities

| Entity | Description |
|---|---|
| Agent | An OpenClaw agent with a specific task role, cron schedule, and model assignment |
| Model Tier | Classification determining which LLM an agent uses (routine = cheap, complex = capable) |
| Model Policy | Whether an agent is pinned to its assigned model or eligible for future optimization |
| Agent Registry | Machine-readable JSON + narrative markdown documenting all agents and their configurations |
| OpenClaw Config | Configuration on office2 containing global defaults and per-agent settings |

---

## Success Criteria

- Monthly API spend decreases by at least 60% from the ~$115/month baseline
- Every agent's model assignment is validated before production deployment
- No missed escalation triggers or inbox misroutes after model changes
- Agent registry includes model, policy, and rationale for every agent
- New agent registration process requires model tier selection
- Configuration persists across OpenClaw restarts without manual intervention
- Monthly cost target is documented with per-agent cost breakdown based on actual data

---

**END OF SPECIFICATION**
