# Implementation Plan: OpenClaw Agent Model Tiering

**Branch**: `main` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/021-openclaw-agent-model-tiering/spec.md`
**Source Issue**: #135 (parent: #137)

## Summary

Implement per-agent model selection across the OpenClaw agent fleet on office2 to reduce monthly API costs by 60-80%. OpenClaw natively supports per-agent model override via the `model` field in `openclaw.json`. The implementation changes config values, validates quality on the cheaper model, updates the agent registry with new model-related attributes, and documents the model assignment policy.

## Technical Context

**Platform**: office2 (Ubuntu 24.04 LTS) via `ssh office2-claude`
**Config Format**: JSON (`/home/claude/.openclaw/openclaw.json`)
**Agent Registry**: `docs/constitution/agent-registry.json` + `docs/constitution/AGENT-REGISTRY.md`
**Agent Workspaces**: `/data/services/openclaw/{agent-name}/`
**Agent Definitions**: `/home/claude/.openclaw/agents/{agent-id}/agent/`
**Cron Management**: OpenClaw-internal (not system crontab)
**Change Control**: Tier 2 (application config) — Restic backup required before modifying `openclaw.json`
**Testing**: Live validation runs against production inputs; $100 spend limit active

## Research Findings

All unknowns from the spec have been resolved through live discovery on office2:

| Question | Answer | Source |
|---|---|---|
| Does OpenClaw support per-agent model? | **Yes** — `model` field in `agents.list[]` | Read `openclaw.json` |
| How many agents exist? | 5 named + `main` orchestrator | `openclaw.json agents.list` |
| Where is agent config? | `/home/claude/.openclaw/openclaw.json` | Live SSH read |
| Where is agent registry? | `docs/constitution/agent-registry.json` (not `data/`) | Local glob |
| How are crons managed? | OpenClaw-internal, session keys like `agent:...:cron:...` | Session logs |
| Habits agent — daily vs weekly? | Single agent, both tasks. Validate Haiku for both now; split later (#141) | Kent decision |
| Global default field? | `agents.defaults.model.primary` | `openclaw.json` |

**No research.md needed** — all clarifications resolved through live discovery.

## Agent Classification

Based on task complexity analysis from AGENTS.md standing orders and discovery conversation:

| Agent ID | Task Type | Complexity | Proposed Model | Rationale |
|---|---|---|---|---|
| `main` | Orchestrator | Complex | `anthropic/claude-sonnet-4-6` (pinned) | Core routing and orchestration |
| `felix-admin-capture` | Inbox classification & routing | Routine | `anthropic/claude-haiku-4-5` (validate) | Pattern matching against routing table |
| `felix-admin-habits` | Daily check-in + weekly review | Mixed | `anthropic/claude-haiku-4-5` (validate) | Daily is routine; weekly does trend reasoning — validate both on Haiku; split to separate agents later (#141) |
| `felix-admin-escalation` | Overdue task detection & alerting | Complex | Validate — Haiku or Sonnet | Date math + priority inference; highest risk if wrong |
| `felix-admin-tasker` | Task enrichment & goal matching | Complex | `anthropic/claude-sonnet-4-6` (pinned) | Multi-step attribute inference, goal relationship detection |

## Implementation Approach

### Phase 1: Pre-flight (Tier 2 compliance)

1. Confirm recent Restic backup on office2
2. Take a snapshot of current `openclaw.json` (copy to backup location)
3. Document current model assignments as baseline

### Phase 2: Validation Testing

For each Haiku candidate (`felix-admin-capture`, `felix-admin-habits`, `felix-admin-escalation`):

1. Identify 3+ recent production inputs from agent session logs or workspace
2. Run those inputs through Haiku (temporarily change one agent's model, trigger a run, observe output)
3. Compare to recent Sonnet output for the same or equivalent inputs
4. Record pass/fail with specific quality observations
5. Revert to Sonnet if validation is in progress and agent needs to remain functional

**Validation order** (lowest risk first):
1. `felix-admin-capture` (inbox scan) — simplest task, highest volume, biggest cost savings
2. `felix-admin-habits` (daily + weekly) — test daily first, then weekly separately
3. `felix-admin-escalation` — highest risk, test last with known escalation triggers

### Phase 3: Deploy Configuration

1. Edit `openclaw.json`:
   - Set `agents.defaults.model.primary` to `anthropic/claude-haiku-4-5`
   - Update each agent's `model` field based on validation results
   - Agents that failed validation stay on Sonnet
2. Restart OpenClaw (or confirm config reload mechanism)
3. Verify each agent runs on correct model in next scheduled execution
4. Monitor first full day of tiered operation

### Phase 4: Registry and Documentation

1. Add `model`, `model_policy`, `model_rationale` fields to `agent-registry.json`
2. Update `AGENT-REGISTRY.md` with model tier column
3. Update `service-inventory.md` OpenClaw entry
4. Update agent-setup runbook with model tier requirement
5. Calculate and document monthly cost target from validation run token counts

## Project Structure

### Files Modified on office2

```
/home/claude/.openclaw/openclaw.json     ← per-agent model + global default change
```

### Files Modified in kg-automation repo

```
docs/constitution/agent-registry.json    ← add model fields per agent
docs/constitution/AGENT-REGISTRY.md      ← add model tier column
docs/design/architecture/service-inventory.md  ← update OpenClaw entry
docs/runbooks/openclaw-agent-setup.md    ← add model tier to registration checklist
```

### Files Created in mission directory

```
kitty-specs/021-openclaw-agent-model-tiering/
├── spec.md              ← complete
├── plan.md              ← this file
├── meta.json            ← complete
├── checklists/
│   └── requirements.md  ← complete
└── tasks/               ← populated by /spec-kitty.tasks
```

## Risk Mitigation

| Risk | Mitigation | Phase |
|---|---|---|
| Config change breaks agents | Restic backup + openclaw.json snapshot before any changes | Phase 1 |
| Haiku produces wrong inbox routing | Validate with 3+ real inputs before production switch | Phase 2 |
| Habits weekly review degrades on Haiku | Test weekly review separately; if fails, keep habits on Sonnet until #141 splits the agent | Phase 2 |
| Escalation misses critical items | Test with known escalation triggers; if any doubt, keep on Sonnet | Phase 2 |
| Config doesn't persist across restart | Verify after restart in Phase 3 | Phase 3 |

## Complexity Tracking

No charter violations. This feature:
- Modifies one config file on office2
- Updates existing registry and documentation files
- Creates no new services, ports, credentials, or data flows
- Follows standard Tier 2 change control

## Branch Contract

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **true**

---

**PLAN COMPLETE** — Ready for `/spec-kitty.tasks --feature 021-openclaw-agent-model-tiering`
