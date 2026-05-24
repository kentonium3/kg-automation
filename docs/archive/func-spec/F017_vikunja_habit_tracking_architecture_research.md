---
title: "F017: Vikunja Habit Tracking Architecture Research"
doc_type: func-spec
status: draft
---

# F017: Vikunja Habit Tracking Architecture Research

**Version**: 1.0
**Priority**: HIGH
**Mission type**: research
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
of habit tasks 14–20 in Vikunja, the agent's standing orders, and the cron
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

## Known Sources

### Internal sources (examine first)

- `docs/func-spec/F009_daily_habit_checkin.md` — full requirements including
  the deferred architecture decision and evaluation notes already in the spec
- `docs/runbooks/habits-ops.md` — current agent, cron, and task documentation;
  contains task IDs 14–20 and the current comment-based completion model
- Live Vikunja instance on office2 — inspect habit tasks 14–20 directly via
  API to determine current state (due_date, recurrence fields, comment history)
- `/data/services/openclaw/habits-agent/AGENTS.md` on office2 — the agent's
  standing orders; reveals whether the agent was designed to create tasks or
  query static ones
- `openclaw cron list` on office2 — confirms whether cron jobs exist and
  their current configuration

### External sources

- Vikunja API reference: https://try.vikunja.io/api/v1/docs#tag/task — task
  schema fields including repeat_mode, repeat_after, and related fields
- Vikunja help docs (dates and reminders): https://vikunja.io/help/dates-and-reminders/
  — documents recurrence behavior and the Today filter
- Vikunja community forum — prior discussions on recurring task behavior and
  completion history limitations (several relevant threads already identified
  in pre-research)

### Sources to approach with caution

- Vikunja community forum posts pre-2024 — the recurring task model has
  changed across versions; verify findings against the version running on
  office2 (`docs/design/architecture/data/service-inventory.json` has the
  version)

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

## Scope

### In scope

- Vikunja's native recurring task model and its API behavior
- Agent-managed daily task creation as an alternative model
- Hybrid approaches using Vikunja tasks plus a lightweight external log
- The current F009 deployment state on office2
- API capabilities needed to implement the recommended approach

### Out of scope

- ❌ Implementation of the recommended approach — that is the revised F009
  software-dev mission
- ❌ Evaluation of non-Vikunja task management tools — Vikunja is the
  established task store and is not under reconsideration
- ❌ Changes to the habit list or habit definitions — content, not architecture
- ❌ WhatsApp delivery or agent behavior changes — those are F009 implementation
  concerns, not architecture research
- ❌ Any modifications to the live system during research

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
- Current state report → Problem Statement section (what was built vs. what was intended)
- Architecture recommendation → replaces the deferred decision in the F009
  "Habits Are Not Tasks" architecture principle section
- API capability confirmation → "Study These Files First" and "Notes for
  Implementation" sections of the revised F009 spec
- Candidate comparison → Risk Considerations section of revised F009 spec

---

## Constraints

- Read-only on the live Vikunja instance and office2 during research — no task
  creation, modification, deletion, or agent file changes
- The recommended approach must be implementable within the existing Vikunja
  instance (no schema changes, no new services)
- Vikunja API token location: `/data/services/openclaw/secrets/vikunja-api`
- Vikunja base URL: `https://office2.tail0f5f56.ts.net`
- office2 access: `ssh office2-claude` (read-only queries only)

---

## Success Criteria

### Evidence
- [ ] RQ-1 through RQ-4 each have findings with cited sources
- [ ] At least 3 independent sources consulted (API docs, live system,
  community/forum or version changelog)
- [ ] Findings reflect the Vikunja version actually running on office2,
  not a different version

### Findings
- [ ] `findings.md` addresses all four RQs with supported conclusions
- [ ] Each of the five evaluation criteria has evidence for each candidate
  approach assessed
- [ ] Current F009 implementation state documented factually — gaps
  between spec intent and actual deployment called out explicitly
- [ ] Any API capabilities that could not be confirmed are noted as gaps

### Recommendation
- [ ] A single recommended approach is stated clearly
- [ ] Rationale maps recommendation to evaluation criteria by name
- [ ] Known risks or limitations of the recommended approach are documented

### Downstream readiness
- [ ] The revised F009 implementation spec can be written using findings
  without requiring further API discovery or live system inspection
- [ ] The deferred architecture decision in the current F009 spec is
  fully resolved by the recommendation

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
- The three candidate approaches to evaluate are: (A) native Vikunja recurring
  tasks, (B) agent-managed daily task creation with dated child tasks, and
  (C) hybrid — recurring tasks for Today filter visibility with completion
  history in a lightweight external log

---

**END OF SPECIFICATION**
