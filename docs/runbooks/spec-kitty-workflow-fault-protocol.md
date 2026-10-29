---
id: spec-kitty-workflow-fault-protocol
doc_type: runbook
title: Spec-Kitty Workflow-Fault Detour Protocol (SUPERSEDED — pointer)
status: deprecated
level: reference
owners: [kent]
last_validated: 2026-09-28
version: 2.0.0
---

# Spec-Kitty Workflow-Fault Detour Protocol — SUPERSEDED

⛔ **This copy is retired. Do not follow it. Do not restore it from history.**

**The canonical protocol is:**

> `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-workflow-fault-protocol.md`

**And the canonical bug-reporting procedure — how to actually report anything a fault
produces — is the single source of truth here:**

> `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-bug-reporting.md`

The fault protocol covers **how to handle a fault**. It defers **all reporting mechanics**
to the bug-reporting runbook. There is no third copy of either.

## Why this was retired (2026-09-28)

This file sat at **v1.0.0, last validated 2026-07-18**, while the canonical copy advanced to
v2.1.0 and the bug-reporting runbook to v2.6. It had **drifted into contradicting them**, and
two of its instructions were actively wrong:

1. ⛔ **It told agents to `@mention` the program's maintainer when an upstream issue was CLOSED.**
   That guidance predates **v2.3 (2026-09-13)**, which replaced closed-match comments with a new
   issue. On 2026-09-28 an agent followed this file and mentioned **spec-kitty's CEO, two levels
   above the actual maintainer**, on `spec-kitty/spec-kitty#5310`. The mention was retracted; the
   notification could not be.
2. **It described the dual-track model** (internal mirror issue in `kg-automation`, then an
   upstream report). **That model is retired** — the upstream queue is the team's queue, and
   `kg-automation` tracking issues are no longer created.

**The current dedup rule, in one place, is three dispositions:**

| Search result | Disposition |
|---|---|
| **no match** | open a **new issue** |
| **open match** | add a **recurrence comment** to it |
| **closed match** | open a **NEW issue referencing the closed one** — ⛔ never comment on a closed issue |

⛔ **Never `@mention` a maintainer in any of the three.**

## The lesson this file is kept to record

**A stale duplicate is worse than a missing document.** An agent that finds no runbook asks;
an agent that finds an outdated one follows it. This file was authoritative-looking, in the
expected location, and wrong — and it was cited by the team lead as well as the worker.

**Keep one canonical source. Point at it. Never fork it.**
