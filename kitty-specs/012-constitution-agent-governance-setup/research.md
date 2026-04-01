# Research: Constitution & Agent Governance Setup

**Feature**: 012-constitution-agent-governance-setup
**Date**: 2026-04-01

## Decision 1: Observation Mode Delivery Mechanism

### Evaluation

| Mechanism | Impl Cost | Content Flexibility | Mac/iPhone | Critical Alerts | Manageability |
|-----------|-----------|-------------------|------------|-----------------|---------------|
| WhatsApp | LOW | POOR (5-6 lines max) | GOOD (push) | STRONG (push notification) | MODERATE (no rewrite/delete) |
| Email | HIGH (no infra exists) | EXCELLENT | GOOD (push) | MODERATE (inbox noise) | MODERATE |
| Dashboard | MODERATE-HIGH (new service) | EXCELLENT | GOOD (Tailscale) | NONE (pull only) | GOOD |
| Obsidian notes | VERY LOW | EXCELLENT | EXCELLENT (synced) | NONE (pull only) | EXCELLENT (rewritable, deletable, partitioned) |

### Hybrid Combinations Evaluated

| Combination | Verdict |
|-------------|---------|
| **Obsidian + WhatsApp (critical only)** | Best cost/value. Rich content in vault. Push for urgent items only. |
| Obsidian + Email (critical only) | Email infra overkill for alert-only use. |
| Dashboard + WhatsApp | Two new components to build. Over-engineered for 2 agents. |
| WhatsApp + Obsidian (detail) | Most WhatsApp messages would just say "check Obsidian." Noisy. |

### Decision: Obsidian (primary) + WhatsApp (critical alerts only)

**Rationale:**
1. **Minimal implementation cost.** The intelligence layer writes a markdown file into `notes/00-System/agent-activity/`. Obsidian Sync handles delivery. No new services.
2. **Unconstrained content.** Whether 2 lines or 50, markdown handles it.
3. **Rewritable rolling summary.** Agent overwrites each cycle. Kent always sees current state. No inbox clutter.
4. **WhatsApp proportionate for critical alerts.** Errors and security concerns are rare, short messages. Points to Obsidian for detail. Keeps WhatsApp volume low (reduces Baileys ban risk).
5. **Graceful degradation.** If WhatsApp/Baileys breaks, Obsidian still contains critical alerts (pull-only). Email can be added later as a replacement critical-alert channel.

**Critical implementation note:** Existing `agents/logs/` is outside Obsidian Sync scope (git-synced only). Surfaced digests must be written inside `notes/` — specifically to a path like `notes/00-System/agent-activity/`. Raw audit logs remain at `agents/logs/`.

**WhatsApp DM policy note:** Currently `disabled` per 2026-03-31 incident. F012 implements the WhatsApp critical-alert path but it activates only when DM policy is re-enabled. Obsidian path works regardless.

### Alternatives Considered
- Email: rejected due to high implementation cost for F012 scope (no email integration exists)
- Dashboard: rejected as primary because it cannot push critical alerts; would still need a push companion
- WhatsApp-primary: rejected because content length constraints make it unsuitable for detailed digests

---

## Decision 2: Surfacing Cadence

### Decision: Daily digest + immediate critical alerts

- Intelligence layer runs once daily at **7:00 PM ET** (after the last inbox processing run at 6:00 PM)
- Produces a consolidated digest covering all agent runs that day
- Critical alerts (errors, security, failures) surface **immediately** at run time — not batched
- Immediate alerts go to WhatsApp AND are written to the Obsidian digest

**Rationale:** Per-run surfacing is excessive for 3x/day capture + 1x/day habits. Daily digest is proportionate. If volume increases, cadence can move to 2x/day without architectural change.

---

## Decision 3: Time Window

### Decision: Rolling 24-hour window, reset at digest time

- Each daily digest covers activity since the previous digest
- Obsidian file is overwritten each cycle — always shows the most recent period
- No accumulation of old digests in the vault

---

## Decision 4: Retention

| Content | Retention | Mechanism |
|---------|-----------|-----------|
| Surfaced digest (Obsidian) | Current cycle only | Overwritten each run |
| Raw audit logs (`agents/logs/`) | 90 days | Git-synced. Log rotation after 90 days to `agents/logs/archive/` |
| Critical alert messages (WhatsApp) | Indefinite | WhatsApp chat history, not system-managed |

**Rationale:** Overwriting rather than appending prevents vault clutter. History lives in audit logs — that is their purpose.

---

## Decision 5: Intelligence Layer Architecture

### Decision: Centralized summarization service (separate scheduled job)

- A dedicated script reads all agent logs and produces a unified digest
- Not embedded in individual agents — decoupled from agent execution
- Runs on a cron schedule (daily at 7:00 PM ET) on office2
- Reads standardized log files, applies filtering/consolidation rules, writes Obsidian digest

**Rationale:**
- Standardized log format enables centralized processing
- Universal improvements apply to all agents at once
- Decoupled from agent execution — agent run time unaffected
- Single place to adjust filtering rules, summary format, and delivery logic
- Scales without modifying each agent as new agents are added

**Future extensibility:** When agent count grows or log formats diverge, per-agent summarization rules can be added to the centralized service without rearchitecting.

---

## Decision 6: ClawHub Constraint Placement

### Decision: Constitution only (not in current agent standing orders)

- Neither felix-admin-capture nor felix-admin-habits has skill management capability
- Adding the constraint to their AGENTS.md would be dead text — they cannot install skills
- The constraint is encoded in the constitution (FR-001) and the skill-authoring skill (FR-015)
- Any future agent given skill management capability will have the constraint via the constitution reference in their standing orders

---

## Decision 7: Agent Registry Format

### Decision: Dual-format — JSON (machine-readable) + Markdown (human-readable)

- `docs/constitution/agent-registry.json` — authoritative operational record
  - Used by the centralized summarizer, agents, and tooling
  - Fields per agent: name, team, scope, gate, observation_mode, deployed_feature, gate_history
- `docs/constitution/AGENT-REGISTRY.md` — human-readable narrative view
  - Generated/maintained alongside JSON, not a separate source of truth
  - Used by Kent for quick reference

**Schema for agent-registry.json:**
```json
{
  "version": "1.0",
  "updated": "2026-04-01",
  "updated_by": "F012",
  "agents": {
    "felix-admin-capture": {
      "team": "SuperAdmin (B)",
      "scope": "Obsidian inbox processing — classifies notes, routes to vault, creates Vikunja tasks",
      "gate": 1,
      "observation_mode": "on",
      "deployed_feature": "F008",
      "registered": "2026-04-01",
      "gate_history": [
        { "date": "2026-04-01", "gate": 1, "reason": "Initial registration (F012)", "decided_by": "Kent Gale" }
      ]
    }
  }
}
```

**Future extensibility:** When Felix becomes self-modifying, the JSON registry moves to a runtime-writable store on office2 with sync-back to repo. For now, repo-authored and deployed.

---

## Decision 8: Observation Mode File Structure

### Decision: Per-agent files + consolidated overview

```
~/second-brain/notes/00-System/agent-activity/
  overview.md                    # Consolidated digest across all agents
  felix-admin-capture.md         # Per-agent detail
  felix-admin-habits.md          # Per-agent detail

~/second-brain/agents/logs/      # Unchanged — raw audit trail, git-synced
  inbox-processing-2026-04-01.md
  habits-checkin-2026-04-01.md
```

- `overview.md` is the primary file Kent checks — answers "what do I need to know?"
- Per-agent files provide drill-down if the overview surfaces something needing investigation
- All files overwritten each digest cycle (rolling)
- Vault path `notes/00-System/agent-activity/` chosen to align with vault taxonomy

---

## Research: Skill-Authoring Skill Content

### OpenClaw Skill Conventions (from deployed skills)

Skills are **knowledge documents**, not function definitions. The agent reads SKILL.md and follows its instructions using available tools (primarily `exec` for curl commands). Skills teach agents *how* to interact with a service.

**Required frontmatter:** name, description (with trigger phrases and scope boundaries), version (semver)

**Body structure:** Title → Prerequisites/health check → Step-by-step operations → Error handling → Examples → References

### Best Practices to Encode

1. **Scope boundaries** — state what the skill does AND does not handle in the description frontmatter
2. **Health check first** — always verify service availability before operations
3. **Pre-flight validation** — reject bad input before making external calls
4. **Credential store pattern** — read from `/data/services/openclaw/secrets/`, never embed
5. **Resolve by name** — never hardcode IDs; resolve projects, labels, entities by name at runtime
6. **Every error path documented** — categorize as transient vs. permanent, specify agent behavior for each
7. **Never fail silently** — every failure produces observable output
8. **Never invent data** — halt and report if required information is missing
9. **Identity labels required** — every agent-created task must have a label (personal/intentional/metalcasework)
10. **Logging for accountability** — skills provide structured outputs; calling agents log them
11. **Concrete examples** — show full workflows so agents understand operation sequence

### Community Skill Review Criteria

| Category | Check |
|----------|-------|
| Security | Credential handling, arbitrary execution, path access, external communication, Tailscale-only |
| Quality | Valid frontmatter, accurate description, error paths, pre-flight validation, health check, examples |
| Compatibility | Required dependencies available on office2, no scope conflicts, credential store pattern, identity labels |
| Scope | One responsibility, explicit "does not handle" list, narrow enough for clear agent decision-making |

### Pattern References

- **Format reference:** `scripts/openclaw/skills/whisper/SKILL.md` — simplest skill, clean structure
- **Comprehensive reference:** `scripts/openclaw/skills/vikunja-api/SKILL.md` — error handling, credentials, structured operations
- **Description best practice:** spec-kitty skills — trigger/anti-trigger phrases in frontmatter
