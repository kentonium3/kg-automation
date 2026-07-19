---
title: Process-Flow Docs — Convention & Index
doc_type: explanation
status: active
level: concept
audience: agents_and_humans
owners: [kgale]
created: 2026-07-19
last_updated: '2026-07-19'
last_validated: '2026-07-19'
version: v1.0
updated_by: 'process-flow-docs-home (#794) — establishes the discoverable home + shape for user process-flow docs and back-fills the existing flows'
tags: [794, 780]
---

# Process-Flow Docs — Convention & Index

> **Divio type: Explanation / Reference (current-state).** The docs in this
> directory describe *what a Felix user-facing process does today* — the actors,
> the states, the operating rules (with the invariant/requirement IDs they
> enforce), and the code seams that implement them. They are **not** runbooks
> (how to operate) and **not** specs (what to build). Runbooks and agent
> `TOOLS.md`/`AGENTS.md` link here rather than restating the rules.

## Why this directory exists

A "user process flow" is one of Felix's end-to-end behaviors that a captured
signal moves through — inbox routing, calendar clarification, someday, journal,
habits. Before this convention, the only way to learn a flow's *current-state*
behavior was to open the individual `kitty-specs/` missions that built it and
reconstruct it from FRs scattered across several specs. That is the exact pain
[#780](https://github.com/kentonium3/kg-automation/issues/780) hit: to add the
all-day fallback it had to re-derive the whole calendar-clarification flow from
FR-007 + #739 across multiple archived missions, and nearly re-introduced a wrong
eligibility rule in the process.

This directory is the **single canonical, machine-discoverable home** for those
current-state explanations. Each doc **credits and consolidates** the missions
that built the flow; it does not reinvent them. [#794](https://github.com/kentonium3/kg-automation/issues/794)
established the convention and back-filled the existing flows;
[#780](https://github.com/kentonium3/kg-automation/issues/780) wrote the first
one (calendar-clarification) as the exemplar.

## When to write / update a process-flow doc

- **A mission changes a documented flow** → update that flow's doc in the **same
  merge** (the `signal-to-doc-map.json` change classes below route the mission to
  it). This is the standing requirement, same class as updating
  `docs/design/architecture/` when a service changes.
- **A mission creates a new user-facing flow** → add a new doc to this directory
  in the shape below, register its change class in `signal-to-doc-map.json`, and
  add it to `docs/INDEX.md` (see the checklist).
- **A pure implementation refactor that does not change observable behavior** →
  update the **Implementing seams** table only (keep the file/function list
  current) so a reader can still jump from a rule to the code.

## Canonical shape

Every process-flow doc follows the **same section order** — the shape the
calendar-clarification exemplar established. Keep it identical so a reader who
knows one doc knows them all:

1. **Frontmatter** — see below.
2. **Divio-type callout** — the blockquote declaring "Explanation / Reference
   (current-state), not a runbook."
3. **Why this document exists** + a **contributing missions** table
   (`contribution | origin issue/mission`) that credits the missions/issues the
   behavior came from.
4. **Actors & trigger** — which agents/actors participate and what starts the flow.
5. **Flow & states** — an ASCII flow diagram **and** a precise states table
   (`state | meaning | terminal?`).
6. **Operating rules & invariants** — a numbered list where **each rule cites the
   FR/INV/constraint/mission ID it enforces**, so a reader can trace the rule to
   the requirement and confirm the code enforces exactly what is written.
7. **Implementing seams** — a table (`seam | file | role`) of the exact
   files+functions, plus a **State store** note for any persisted state.
8. **State diagram** — a Mermaid `stateDiagram-v2`.
9. **Cross-references** — source issue(s), related/next work, prior missions
   consolidated, and the mission spec(s) for full FR detail.

### Frontmatter convention

Use the kg-automation front-matter keys plus the process-flow specifics:

```yaml
title: <Flow Name> Process Flow
doc_type: explanation          # always — these are Divio explanation/reference
status: active
level: concept
audience: agents_and_humans    # both the machine-discovery path and humans read these
owners: [kgale]
created: 'YYYY-MM-DD'
last_updated: 'YYYY-MM-DD'
last_validated: 'YYYY-MM-DD'
version: vX.Y
updated_by: '<mission-slug> (#NNN) — one-line why'
tags: [<contributing issue numbers>]   # e.g. [780, 746, 786]
```

### The ID-citation discipline (load-bearing)

The value of these docs is that a rule can be **traced to the requirement and the
code**. Follow the exemplar's discipline:

- **Cite the real ID** as it appears in the spec/code — `FR-005`, `INV-6`,
  `C-004`, `NFR-001`, or a bare issue `#NNN`.
- **Disambiguate by mission slug when IDs collide.** IDs are only unique *within a
  mission*. The journal flow, for example, is governed by **two different
  FR-010s** — one from `capture-d6-helpers-extraction-01KTMS5Q` (atomic write) and
  one from `capture-atomic-finalize-01KXRM7J` (per-block idempotency). Always
  write `FR-010 (capture-atomic-finalize-01KXRM7J)`, never a bare `FR-010`, when
  ambiguity is possible.
- **Flag drift explicitly.** When current code and a prior spec disagree (a
  superseded requirement), describe *current* behavior and note which FR it
  superseded, with the mission that changed it. Do not silently document the old
  spec.

## Machine discovery

Process-flow docs are wired into the same discovery path spec/plan agents already
use for architecture docs:

- **`docs/design/architecture/data/signal-to-doc-map.json`** — each flow has one
  or more `change_class` entries whose `doc_targets` name the flow doc. A mission
  whose Architecture Impact matches that class is routed to the doc. Filter by
  `match.source == "mission-architecture-impact"`. Current process-flow change
  classes:

  | change_class | routes to |
  |---|---|
  | `calendar-flow-changed` | `calendar-clarification.md` |
  | `inbox-routing-changed` | `inbox-routing.md` (+ `calendar-clarification.md` where the change touches it) |
  | `someday-flow-changed` | `someday.md` |
  | `journal-flow-changed` | `journal.md` |
  | `habits-flow-changed` | `habits.md` |

- **`docs/INDEX.md`** § *docs/design/process-flows/* — the human discovery entry;
  every flow doc is listed here with a one-line description.
- **`docs/DEVELOPER_PORTAL.md`** — the onboarding sitemap points at this directory
  as the current-state behavior reference for a flow.

## Checklist — adding a new flow doc

1. Write `docs/design/process-flows/<flow>.md` in the canonical shape above.
2. Add a `<flow>-flow-changed` (or equivalent) `change_class` to
   `signal-to-doc-map.json` with `doc_targets` pointing at the new doc, and add
   the same class to any adjacent flow's rationale that hands off to it.
3. Add a one-line entry under the *docs/design/process-flows/* section of
   `docs/INDEX.md`.
4. Update the table above in this README.
5. Run `python tooling/scripts/validate_docs.py` and the architecture-data
   validator before committing.

## Index of current process-flow docs

| Flow | Doc | What it covers |
|---|---|---|
| **Inbox routing** | [inbox-routing.md](./inbox-routing.md) | The umbrella capture lifecycle: tick → prescan → classify → route → atomic finalize → mark processed, and the note states around it. |
| **Calendar clarification** | [calendar-clarification.md](./calendar-clarification.md) | The child flow when a captured note is an appointment with a date but no time: ask-first → 8h window → answered-timed / all-day fallback / delete-and-release. |
| **Someday** | [someday.md](./someday.md) | Captures classified "someday" → a `q:schedule` + no-due-date Vikunja task in Inbox, with fail-soft label attach. |
| **Journal** | [journal.md](./journal.md) | Captures classified "journal" → a dated, atomic append into the `08-Journal/` vault tree. |
| **Habits** | [habits.md](./habits.md) | The habit completion lifecycle: completion → `record_completion` (history + ET-EOD reschedule) and the reporting/escalation boundary. |
