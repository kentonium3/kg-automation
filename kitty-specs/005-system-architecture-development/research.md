# Research: System Architecture Development

**Feature**: 005-system-architecture-development
**Date**: 2026-03-29
**Strategy**: Breadth-first — gather all research before synthesizing deliverables

## Research Tasks

### Phase 0A: Local Audit (no external access)

#### RA-001: Current State Validation

**Question**: What has actually been built (F001-F004) and how does it compare
to what v0.3 designed?

**Sources**:
- `docs/design/personal-ai-system-spec-v03.md`
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/data/credential-manifest.json`
- `docs/func-spec/F001_vikunja_docker_deploy.md`
- `docs/func-spec/F002_openclaw_install.md`
- `docs/func-spec/F003_transcribe_api.md`
- `docs/func-spec/F004_whatsapp_channel.md`
- `docs/handbooks/` (all operational runbooks)

**Output**: Validated inventory of deployed services, ports, credentials, data
flows. List of deviations from v0.3 plan. List of v0.3 items not yet built.

---

#### RA-002: Constitution and Governance Audit

**Question**: What governance is currently in place, and what gaps exist for the
expanded vision?

**Sources**:
- `.kittify/constitution/constitution.md`
- `docs/design/architecture/security-posture.md`

**Output**: Current governance state. Gaps relative to the four new constitution
directives (narrow scope, earned autonomy, central logging, safety parameters).

---

### Phase 0B: OpenClaw Capability Research (external)

#### RB-001: Agent Teams and Organization

**Question**: RQ-1 — Does OpenClaw support the concept of agent teams natively,
or does this need to be modeled differently?

**Sources**: docs.openclaw.ai, github.com/openclaw/openclaw

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

#### RB-002: Skill/Agent/Orchestrator Mapping

**Question**: RQ-2 — How should the five capability areas map to OpenClaw
skills, agents, and orchestrators?

**Sources**: docs.openclaw.ai (skills, agents, orchestrators documentation)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

#### RB-003: Action Logging

**Question**: RQ-3 — What is the right mechanism for agent action logging?

**Sources**: docs.openclaw.ai (logging, observability documentation)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

#### RB-004: Autonomy Gate Implementation

**Question**: RQ-4 — How should the three-gate autonomy model be implemented
within OpenClaw?

**Sources**: docs.openclaw.ai (permissions, approval flows, human-in-the-loop)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

#### RB-005: Claude Code / Spec-Kitty Coordination

**Question**: RQ-5 — How should OpenClaw orchestrate or coordinate with Claude
Code and spec-kitty (used by the Development team)?

**Sources**: docs.openclaw.ai (external tool integration, shell skills)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

#### RB-006: System Identity Representation

**Question**: RQ-14 — How should Felix (the system-wide identity) be represented
within OpenClaw's architecture?

**Sources**: docs.openclaw.ai (personas, identity, configuration)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

### Phase 0C: Integration and Tool Research (external, scoped)

#### RC-001: SuperAdmin Integrations

**Question**: RQ-6 — What integrations are needed for SuperAdmin? Minimum:
Google Calendar, Gmail. What else?

**Sources**: User stories from spec (Capability B), docs for confirmed tools

**Output**: List of required integrations with purpose, auth method, data flow
direction. Known tools documented. Open decisions documented with need, options,
criteria.

---

#### RC-002: BizOps Business Systems

**Question**: RQ-7 — What business systems are needed for BizOps?

**Sources**: User stories from spec (Capability E), Kent's input

**Output**: List of required systems. HubSpot confirmed as mentioned. Other
CRM, invoicing, order management — open decisions documented.

---

#### RC-003: Content Creation Tools

**Question**: RQ-8 — What AI tools are needed for Content Creation beyond Canva?

**Sources**: User stories from spec (Capability D), research brief seed stories

**Output**: Canva confirmed. Additional tools — open decisions documented with
need, options, criteria.

---

#### RC-004: Email Integration

**Question**: RQ-9 — What is the right approach to email integration given
security constraints?

**Sources**: docs.openclaw.ai (email channels), Gmail API docs (scoped)

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

### Phase 0D: Data, Privacy, and Identity Research

#### RD-001: Data Ownership Model

**Question**: RQ-10 — What data should persist in Vikunja vs OpenClaw vs the
second brain?

**Sources**: Vikunja API docs (scoped), OpenClaw docs, existing architecture docs

**Output**: Canonical data ownership model per capability area.

---

#### RD-002: SuperAdmin Privacy Boundary

**Question**: RQ-11 — What is the right scope boundary for SuperAdmin relative
to 02-Growth/_private/?

**Sources**: Existing constitution, second brain structure

**Output**: Documented boundary with clear rules. 02-Growth/_private/ remains
absolute non-negotiable. Boundary for other 02-Growth/ areas documented.

---

#### RD-003: Personal Brand Content Domain

**Question**: RQ-12 — What constitutes personal brand content and where does it
live?

**Sources**: Second brain structure, Kent's input

**Output**: Definition and location. May be an open decision requiring Kent's input.

---

#### RD-004: Identity Model Extension

**Question**: RQ-13 — How should the identity model extend for personal,
Intentional, and metal casework?

**Sources**: v0.3 spec (current two-identity model), OpenClaw persona support

**Output**:
- Decision: [to be filled by research]
- Rationale: [to be filled]
- Alternatives considered: [to be filled]

---

## Research Execution Notes

- All research tasks are independent and can be parallelized
- Phase 0A (local audit) has no external dependencies
- Phase 0B (OpenClaw) is the critical path — most deliverables depend on
  understanding OpenClaw's native capabilities
- Phase 0C and 0D can run in parallel with 0B
- Open decisions are expected and acceptable — document them rather than assume
