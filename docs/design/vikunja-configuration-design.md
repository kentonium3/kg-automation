---
title: "Vikunja Configuration Design"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-07-12'
audience: agents_and_humans
---

# Vikunja Configuration Design

**Status:** Draft
**Author:** Kent Gale
**Location:** `docs/design/vikunja-configuration-design.md`
**Related:** Vikunja Configuration Reset Epic ([#714](https://github.com/kentonium3/kg-automation/issues/714)) — executes this design; Felix/Vikunja Integration Epic (TBD)

---

## Problem Statement

Vikunja's current configuration drifted into an unusable state during Felix's
early development. Projects were created to serve as views (Today, Upcoming,
Someday, Everyday, Favorites), labels were applied inconsistently, and the
friction/Eisenhower taxonomy designed for Felix integration was never
implemented. The result is a task system that neither Felix nor Kent can
use effectively.

This document defines the canonical configuration: project structure, label
taxonomy, saved filters, and the principles governing each. It is the
authoritative reference for Vikunja setup and for future Felix/Vikunja
integration design.

---

## Guiding Principles

**Projects hold tasks. Saved filters are views.** The core Vikunja construct
distinction that the previous setup violated. Projects are topic buckets —
domain containers for related work. Saved filters are cross-project lenses
that answer "what should I be doing right now?" These are never the same
thing.

**Labels are machine-readable and human-readable.** All label names use
structured prefixes (`f:`, `q:`, `t:`, `loe:`) so Felix can query by label
reliably via the API. Names are chosen to be meaningful to a human reading
them in the UI without needing a reference guide.

**Friction measures internal resistance, not effort or importance.** The
friction taxonomy describes the nervous system's response to a task — not
how hard the task is or how important it is. Those are orthogonal dimensions
captured by LOE and Eisenhower respectively.

**Design for Felix-first, human-readable second.** Label conventions,
project names, and filter definitions must be stable and API-queryable.
Human readability is a constraint, not the primary goal.

**Start minimal, defer what isn't needed yet.** Area labels and other
future dimensions are documented but not implemented until Felix
functionality demands them.

---

## Project Structure

Projects are topic buckets — containers for related tasks. The sidebar
hierarchy reflects domain ownership, not temporal or priority context.

```
Inbox                      (native, kent-owned — verified, never recreated)
Felix / kg-automation      (created by #716)
Clients                    (created by #716 — parent folder, holds no tasks)
  └── PointerHealth         (created by #716, under Clients)
  └── spec-kitty            (created by #716, under Clients)
Personal                   (created by #716)
Metal Casework             (retained — pre-existing, empty)
CT-90day                   (retained — pre-existing, empty)
Habits                     (retained — pre-existing, id 13; untouched by #716)
```

Issue **#716** establishes this structure as an **additive-only** reconcile: it
creates the five new topic projects (`Felix / kg-automation`, `Clients`,
`PointerHealth`, `spec-kitty`, `Personal`) as kent, verifies `Inbox`, and
deletes the legacy saved filters (below). It never deletes a project. The
task-bearing legacy projects (`Everyday`, `Someday`, `Personal Growth &
Transformation`, `Household`, `Goals`, `Research`) and all task migration are
deferred to **#717**, which requires human judgment; the `t:habit` label (created
in #715) becomes the habit identity there, at which point the `Habits` project
(id 13) can be retired. Until #717 runs, `Habits` and the other task-bearing
projects remain intact.

**Inbox** is Vikunja's native quick-capture project. Tasks created without
a project assignment land here. It is a staging area only — tasks should
be triaged out of Inbox daily into their correct project with full label
metadata applied. Inbox is never a permanent home for any task. The reconcile
helper **verifies** Inbox (id 1, kent-owned) and never recreates it; owner-scoped
matching ignores the felix-bot token's separate `Inbox` (id 14).

**Clients** is a parent project (folder) with no tasks of its own.
`PointerHealth` and `spec-kitty` are sub-projects that inherit the
Clients grouping in the sidebar. This structure keeps client work
isolated and browsable without requiring a label to identify it.

**Personal** catches everything that doesn't belong to a named domain:
household, administrative, learning, relationships.

**Pseudo-views vs. native filters.** Earlier ad-hoc "views" — `Today`,
`Upcoming`, `Overdue`, `Goals`, and `Completed` — were **saved filters**, which
Vikunja surfaces in the project sidebar as **negative-id pseudo-projects**
(`id <= -2`). They are not real projects. Issue **#716** removes these five
legacy saved filters (deriving each filter id from its pseudo-project and reading
back the title before deleting). `Favorites` (pseudo-id `-1`) is a **native**
Vikunja view, not a deletable saved filter, and is left untouched. The six
canonical replacement saved filters are created separately by **#718** (see the
Saved Filters section below).

---

## Label Taxonomy

Labels encode task metadata across four dimensions. Each dimension uses a
consistent prefix for API queryability. Labels are applied at task creation
and validated by Felix (see Felix Integration section).

### Friction (`f:`) — Internal Resistance

Friction describes the nervous system's response to starting a task. It is
grounded in the Yerkes-Dodson Law, the Three-Ring Model, and research on
the Anterior Mid-Cingulate Cortex (aMCC) — the brain region that governs
tenacity and willpower, and that physically grows when a person does things
they don't want to do.

The key insight: discomfort is not a side effect of growth — it is the
mechanism. The avoidance urge on an Edge task is the aMCC being challenged.
Every push-through is literal neural remodeling.

| Label | Name | Color (hex) | Nervous System State |
|---|---|---|---|
| `f:1-flow` | Flow | `4caf50` | No internal resistance. Confident execution regardless of effort level. Basal ganglia autopilot or full engagement — neither generates a threat response. |
| `f:2-growth` | Growth | `fbc02d` | Moderate activation. Prefrontal cortex engaged. Discomfort is present and functional — the signal that learning is occurring. |
| `f:3-edge` | Edge | `fb8c00` | aMCC activated. Visceral avoidance urge. Maximum neuroplasticity territory. The exact zone where tenacity is built. Discomfort as power, not pain. |
| `f:4-overload` | Overload | `e53935` | Amygdala hijack. Prefrontal cortex offline. Cognitive shutdown. Not an executable task — requires decomposition before it can be scheduled. |

**Critical distinction:** Friction is orthogonal to effort and importance. A
high-effort, high-value task can be `f:1-flow` if it feels natural to
execute. A trivial task can be `f:3-edge` if avoidance is strong.

**`f:4-overload` is a decomposition trigger, not a schedulable state.** A
task labeled Overload should never appear in an active work queue. Felix
intercepts Overload tasks at intake and prompts decomposition into Growth
or Edge sub-tasks before allowing scheduling.

**Daily accountability signal:** A day without at least one `f:3-edge` task
completed is a day without aMCC exercise. Felix surfaces this in the daily
briefing.

### Eisenhower (`q:`) — Strategic Classification

The Eisenhower Matrix classifies tasks on two axes: importance and urgency.
It forces the question of whether a task deserves attention and why.

| Label | Quadrant | Color (hex) | Meaning |
|---|---|---|---|
| `q:do` | Important + Urgent | `1565c0` | Do first. Uses native priority field to order within this quadrant. |
| `q:schedule` | Important + Not Urgent | `1e88e5` | Schedule deliberately. Highest strategic value — most likely to be deferred. The quadrant Felix should surface most aggressively. |
| `q:delegate` | Not Important + Urgent | `42a5f5` | Handle but don't personally own. |
| `q:eliminate` | Not Important + Not Urgent | `90caf9` | Remove from the list. Exists briefly to make the elimination decision explicit. |

**Relationship to native Priority field:** Eisenhower captures strategic
classification. Native priority (0–5 integer, displayed as Not set / Low /
Medium / High / Urgent / DO NOW) orders tasks within `q:do`. Both are
needed; they are not redundant. The native priority display labels are poor
but the underlying integer values are queryable by Felix regardless.

**`q:schedule` is the highest-value quadrant.** Important work without
deadline pressure is the work most likely to be avoided. Combined with
`f:3-edge`, it surfaces the tasks that matter most and are most resisted —
the primary focus signal for Felix.

### Type (`t:`) — Behavioral Classification

Type describes how a task behaves, not what domain it belongs to.

| Label | Name | Color (hex) | Meaning |
|---|---|---|---|
| `t:habit` | Habit | `8e24aa` | A recurring task tracked by Felix. Completion is reported via WhatsApp daily. Felix maintains a persistent completion record. Frequency lives on the task via repeat interval / RRULE, not in a project or bucket. |

Additional type labels will be defined as Felix functionality requires them.

### Level of Effort (`loe:`) — Size Signal

LOE is a coarse estimate of execution size. It informs Felix on whether a
task should be scheduled as-is, calendar-blocked, or decomposed into
sub-tasks. Custom fields are not filterable in Vikunja's current query
language, so LOE is implemented as labels.

| Label | Name | Color (hex) | Meaning | Felix Implication |
|---|---|---|---|---|
| `loe:s` | Small | `bdbdbd` | Single focused session, ~1 hour or less | Schedule as-is |
| `loe:m` | Medium | `757575` | Multiple sessions or roughly half a day | Consider calendar blocking |
| `loe:l` | Large | `424242` | Multi-day effort | Prompt decomposition into sub-tasks |

`loe:l` is a soft signal analogous to `f:4-overload`: Felix should flag
large tasks and confirm they don't need breaking down before scheduling.

### Deferred Dimensions

**Area labels (`area:`)** — semantic domain anchors for Felix routing
(e.g., `area:health`, `area:felix`, `area:business`). Deferred until Felix
requires domain-based briefing or task routing that cannot be expressed
cleanly via project membership alone. Project names are human-readable but
fragile; area labels will provide stable semantic anchors when needed.

---

## Required Fields (Task Intake Standard)

Every task that exits Inbox into a working project must have the following
fields populated before it is considered schedulable:

**Tier 1 — Always required:**
- Project assignment (not Inbox)
- Friction label (`f:1` through `f:3` — `f:4-overload` triggers
  decomposition, not scheduling)
- Eisenhower quadrant (`q:do`, `q:schedule`, `q:delegate`, `q:eliminate`)

**Tier 2 — Required when applicable:**
- Due date (required if `q:do` or `q:schedule` with a committed date)
- `t:habit` label (if recurring)
- LOE label (`loe:s`, `loe:m`, `loe:l`)

Felix validates Tier 1 completeness and prompts via WhatsApp for any missing
fields. This validation loop is the mechanism that ensures the label taxonomy
stays populated rather than decaying into inconsistency.

---

## Saved Filters

Saved filters are personal cross-project views. They replace the pseudo-view
projects (Today, Upcoming, Someday, Everyday, Favorites) that previously
polluted the project structure.

| Filter | Query | Purpose |
|---|---|---|
| **Today** | `dueDate <= now/d && done = false` | Primary daily driver. Set as dashboard default. |
| **Habits** | `label = t:habit && done = false` | All habit tasks regardless of schedule. Felix's daily prompt source. |
| **Upcoming** | `dueDate > now/d && dueDate < now+7d && done = false` | 7-day horizon. |
| **Someday** | `label = q:schedule && dueDate = null && done = false` | Important but not yet committed to a date. |
| **High Priority** | `priority >= 4 && done = false` | Urgent items by native priority. |
| **Edge + Schedule** | `label = f:3-edge && label = q:schedule && done = false` | The most important filter: high-value, not urgent, high resistance. The work most likely to be avoided and most worth doing. |

**Dashboard default:** Today filter. This is what Felix and Kent see on login.

**Note on subtask visibility:** A known Vikunja bug (issue #2494) means
subtasks are not shown in saved filters if their parent task doesn't match
the filter criteria. Avoid nesting habit or Edge tasks under parent tasks
that would be excluded by active filters.

---

## Migration Sequence

The following sequence transitions from the current state to this design.
Steps 1 and 5 require human judgment; the rest are mechanical and scripted via
the Vikunja API. Steps are annotated with the issue that owns them.

1. **Audit current tasks** — identify real vs. stale across all existing
   projects. Delete or archive anything no longer active.
2. **Create the label taxonomy** (#715) — all `f:`, `q:`, `t:`, and `loe:`
   labels, created as kent via the API. (Done.)
3. **Create the project structure** (#716) — verify Inbox exists, then
   additively create the *missing* topic projects: Felix / kg-automation,
   Clients (parent), PointerHealth, spec-kitty, Personal. (Intentional LLC,
   Business Acquisition, Health & Conditioning, Metal Casework, CT-90day, and
   Habits already exist and are retained — not recreated.)
4. **Delete the legacy saved filters** (#716) — Today, Upcoming, Overdue,
   Goals, Completed. These are negative-id *saved filters*, not projects;
   Favorites is Vikunja's native view and is left untouched. Backup-gated
   (Tier 2). The canonical replacement filters are created in step 7 (#718).
5. **Migrate surviving tasks + delete emptied projects** (#717, human
   judgment) — move tasks out of the task-bearing projects (Everyday, Someday,
   Personal Growth & Transformation, Household, Goals, Research) into their
   correct topic projects with Tier 1/2 labels, then delete those projects
   once confirmed empty. (Personal Growth & Transformation + Household fold
   into the new Personal.)
6. **Create saved filters** (#718) — all six filters defined above.
7. **Set dashboard** — Today filter as home screen default.
8. **Verify Felix label references** — confirm Felix skill and briefing
   queries match the locked label names in this document.

---

## Felix Integration Notes

This document scopes Vikunja configuration only. The following are
integration points that will be inputs to a future Felix/Vikunja
integration design spike:

- **Task intake validation loop** — Felix scans for Tier 1 incomplete tasks
  in Inbox and prompts via WhatsApp for missing metadata.
- **Daily habit prompt** — Felix queries the Habits saved filter, assembles
  the day's habit stack, delivers via WhatsApp, and records completion.
- **Edge accountability signal** — Felix tracks whether at least one
  `f:3-edge` task was completed each day and surfaces this in the daily
  briefing.
- **Overload interception** — Felix detects `f:4-overload` tasks at intake
  and refuses to schedule them until decomposed.
- **Edge + Schedule surfacing** — Felix prioritizes the Edge + Schedule
  filter in briefings as the primary high-value/high-resistance signal.
- **LOE-based calendar blocking** — Felix uses `loe:m` and `loe:l` as
  signals for calendar block suggestions (design TBD).
- **Purpose hierarchy assessment** — future capability; depends on Graphiti
  graph layer. Every task will trace to a Purpose via the ontology. This
  label schema is designed to be compatible with that future layer.

The Felix/Vikunja integration epic should treat this document as the
authoritative Vikunja configuration reference and design the interaction
model against it.

---

## Open Items

- [ ] Confirm Vikunja version on office2 supports all filter syntax used
      in saved filter definitions above
- [ ] Decide whether migration should be manual or API-scripted based on
      task volume in current pseudo-view projects
- [ ] Upstream contribution opportunity: rename native priority display
      labels to professional values (`None`, `Low`, `Medium`, `High`,
      `Critical`, `Immediate`)
- [ ] Upstream contribution opportunity: redesign task relation types —
      current set conflates hierarchy, sequencing, state, and provenance
      into a single attribute
