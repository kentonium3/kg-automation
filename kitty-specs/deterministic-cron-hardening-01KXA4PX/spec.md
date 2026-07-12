# Feature Specification: Deterministic escalation + weekly-report crons

**Mission**: deterministic-cron-hardening-01KXA4PX
**Source**: GitHub issue #723 (surfaced by the #722 canary observability work)
**Status**: Draft

## Overview

Two of Felix's scheduled jobs fail silently because a large-language-model (LLM)
agent improvises fragile operations at run time instead of invoking deterministic,
tested code:

- **Daily escalation** hand-builds a task query and filters it with a freshly
  written inline script every run — a dice-roll that recently errored and did not
  deliver.
- **Weekly habit report** is a fully deterministic "run the report, post it"
  task, yet it is routed through an LLM agent that went off-script and errored;
  it has not delivered for over five days.

This mission removes the fragile improvisation from both paths: escalation gains a
deterministic candidate-enumeration helper (the agent keeps only genuine judgment),
and the weekly report moves entirely off the LLM into a scheduled deterministic
process. The Vikunja selection criteria both paths depend on are externalized into
shared configuration so the upcoming Vikunja reorganization (#714) is a
configuration change rather than code.

## User Scenarios & Testing

### Scenario 1 — Daily escalation runs deterministically (primary)
- **Actor**: the escalation agent (on its daily schedule); Kent receives the result.
- **Trigger**: the daily escalation schedule fires.
- **Happy path**: the agent obtains the qualifying task set from a single
  deterministic enumeration call, decides per-task escalation levels, and either
  sends a level-appropriate alert to Kent or emits the no-op marker. The run
  completes without a tool error.
- **Exception**: the enumeration call fails (task store unreachable) → the agent
  surfaces a truthful failure and the run does not fabricate a result.

### Scenario 2 — Weekly report delivered without an LLM (primary)
- **Actor**: a scheduled deterministic process; Kent receives the report.
- **Trigger**: the weekly-report schedule fires.
- **Happy path**: the process runs the report helper and delivers the rendered
  report to Kent, prefixed only by an attribution line. No LLM turn occurs.
- **Exception**: report generation or delivery fails → the failure is surfaced to
  the monitoring system; nothing false is reported as delivered.

### Scenario 3 — Vikunja reorganization is absorbed by configuration (#714)
- **Trigger**: the Vikunja taxonomy changes (habit identity moves from
  project-membership to a label; project IDs change).
- **Outcome**: only the shared scope configuration is edited; the escalation and
  habit selection logic continues to return correct results with no code change.

### Scenario 4 — Both jobs are observable
- **Trigger**: either job succeeds or fails on a scheduled run.
- **Outcome**: the health-monitoring system reports the job healthy when it runs
  correctly and raises an alert when it fails.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Escalation candidate enumeration MUST be performed by a single invocation of deterministic, tested code — not by agent-improvised query construction or inline scripting. | Draft |
| FR-002 | The enumeration MUST apply the established escalation qualification criteria (overdue or due-today-with-high-priority, minimum priority, excluded task groups) and return the qualifying candidate set for the agent to act on. | Draft |
| FR-003 | The escalation agent's standing orders MUST call the enumeration code; the agent's remaining responsibilities are limited to judgment (escalation-level determination, alert composition) and state recording. | Draft |
| FR-004 | The weekly habit report MUST be generated and delivered by a scheduled deterministic process with no LLM agent turn. | Draft |
| FR-005 | The delivered weekly-report body MUST be byte-identical to the report helper's output, prefixed only by a fixed attribution line. | Draft |
| FR-006 | The weekly-report process MUST report delivery truthfully: success is recorded only when delivery is confirmed, and any failure is surfaced rather than silently dropped. | Draft |
| FR-007 | The prior LLM-driven weekly-report schedule MUST be retired so the report is produced by exactly one path. | Draft |
| FR-008 | The Vikunja scope selectors used by escalation enumeration and habit selection (excluded task groups, habit identity) MUST be read from shared configuration, so a taxonomy change is a configuration edit rather than a code change. | Draft |
| FR-009 | Both the daily escalation job and the new weekly-report process MUST be observable by the health-monitoring system: healthy when running correctly, alerting on failure. | Draft |
| FR-010 | Retiring the weekly-report schedule MUST update the monitored-service definition so the health system no longer expects the retired schedule and instead monitors the new weekly-report process. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The escalation enumeration completes quickly enough not to affect the run. | ≤ 30 seconds per run under normal task-store latency | Draft |
| NFR-002 | The weekly-report process completes generation and delivery within one run window. | ≤ 60 seconds end-to-end | Draft |
| NFR-003 | The deterministic enumeration code and the weekly-report driver are covered by automated tests including failure modes (store unreachable, empty result, delivery failure). | Each unit independently tested; failure modes asserted | Draft |
| NFR-004 | A change of Vikunja scope selectors (e.g. habit identity from group-membership to a label) requires configuration-only changes. | 0 code changes to enumeration/selection logic for a taxonomy swap | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Escalation remains an LLM agent for judgment (level determination, alert composition); only candidate enumeration is mechanized. The morning habit check-in is unchanged. | Draft |
| C-002 | The escalation qualification criteria themselves are unchanged — only mechanized into deterministic code. | Draft |
| C-003 | Editing agent standing orders is an audited surface; the deploy MUST trigger a security-baseline rebaseline. | Draft |
| C-004 | Retiring the weekly-report schedule drifts a monitored baseline with no repository-file signal; the deploy MUST declare the expected baseline drift so the auto-rebaseline covers it. | Draft |
| C-005 | The privacy boundary is unchanged: `_private` content is never read, referenced, or logged. | Draft |
| C-006 | Deterministic work belongs in tested helpers/drivers (Directive 6); the shared scope configuration decouples this mission from the #714 Vikunja reorganization. | Draft |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | The daily escalation run completes with no tool error on consecutive scheduled runs, and the health monitor reports the escalation job healthy. |
| SC-002 | The weekly report is delivered to Kent on its schedule with no LLM agent involvement, and the health monitor reports the weekly-report service healthy. |
| SC-003 | A simulated Vikunja taxonomy change (habit identity group→label) is absorbed by a configuration edit alone, with selection still returning correct results. |
| SC-004 | Both previously-failing jobs report healthy in the health-monitoring system after deploy, replacing the pre-mission failing state. |

## Key Entities

- **Escalation candidate** — a task meeting the escalation qualification criteria on a given day.
- **Vikunja scope configuration** — the externalized selectors (excluded task groups, habit identity) shared by escalation enumeration and habit selection.
- **Weekly report artifact** — the rendered weekly habit-report text produced by the report helper.
- **Monitored-service definition** — the health-monitoring system's record of what to expect for each job.

## Assumptions

- The weekly-report helper is correct and remains the sole source of report content and rendering (verified producing a full report on demand).
- A deterministic message-delivery channel to Kent exists and supports the weekly report's delivery (exact interface to be confirmed during planning).
- The escalation agent retains its existing deterministic state helpers (state derivation and completion recording) unchanged.

## Domain Language

- **Escalation candidate**: a task qualifying for escalation per the established criteria.
- **Scope config**: the externalized Vikunja selectors that decouple selection logic from the concrete project/label taxonomy.
- **Deterministic driver**: a scheduled non-LLM process that runs a helper and delivers its output.

## Out of Scope

- Changing the escalation qualification criteria themselves (only mechanized).
- The morning habit check-in (already helper-backed; not failing).
- Performing the #714 Vikunja reorganization (this mission only makes the selectors config-driven and hands the taxonomy update to #714).
