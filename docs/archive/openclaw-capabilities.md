---
title: "OpenClaw Capability Research: F005 System Architecture Development"
doc_type: explanation
status: approved
owners: [kgale]
---
# OpenClaw Capability Research: F005 System Architecture Development

**Date**: 2026-03-29
**WP**: WP02 — OpenClaw Capability Research
**Sources**: docs.openclaw.ai, github.com/openclaw/openclaw
**Status**: Complete

---

## RQ-1/RQ-2: Agent Teams, Skills, and Orchestrators

### Decision

OpenClaw does **not** support "agent teams" as a native first-class concept.
However, it provides sufficient primitives to construct a team-like topology
using **multi-agent routing**, **broadcast groups**, **subagent orchestration**,
and **per-agent workspaces**.

The five capability area teams would map to OpenClaw as **named agents**, each
with their own workspace, identity, skills, and tool policies, coordinated
through bindings and broadcast groups.

### Proposed Team Mapping

| Team | Agent Name | Role | Key Config |
|------|-----------|------|------------|
| Core Hub (A) | felix-core | Infrastructure, routing, heartbeat, monitoring | Broadcast groups, agent-to-agent messaging |
| SuperAdmin (B) | felix-admin | Executive function, calendar, email | Restricted tool policy (allowlist), approval gates |
| Development (C) | felix-dev | App building, spec-kitty, Claude Code | Full exec access, sandboxed |
| Content Creation (D) | felix-content | Content generation, Canva, media | Content-focused skills, media handling |
| BizOps (E) | felix-bizops | CRM, marketing, reporting | Business system skills |

Each agent would have its own `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, and
`TOOLS.md` in its workspace.

### Rationale

- **Agents**: Each agent is "a fully scoped brain with its own workspace, state
  directory, and session store." Agents maintain separate auth profiles, skills,
  models, and sessions with "no cross-talk unless explicitly enabled."
- **Skills**: AgentSkills-compatible folders containing `SKILL.md` with YAML
  frontmatter. Skills load from six locations with workspace taking highest
  priority. Skills can be gated on required binaries, env vars, config, and OS.
- **Orchestration**: Subagents provide hierarchical orchestration with
  `maxSpawnDepth: 2` enabling main → orchestrator → worker pattern. Broadcast
  groups allow multiple agents to process the same message (parallel or
  sequential strategy).

### Alternatives Considered

- **Single agent with sub-personas**: Simpler but loses isolation, per-team
  tool policies, and independent session histories. Less auditable.
- **Subagent-only model**: One master agent spawning subagents per request.
  Loses persistent state and is limited to 5 children per agent.

### Gaps

- No native "team" abstraction — teams must be constructed from individual
  agents + routing config + naming conventions
- Agent-to-agent messaging is disabled by default (must be explicitly
  allowlisted via `tools.agentToAgent`)
- No native workflow orchestration between agents (no state machines, no
  dependency graphs) — coordination logic lives in standing orders or hooks
- Broadcast groups are currently WhatsApp-only (experimental, added 2026.1.9)

---

## RQ-3: Logging and Observability

### Decision

OpenClaw provides **substantial native logging** but does **not** provide a
unified, centralized action audit log suitable for the constitution directive.
A custom logging layer will be needed, though OpenClaw provides excellent
building blocks.

### What OpenClaw Logs Natively

| Log Type | Format | Location | Content |
|----------|--------|----------|---------|
| Gateway logs | JSONL | /tmp/openclaw/openclaw-YYYY-MM-DD.log | All gateway events |
| Command logs | JSONL | ~/.openclaw/logs/commands.log | All command events (bundled hook) |
| Session transcripts | JSONL | ~/.openclaw/agents/\<id\>/sessions/\<id\>.jsonl | Full conversation history |
| Cron run history | JSONL | ~/.openclaw/cron/runs/\<jobId\>.jsonl | Scheduled job execution |
| OpenTelemetry | OTLP/HTTP | Configurable collector | Metrics, traces, logs |

**OpenTelemetry integration** exports:
- Metrics: token usage counters, message flow histograms
- Traces: model usage, webhook processing, message handling spans
- Logs: optionally via OTLP/HTTP to any compatible collector
- Diagnostic events: model usage (tokens, cost, duration), message flow,
  queue/session state transitions, periodic heartbeat aggregations

### What's Missing for Felix

- No single unified "action log" spanning all agents
- No cross-agent action correlation
- No semantic action classification (e.g., "file written", "email sent")
- No built-in dashboard for audit review

### Recommended Approach

Use the OpenTelemetry plugin to export all signals to a collector (e.g.,
Grafana stack on office2), then build a thin Felix-specific layer that:
1. Consumes OTLP traces/metrics/logs
2. Enriches with Felix-specific metadata (team, action type, autonomy gate)
3. Provides a queryable audit store

### Alternatives Considered

- **Custom hook per action category**: Simpler but fragile, doesn't capture
  tool execution details
- **Rely solely on session transcripts**: Contains everything but requires
  parsing conversation history rather than structured action records

### Gaps

- No cross-agent action correlation natively
- No semantic action audit trail (must be derived from raw logs)
- OpenTelemetry covers transport but not Felix-specific semantics

---

## RQ-4: Three-Gate Autonomy Model

### Decision

OpenClaw provides **strong primitives** for implementing the three-gate model.
The exec approval system, standing orders, tool policies, and sandbox modes
map naturally to the three tiers. The gate-switching logic must be a custom
layer.

### Gate-to-OpenClaw Mapping

| Gate | OpenClaw Configuration | Behavior |
|------|----------------------|----------|
| Gate 1: Human In The Middle | `tools.exec.ask: "always"`, `tools.exec.security: "allowlist"` | Every command requires human approval. Only pre-approved binaries can run. |
| Gate 2: Human Monitored | `tools.exec.ask: "on-miss"`, standing orders with approval gates | Agent acts on allowlisted operations, prompts on unknown. Async review via cron reports. |
| Gate 3: Autonomous | `tools.exec.security: "full"`, `tools.exec.ask: "off"` | Unrestricted execution within standing order scope. Heartbeat monitoring only. |

### Key OpenClaw Features

- **Exec approvals**: Display command, args, workdir, agent ID, host metadata.
  User can "Allow once", "Always allow", or "Deny"
- **Multi-channel approval routing**: Approvals forwarded to Discord/Telegram/
  Slack via `/approve <id> [allow-once|allow-always|deny]`
- **Standing orders**: Define scope of authority with triggers, approval gates,
  and escalation rules per "program"
- **Delegate architecture tiers**: Tier 1 (Read-Only + Draft), Tier 2 (Send
  on Behalf), Tier 3 (Proactive) — maps to the three gates

### Alternatives Considered

- **Pure standing-order approach**: Define all tiers as standing order configs
  with no exec-level enforcement. Risk: instructions are advisory, not enforced
  at gateway level
- **Separate gateway instances per tier**: One per autonomy level. Overly
  complex, loses coordination benefits

### Gaps

- No native "autonomy level" concept that can be queried or switched
  programmatically
- Gate transitions must be config changes (manual or scripted), not a built-in
  state machine
- No built-in audit of gate transitions themselves
- Approval timeout defaults to denial (safe) but no auto-escalation to
  alternative channel

---

## RQ-5: External Tool Coordination (Claude Code, spec-kitty)

### Decision

OpenClaw can orchestrate external tools through **exec tool** (shell execution),
**inbound webhooks**, **cron scheduling**, and **custom hooks**. The coordination
model is primarily command-line invocation and event-driven.

### Coordination Mechanisms

| Mechanism | Use Case | Details |
|-----------|----------|---------|
| Exec tool | Run Claude Code or spec-kitty commands | Foreground/background modes, timeout configurable (default 1800s) |
| Inbound webhooks | External tools notify OpenClaw | `POST /hooks/wake`, `POST /hooks/agent`, custom mapped webhooks, bearer token auth |
| Cron scheduling | Scheduled spec-kitty workflows | Isolated sessions, announce/webhook/internal delivery modes |
| Custom hooks | Event-driven coordination | TypeScript handlers for message, session, command, gateway events |

### How It Would Work

- **Claude Code**: Agent runs `claude --print "implement feature X"` via exec
  tool. Background sessions return immediately, announce completion via system
  events.
- **Spec-kitty**: Agent runs `spec-kitty next --agent felix-dev` via exec.
  CI/spec-kitty hooks call OpenClaw inbound webhooks on completion.
- **GitHub Actions**: Webhook to OpenClaw on CI completion or PR events.

### Alternatives Considered

- **MCP integration**: OpenClaw has `openclaw mcp` CLI but docs don't detail
  using it for tool coordination. Would need investigation.
- **Dedicated "tool runner" agent**: Adds complexity without clear benefit
  over direct exec.

### Gaps

- No native outbound webhooks (only inbound) — tools must call OpenClaw, not
  the reverse
- No native event bus beyond hooks
- Long-running tool invocations need careful timeout configuration
- No native integration with Claude Code agent SDK or spec-kitty

---

## RQ-14: System Identity (Felix)

### Decision

OpenClaw supports **per-agent identity** through workspace files (`IDENTITY.md`,
`SOUL.md`), which maps well to a system-wide "Felix" identity with per-team
sub-identities. No native "persona hierarchy" exists — the unified identity
must be constructed through configuration.

### Identity Architecture

| File | Purpose | Per-Team? |
|------|---------|-----------|
| IDENTITY.md | Name, avatar, visual identity | Yes — "Felix" prefix with team suffix |
| SOUL.md | Persona, communication style, boundaries | Yes — team-specific personality |
| AGENTS.md | Operating instructions, standing orders | Yes — team-specific scope |
| USER.md | User profile and preferences | Shared across all teams |

### Channel Identity

- **WhatsApp**: Single phone number = single Felix identity. Internal routing
  determines which agent-brain processes messages. User always sees "Felix."
- **Sub-team differentiation**: Must be textual ("Felix Dev here: ..."), not
  visual — WhatsApp constrains to one profile picture per number
- **Delegation model**: "The agent never impersonates a human. It sends under
  its own account with explicit delegation permissions."

### Identity Model for Three Business Contexts

| Context | OpenClaw Representation |
|---------|----------------------|
| Personal (Kent Gale) | Default identity, personal Google credentials |
| Intentional LLC | Agent config with Intentional branding in SOUL.md |
| Metal Casework | Agent config with metal casework branding in SOUL.md |

Identity routing by Vikunja labels (personal/intentional) already exists
from F001. Metal casework would add a third label.

### Alternatives Considered

- **Single agent with role-switching**: Loses isolation and auditability
- **Multiple WhatsApp numbers**: Defeats unified Felix identity, expensive
- **Webhook-based persona router**: OpenClaw's native routing handles this

### Gaps

- No native persona hierarchy (parent + children)
- No way to dynamically announce which team is responding without explicit
  instructions in AGENTS.md
- WhatsApp constrains to single visual identity
- No identity federation — keeping identity files consistent requires manual
  coordination or shared templates

---

## Summary: What OpenClaw Can Do vs. What Must Be Built

### Natively Supported

- Multi-agent with full isolation (workspaces, sessions, auth, tool policies)
- Per-agent identity/persona files
- Channel routing to specific agents (binding-based)
- WhatsApp integration (Baileys, already deployed)
- Shell command execution (foreground/background, sandboxed)
- Human approval flows (allow once/always/deny, multi-channel routing)
- Tool restriction per agent (allow/deny lists, sandbox isolation)
- Scheduled execution (cron + heartbeat)
- Standing authority (scoped programs with approval gates)
- Inbound webhooks (token-authenticated)
- JSONL logging (gateway, sessions, commands, cron)
- OpenTelemetry export (metrics, traces, logs)
- Subagent orchestration (hierarchical, depth-controlled)
- Broadcast groups (multi-agent parallel/sequential, WhatsApp)
- Event-driven hooks (TypeScript handlers)

### Must Be Built Around OpenClaw

| Requirement | Approach |
|-------------|----------|
| Team abstraction | Convention-based naming, shared templates, routing config |
| Unified Felix identity | Shared IDENTITY.md templates; WhatsApp single-number is natural Felix identity |
| Centralized audit log | OpenTelemetry collector + custom enrichment layer |
| Cross-agent correlation | Custom correlation IDs via hooks or standing order conventions |
| Three-gate switching | Config management layer adjusting exec security/ask per agent |
| Gate transition audit | Custom logging of config changes |
| Outbound notifications | Custom hooks that POST to external services |
| Spec-kitty integration | Shell exec + inbound webhooks from CI/spec-kitty |
| Claude Code coordination | Shell exec with timeout management for long sessions |
| Persona hierarchy | Template/convention management, possibly validation hook |
| Inter-team workflow | Agent-to-agent messaging (explicitly enabled) + standing orders |
