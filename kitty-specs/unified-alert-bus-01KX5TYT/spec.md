# Feature Specification: Unified Alert Bus

**Mission**: unified-alert-bus-01KX5TYT
**Source issue**: kentonium3/kg-automation#701 (child of #516; advances RFC #327; grandparent #673 Bedrock F1)
**Mission type**: software-dev

## Overview

Felix's operator alerts are fragmented across several notification threads and emitted by
independent, ad-hoc code paths. Many alerts are cryptic — a phase name plus a truncated error
summary with no context — so a failing component gives the operator little to act on, and every
alert costs a manual investigation to decode. This feature consolidates alerting into a single
canonical thread carrying a uniform, self-explanatory message schema, delivered through one shared
"alert bus" that every component calls. A failing Felix component should clearly say *what* failed,
*when*, *how bad*, and *what to do*.

This mission builds the substrate and migrates the worst-offending emitters onto it. It is the
observability foundation the rest of the Bedrock stabilization work depends on.

## User Scenarios & Testing

**Primary actor**: Kent, acting as the Felix operator, reading alerts on his phone.

**Primary scenario (happy path)**: A Felix component (e.g. the deployer) fails during a routine
operation. The operator receives a single alert on one thread. Reading only that alert, he knows
which component failed, at what time, how severe it is, a plain-language description of what went
wrong including the actual error text, and — when known — the recovery step. He resolves it without
first logging into office2 to decode a phase code.

**Main exception path**: The notification endpoint is temporarily unreachable when a component tries
to alert. The emitting component must not crash, hang, or block on the failed delivery — it degrades
gracefully and continues its own work; the alert delivery fails safe.

**Secondary scenario (verification)**: The operator (or a deploy step) triggers an on-demand
self-test alert and confirms end-to-end delivery and correct formatting on the canonical thread.

**Rule that must always hold**: Every operator-facing alert is constructed and delivered through the
single shared alert bus — no component retains its own ad-hoc delivery path after migration.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | All operator-facing Felix alerts are delivered to a single canonical notification thread (one new dedicated thread; the prior per-component threads are retired for these emitters). | Planned |
| FR-002 | Each alert is constructed from a uniform structured schema: timestamp (UTC + local), issuing source/function (component + specific phase), severity, short human-readable title, plain-language description, action-required (when known), and structured details (ids, paths, exit codes). | Planned |
| FR-003 | For failure alerts, the details include the actual underlying error output (captured stderr / exception text), not merely a phase code or truncated summary. | Planned |
| FR-004 | Severity is expressed on a defined vocabulary — `info` / `warn` / `error` / `critical` — and each level maps deterministically to a notification priority and a visual tag, so the single thread still visually distinguishes critical from informational alerts. | Planned |
| FR-005 | A single shared alert bus is the only path that constructs and delivers alerts; it is callable from both Python and shell contexts (some emitters are shell scripts). | Planned |
| FR-006 | The five named emitters — felix-deployer, security-monitor, felix-health-check, doc-auditor, and the openclaw enforcement notifier — emit exclusively via the shared alert bus, and their previous ad-hoc per-script delivery code is removed. | Planned |
| FR-007 | The canonical thread identity is stored in the project's topic/credential registry (configuration), not hard-coded in individual emitters. | Planned |
| FR-008 | An operator can trigger an on-demand self-test alert to verify end-to-end delivery and formatting. | Planned |

### Non-Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | An emit call completes within 5 seconds and never blocks the host component beyond that even when the notification endpoint is unreachable; a delivery failure never crashes or hangs the emitting component (fail-safe delivery). | Planned |
| NFR-002 | The shared alert-bus module has direct unit tests for schema construction, severity→priority/tag mapping, topic resolution, and delivery-failure handling, with line+branch coverage ≥ 90% for the module and no reduction to the repository's enforced coverage gate. | Planned |
| NFR-003 | An alert missing one or more optional fields (e.g. no known action) still produces a deliverable, human-readable message; no alert is dropped because an optional field is absent. | Planned |
| NFR-004 | Migrating an emitter changes only its alert delivery/formatting path; the component's core behavior and existing health signals (tick logs, `last-tick.json`) remain unchanged and continue to pass. | Planned |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Delivery transport remains ntfy (the existing operator channel); no new notification vendor is introduced. | Active |
| C-002 | The change deploys to office2 exclusively through the manifest pipeline (`deploys/queued/<name>.yaml`); no out-of-band edits on office2. | Active |
| C-003 | No new external package source is introduced (no new brew tap / pip index / npm registry / MCP plugin); delivery uses HTTP patterns already present in the repo. | Active |
| C-004 | Risk tier is Tier 3 (Standard). The change touches audited surfaces (`scripts/deploy/**`, security-monitor scripts); rebaseline per #557 applies and the manifest pipeline auto-rebaselines on deploy, recorded on the merge/applied record. | Active |
| C-005 | The alert bus must be invocable from shell (bash-callable shim) as well as Python, because emitters like `audit.sh` are shell. | Active |
| C-006 | Out of scope for this mission: routing LLM-agent-detected failures through the bus, the #327 canary registry, and new emitters not yet alerting (#637). | Active |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | After deploy, 100% of alerts from the five migrated components arrive on the single canonical thread; zero arrive on the retired per-component threads. |
| SC-002 | For a forced felix-deployer failure, the resulting alert contains the underlying error text sufficient to diagnose the cause without logging into office2 — verified against the #699 missing-executable-bit class (the alert names the failing cause, not just "dry-run failed"). |
| SC-003 | Every migrated alert displays all applicable schema fields; reading any single alert tells the operator what failed, when, how bad, and the next step. |
| SC-004 | Critical and informational alerts are visually distinguishable on the single thread (priority/tag). |
| SC-005 | A delivery outage (notification endpoint unreachable) does not crash, hang, or block any emitting component. |
| SC-006 | No migrated emitter retains ad-hoc alert-delivery code — a repository search finds alert delivery only in the shared alert bus. |

## Key Entities

- **Alert** — a single operator notification carrying the structured schema fields.
- **Severity level** — one of `info` / `warn` / `error` / `critical`, each mapped to a notification priority and a visual tag.
- **Alert source** — the component plus the specific function/phase that issued the alert.
- **Canonical topic** — the single notification thread identity, stored in the topic/credential registry.

## Domain Language

- **Alert bus** — the shared mechanism that constructs and delivers alerts (library + CLI + shell shim). Canonical term for the substrate.
- **Emitter** — a Felix component that raises alerts.
- **Alert** — canonical term for an operator notification; avoid "notification", "ping", or "message" as drifting synonyms in code and docs.

## Assumptions

- Kent is the sole consumer of these alerts, via ntfy on his phone; a new dedicated topic will be minted and subscribed.
- Existing ntfy infrastructure and credentials remain available.
- Emitters can be migrated one at a time; a transient mixed state (some emitters on the bus, some not yet) is tolerable during rollout, provided the mission ends with all five migrated.

## Dependencies

- ntfy (existing operator notification channel).
- office2 manifest deploy pipeline (felix-deployer) for delivery to the host.
- Topic/credential registry under `docs/design/architecture/data/` for the canonical topic id.
