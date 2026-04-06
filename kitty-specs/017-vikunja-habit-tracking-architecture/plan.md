# Implementation Plan: F017 Vikunja Habit Tracking Architecture

**Branch**: `main` | **Date**: 2026-04-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/017-vikunja-habit-tracking-architecture/spec.md`
**Mission**: research

---

## Summary

Investigate the correct Vikunja data model for daily habit tracking so
habits appear in the Today filter. Four research questions examine
Vikunja's native recurring task behavior, the current F009 deployment
state, three candidate approaches against five evaluation criteria, and
the API capabilities needed to implement the recommended approach.
Findings feed directly into a revised F009 implementation spec.

## Technical Context

This is a research mission — no code is written. The "implementation"
is structured investigation producing documentation.

**Tools**: Vikunja REST API (read-only queries), SSH to office2, web
research (Vikunja docs, community forum, API reference)
**Storage**: N/A (research outputs are markdown documents)
**Testing**: N/A (findings validated against success criteria in spec)
**Target Platform**: N/A (research deliverables only)
**Constraints**: Read-only access to live Vikunja instance and office2;
no task creation, modification, or agent file changes during research

## Constitution Check

*GATE: Passed. Research mission — no code, no deployments, no service
changes. Constitution governance applies to the downstream F009
implementation, not to this investigation.*

- Felix Constitution Directive 5 (documentation standards): Applies —
  findings.md must follow documentation conventions
- Autonomy Level 1 (Assisted): The habits agent operates at Level 1;
  this research does not change that
- No tier-gated changes: All research is read-only (below Tier 4)

## Project Structure

### Documentation (this feature)

```
kitty-specs/017-vikunja-habit-tracking-architecture/
├── plan.md              # This file
├── research.md          # Phase 0: methodology and source plan
├── spec.md              # Feature specification
├── meta.json            # Feature identity metadata
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks/               # Work package files (created by /spec-kitty.tasks)
```

### Source Code

No source code is produced by this research mission. The downstream
F009 revised implementation spec will define code changes.

## Research Methodology

### Phase 0: Source Plan and Methodology

The research follows the dependency order defined in the spec:

**Independent track (can begin immediately)**:
- **RQ-2**: Inspect the current F009 deployment state on office2.
  Partially answered by diagnostic work already performed — task IDs
  14-20 have no due_date set, cron is running and delivering, agent
  queries static tasks and records completions as comments. The WP
  should verify this is complete and document it formally.

**Sequential track (dependency chain)**:
- **RQ-1**: Verify Vikunja's native recurring task behavior. Sources:
  Vikunja API docs, help docs on dates/reminders, community forum
  threads, and ideally a read-only inspection of the task schema fields
  (repeat_mode, repeat_after) on the live instance. Must confirm: what
  happens to due_date, done status, and comments when a recurring task
  is marked complete.
- **RQ-3** (depends on RQ-1): Evaluate three candidate approaches
  against the five evaluation criteria. Option C's external log
  component is evaluated open-ended.
- **RQ-4** (depends on RQ-3): Confirm API endpoints and fields needed
  for the recommended approach.

### Sources to consult

| Source | Type | RQs served |
|--------|------|------------|
| Live Vikunja instance (API queries via office2) | Primary | RQ-1, RQ-2 |
| Vikunja API reference (try.vikunja.io/api/v1/docs) | Primary | RQ-1, RQ-4 |
| Vikunja help docs (vikunja.io/help/dates-and-reminders/) | Secondary | RQ-1 |
| Vikunja community forum | Secondary | RQ-1 |
| docs/func-spec/F009_daily_habit_checkin.md | Internal | RQ-2, RQ-3 |
| docs/runbooks/habits-ops.md | Internal | RQ-2 |
| AGENTS.md on office2 | Internal | RQ-2 |
| docs/design/architecture/data/service-inventory.json | Internal | Version verification |
| Pre-research diagnostic findings (this conversation) | Internal | RQ-2 (partial) |

### Version verification

Before consulting external sources, confirm the Vikunja version running
on office2 from `service-inventory.json`. All findings must be validated
against this version — community posts referencing older versions should
be flagged as potentially outdated.

## Evaluation Framework

The spec defines five evaluation criteria. Each candidate approach must
be assessed against all five:

| Criterion | Weight | Measurement |
|-----------|--------|-------------|
| Today filter visibility | High | Does the approach produce tasks with due_date = today that appear in the Today filter? |
| Skipped state expressible | High | Can "will not do" be recorded distinctly from "complete"? |
| Completion history survives 90 days | High | Are individual records queryable by date across 90+ days? |
| 48-hour catch-up window | Medium | Can a missed habit be marked retroactively? |
| Agent implementation complexity | Medium | Can felix-admin-habits implement this without a new external data store? |

### Candidate approaches to evaluate

- **Option A**: Native Vikunja recurring tasks (repeat_mode + repeat_after)
- **Option B**: Agent-managed daily task creation (new child tasks with dated due_date)
- **Option C**: Hybrid (Vikunja tasks for Today visibility + lightweight external log for history/state)

## Expected Deliverables

A single `findings.md` document organized by research question:

1. **RQ-2 — Current State Report**: What F009 actually deployed vs. what
   the spec intended
2. **RQ-1 — Recurring Task Behavior**: Verified description of Vikunja's
   native model, with version-specific evidence
3. **RQ-3 — Candidate Comparison**: Table mapping three options against
   five criteria, with evidence citations and a single recommendation
4. **RQ-4 — API Capability Confirmation**: Endpoint-level detail for
   implementing the recommended approach

Plus an **Architecture Recommendation** section with:
- The recommended approach (one of A/B/C)
- Rationale mapped to evaluation criteria
- Known risks and limitations
- Specific guidance for the revised F009 implementation spec

## Work Package Strategy

Single WP covering the full investigation. One review cycle at the end
against the spec's success criteria. The findings document is organized
by RQ so each section can be evaluated on its own merits during review.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Vikunja recurring task behavior differs from documentation | Medium | High | Verify against live instance, not just docs |
| No candidate approach satisfies all five criteria | Low | Medium | Spec allows documenting "best available trade-off" |
| Community forum sources reference wrong Vikunja version | Medium | Low | Version-check all external findings against service-inventory.json |
| office2 or Vikunja unavailable during research | Low | High | Most external source research can proceed independently; retry API queries |

---

**Branch contract (confirmed)**:
- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **yes**

---

**END OF PLAN**
