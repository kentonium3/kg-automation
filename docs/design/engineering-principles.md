---
title: kg-automation Engineering Principles
doc_type: standard
status: approved
last_updated: '2026-06-19'
last_validated: '2026-06-19'
owners: [kgale]
version: '1.1'
tags: [architecture, principles, governance]
---

# kg-automation Engineering Principles

These principles sit between broad Felix governance and individual feature
specs. They are intended to guide new work before it creates retrofit debt.

Principles 1–10 approved 2026-06-05 from the architecture review report at
`docs/research/kg-automation-architecture-review/`. Constitution Directive 6
will reference this document; CLAUDE.md gains an "Engineering Principles"
section pointing here in a follow-on commit.

Principles 11–13 added 2026-06-19 (kentonium3/kg-automation#624), adapted from
the [system-design-primer](https://github.com/donnemartin/system-design-primer)
and selected for a single-server, solo-operator system. The charter's
`## Design Principles` section is the spec-kitty-active subset that cross-references
these entries.

## 1. Runtime Truth Must Have a Machine-Readable State

Every deployed or scheduled component needs one authoritative state signal that
can represent at least:

- `healthy`
- `degraded`
- `failed`
- `stale`
- `disabled`
- `suspended`

A stale `success` file is not a valid representation of suspension.

## 2. Deterministic Work Belongs Behind a Contract

If correctness can be verified mechanically, put it behind a helper, library, or
schema rather than in an agent prompt. Use the helper/library/skill distinction
from `docs/design/helper-script-conventions.md` once approved.

## 3. Integration Clients Are Shared Boundaries

External systems such as Vikunja, GitHub, Anthropic, OpenClaw, Tailscale, and
the vault should have shared client/config boundaries once two domains need the
same behavior. Repeated URL, token, timeout, retry, and error-message logic is a
design smell.

## 4. Authoritative JSON Must Be Semantically Validated

If a JSON file is policy-authoritative, CI should validate more than parseability.
Dates, enum values, required fields, lifecycle states, health-check requirements,
and schema-version rules should be checked automatically.

## 5. Tests Are Part of the Architecture

A test suite that is not run in CI is documentation, not enforcement. All
non-live tests should run on push to `main`; live smoke tests stay opt-in.

## 6. Privacy Boundaries Need Both Policy and Enforcement

The constitution names the boundary; code, prompts, templates, registries, and
CI linting must enforce the same current boundary. Historical boundary names
belong only in migration history with explicit context.

## 7. Active Script Surfaces Must Not Preserve Deprecated Patterns

Scripts in active paths are copyable examples. If a script is no longer a valid
pattern, archive it or mark it loudly as historical. Migration completeness
includes removing obsolete operational examples.

## 8. Suspension Is an Operational State, Not an Absence of Scheduling

Cost-control or operator-paused components should be represented as suspended in
service inventory, runbooks, health checks, and status signals. Disabled timers
alone are not enough.

## 9. Feature Specs Must Ask "How Will We Know This Broke?"

Architecture impact should include observability impact. Every new deployed
component, scheduled job, or automation path should define its health signal,
failure observer, and response route before implementation.

## 10. Prefer Small Guardrails Over Large Retrofits

When a pattern recurs, add a small validator, template checkbox, shared helper,
or issue-template prompt while the pattern is still small. Avoid waiting until a
Felix-wide retrofit is necessary.

## 11. Retryable Operations Must Be Idempotent

Any operation that can fire more than once — cron-triggered runs, agent actions
that may be retried, deploy applies, task/inbox creation — must be safe to replay
without duplicating or corrupting state. Creation paths check for an existing
record before inserting; partial-update APIs are treated as read-modify-write
(e.g. Vikunja POST zeroes unstated fields); deploy applies are gated and
re-runnable. A second identical run that yields different state is a defect, not
an edge case.

## 12. Decouple Producers and Consumers

Components that hand work to each other should communicate through a durable queue
or a polled store, not a tight synchronous call, so that a slow or failed
component degrades locally instead of blocking the rest. The inbox is a file queue
drained by cron; Felix↔Vikunja sync is ~5-minute polling rather than webhooks. New
agent-to-agent paths default to a queue/poll boundary. This principle grows in
weight as more agents are added.

## 13. No Single Point of Failure Without a Recovery Path

For each new stateful component, identify what its loss would stop and ensure a
recovery path exists. On a deliberately single-host system (office2) the
mitigation is backup + degraded-mode operation, not redundancy: Tier 2 changes
require a Restic snapshot ≤24h, the daily security audit and felix-deployer are
the drift safety nets, and any new stateful dependency documents how it is
restored. A component whose loss is unrecoverable and undocumented is a latent
outage.
