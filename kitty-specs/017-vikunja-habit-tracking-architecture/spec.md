# R001: Vikunja Habit Tracking Architecture

**Feature**: 017-vikunja-habit-tracking-architecture
**Mission**: research
**Status**: draft
**Priority**: HIGH
**Informs**: F009 (Daily Habit Check-in) — revised implementation spec

---

## Research Purpose

F009 was implemented with a data model assumption — static habit tasks with
completion history stored as API comments — that has not been validated against
Vikunja's actual behavior. Daily habit tasks are not appearing in the Vikunja
Today filter, indicating the current approach is incorrect. Before F009 can be
fixed or reimplemented, the correct data model must be determined.

**Decision gate**: The F009 revised implementation spec cannot be written until
this research answers which Vikunja data model correctly satisfies all habit
tracking requirements. The current blocker is: we do not know whether Vikunja's
native recurring task feature, agent-managed daily task creation, or a hybrid
approach is the right fit for this system's needs.

---

## Research Questions

### RQ-1: What does Vikunja's native recurring task model actually do?

Vikunja supports repeating tasks with calendar-style recurrence rules. The
exact behavior when a recurring task is marked done — whether the task resets,
a new instance is created, and what happens to comments and history — must be
verified against actual system behavior, not just documentation.

**Acceptable answer form**: A precise behavioral description covering: what
happens to due_date, task status, and comments when a recurring task is marked
done; whether completion history is preserved anywhere in Vikunja; and whether
a "skipped" or "will not do" state is natively expressible.

---

### RQ-2: Does the current F009 implementation match the intended design?

The felix-admin-habits agent was deployed as part of F009. The current state
of habit tasks 14-20 in Vikunja, the agent's standing orders, and the cron
job configuration must be inspected to understand what was actually built vs.
what the spec intended.

**Acceptable answer form**: A factual description of the current state —
whether tasks have due_date set, whether cron jobs are running, whether the
agent creates new tasks daily or queries static ones, and whether any
completion state is being recorded.

**Depends on**: Can be answered independently of RQ-1.

---

### RQ-3: Do any of the candidate approaches satisfy all five evaluation criteria?

Three candidate approaches must be evaluated against the criteria defined in
this spec. At least one must satisfy all five criteria for the research to
produce a clear recommendation. If none do, the findings must document the
best available trade-off.

**Candidate approaches**:

- **Option A**: Native Vikunja recurring tasks — use Vikunja's built-in
  repeat_mode and repeat_after fields to make habits recur automatically
- **Option B**: Agent-managed daily task creation — the felix-admin-habits
  agent creates new dated child tasks each morning with today's due_date
- **Option C**: Hybrid approach — use Vikunja tasks for Today filter
  visibility combined with a lightweight external log (technology to be
  evaluated open-ended) for completion history and state tracking

**Acceptable answer form**: A comparison table mapping each candidate approach
against all five evaluation criteria, with a supported conclusion identifying
the recommended approach or the best available trade-off.

**Depends on**: RQ-1 (to evaluate Option A accurately).

---

### RQ-4: What specific Vikunja API capabilities support the recommended approach?

Once the recommended approach is identified, the specific API behavior needed
to implement it must be confirmed to exist — task creation, filtering by
due_date, querying history, and expressing completion states.

**Acceptable answer form**: A list of confirmed API capabilities (with endpoint
references) sufficient for the F009 implementation spec to be written without
further API discovery.

**Depends on**: RQ-3.

---

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Research must verify Vikunja recurring task behavior by inspecting the live system on office2, not solely from documentation | draft |
| FR-002 | Research must document the current F009 deployment state: task fields, cron configuration, agent standing orders, and any existing completion records | draft |
| FR-003 | Research must evaluate three candidate approaches (native recurring, agent-managed daily creation, hybrid) against all five evaluation criteria | draft |
| FR-004 | Research must confirm specific API endpoints and fields needed to implement the recommended approach | draft |
| FR-005 | Research must produce a single recommended approach with rationale mapped to evaluation criteria | draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | At least 3 independent sources must be consulted (API docs, live system, community/changelog) | >= 3 sources | draft |
| NFR-002 | Findings must reflect the Vikunja version running on office2, not a different version | Version-verified | draft |
| NFR-003 | Research must be read-only — no modifications to the live Vikunja instance or office2 agent files | Zero writes | draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Read-only access to the live Vikunja instance and office2 during all research — no task creation, modification, deletion, or agent file changes | active |
| C-002 | The recommended approach must be implementable within the existing Vikunja instance (no schema changes, no new services) | active |
| C-003 | Vikunja API access via token at `/data/services/openclaw/secrets/vikunja-api` on office2; base URL `https://office2.tail0f5f56.ts.net` | active |
| C-004 | office2 access via `ssh office2-claude` only | active |

---

## Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Today filter visibility | High | Habit tasks for today appear in the Vikunja Today saved filter without manual intervention |
| Skipped state expressible | High | A "will not do" or "skipped" outcome can be recorded distinctly from "complete" |
| Completion history survives 90 days | High | Individual completion records are queryable by date across at least 90 days |
| 48-hour catch-up window | Medium | A habit due yesterday that was not marked can still be marked today without losing the historical record |
| Agent implementation complexity | Medium | The approach can be implemented by the felix-admin-habits agent without requiring a separate external data store |

---

## Known Sources

### Internal sources (examine first)

- `docs/func-spec/F009_daily_habit_checkin.md` — full requirements including
  the deferred architecture decision and evaluation notes already in the spec
- `docs/runbooks/habits-ops.md` — current agent, cron, and task documentation;
  contains task IDs 14-20 and the current comment-based completion model
- Live Vikunja instance on office2 — inspect habit tasks 14-20 directly via
  API to determine current state (due_date, recurrence fields, comment history)
- `/data/services/openclaw/habits-agent/AGENTS.md` on office2 — the agent's
  standing orders; reveals whether the agent was designed to create tasks or
  query static ones
- `openclaw cron list` on office2 — confirms whether cron jobs exist and
  their current configuration

### External sources

- Vikunja API reference: task schema fields including repeat_mode, repeat_after
- Vikunja help docs (dates and reminders): documents recurrence behavior and
  the Today filter
- Vikunja community forum: prior discussions on recurring task behavior and
  completion history limitations

### Sources to approach with caution

- Vikunja community forum posts pre-2024 — the recurring task model has
  changed across versions; verify findings against the version running on
  office2 (`docs/design/architecture/data/service-inventory.json` has the
  version)

---

## Scope

### In scope

- Vikunja's native recurring task model and its API behavior
- Agent-managed daily task creation as an alternative model
- Hybrid approaches using Vikunja tasks plus a lightweight external log
  (technology evaluated open-ended based on fitness for purpose)
- The current F009 deployment state on office2
- API capabilities needed to implement the recommended approach

### Out of scope

- Implementation of the recommended approach (that is the revised F009
  software-dev mission)
- Evaluation of non-Vikunja task management tools (Vikunja is the
  established task store and is not under reconsideration)
- Changes to the habit list or habit definitions (content, not architecture)
- WhatsApp delivery or agent behavior changes (F009 implementation
  concerns, not architecture research)
- Any modifications to the live system during research

---

## User Scenarios and Testing

### Scenario 1: Research consumer reviews findings

**Actor**: Kent (system owner)
**Flow**: Kent reads the findings document and can determine which data model
to use for habits without needing to perform additional API investigation or
live system inspection.
**Acceptance**: All four RQs are answered with cited evidence. The
recommendation is actionable — it names specific API calls, fields, and
agent workflow changes needed.

### Scenario 2: Implementation spec author uses findings

**Actor**: Claude Code (implementing the revised F009 spec)
**Flow**: The agent reads the findings and can write the F009 implementation
spec without further API discovery, live system queries, or architecture
decisions.
**Acceptance**: API endpoints are confirmed with field-level detail. The
recommended approach specifies what the agent creates, when, and how
completion states are recorded.

### Scenario 3: Recommendation resolves the deferred decision

**Actor**: The F009 spec's "Habits Are Not Tasks" architecture principle
**Flow**: The deferred architecture decision in F009 is fully resolved by
the research recommendation.
**Acceptance**: The recommendation explicitly addresses the three candidate
approaches and explains why the selected one satisfies all evaluation
criteria (or documents the best trade-off if none fully satisfies all five).

---

## Expected Outputs

| Output | Answers | Description |
|--------|---------|-------------|
| Current state report | RQ-2 | Factual description of what F009 actually deployed: task structure, cron state, agent standing orders, whether any completion data exists |
| Recurring task behavior findings | RQ-1 | Verified description of Vikunja's native recurring model behavior on completion, including comment persistence and history queryability |
| Candidate approach comparison | RQ-3 | Table mapping all three options against the five evaluation criteria, with evidence citations |
| API capability confirmation | RQ-4 | List of confirmed API endpoints and fields supporting the recommended approach |
| Architecture recommendation | RQ-3, RQ-4 | Single recommended approach with rationale tied to evaluation criteria; risks and caveats documented |

**Downstream use**: Findings feed directly into the F009 revised implementation spec:
- Current state report -> Problem Statement section
- Architecture recommendation -> replaces the deferred decision in F009
- API capability confirmation -> implementation reference sections
- Candidate comparison -> Risk Considerations section of revised F009 spec

---

## Success Criteria

### Evidence
- [ ] RQ-1 through RQ-4 each have findings with cited sources
- [ ] At least 3 independent sources consulted (API docs, live system, community/forum or version changelog)
- [ ] Findings reflect the Vikunja version actually running on office2, not a different version

### Findings
- [ ] `findings.md` addresses all four RQs with supported conclusions
- [ ] Each of the five evaluation criteria has evidence for each candidate approach assessed
- [ ] Current F009 implementation state documented factually — gaps between spec intent and actual deployment called out explicitly
- [ ] Any API capabilities that could not be confirmed are noted as gaps

### Recommendation
- [ ] A single recommended approach is stated clearly
- [ ] Rationale maps recommendation to evaluation criteria by name
- [ ] Known risks or limitations of the recommended approach are documented

### Downstream readiness
- [ ] The revised F009 implementation spec can be written using findings without requiring further API discovery or live system inspection
- [ ] The deferred architecture decision in the current F009 spec is fully resolved by the recommendation

---

## Assumptions

- The Vikunja instance on office2 is representative of the production environment (it IS the production environment)
- The felix-admin-habits agent's AGENTS.md on office2 reflects the current deployed standing orders
- Vikunja's Today filter queries on `due_date` matching today's date (to be confirmed during research)
- The seven habit tasks (IDs 14-20) in Vikunja project 13 are the complete set of active habits

---

## Notes for Methodology Phase

- The current F009 spec (`docs/func-spec/F009_daily_habit_checkin.md`)
  explicitly flagged the architecture decision as deferred — read the
  "Habits Are Not Tasks" architecture principle and the Risk Considerations
  section before beginning gathering
- The habits-ops.md runbook documents the current system state as designed;
  the live system inspection (RQ-2) may reveal drift from that documentation
- Pre-research has identified relevant Vikunja community threads on recurring
  task behavior — the methodology phase should locate and use these as
  secondary sources, not primary ones; live system behavior takes precedence
- For the hybrid approach (Option C), evaluate the external log component
  open-ended — consider flat files, a second Vikunja project, the existing
  comment model, JSONL logs, or any other lightweight option that best fits
  the evaluation criteria

---

## Dependencies

- Vikunja instance on office2 must be accessible via API during research
- SSH access to office2 via `ssh office2-claude` must be available
- The diagnostic findings from the pre-research session (this conversation)
  partially answer RQ-2 and should be used as a starting point, not re-gathered

---

**END OF SPECIFICATION**
