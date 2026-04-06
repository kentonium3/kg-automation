---
title: "TEMPLATE: Spec-Kitty Research Mission Input"
doc_type: reference
status: approved
---

# TEMPLATE: Spec-Kitty Research Mission Input

**Version**: 1.0
**Date**: 2026-04-06
**Purpose**: Standard format for research mission inputs to the spec-kitty workflow

---

## About This Template

This template defines the standard format for research mission specifications that
serve as inputs to `/spec-kitty.specify --mission research`. It is the companion
to `_TEMPLATE_spec_kitty_input.md`, which covers `software-dev` missions.

Research missions use a different step sequence and produce different artifacts
than software-dev missions. This template is structured accordingly.

### The Research Mission Workflow

```
scoping --> methodology --> gathering <--> synthesis --> output --> done
  ↓              ↓              ↓              ↓           ↓
(WHAT &       (HOW we       (collect       (analyze    (findings.md
 WHY)          gather)       evidence)      evidence)   + decision)
```

The `gathering ↔ synthesis` loop is intentional — spec-kitty allows returning
to gathering after an initial synthesis pass if the evidence is insufficient.

**Required artifacts spec-kitty will produce:**
- `spec.md` — scoping document (this input becomes its source)
- `plan.md` — methodology plan
- `tasks.md` — evidence-gathering work packages
- `findings.md` — synthesis and conclusions
- `source-register.csv` — tracked sources
- `evidence-log.csv` — evidence items linked to research questions

### Key Principles

**Focus on WHAT to learn and WHY it matters:**
- State the research questions precisely
- Explain what decision the research informs
- Define what "sufficient evidence" looks like
- Point to known sources worth examining
- **Let spec-kitty methodology phase determine HOW to gather**

**Trust the Research Mission Guards:**
```
scoping → methodology    requires: spec.md exists
methodology → gathering  requires: plan.md exists
gathering → synthesis    requires: ≥3 sources documented
synthesis → output       requires: findings.md exists
output → done            requires: publication approved
```

**What NOT to Include:**
- ❌ Predetermined conclusions (research must remain open)
- ❌ Implementation instructions (this is not a software-dev mission)
- ❌ Specific commands or API calls to run (methodology phase determines this)
- ❌ Time estimates (tasks phase handles this)
- ❌ File lists to modify (no implementation in research missions)
- ❌ A prescribed answer to the research question

---

## Template Structure

```markdown
# FXXX: [Research Topic]

**Version**: 1.0
**Priority**: [HIGH | MEDIUM | LOW]
**Mission type**: research
**Informs**: [Feature or decision this research feeds into]

---

## Research Purpose

[2-3 sentences: what gap in knowledge this research fills and what
decision it enables. Why is this research needed now?]

**Decision gate**: This research must be complete before [FXXX / decision D0X]
can proceed. The current blocker is: [specific unknown].

---

## Research Questions

These are the questions the research must answer. Findings must address
each one. Questions are ordered by dependency — later questions may build
on answers to earlier ones.

### RQ-1: [Primary question]

[1-2 sentences expanding on what specifically needs to be understood and why.]

**Acceptable answer form**: [Describe what a good answer looks like —
e.g., "a ranked comparison of options against defined criteria" or
"a yes/no determination with supporting evidence" or "a recommended
approach with documented rationale"]

---

### RQ-2: [Secondary question]

[1-2 sentences expanding on the question.]

**Acceptable answer form**: [Describe what a good answer looks like]

**Depends on**: RQ-X [if this question can only be answered after another]

---

[Repeat RQ-X pattern. Aim for 3–6 questions. More than 6 suggests the
scope is too broad — consider splitting into two research missions.]

---

## Known Sources

Point the gathering phase toward sources worth examining. These are
starting points, not an exhaustive list — the methodology phase may
identify additional sources.

### Internal sources (examine first)

- [File path or system component] — [what it reveals about RQ-X]
- [File path or system component] — [what it reveals about RQ-X]
- [Live system / SSH target] — [what queries or reads are relevant]

### External sources

- [URL or reference] — [what it covers and which RQ it informs]
- [URL or reference] — [what it covers and which RQ it informs]

### Sources to approach with caution

- [Source] — [why it may be biased, outdated, or incomplete]

---

## Evaluation Criteria

When multiple options or approaches are under evaluation, define the
criteria the research should use to compare them. This prevents the
synthesis phase from comparing options arbitrarily.

| Criterion | Weight | Description |
|-----------|--------|-------------|
| [Criterion 1] | High / Medium / Low | [What this measures and why it matters] |
| [Criterion 2] | High / Medium / Low | [What this measures and why it matters] |
| [Criterion 3] | High / Medium / Low | [What this measures and why it matters] |

*Remove this section if the research is not comparative (e.g., purely
descriptive or a single yes/no question).*

---

## Scope

### In scope

- [Specific area, technology, or system included]
- [Specific area, technology, or system included]

### Out of scope

- ❌ [Topic explicitly excluded — and why]
- ❌ [Topic explicitly excluded — and why]
- ❌ [Implementation work — research missions do not produce code or config]

---

## Expected Outputs

These are the deliverables `findings.md` must contain for the research
to be accepted. They map directly to the research questions.

| Output | Answers | Description |
|--------|---------|-------------|
| [Deliverable 1] | RQ-1 | [What this contains and how it will be used] |
| [Deliverable 2] | RQ-2, RQ-3 | [What this contains and how it will be used] |
| [Recommendation] | All | [The synthesized recommendation and its rationale] |

**Downstream use**: The findings from this research will be consumed by:
- [FXXX spec] — [which outputs feed which sections of the spec]
- [Decision DXX] — [which outputs resolve which open decision]

---

## Constraints

Constraints the research must respect. These are not methodology
preferences — they are hard boundaries.

- [Constraint 1 — e.g., read-only access to live system during research]
- [Constraint 2 — e.g., must be compatible with existing architecture decisions]
- [Constraint 3 — e.g., cost or licensing constraints on options evaluated]

---

## Success Criteria

Research is complete when:

### Evidence
- [ ] All research questions have findings with cited sources
- [ ] At least [N] independent sources consulted
- [ ] Conflicting evidence documented and reconciled

### Findings
- [ ] `findings.md` addresses every RQ with supported conclusions
- [ ] Each evaluation criterion has evidence for each option assessed
- [ ] Gaps or unknowns explicitly called out rather than silently omitted

### Recommendation
- [ ] A clear recommendation is stated (not just a summary of evidence)
- [ ] Rationale maps recommendation to evaluation criteria
- [ ] Risks or caveats to the recommendation are documented

### Downstream readiness
- [ ] [FXXX] spec can be written without further unknowns
- [ ] [Decision DXX] can be resolved using findings

---

## Notes for Methodology Phase

Discovery pointers — WHERE to look, not HOW to interpret findings.
The methodology phase determines the gathering strategy; these notes
help it start efficiently.

- [Pointer to relevant existing pattern or prior work]
- [Pointer to where the live system state can be inspected]
- [Pointer to any prior research or decisions that constrain the question]

---

**END OF SPECIFICATION**
```

---

## Section Descriptions

### Research Purpose
**Purpose**: Orients the research mission — what knowledge gap it fills and what
decision it unblocks.
**Key**: State the specific blocker. "We don't know enough about X" is weak.
"We cannot write the F019 spec until we know whether Y supports Z" is strong.

### Research Questions (RQ-X)
**Purpose**: The questions the research must answer. These become the organizing
structure for `findings.md`.
**Key**: Each RQ must be answerable in principle. "What is the best approach?" is
too vague. "Does Vikunja's native recurring task model preserve comment history
across recurrence cycles?" is answerable.
**Acceptable answer form**: Specify this so the synthesis phase knows what
"done" looks like for each question. A yes/no question has a different answer
form than a ranked comparison.

### Known Sources
**Purpose**: Discovery pointers for the gathering phase.
**Key**: Internal sources first — live system, existing docs, prior research.
External sources second — docs, community forums, issue trackers.
Do NOT prescribe specific API calls or commands; point to where the methodology
phase will find them.

### Evaluation Criteria
**Purpose**: Defines how options are compared when the research is evaluating
alternatives. Prevents arbitrary synthesis.
**Key**: Only include this section for comparative research. Assign weights
(High/Medium/Low) — not numeric scores — to keep it lightweight.
**Omit** if the research is purely descriptive or has a single yes/no question.

### Scope
**Purpose**: Hard boundaries on what the research covers.
**Key**: "Out of scope" is as important as "in scope." Explicitly exclude
adjacent topics that could expand the gathering phase indefinitely.
Always exclude implementation work — research missions do not produce code.

### Expected Outputs
**Purpose**: Maps research questions to `findings.md` deliverables.
**Key**: Every RQ must map to at least one output. If you cannot describe what
a good answer looks like, the question is not well-formed.
**Downstream use**: State explicitly what consumes the findings — a feature spec,
an open decision, or both. This keeps the research grounded in utility.

### Constraints
**Purpose**: Hard boundaries on HOW the research is conducted.
**Key**: Distinguish constraints (hard limits) from preferences (methodology
suggestions). "Read-only on the live system" is a constraint. "Prefer official
docs over community forums" is a preference — put it in Notes, not Constraints.

### Success Criteria
**Purpose**: The acceptance gate for the research mission.
**Key**: Must include downstream readiness criteria — research is only done when
the thing it was meant to unblock is actually unblocked.

### Notes for Methodology Phase
**Purpose**: Efficiency hints for the gathering phase.
**Key**: Discovery pointers only. Never prescribe specific commands, queries,
or interpretation guidance. If you find yourself writing a curl command — stop.

---

## Writing Guidelines

### DO ✅

**State research questions precisely:**
- "Does Vikunja's native recurring task model preserve comment history
  across recurrence cycles?"
- "What API endpoints support querying task completion history by date range?"
- "Which of the three candidate approaches satisfies all five evaluation criteria?"

**Define acceptable answer forms:**
- "A yes/no determination with a documented API response as evidence"
- "A ranked comparison table mapping each option against the evaluation criteria"
- "A single recommended approach with rationale"

**Point to sources without prescribing methodology:**
- "Inspect habit tasks 14–20 in the live Vikunja instance"
- "Consult Vikunja API docs at [URL]"
- "Study existing agent AGENTS.md for context on current behavior"

**Set clear downstream gates:**
- "F009 implementation spec can proceed once RQ-3 is answered"
- "Decision D07 can be resolved using the recommendation from this research"

**Scope tightly:**
- "Out of scope: implementation of the recommended approach — that is F009"
- "Out of scope: evaluation of non-Vikunja task management tools"

### DON'T ❌

**Don't presuppose conclusions:**
- ❌ "Confirm that native recurring tasks are the right approach"
- ✅ "Evaluate whether native recurring tasks satisfy the evaluation criteria"

**Don't include implementation instructions:**
- ❌ "Create a daily task for each habit using the Vikunja API"
- ✅ Research missions produce findings, not implementation artifacts

**Don't prescribe methodology:**
- ❌ "Run `curl GET /api/v1/tasks/14` to check the due_date field"
- ✅ "Inspect the current state of habit tasks in the live system"

**Don't write open-ended questions:**
- ❌ "What are Vikunja's recurring task capabilities?"
- ✅ "Does Vikunja's recurring task model support a 'skipped' completion state?"

**Don't omit the downstream use:**
- ❌ Research that produces findings with no stated consumer
- ✅ "Findings feed directly into the F009 revised implementation spec"

---

## Common Patterns

### Pattern: Technology Evaluation Research

```markdown
## Research Purpose

We need to choose between [Option A] and [Option B] before [FXXX] can be
specced. The specific unknown is whether [Option A's claimed capability]
actually works as documented in our context.

### RQ-1: Does [Option A] support [required capability]?

Determine whether [Option A]'s native [feature] satisfies [specific requirement].

**Acceptable answer form**: Yes/no with documented evidence from official
source or live system inspection.

### RQ-2: How does [Option A] compare to [Option B] against our criteria?

**Acceptable answer form**: Comparison table mapping each option against
the evaluation criteria defined in this spec.
```

### Pattern: Architecture Decision Research

```markdown
## Research Purpose

[FXXX] spec deferred the choice of [architectural pattern] to the planning
phase. That deferral was incorrect — the choice affects the spec itself.
This research resolves the decision before F-series implementation begins.

### RQ-1: What does [system X] actually do when [condition Y] occurs?

[Specific behavior to verify against actual system behavior, not documentation.]

**Acceptable answer form**: Observed behavior documented with evidence
(API response, log output, or behavior description from live system).
```

### Pattern: Feasibility Research

```markdown
## Research Purpose

Before committing to [capability], we need to confirm it is feasible
within the constraints of [existing system]. The specific risk is
[specific concern].

### RQ-1: Is [capability] feasible given [constraint]?

**Acceptable answer form**: Feasibility determination (feasible /
feasible with workaround / not feasible) with supporting evidence.

### RQ-2: If feasible, what is the recommended implementation approach?

**Acceptable answer form**: A recommended approach with rationale.
Only answer this if RQ-1 concludes feasible.

**Depends on**: RQ-1
```

---

## Checklist for Research Spec Authors

Before submitting to spec-kitty, verify:

### Structure
- [ ] Research Purpose states the specific decision blocker
- [ ] 3–6 RQ-X sections, each with an acceptable answer form
- [ ] Known Sources section with internal sources listed first
- [ ] Evaluation Criteria present if research is comparative (omit if not)
- [ ] Scope section with explicit out-of-scope items
- [ ] Expected Outputs table with downstream use documented
- [ ] Constraints section with hard limits only
- [ ] Success Criteria including downstream readiness
- [ ] Notes for Methodology Phase with discovery pointers

### Content Quality
- [ ] Each RQ is answerable in principle (not vague or open-ended)
- [ ] No predetermined conclusions embedded in question framing
- [ ] Sources are pointers, not methodology prescriptions
- [ ] Evaluation criteria are specific enough to compare against
- [ ] Out of scope explicitly excludes implementation work
- [ ] Downstream consumer (feature spec or decision) named

### What's NOT Included
- [ ] No implementation instructions or code
- [ ] No prescribed methodology steps or specific commands
- [ ] No time estimates
- [ ] No presupposed conclusions
- [ ] No file modification lists

---

## Relationship to Software-Dev Template

| Aspect | software-dev input | research input |
|--------|-------------------|----------------|
| Core unit | Functional Requirement (FR-X) | Research Question (RQ-X) |
| "Study these files" | Pattern discovery for implementation | Known sources for gathering |
| Success criteria | Tests pass, features work | Findings complete, decision unblocked |
| Primary output | Working code | `findings.md` + recommendation |
| Out of scope | Features deferred | Topics deferred + no implementation |
| Feeds into | Acceptance + merge | Software-dev spec or open decision |

Research missions frequently feed directly into software-dev missions.
The standard pattern in this project:

```
Research mission → findings.md → revised software-dev spec → implementation
```

When this pattern is used, the research spec's "Expected Outputs" section
should explicitly state which sections of the downstream software-dev spec
the findings will populate.

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-06 | Initial version — companion to software-dev template |

---

**END OF TEMPLATE**
