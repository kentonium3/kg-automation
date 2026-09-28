---
id: spec-kitty-bug-reporting
doc_type: runbook
title: Spec-Kitty Bug Reporting (SUPERSEDED — pointer)
status: deprecated
level: reference
owners: [kent]
last_validated: 2026-09-28
version: 2.0.0
---

# Spec-Kitty Bug Reporting — SUPERSEDED

⛔ **This copy is retired. Do not follow it. Do not restore it from history.**

**The single canonical source of truth is:**

> `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-bug-reporting.md`

**Templates live beside it** — `~/repos/spec-kitty-qa/docs/templates/`:
- `spec-kitty-bug-report-external-template.md` — a new upstream issue
- `spec-kitty-upstream-comment-template.md` — a comment on an existing OPEN issue

The **workflow-fault** protocol (`spec-kitty-qa/docs/runbooks/spec-kitty-workflow-fault-protocol.md`)
covers **how to handle a fault** and defers **all reporting mechanics** to the runbook above.
There is no third copy of either.

## What changed (2026-09-28)

**1. Single-track. `kg-automation` tracking issues are no longer created.**
Kent leads QA at spec-kitty; the upstream queue is the team's queue. The dual-track model this
file described — an internal mirror issue, then a slim external report generated from it — is
retired. **File upstream, using the QA rules.** Existing `kg-automation` issues stay as history.

**2. Dedup resolves to exactly three dispositions:**

| Search result (open AND closed) | Disposition |
|---|---|
| **no match** | open a **new issue** |
| **open match** | add a **recurrence comment** to it |
| **closed match** | open a **NEW issue referencing the closed one** — ⛔ never comment on a closed issue |

⛔ **Never `@mention` a maintainer in any of the three.**

**3. The footer is two lines.** `Authored by` and `Submission approved by`. The old third line,
`Local tracking: kentonium3/kg-automation#NNN`, is **dropped** — single-track leaves nothing for
it to point at. The canonical template already carries the correct two-line form.

**4. The pre-filing approval checklist that lived here is obsolete as a section**, but its
requirements stand and now live in the filing instructions: **the operator approves the exact
TITLE and the paste-ready BODY before anything is filed, and the request states the title
explicitly** rather than assuming it can be inferred from the body.

## Why this file was retired

It sat at **v1.7** while the canonical copy advanced to **v2.6**, and had drifted into
contradicting it — including a three-line footer the canonical template no longer uses, which is
the version that reached `spec-kitty/spec-kitty#5310` on 2026-09-28.

**A stale duplicate is worse than a missing document.** An agent that finds no runbook asks; an
agent that finds an outdated one follows it. **Keep one canonical source. Point at it. Never fork it.**
