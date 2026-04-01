---
title: "F011: Constitution Update and Minimal Agent Setup"
doc_type: func-spec
status: stub
feature: F011
---

# F011: Constitution Update and Minimal Agent Setup

**Version**: 0.1 (stub — full spec to be written after F010)
**Priority**: HIGH
**Type**: Infrastructure

---

## Status

This is a placeholder stub. The full spec will be written after F010
(Obsidian Sync on office2) is complete.

---

## Known Requirements (captured before full spec is written)

### Constitution directives to formalize

The following four directives must be incorporated into the constitution:

1. **Narrow agent scope** — agents have one clearly defined responsibility
2. **Earned autonomy (three-gate model)** — Human In The Middle → Human
   Monitored → Autonomous. Every agent starts at Gate 1, no exceptions.
3. **Central action logging** — all agent actions logged centrally with
   team, action type, and autonomy gate level
4. **Safety parameters and clear boundaries** — agents stop and alert when
   asked to do something outside their scope or that they don't know how
   to do. Never fail silently.

### Observation Mode — new agent visibility

**REQUIREMENT — Observation Mode for new and changed capabilities:**

Whenever a new agent capability is deployed or an existing one is
significantly changed, Felix must automatically enter an Observation
Mode for that capability: a daily WhatsApp summary of what the agent
did is delivered to Kent for a configurable period, until Kent
explicitly turns it off.

**How it works:**
- When a new agent is deployed or a significant change is made, a flag
  is set: `observation_mode: true` with a start date
- The daily briefing agent (F014) or a dedicated observation skill
  queries each agent in observation mode and includes a summary of its
  recent actions in the daily WhatsApp message
- Kent can turn off observation mode for any agent by saying "I don't
  need observation reports for inbox processing anymore" via WhatsApp
- Default observation period: until Kent explicitly disables it

**Applies to**: Every new agent deployed, every significant change to
an existing agent's scope or behavior.

**Source of this requirement**: Identified during F008 completion
(2026-03-31) as a governance pattern for building trust with new agent
capabilities.

### Agent configuration notes

**CRITICAL — ClawHub community skill installation constraint:**

When configuring Core Hub agents (felix-core-*) with any capability to
install or modify OpenClaw skills, their standing orders MUST explicitly
include the following constraint:

> Community skills from ClawHub require Kent's explicit approval before
> installation. The agent must present the full SKILL.md content and any
> supporting files to Kent for review. The agent must never self-approve
> a community skill installation, regardless of autonomy gate level.
> This constraint does not expire and applies even at Gate 3 (Autonomous).

**Source of this requirement**: Identified during F007 planning (2026-03-30).

### Skill authoring skill

**REQUIREMENT — Skill-writing capability:**

Before any agent is given the ability to write or modify OpenClaw skills,
a dedicated skill-authoring skill must exist. This skill teaches agents
how to write skills that conform to current project standards.

The skill-authoring skill must encode:
- The current OpenClaw SKILL.md format and frontmatter requirements
- Project-specific conventions (credential access patterns, error handling
  requirements, the "never fail silently" rule, identity label requirements)
- Safety protocols (no credentials in skill code, no hardcoded IDs,
  halt-on-ambiguity behavior per FR-5 pattern established in F007)
- The ClawHub community skill review constraint
- How to write skills that are narrow in scope (one responsibility)
- How to write skills that produce structured errors the calling agent
  can act on

**Source of this requirement**: Identified during F007 implementation
(2026-03-30).

### Security review agent

**REQUIREMENT — Adversarial security capability:**

The system needs a dedicated security review agent that operates with an
adversarial mindset — not just monitoring known baselines (which audit.sh
already does) but actively looking for new vulnerabilities, bad practices,
and emerging risks across the full system stack.

**What distinguishes this from audit.sh:**
- `audit.sh` detects drift from known baselines — it catches what changed
- The security agent reasons about what *should* concern us — it evaluates
  whether the current state is safe, not just whether it changed
- `audit.sh` is reactive; the security agent is proactive and analytical

**Scope of the security agent's review:**
- Credential exposure risks (secrets, tokens, OAuth credentials)
- Agent permission scope — are any agents accumulating more access than
  their defined scope requires?
- Skill and plugin supply chain — any new dependencies introduced since
  last review? Any open source updates with security implications?
- Network exposure — any new open ports, unexpected outbound connections,
  or Tailscale configuration changes?
- OpenClaw agent behavior — any agents operating outside their
  documented standing orders?
- Second brain access patterns — any vault access inconsistent with
  the defined access model?
- Account access review — API keys, OAuth tokens, service credentials
  — any that should be rotated or have unusual recent activity?
- Emerging threat context — are there new attack patterns relevant to
  the tools and services in the stack?

**Cadence**: Weekly (Sunday)

**Gate**: Gate 1 indefinitely for any remediation actions. Observe and
report autonomously; never modify configuration without Kent's approval.

**AI model for security review — open question:**
- Evaluate using a non-Claude model (Gemini, Codex) for adversarial
  independence and vendor diversity. OpenClaw supports multiple models
  per agent — this is a configuration choice.
- Let performance on a sample security review task determine the choice.

**Threat intelligence feeds (candidate sources):**
- CISA Known Exploited Vulnerabilities (RSS/JSON)
- SANS Internet Storm Center (RSS)
- NVD — queryable by product/vendor for Docker, Node.js, OpenClaw deps
- OpenClaw release notes / changelog
- Tailscale security advisories
- Anthropic safety/security updates

**Source of this requirement**: Identified during F007 implementation
(2026-03-30) and reinforced by the 2026-03-31 WhatsApp pairing /
axios supply chain incidents.

---

## Placeholder — full spec coming

The full spec covering agent team configuration, gate initialization, and
constitution document updates will be written when this feature is next
in the implementation queue.

---

**END OF STUB**
