---
title: "F010: Constitution Update and Minimal Agent Setup"
doc_type: func-spec
status: stub
feature: F010
---

# F010: Constitution Update and Minimal Agent Setup

**Version**: 0.1 (stub — full spec to be written after F009)
**Priority**: HIGH
**Type**: Infrastructure

---

## Status

This is a placeholder stub. The full spec will be written after F009
(Daily Habit Check-in and Commitment Tracking) is complete.

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

**Rationale**: ClawHub is an open public registry. Any community skill
executes with agent-level access to office2 credentials and the second brain.
Supply chain risk is real — this is the same reason the constitution already
prohibits community OpenClaw skills without source review. When agents gain
the ability to install skills autonomously, this human-in-the-loop gate must
be preserved as a hard boundary, not a preference.

**Source of this requirement**: Identified during F007 planning (2026-03-30)
when ClawHub documentation was reviewed. Applies to any future feature that
gives agents skill management capabilities.

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

**Why this matters**: Without this skill, agents writing skills will drift
from project standards over time. Each agent will develop its own
conventions, error patterns, and assumptions. The skill-authoring skill
is the mechanism that keeps the system coherent as it grows.

**Evolution**: This skill must be updated whenever project standards change
— new safety protocols, new conventions, new tool patterns. It is a living
document, not a one-time artifact. The Core Hub agent responsible for
system governance owns this skill's maintenance.

**Source of this requirement**: Identified during F007 implementation
(2026-03-30) as a necessary prerequisite for agent-driven system extension.

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
  the tools and services in the stack (supply chain attacks, LLM-specific
  threats, etc.)?

**Cadence**: Weekly (Sunday, before or after the weekly review heartbeat)

**Output**: A security briefing delivered to Kent via WhatsApp summarizing
findings by severity: critical (immediate action required), advisory
(attention recommended), and informational (no action needed, for awareness).

**Gate**: This agent operates at Gate 1 (Human In The Middle) indefinitely
for any remediation actions. It can observe and report autonomously, but
cannot modify system configuration, rotate credentials, or take corrective
action without Kent's explicit approval.

**Team placement**: Whether this belongs to Core Hub (A) or as an
independent capability is TBD. Arguments for Core Hub: it's system
infrastructure. Arguments for independence: an adversarial reviewer
should be somewhat isolated from the system it reviews. Recommend
resolving during F010 full spec authoring.

**AI model for security review — open question:**

Using a different AI model (Gemini, Codex, or other) for the security
agent is worth evaluating for two reasons:

1. **Adversarial independence** — a model from a different provider
   has no shared training, no shared failure modes, and no shared
   blind spots with Claude. If Claude has a systematic vulnerability
   in how it reasons about security (prompt injection susceptibility,
   tendency to rationalize unsafe configurations), a different model
   is less likely to share it.

2. **Vendor diversity as a security property** — if Anthropic's API
   has an outage, the security review still runs. If a future Claude
   update introduces a regression in security reasoning, a separate
   model provides a check.

The counterargument is that Claude can be prompted to adopt an
adversarial outsider persona effectively, and keeping the stack
homogeneous reduces operational complexity. If model quality and
effectiveness are comparable on security reasoning tasks, Claude
with a well-crafted adversarial prompt may be sufficient.

**Recommendation**: Evaluate during F010 full spec authoring by
testing both approaches on a sample security review task against the
live system. Let performance determine the choice, not assumption.
OpenClaw supports multiple models per agent — this is a configuration
choice, not an architectural constraint.

**Threat intelligence feed:**

The security agent should monitor one or more reliable threat intelligence
sources as part of its weekly review — not just audit the local system
but bring external context to the assessment.

Candidate sources (to be evaluated during F010 spec authoring):
- **CISA Known Exploited Vulnerabilities feed** (RSS/JSON) — authoritative,
  US government, covers actively exploited CVEs
- **SANS Internet Storm Center** (RSS) — practitioner-oriented daily threat
  briefings, high signal-to-noise
- **NVD (National Vulnerability Database)** (JSON API) — comprehensive CVE
  database, queryable by product/vendor (e.g., filter for Docker, Node.js,
  OpenClaw dependencies)
- **OpenClaw release notes / changelog** — any security-relevant updates
  to the orchestration engine itself
- **Tailscale security advisories** — relevant given Tailscale is the
  network perimeter
- **Anthropic safety/security updates** — LLM-specific threat patterns

The agent's job is not to read every feed exhaustively but to filter for
threats relevant to the specific tools, languages, and services in the
Felix stack and surface anything actionable. A weekly digest of
"here's what's new in the threat landscape that's relevant to you"
is the goal — not a firehose.

This is one of the strongest arguments for a non-Claude model for this
agent: a model that can fetch and reason over live feed content without
being constrained to a training cutoff brings more current threat
awareness than a static knowledge base.

**Source of this requirement**: Identified during F007 implementation
(2026-03-30) as a necessary ongoing capability given the system's access
to credentials, second brain content, external services, and open source
dependencies.

---

## Placeholder — full spec coming

The full spec covering agent team configuration, gate initialization, and
constitution document updates will be written when this feature is next
in the implementation queue.

---

**END OF STUB**
