---
work_package_id: WP06
title: Calendar-clarification process-flow doc (discoverable)
dependencies:
- WP03
- WP05
requirement_refs:
- FR-007
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
agent: claude
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: curator-carla
authoritative_surface: docs/design/process-flows/
create_intent:
- docs/design/process-flows/calendar-clarification.md
execution_mode: code_change
owned_files:
- docs/design/process-flows/calendar-clarification.md
- docs/design/architecture/data/signal-to-doc-map.json
- docs/INDEX.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

Adopt its identity, governance scope, and boundaries before reading further.

## Objective

Document the **calendar-clarification user process flow** and its operating rules as
a canonical, discoverable design doc, so future missions find current-state behavior
here instead of spelunking prior `kitty-specs/` missions (the exact pain #780 hit).
This is the **exemplar** for #794's systemic back-fill of all process-flow docs.

## Context

- The flow spans several prior missions — credit them, don't reinvent: forced
  clarification = locked #739 decision; the pending-clarification state file + timeout
  = `inbox-calendar-and-aspiration-routing-01KTHHXS` FR-007; atomic finalize = #746;
  all-day helper = #786; the all-day fallback + 8h window = **this** mission (#780).
- This WP depends on WP03 (implemented behavior) + WP05 (the wired invocation) so the
  doc reflects shipped reality, not just intent.
- Related follow-up: **#794** (systemic: a convention + machine-discovery home for all
  process-flow docs). This doc establishes the reusable shape #794 generalizes.

## Subtasks

### T017 — Author the process-flow doc

**File**: `docs/design/process-flows/calendar-clarification.md` (new; create the dir)

Document, as a Divio *explanation/reference* (current-state, not a runbook):
1. **Actors + trigger**: capture agent tick; an inbox note classified as a calendar
   event with a resolved date but no time.
2. **Flow + states**: capture → `validate_calendar_event` → (complete → timed create)
   / (start-time missing → record pending clarification + **ask** Kent) → **8h
   window** → answered (timed create) / **unanswered**: eligible → **all-day event**
   (age-out create) / ineligible → **delete-and-release** (re-scan).
3. **Operating rules / invariants** (cite the FR/INV IDs from this mission's spec):
   ask-first (never pre-empt, C-005); 8h whole-window (C-006); timing-only-gap
   eligibility (FR-005); idempotent + atomic via #746 (FR-004); fail-closed +
   reconcile (FR-008/009); deterministic, no LLM on the sweep path (NFR-001);
   date-fidelity/no-week-drift (INV-5); distinct observability marker (FR-007/C-007).
4. **Implementing seams** (file references, kept current): `validate_calendar_event`,
   `route_calendar_event`, `route_and_finalize`, `clarification_sweep_finalize`,
   `handle_clarification_state`, and the `felix-admin-capture` AGENTS.md steps.
5. A small **state diagram** (Mermaid preferred per the docs standards).

### T018 — Register for machine + human discovery

1. **`docs/design/architecture/data/signal-to-doc-map.json`**: add an entry (or
   entries) so relevant change classes (calendar-flow / inbox-routing changes) route
   missions to this doc. Match the existing schema exactly (read neighboring entries
   first; the file is validated by the blocking architecture-data validator —
   [[reference_architecture_data_validator]] — so keep it schema-valid).
2. **`docs/INDEX.md`**: add the doc under the appropriate group with its Divio type
   annotation, so humans discover it from the master index.

### T019 — Cross-link + establish the reusable shape

1. Cross-link the doc to #780 (source), #794 (systemic follow-up), and the prior
   missions it consolidates (#739, FR-007 mission, #746, #786).
2. Note at the top that this doc's **shape** (actors / trigger / states / operating
   rules+invariants / seams / diagram) is the template #794 will reuse for the other
   flows (inbox routing, someday, journal, habits).

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree per computed lane in `lanes.json`.

## Definition of Done

- [ ] `docs/design/process-flows/calendar-clarification.md` exists with actors/trigger/states/rules+invariants/seams/diagram, citing this mission's FR/INV IDs and crediting the prior missions.
- [ ] `signal-to-doc-map.json` routes the relevant change classes to the doc; the architecture-data validator passes (`make test` / pre-commit green).
- [ ] `docs/INDEX.md` lists the doc with its Divio type.
- [ ] A fresh agent, given only INDEX + signal-to-doc-map, can find and read the current-state rules without opening any `kitty-specs/` mission.
- [ ] The reusable-shape note for #794 is present.

## Risks / reviewer guidance

- **Accuracy over prose**: the doc must match shipped behavior (8h, timing-only eligibility, reconcile/fail-closed) — reviewer cross-checks against WP03.
- **Schema validity**: the `signal-to-doc-map.json` edit must pass the blocking validator — reviewer runs it.
- **No duplication drift**: the doc is the canonical explanation; runbooks/TOOLS.md (WP05) link to it rather than restating the rules.
