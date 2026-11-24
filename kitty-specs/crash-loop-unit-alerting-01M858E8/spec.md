# Mission Specification: Crash-loop unit alerting

> **Ruling, Kent, 2026-11-24 (in-mission, after the post-merge Codex review round 4): count ticks, not time.** This supersedes every wall-clock interval rule in this file: the proven-crossing (pigeonhole) rule, the observation-time bracket, clock-regression handling, and history compaction. Earlier text is kept as history.
> - **Page rule.** For each watched unit or container, page when its persistent restart counter has **risen by ≥3 since the previous canary tick** (ticks are 15 min apart), **or has risen (by ≥1) on 2 consecutive ticks**.
> - **What stays.** A counter decrease, or a boot-ID or container-ID change, sets a new baseline with no alert. First sight sets a baseline. "Could not check" never reads as healthy. One alert per episode. A re-remind on the canary's 6-hour cadence, driven by fresh evidence (WP02 ruling). Cleared after K=2 quiet ticks. The ignore list. A cap of 3 alerts per tick, plus one aggregate.
> - **Timestamps** may appear in alert text and the ledger as information only. They are never an input to the decision.
> - **Expected outcomes.** The 2026-11-23 loop pages on the next tick. A steady loop of 2 restarts per tick pages on its 2nd tick. A single restart never pages.


**Mission Branch**: `kitty/mission-crash-loop-unit-alerting-01M858E8` (merge target `fix/crash-loop-unit-alerting`, PR-bound to `main`)
**Created**: 2026-11-23
**Status**: Draft
**Input**: kentonium3/kg-automation#1133. Crash-looping systemd units raise no alert (obsidian-sync restarted 39 times in about 7 minutes on 2026-11-23 and nothing alerted).

## Context

On 2026-11-23, during the Node 22 to 24 switch in kentonium3/kg-automation#1122, `obsidian-sync` restarted 39 times between 12:31Z and 12:38Z. The alert-bus ledger recorded nothing, and Kent found the loop by hand.

Today's checks on office2 look at unit state only at the moment they run:

- felix-canary checks "is it active" every 15 minutes.
- felix-health-check checks "is it active" twice a day.
- The security monitor baselines unit configuration, not runtime behaviour.

A unit with `Restart=always` is "active" most of the time while it loops, and it never reaches the `failed` state. The canary ticks just before and just after the loop (12:28:46Z and 12:44:46Z) both reported healthy. The unit's restart counter, though, still showed 39 about nine hours later (21:30Z). That persistent counter is the signal this mission uses.

## Intent Summary (confirmed by Kent, 2026-11-23)

- **What:** felix-canary raises one alert to Kent when any watched unit or container on office2 restarts too often within a short window, and logs a "cleared" entry once it has been quiet again.
- **Actor:** felix-canary, on its existing 15-minute timer.
- **Recipient:** Kent, through the alert bus (ntfy notification plus alert-bus ledger entry).
- **Trigger:** a watched unit's restart count has risen by at least the global threshold within the window.
- **Outcome:** a loop like the 2026-11-23 one produces one alert within one canary tick.
- **Invariant:** detection reads the persistent restart counter, not a one-off state check. A loop that starts and ends between two ticks is therefore still caught.

Discovery decisions (Decision Moments, all resolved 2026-11-23):

| Decision | Answer |
|---|---|
| `watched_units` (01M858F6J5R952H2XV7BD5Q8VR) | Every system unit and `claude` user unit with a restart policy, plus docker containers, minus an ignore list |
| `loop_threshold` (01M858M4XMRTEBMHGBVVY10QCW) | N restarts within a window, one global default (e.g. at least 3 in 15 minutes); a single restart does not alert |
| `owning_monitor` (01M858M7GTC56YQZ1Y6XZPJQXX) | felix-canary, as a new probe method |
| `detection_latency` (01M858MA4V9RNQFF2PAN0XY563) | Within one canary tick (15 minutes or less), using the persistent restart counter |
| `alert_lifecycle` (01M858MCPTFXEKHDDM7ZCSP4N0) | Once per loop episode, with a cleared entry after K quiet ticks, matching the canary's dedup |

Kent also decided at Intent Summary confirmation: a loop episode that lasts longer than 6 hours re-reminds on the canary's existing 6-hour re-remind cadence, rather than staying silent after the first alert.

## Domain Language

| Term | Meaning | Avoid |
|---|---|---|
| **Crash loop** | A watched unit or container whose restart count rises by at least the threshold within the window | "failed unit" (a looping unit is usually not `failed`) |
| **Restart count** | The persistent per-unit counter of automatic restarts the service manager (or the container runtime) keeps until the unit is explicitly restarted or the host reboots | "restarts in the journal" (not readable by the checking account) |
| **Watched unit** | A system unit, a `claude` user unit, or a docker container that has a restart policy other than "never" and is not on the ignore list | "monitored service" (that means an inventory component) |
| **Loop episode** | From the first tick at which a watched unit is over the threshold until the tick on which it has been quiet for K consecutive ticks | |
| **Quiet tick** | A canary tick at which the unit's restart count did not rise | |
| **Ignore list** | A version-controlled list of units or containers that never raise a crash-loop alert | |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A looping service reaches Kent (Priority: P1)

A service on office2 starts crash-looping, for example after a runtime upgrade. Within one canary tick Kent gets an alert naming the service and saying how many restarts happened over what period. He can act on it before the outage matters.

**Why this priority**: This is the failure that happened on 2026-11-23 and went unseen. Without it the mission delivers nothing.

**Independent Test**: Simulate a watched unit whose restart count rises by 39 between two ticks while its state reads "active" at both ticks. Exactly one crash-loop alert must be emitted, naming that unit.

**Acceptance Scenarios**:

1. **Given** obsidian-sync's restart count was 0 at the previous tick, **When** the next tick reads 39 and the unit is "active", **Then** one crash-loop alert is emitted naming obsidian-sync, with a restart delta of 39 and the period between the two ticks.
2. **Given** a `claude` user unit with a restart policy, **When** its restart count rises by at least the threshold between ticks, **Then** one crash-loop alert is emitted naming that user unit.
3. **Given** a docker container behind a compose wrapper unit (the wrapper shows "active (exited)"), **When** the container's restart count rises by at least the threshold between ticks, **Then** one crash-loop alert is emitted naming the container.
4. **Given** a loop that started and stopped entirely between two ticks, **When** the second tick runs, **Then** the loop is still detected from the counter delta and alerted.

---

### User Story 2 - One alert per episode, then a clear (Priority: P2)

Kent gets one alert per loop, not one every 15 minutes. He is reminded at the canary's usual 6-hour cadence if the loop persists, and a "cleared" entry marks its end.

**Why this priority**: Without episode handling the feature pages every tick and gets muted, which recreates the blind spot.

**Independent Test**: Drive a unit through loop, loop, loop, then K quiet ticks. Assert one alert, no repeats before 6 hours, then exactly one cleared entry.

**Acceptance Scenarios**:

1. **Given** an alert was emitted for a unit at tick T, **When** the unit is still looping at T+1 and T+2 (under 6 hours), **Then** no further crash-loop alert is emitted for it.
2. **Given** a loop episode has lasted 6 hours since its last alert, **When** the next tick still sees the unit looping, **Then** one re-remind alert is emitted, on the canary's existing re-remind cadence.
3. **Given** a unit in a loop episode, **When** K consecutive quiet ticks pass, **Then** exactly one "cleared" entry is recorded for it and the episode ends.
4. **Given** an episode has cleared, **When** the unit starts looping again, **Then** a new alert is emitted (a new episode is never swallowed).

---

### User Story 3 - Normal restarts stay quiet (Priority: P2)

Single restarts, such as a package refresh or an intentional restart, do not page Kent. Units Kent has chosen to ignore never page.

**Why this priority**: False alerts erode trust in every alert on the bus.

**Independent Test**: On the same fixture, a delta of 1 raises no alert while a delta at the threshold does. An ignored unit with a delta of 39 raises no alert while the same unit, not ignored, does.

**Acceptance Scenarios**:

1. **Given** snapd's restart count rises by 1 between ticks, **When** the tick runs, **Then** no crash-loop alert is emitted.
2. **Given** a unit on the ignore list, **When** its restart count rises by 39 between ticks, **Then** no crash-loop alert is emitted for it.
3. **Given** a unit's restart count goes down between ticks (explicit restart, service-manager re-exec, or reboot), **When** the tick runs, **Then** the new value becomes the baseline and no alert is emitted.
4. **Given** a unit seen for the first time, **When** the tick runs, **Then** its restart count is recorded as the baseline and no alert is emitted.

---

### User Story 4 - The check fails safe (Priority: P3)

If the crash-loop check cannot read restart information, Kent sees "could not check", never a false "healthy". The rest of the canary pass still runs.

**Why this priority**: Engineering principle: checks must distinguish verified-false from could-not-check. A silent monitoring gap is the defect this mission exists to close.

**Independent Test**: Make the restart-count source fail for one scope (for example, the container runtime unavailable). That scope reports "could not check", the other scopes and all other canary components still evaluate, and the canary pass completes.

**Acceptance Scenarios**:

1. **Given** the container runtime cannot be queried, **When** the tick runs, **Then** container crash-loop detection reports "could not check" and system and user unit detection still runs.
2. **Given** the crash-loop check raises an unexpected error, **When** the tick runs, **Then** every other canary component is still evaluated and the pass completes.

### Edge Cases

- **Host reboot.** All restart counters reset to 0. This is treated as a counter reset (new baseline), not a loop.
- **Unit removed or renamed.** It drops out of the watched set without alerting. Its stored state is discarded or ignored.
- **New unit installed.** It is picked up at the next tick (first observation sets the baseline).
- **Unit loops so fast that systemd hits its start limit and enters `failed`.** The crash-loop alert still fires from the counter delta. Existing failed-state checks may also fire. Both are acceptable; neither may suppress the other.
- **Restart policy "never" (`Restart=no`).** Not watched, because such a unit cannot loop.
- **Window longer than one tick.** If the threshold window spans several ticks, restarts accumulated across those ticks count toward the threshold.
- **Persisted state missing or corrupt.** Loads as empty (all units first-seen, no alert), never a crash.
- **Two scopes with a same-named unit.** Units are identified by scope plus name, so a system unit and a user unit never collide.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Discover watched units | As Kent, I want every office2 system unit and `claude` user unit with a restart policy other than "never", and every docker container with a restart policy other than "no", watched at each tick, so that a loop in any of them is detectable without anyone listing it first. | High | Open | [build] | no |
| FR-002 | Ignore list | As Kent, I want a version-controlled ignore list of units and containers that never raise a crash-loop alert, so that known-noisy units cannot erode trust in the alert. | Medium | Open | [build] | no (same-fixture positive control: the same unit, not ignored, alerts) |
| FR-003 | Restart-count delta detection *(Ruling 2026-11-24: rise ≥3 since the previous tick, or any rise on 2 consecutive ticks; see the ruling above)* | As Kent, I want each tick to compare every watched unit's persistent restart count with its value at the previous tick, and to flag a crash loop when the increase within the threshold window reaches the threshold, so that loops are caught whatever the unit's state at the moment of the tick. | High | Open | [build] | no |
| FR-004 | Single global threshold *(Ruling 2026-11-24: the threshold is 3 per tick interval, plus the 2-consecutive-rising-ticks rule; no time window)* | As Kent, I want one global threshold and window (default: at least 3 restarts within 15 minutes), so that a single restart never alerts. | High | Open | [build] | yes (the delta-of-1 "no alert" case is paired with a delta-at-threshold "alert" case on the same fixture) |
| FR-005 | Between-tick loops are caught | As Kent, I want a loop that starts and ends entirely between two ticks to be alerted at the second tick, so that the 2026-11-23 blind spot is closed. | High | Open | [build] | no |
| FR-006 | Alert content and route | As Kent, I want each crash-loop alert sent through the alert bus (notification and ledger) naming the unit or container and its scope, the restart increase, the period it covers, and the unit's current state, so that I can act without logging in first. | High | Open | [build] | no |
| FR-007 | One alert per episode, 6-hour re-remind | As Kent, I want one alert when a loop episode starts, no further alert while it continues, and a re-remind only on the canary's existing 6-hour cadence, so that a long loop neither pages every tick nor goes silent. | High | Open | [build] | no |
| FR-008 | Cleared entry after K quiet ticks | As Kent, I want exactly one "cleared" entry when a unit in a loop episode has had K consecutive quiet ticks (K a named configuration value), and a fresh alert if it loops again afterwards, so that I know when a loop has ended and a recurrence is never swallowed. | Medium | Open | [build] | no |
| FR-009 | Counter reset is a new baseline | As Kent, I want a restart count that goes down (explicit restart, service-manager re-exec, host reboot) treated as a new baseline with no alert, so that maintenance and reboots do not page. | Medium | Open | [build] | yes (paired with a rising-count positive control on the same unit) |
| FR-010 | First sight is a baseline | As Kent, I want a unit or container seen for the first time (including after state loss) recorded as a baseline with no alert, so that deploying the check or adding a unit does not page. | Medium | Open | [build] | yes (paired with the second-tick rising-count positive control) |
| FR-011 | Could-not-check, never false healthy | As Kent, I want a scope (system, user, containers) whose restart information cannot be read reported as "could not check", while the other scopes still run, so that a broken probe is visible and not mistaken for health. | High | Open | [build] | no |
| FR-012 | Containers behind compose wrappers | As Kent, I want restarts of the vikunja and transcribe-api containers detected even though their systemd wrapper units show "active (exited)", so that container loops are not hidden by the wrapper. | Medium | Open | [folded] FR-001 + FR-003 (containers are in the watched set and use the same delta rule) | no |
| FR-013 | Existing canary behaviour unchanged | As Kent, I want every existing canary component's outcome, dedup and alert behaviour unchanged by the new check, and a fault in the crash-loop check never aborting the canary pass, so that adding coverage costs nothing in existing coverage. | High | Open | [ratchet] | yes (guarded by the existing canary test suite plus one fault-injection positive control showing the pass completes when the crash-loop check raises) |
| FR-014 | Living documentation | As Kent, I want the service inventory, the canary's documentation and the relevant monitoring runbook to describe crash-loop detection, the threshold, K and the ignore list, so that the next operator knows the check exists and how to tune it. | Medium | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Detection latency | A loop whose restart count crosses the threshold is alerted no later than the first canary tick after the crossing: at most 15 minutes plus one tick's run time (under 1 minute). | Performance | High | Open |
| NFR-002 | Tick cost | The crash-loop check adds no more than 10 seconds of wall time to a canary pass on office2 (today about 5 seconds for 33 components) for up to 50 watched units and containers. | Performance | Medium | Open |
| NFR-003 | No privilege | The check runs as the `claude` account with zero sudo invocations and zero reads of the system journal or of any credential file. | Security | High | Open |
| NFR-004 | False-alert rate | Over the first 7 days after deploy, zero crash-loop alerts for units whose restart count rose by fewer than the threshold within the window (verified from the alert-bus ledger against restart counts). | Reliability | High | Open |
| NFR-005 | Fail-open isolation | 0 canary passes aborted by a fault in the crash-loop check (verified by fault-injection test and by the canary's run records for 7 days after deploy). | Reliability | High | Open |
| NFR-006 | Deterministic | 100% of the detection decision is deterministic code with no model call, and the decision logic is testable offline with injected restart counts and clock. | Maintainability | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Owner is felix-canary | Crash-loop detection is a new probe method of felix-canary on its existing 15-minute timer, not a new timer and not part of felix-health-check or the security monitor (Decision `owning_monitor`). | Technical | High | Open |
| C-002 | Signal is the persistent restart counter | Detection uses the restart counters the service manager and container runtime already keep. It does not depend on the system journal, which the `claude` account cannot read. | Technical | High | Open |
| C-003 | Alert bus only | All alerts and cleared entries go through the existing felix-alert bus. Nothing talks to the notification service directly. | Technical | High | Open |
| C-004 | Deploy through the manifest pipeline | Changes reach office2 only through a `deploys/queued/` manifest applied by felix-deployer, including any audited-surface rebaseline the change triggers. | Business | High | Open |
| C-005 | Detection only, no remediation | The mission detects and alerts. It does not restart, stop or reconfigure any unit or container, and does not change any unit's restart policy. | Business | High | Open |
| C-006 | Unit-file drift is out of scope | The drift between the repo copy of `obsidian-sync.service` and the deployed unit (Restart, RestartSec, User, WantedBy) is tracked separately. Follow-up: kentonium3/kg-automation#1138. | Business | Medium | Open |
| C-007 | Architecture docs in the same change | Per the repo's standing requirement, the service inventory (JSON and narrative), the service-dependencies view and the capability roadmap are reviewed and updated in this mission's merge where they are affected (signal-to-doc-map class `service-added-or-modified`), and `docs/INDEX.md` for any runbook change (`runbook-modified`). | Business | Medium | Open |
| C-008 | Watched user scope is `claude` only | Only the `claude` account's user manager is watched. Other accounts' user units are not reachable without privilege and are out of scope. | Technical | Medium | Open |

### Key Entities

- **Watched unit**: identified by scope (system, `claude` user, container) plus name. Attributes: restart policy, current restart count, current state.
- **Restart observation**: per watched unit, the restart count and time recorded at the previous tick. It persists between ticks and is the baseline for the next delta.
- **Loop episode**: per watched unit. Records when it started, when it last alerted (for the 6-hour re-remind) and the consecutive-quiet-tick count toward K.
- **Crash-loop configuration**: the global threshold, the window, K, and the ignore list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A replay of the 2026-11-23 incident shape (39 restarts between two ticks, unit "active" at both) produces exactly 1 crash-loop alert naming obsidian-sync at the second tick. Before this mission it produced 0. — [build] · no-op passable: no
- **SC-002**: A loop episode that continues for 5 consecutive ticks produces exactly 1 alert, and K quiet ticks after it stops produce exactly 1 cleared entry. — [build] · no-op passable: no
- **SC-003**: During the first 7 days after deploy, the alert-bus ledger holds 0 crash-loop alerts for units that did not cross the threshold. — [build] · no-op passable: yes (paired with SC-001's positive case on the same detection rule)
- **SC-004**: A restart loop in a docker container behind a compose wrapper unit produces exactly 1 alert naming the container within one tick. — [build] · no-op passable: no
- **SC-005**: Every existing canary component reports the same outcomes before and after the change on the same inputs. — [ratchet] · no-op passable: yes (guarded by the existing canary suite plus the FR-013 fault-injection control)

## Assumptions

- The threshold window defaults to 15 minutes, which equals one canary tick. A different window or threshold is a configuration change, not a code change.
- K (quiet ticks before "cleared") is chosen in the plan. Its value is recorded in the crash-loop configuration and the runbook.
- The initial ignore list may be empty. Entries are added only with a stated reason.
- A unit that is currently in a loop when the check is first deployed is first-seen at that tick (baseline, no alert) and alerts from the second tick if it keeps looping.

## Out of Scope

- Repairing the drifted repo copy of `obsidian-sync.service` (kentonium3/kg-automation#1138).
- Any automatic remediation of looping units.
- Units of accounts other than `claude`, and hosts other than office2.
- Replacing the existing "is it active" and failed-unit checks. They stay as they are.
