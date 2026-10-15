# Mission Specification: Off-host dead-man pings for the on-host watchers

**Mission Branch**: `feat/offhost-deadman-pings`
**Created**: 2026-10-15
**Status**: Draft
**Input**: kentonium3/kg-automation#1077, which implements the decision recorded on RFC #1069. The intent summary was confirmed by Kent on 2026-10-15 (decision `01M5099EQ6CDPRYPRNHK4HZSWE`).

## Context

felix-canary watches every component. felix-health-check watches the canary through a dead-man's switch (#1063). Both run on office2, under the same `claude` user manager, from the same checkout, and they alert through the same `felix-alert` ntfy topic. Any of these can fail and silence both watchers together: the host goes down or wedges, the user manager doesn't start, the checkout breaks, the topic env file goes missing, or ntfy itself is down. Nothing would tell Kent.

RFC #1069 decided on a hosted dead-man service, healthchecks.io. Each watcher pings its own check after it runs. When pings stop, the service **emails** Kent, deliberately never through ntfy.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Silence becomes an email (Priority: P1)

office2 goes dark at night. Everything on it stops, including both watchers. About an hour later (the canary check's 15-minute period plus 45-minute grace), healthchecks.io emails Kent that `felix-canary` missed its pings. He learns about the outage without having to notice that Felix went quiet.

**Why this priority**: this is the whole purpose. It is the failure no on-host watcher can report.

**Independent Test**: run a watcher's entry point with a recording fake ping transport and assert exactly one success ping per completed run. Live: once the URLs are provisioned, the check shows a received ping.

**Acceptance Scenarios**:

1. **Given** a configured ping URL, **When** a canary tick completes, **Then** one success ping is sent to the canary's check.
2. **Given** a configured ping URL, **When** a felix-health-check run completes, **Then** one success ping is sent to the health-check's check.
3. **Given** a tick or run that finds unhealthy components, **When** it completes, **Then** it still sends a success ping. The ping means the watcher ran, not that everything it watches is healthy.

---

### User Story 2 - A dead alert channel still reaches Kent (Priority: P1)

The ntfy topic env file is missing, or ntfy is down. A watcher detects that its alert channel is broken: the topic is not configured, or the most recent felix-alert delivery from any emitter failed. It sends a *fail* ping instead of a success ping, and healthchecks.io emails Kent at once. It keeps sending fail pings until a felix-alert is delivered again.

**Why this priority**: today an undelivered alert is only written to local files nobody reads.

**Independent Test**: inject an alert transport that reports a failed delivery, and assert a fail ping and no success ping for that run.

**Acceptance Scenarios**:

1. **Given** a run in which at least one alert delivery failed, **When** it completes, **Then** it sends a fail ping, not a success ping.
2. **Given** a run in which every attempted alert was delivered, or none was needed, **Then** it sends a success ping.

---

### User Story 3 - The watchers are never harmed (Priority: P1)

The ping can be unconfigured, unreachable, slow or misconfigured. In every case the watchers behave exactly as they do today.

**Why this priority**: these are the monitoring watchers themselves, so a regression here could silence everything.

**Independent Test**: run each failure mode (unset, unreadable, malformed, connection refused, timeout, HTTP error) and compare exit code, verdicts, emitted alerts and written records with a run that has no ping at all.

**Acceptance Scenarios**:

1. **Given** no ping URL is configured, **Then** nothing is sent and nothing else changes.
2. **Given** an unreachable or slow endpoint, **Then** the run finishes within the ping's bound and its exit code, records and alerts are unchanged.
3. **Given** a malformed or non-HTTPS URL in the env file, **Then** nothing is sent, the run is unchanged, and a local log line names the problem without printing the URL.

### Edge Cases

- **Dry-run and self-check** send nothing.
- **Runner-level failures send a fail ping.** These are a canary pass that raises, a pass whose status is `error`, or a health-check run that could not do its own work: script missing or timed out, coverage could not start, or the record write failed. The watcher's exit code and the canary's `OnFailure` handler are unchanged.
- **Channel debt.** A failed delivery is not forgotten when dedup suppresses the next page. The channel counts as healthy again only after a later felix-alert is delivered, from any emitter, including `alert_bus.sh self-test`.
- **Secrecy.** The ping URL never appears in logs, records, exceptions or test output. Only a fixed, redacted label does.
- **Wrong check.** Each watcher uses its own variable, so a canary ping can never feed the health-check's check.
- **Unknown failure.** An alert transport that raises counts as a failed delivery: a fail ping, never a success ping.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Canary pings on completion | As Kent, I want each completed (non-dry-run) canary tick to send one ping to its own check, so that silence from the host becomes an email. | High | Open | [build] | no — no ping exists today; a recording transport sees zero calls |
| FR-002 | Health-check pings on completion | As Kent, I want each completed felix-health-check run to send one ping to its own check, so that the second watcher is covered too. | High | Open | [build] | no — same as FR-001 |
| FR-003 | Fail ping while the alert channel is broken | As Kent, I want each watcher to send a fail ping instead of a success ping while its alert channel is broken, so that a dead ntfy channel still reaches me. Broken means the topic is not configured in the watcher's environment, or the most recent felix-alert delivery recorded by the alert bus ledger failed. | High | Open | [build] | no — today nothing reads the channel state |
| FR-010 | Fail ping on watcher execution fault | As Kent, I want a watcher that could not do its own work to send a fail ping, so that a broken watcher is never reported up. That covers a canary pass status of `error` or a raised pass, and a health-check script that is missing, timed out or failed to launch, coverage that could not start, or a failed record write. | High | Open | [build] | no — today nothing pings |
| FR-004 | Liveness, not health | As Kent, I want the success ping sent even when the watcher found unhealthy components, so that a component failure is not mistaken for a dead watcher. | High | Open | [build] | no — paired with FR-001 on an unhealthy fixture |
| FR-005 | Unconfigured is a no-op | As an operator, I want no ping, no error and no behaviour change when the ping URL is not configured, so that the code can ship before the account exists. | High | Open | [ratchet] | yes — paired with FR-001's positive control on the same fixture |
| FR-006 | Never harms the watcher | As Kent, I want any ping failure (unreachable, timeout, HTTP error, malformed URL) to leave the watcher's exit code, verdicts, alerts and records unchanged, so that the dead-man cannot become the outage. | High | Open | [build] | no — fault-injection fixtures compared against a no-ping baseline |
| FR-007 | URLs stay secret | As Kent, I want the ping URLs read only from an env file on office2 and never written to logs, records, exceptions or the repo, so that nobody can spoof or silence my checks. | High | Open | [build] | no — a test with a sentinel URL scans all outputs |
| FR-008 | Architecture records the flow | As a maintainer, I want the new external data flow and credential recorded in the architecture data and docs, so that the system map stays true. | Medium | Open | [build] | no — the validator and a docs check assert the entries exist |
| FR-009 | Operator runbook | As an operator, I want a runbook section for provisioning, rotating, pausing and verifying the pings, including how to test a fail email, so that the setup is repeatable. | Medium | Open | [build] | no — a docs check asserts the section exists and names both variables |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Bounded cost | A ping adds at most 20 s wall time to a run in the worst case (unreachable endpoint, 2 attempts), and about 0 s when unconfigured. | Performance | High | Open |
| NFR-002 | Zero regression | The full test suite passes, with 0 new failures. The existing canary and health-check test suites pass unchanged. | Quality | High | Open |
| NFR-003 | No payload | A ping carries no request body and no data beyond the URL path (success or `/fail`). | Privacy | High | Open |
| NFR-004 | HTTPS only, canonical endpoint | A URL that is not `https://`, carries a query or fragment, or already ends in a ping action (`/fail`, `/start`, `/log`, or an exit-code segment) is rejected and never contacted. The fail endpoint is built structurally from the parsed path. | Security | High | Open |
| NFR-005 | Secret containment | Ping URLs are read only from the env file into a private mapping. They are never placed in `os.environ`, never passed to a child process environment or argv, and never logged. | Security | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Email, never ntfy | The dead-man's own alerting is configured on healthchecks.io (email only). No code path routes it through the felix-alert bus. | Technical | High | Open |
| C-002 | No secret in the repo | Ping URLs exist only in an office2 env file under `~/.config/felix/` (mode 0600). They are provisioned by Kent without echoing them. | Security | High | Open |
| C-003 | Scope | Host- and channel-level only. Felix/OpenClaw outage detection (#269/#707) is out of scope. | Business | Medium | Open |
| C-004 | Watcher semantics unchanged | Canary and health-check verdicts, dedup, exit codes and alert content are unchanged. The ping is additive. | Technical | High | Open |

### Key Entities

- **Ping URL**: a capability URL for one healthchecks.io check. One exists per watcher.
- **Ping outcome**: `success` (the run completed and all alerts delivered) or `fail` (the run completed but an alert delivery failed).
- **Dead-man check**: the remote check. It emails Kent when no ping arrives within period plus grace, or when a fail ping arrives.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the URLs provisioned, a healthchecks.io check receives a ping within one period of deploy, for both watchers. — [build] · no-op passable: no
- **SC-002**: A deliberate fail-ping test produces an email to Kent. — [build] · no-op passable: no
- **SC-003**: 0 changes to watcher exit codes, verdicts or alerts across the existing test suites and the first live ticks after deploy. — [ratchet] · no-op passable: yes — paired with SC-001

## Assumptions

- office2 has unrestricted outbound HTTPS. `ollama-ops.md` notes UFW egress is permissive.
- Kent has created the healthchecks.io account and two checks, with email as the only integration (2026-10-15).
  - The canary check uses a simple 15-minute period with 45-minute grace.
  - The health-check check should use a **Cron** schedule, `0 11,23 * * *` in UTC (office2 is `Etc/UTC`), with 1-hour grace, matching its `OnCalendar` timer. A simple 12-hour period drifts against a calendar timer.
- Accepted: if both of a run's ping attempts are lost, the check emails Kent once even though nothing is wrong. The next successful run clears it.
