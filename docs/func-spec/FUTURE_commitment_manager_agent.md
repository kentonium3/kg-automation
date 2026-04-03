---
title: "Future Feature: Commitment Manager Agent"
doc_type: func-spec
status: concept-stub
---

# Future Feature: Commitment Manager Agent

**Status**: Concept only — not yet scheduled in the roadmap
**Captured**: 2026-04-01
**Context**: Emerged from F013 (Vikunja Task Intelligence Agent) design
discussion

---

## Concept

A "Commitment Manager" or "Commitment Coach" agent that looks across all
goals, projects, tasks, and activities to assess whether Kent is on track
with his stated commitments and declared outcomes — in alignment with his
values — and initiates interaction and adjustments when course correction
is needed.

This is distinct from the escalation engine (F014) which has the single
job of escalating tasks meeting specific criteria. The Commitment Manager
operates at a higher level of abstraction, with broader situational
awareness across the full system state.

## Distinguishing it from other agents

| Agent | Scope | Trigger | Action |
|---|---|---|---|
| felix-admin-habits | Recurring habits | Daily schedule | Check-in prompt |
| Escalation engine (F014) | Overdue/flagged tasks | Due date criteria | Escalate task |
| Commitment Manager | All goals, outcomes, values | Weekly + on-demand | Assess alignment, initiate conversation |

## What it would do

- Look across all active goal declarations (Goals-MOC.md, Vikunja Goals
  project) and assess progress toward each
- Look across tasks and habits to evaluate whether daily activity is
  actually moving toward declared outcomes or just generating motion
- Detect misalignment between stated priorities and actual time/task
  allocation
- Surface the question: "Are you on track with what you said matters to you?"
- Could hand specific tasks to the escalation engine with additional
  context or messaging ("This task has been overdue for 10 days and it
  directly supports your $5K/month consulting income goal")
- Weekly rhythm — potentially integrated with the weekly habit pattern
  report from felix-admin-habits

## Relationship to constitution

The commitment manager is the agent most directly aligned with the
constitution directive that goal context inform every priority decision.
It is the agent that makes that directive operational rather than aspirational.

## Why not now

Requires the task intelligence agent (F013) and escalation engine (F014)
to be in place and generating clean, structured data first. The commitment
manager's quality depends entirely on the quality of the underlying task
and goal structure it reasons against. Build the foundation first.

---

**END OF CONCEPT STUB**
