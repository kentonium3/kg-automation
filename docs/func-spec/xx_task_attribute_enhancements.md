---
title: "FUTURE: Task Attribute Enhancements — Eisenhower Matrix and Friction Level"
doc_type: func-spec
status: draft
---

# FUTURE: Task Attribute Enhancements — Eisenhower Matrix and Friction Level

**Status**: Concept stub — not yet scheduled in the F-series
**Captured**: 2026-04-06
**Context**: Emerged from main agent SOUL.md authoring session; friction taxonomy
developed in collaboration with Gemini using neuroscience frameworks

---

## Concept

Two additional task attributes to surface meaningful signals about how Kent
is allocating attention and whether tasks are pushing him toward growth.

---

## Attribute 1: Eisenhower Quadrant

The **Eisenhower Matrix** classifies tasks on two axes:

| | **Urgent** | **Not Urgent** |
|---|---|---|
| **Important** | Do first | Schedule |
| **Not Important** | Delegate | Eliminate |

Assigning a quadrant forces the question of whether a task is actually important
vs. merely urgent or convenient. A portfolio skewed toward "urgent/not important"
is a signal of reactive mode. A portfolio weighted toward "important/not urgent"
is a signal of strategic mode.

**Implementation approach**: Four Vikunja labels (one per quadrant) plus saved
filters to surface distribution. No custom fields needed.

**Label convention**: `q:do`, `q:schedule`, `q:delegate`, `q:eliminate`

**Open questions**:
- Should the agent infer the quadrant from task content and confirm, or always
  ask explicitly?
- What is the right reporting cadence for quadrant distribution feedback?

---

## Attribute 2: Friction Level (Neuroscience-Grounded Taxonomy)

### Background

This taxonomy is grounded in neuroscience frameworks — specifically the
Three-Ring Model (Comfort/Stretch/Stress zones), the Yerkes-Dodson Law
(arousal and performance), and research on the Anterior Mid-Cingulate Cortex
(aMCC) — the brain structure associated with tenacity and will, which grows
in size when people do things they don't want to do.

The core insight: discomfort is not a side effect of growth — it is the
mechanism. The visceral urge to avoid a Level 3 task is the exact moment the
aMCC is being challenged. Every push-through is a physical remodeling of the
brain.

### The Four-Level Friction Taxonomy

| Level | Name | Neural Context | User Experience |
|---|---|---|---|
| **1** | **Maintenance** | Basal ganglia (autopilot) | Routine, low energy, zero friction. Safe but neuroplasticity is dormant. |
| **2** | **The Stretch** | Neuroplastic induction (LTP) | Moderate resistance; requires focus; feels productive. This is where growth happens. |
| **3** | **High Friction** | Limbic Rub (aMCC activated) | Visceral urge to avoid; feels threatening or heavy. High norepinephrine. The most valuable zone. |
| **4** | **Redline** | Amygdala hijack | Cognitive paralysis, fog, shutdown. Prefrontal cortex offline. Requires task decomposition — not execution. |

**Implementation approach**: Four Vikunja labels plus saved filters.

**Label convention**: `f:1-maintenance`, `f:2-stretch`, `f:3-friction`, `f:4-redline`

### Daily Target

- **Level 3: minimum one per day.** This is the primary accountability signal.
  A day without a Level 3 task is a day without aMCC exercise.
- **Level 4: decompose immediately.** If a task stays at Level 4, the agent
  should prompt deconstruction into Level 2/3 sub-tasks before scheduling.
- **Level 1: maintain baseline.** Necessary but not sufficient. A task list
  dominated by Level 1 is a signal of drift.

### Agent Directive for Avoidance

When Kent stalls on a Level 3 task:
- Suggest the **10-Minute Friction Gap**: commit to just 10 minutes to lower
  the entry barrier and quiet the amygdala's threat response
- Apply the **Minimum Viable Action (MVA)** if fully paralyzed: "open the file
  and write one sentence"
- Never penalize a missed task with more work — shame is a high-cortisol state
  that strengthens the avoidance habit

---

## Attribute 3 (Future Consideration): Recovery Score

Gemini's framework also surfaced a **Recovery Score** — a 1–5 daily metric
for whether Kent recovered as hard as he worked. High-friction output without
deliberate recovery leads to avoidance rebound (the brain's forced recovery
via procrastination or lethargy).

Recovery protocols include:
- **Optic Flow** (post Level 3): 5-minute walk, lateral eye movement, quiets
  the amygdala
- **NSDR / Yoga Nidra** (post Level 3): 10–20 minutes, clears norepinephrine,
  resets for another friction bout
- **Victory Lap Log**: immediately after Level 3 completion, note one thing
  that went well — triggers dopamine, buffers norepinephrine, reinforces
  self-image shift
- **Sleep**: primary mechanism for synaptic consolidation — where the day's
  Level 3 work becomes hard-wired into the new self

**Note**: Recovery Score is a future consideration, likely part of the daily
briefing or a dedicated reflection prompt, not a Vikunja task attribute.

---

## Interaction Between Attributes

The most valuable work sits at the intersection:

| Eisenhower | Friction | Signal |
|---|---|---|
| Important + Not Urgent | Level 3 | Highest-value work — strategic, hard, not screaming for attention. The work most likely to be avoided. |
| Urgent + Important | Level 2–3 | Crisis mode — valuable but reactive |
| Not Important + Urgent | Level 1 | Noise disguised as necessity |
| Not Important + Not Urgent | Level 1 | Eliminate |

A combined saved filter for **Important + Not Urgent + Level 3** is the single
most important view in the system — it surfaces the work that matters most
and is most likely to be deferred.

---

## Guiding Principle for Felix

> *"Growth is not linear, but action can be. Kent is not just completing tasks;
> he is starving the old avoidance self of neural reinforcement and physically
> remodeling his brain through voluntary hardship."*

Felix should never make it easy to avoid what is difficult. The role is to
surface reality clearly — not to make it comfortable.

---

## Dependencies

Both attributes require updates to:
- `scripts/openclaw/skills/task-intelligence/SKILL.md` — add friction level
  inference, the 10-minute friction gap logic, MVA fallback, and Eisenhower
  quadrant assignment
- Vikunja label setup — add friction and quadrant labels via API or UI
- Vikunja saved filters — add filters for each level and quadrant, plus the
  combined Important+Not Urgent+Level 3 filter
- Daily briefing agent — surface friction distribution and whether a Level 3
  task was tackled today
- Main agent SOUL.md — already updated with the discomfort/growth context that
  motivates this taxonomy

Depends on F013 (task intelligence) being stable before building on top of it.

---

## Source Reference

The friction taxonomy and recovery protocols in this stub were developed in a
Gemini research conversation on 2026-04-06, drawing on:
- The Three-Ring Model (Comfort/Stretch/Stress zones)
- The Yerkes-Dodson Law
- Anterior Mid-Cingulate Cortex (aMCC) research on tenacity
- Cognitive Load Theory

---

**END OF STUB**
