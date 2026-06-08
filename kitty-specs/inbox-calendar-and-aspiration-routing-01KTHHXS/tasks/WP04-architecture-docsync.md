---
work_package_id: WP04
title: Architecture JSON + narrative doc-sync
dependencies: []
requirement_refs:
- FR-011
tracker_refs: []
planning_base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
merge_target_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
base_commit: 78f19de6c05bbcf8d39fcd4217d4c018aa7b8327
created_at: '2026-06-08T10:32:20.877141+00:00'
subtasks:
- T020
- T021
- T022
- T023
agent: "claude:opus-4-7:reviewer-renata:reviewer"
shell_pid: "34375"
history: []
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data/signal-to-doc-map.json
role: curator
tags: []
---

# WP04: Architecture JSON + narrative doc-sync

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Update the canonical architecture inventories in `docs/design/architecture/data/` (service-inventory.json, data-flows.json, signal-to-doc-map.json) and the narrative `docs/design/architecture/data-flows.md` to reflect this mission's new capabilities and data flows. Per Felix Constitution DIR-005, these updates must land in the same merge as the code/prompt changes — not as a follow-up. This WP runs in parallel with WP01 (no code dependency on the other WPs).

## Context

- **Authority docs**: `spec.md` § Documentation Synchronization Requirement; CLAUDE.md (project) "Standing requirement" about doc-sync; memory `feedback_migration_no_vestiges.md` and `feedback_architecture_docs_first.md`.
- **Correction from plan-phase mis-naming (caught by finalize-tasks --validate-only on 2026-06-07)**: there is NO separate `docs/design/architecture/data/agent-inventory.json` and NO `docs/design/architecture/agents.md`. Agents are catalogued **inside** `service-inventory.json` (alongside other services), and the canonical narrative for inbox / classification flows lives in `data-flows.md`. The spec and plan documents reference `agent-inventory.json` and `agents.md` in error — this WP normalises the correction.
- **Canonical machine-readable artifacts** in `docs/design/architecture/data/`: `service-inventory.json` (services + agents + their consumers/providers), `data-flows.json` (cross-service flows), `credential-manifest.json`, `mutation-surfaces.json`, `network-topology.json`, `hardware-inventory.json`, `signal-to-doc-map.json` (change_class → doc_targets routing).
- **The signal-to-doc map**: `docs/design/architecture/data/signal-to-doc-map.json` enumerates which docs to touch for which change_class. For this mission:
  - `change_class: service-modified` → affects `service-inventory.json` + `data-flows.md` (narrative)
  - `change_class: data-flow-added-or-modified` → affects `data-flows.json` + `data-flows.md`
  - Verify by reading the map's entries for those classes; extend the `doc_targets` arrays if any new doc surface is added.
- **Schema discipline**: existing JSONs have schemas (often inferred by the `validate_docs.py` validator). Treat existing structures as authoritative — don't introduce new top-level keys without operator approval.
- **Cross-references**: `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` may need updates if a new doc surface is added; for this mission they likely don't (no new runbooks, no new narrative sections).

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP04 --agent <name>` (no code dependencies; parallelizable with WP01)
- No dependencies — this WP starts immediately and can complete before WP02/WP03 finish.

---

## Subtask T020: Update service-inventory.json [P]

**Purpose**: Reflect the expanded capabilities of `felix-admin-capture` (new routing destinations) and Felix `main` (new calendar-delegation receiver + clarification-reply handler). Update gog's `used_by` to reflect the new consumer relationship via capture-through-main delegation.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json` end-to-end first — agents and services are catalogued in the same array; capability/role fields vary by entry type. Take the existing structure as canonical.
2. Locate the `felix-admin-capture` entry. Extend its `capabilities` (or equivalent — likely `purpose`, `responsibilities`, or a sub-array) with the new routing destinations:
   - `"Classify and route calendar events to Google Calendar via Felix main delegation"`
   - `"Classify and route aspirations to dated journal entries"`
   - `"Classify and route Someday items to Vikunja Someday project"`
   - `"Maintain pending-calendar-clarifications state file with 24h timeout sweep"`
3. Locate the `main` (or `felix-main`) entry. Extend with:
   - `"Receive calendar-create delegation from felix-admin-capture; execute via gog calendar create"`
   - `"On inbound WhatsApp, resolve open calendar clarifications from pending-calendar-clarifications state file"`
4. Locate the `gog` service entry (research R-001 confirms its presence). Update its `used_by` (or notes) to add `felix-admin-capture (via main delegation; calendar events from inbox)`. If the entry currently says "consumed by any Felix agent" in narrative, leave that prose intact and add the explicit consumer entry.
5. Update each modified entry's `last_modified` (if the schema has it) to today's ISO date.
6. Run `python tooling/scripts/validate_docs.py` from repo root to confirm schema validity.

**Files**:
- `docs/design/architecture/data/service-inventory.json`

**Validation**:
- [ ] `felix-admin-capture` entry has 4 new capability strings (or equivalent under the actual schema field)
- [ ] `main` entry has 2 new capability strings
- [ ] `gog` entry's consumer list reflects the new flow
- [ ] `validate_docs.py` passes
- [ ] JSON parses (no syntax errors)
- [ ] Existing fields in all three entries are preserved verbatim (only additions, no deletions)

---

## Subtask T021: Update data-flows.json [P]

**Purpose**: Document the three new data flows introduced by this mission.

**Steps**:
1. Read `docs/design/architecture/data/data-flows.json`. Examine the existing structure (likely an array of flow entries with `id`, `source`, `destination`, `intermediaries`, `purpose`, etc. — adapt to the actual schema).
2. Add three new flow entries:
   - **Flow A — Inbox → Capture → Felix main → gog → Google Calendar (one-off and recurring)**
     - source: `Obsidian inbox note (WisprFlow or typed)`
     - intermediaries: `felix-admin-capture (classification + validator)` → `main (gog calendar create)`
     - destination: `Google Calendar (kent@intentional.biz primary, or override per payload)`
     - purpose: `Auto-schedule events submitted via inbox capture without creating Vikunja todos`
   - **Flow B — Inbox → Capture → WhatsApp clarification → Kent reply → main → gog → Google Calendar**
     - source: `Obsidian inbox note (incomplete calendar event)`
     - intermediaries: `felix-admin-capture (incomplete classification + state-file write + WhatsApp prompt)` → `Kent WhatsApp reply` → `main (read state file + field merge + re-validate + gog create)`
     - destination: `Google Calendar`
     - purpose: `Resolve incomplete calendar events through a single WhatsApp reply round-trip without losing context`
   - **Flow C — Inbox → Capture → 08-Journal**
     - source: `Obsidian inbox note (aspiration / musing)`
     - intermediaries: `felix-admin-capture (classification + journal write)`
     - destination: `~/second-brain/notes/08-Journal/Journal YYYY-MM-DD HHmm.md`
     - purpose: `Route aspirations and musings to the dated journal instead of Vikunja todos`
3. Mark each flow with `feature: F<XXX>` if the schema supports it; otherwise omit. (This mission's feature number is assigned at merge time.)
4. Run `validate_docs.py` to confirm.

**Files**:
- `docs/design/architecture/data/data-flows.json`

**Validation**:
- [ ] 3 new flow entries present
- [ ] Each entry has source, intermediaries, destination, purpose
- [ ] `validate_docs.py` passes
- [ ] Existing flows preserved verbatim

---

## Subtask T022: Update data-flows.md narrative [P]

**Purpose**: Update the narrative `docs/design/architecture/data-flows.md` to describe the three new flows in human-readable form. This is the narrative counterpart to T021's JSON additions.

**Steps**:
1. Read `docs/design/architecture/data-flows.md` end-to-end first. Identify the section structure (likely organized by capability area or by source).
2. Add narrative for each of the three new flows. Suggested placement: append a section "Inbox classification and calendar routing" (or extend the existing inbox section) covering:
   - The capture agent's expanded classifier vocabulary (calendar / aspiration / Someday in addition to existing destinations)
   - The delegation pattern from capture to Felix main for calendar writes
   - The clarification reply loop via WhatsApp + the pending-calendar-clarifications state file
   - The aspiration → journal flow
3. Keep prose terse and reference-driven; do not duplicate the JSON content.
4. Reference each flow's entry in `data-flows.json` by id.
5. If a `data-flows.view.md` (Mermaid diagram) sibling exists, consider whether the diagram needs updates. Edit only if the existing diagram covers inbox flows and is now incomplete.

**Files**:
- `docs/design/architecture/data-flows.md`
- (optional, if relevant) `docs/design/architecture/data-flows.view.md`

**Validation**:
- [ ] Narrative section for inbox classification + calendar routing present
- [ ] Each new JSON flow entry has a narrative counterpart (referenced by id)
- [ ] No conflicts with existing flow descriptions
- [ ] `validate_docs.py` passes (validator may include narrative-validity checks)

---

## Subtask T023: Update signal-to-doc-map.json + verify INDEX/Portal cross-refs

**Purpose**: Ensure the canonical signal-to-doc map captures this mission's change-class footprint so future agents authoring specs will surface the same docs (per memory `feedback_signal_driven_doc_audit` and `feedback_architecture_docs_first`). Verify the cross-references in `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` still point at real files.

**Steps**:
1. Read `docs/design/architecture/data/signal-to-doc-map.json`. Locate entries with `change_class: service-modified` and `change_class: data-flow-added-or-modified`. Examine their `doc_targets` arrays.
2. Verify `doc_targets` for `service-modified` includes:
   - `docs/design/architecture/data/service-inventory.json`
   - `docs/design/architecture/data-flows.md` (if service changes typically need narrative updates per existing convention)
3. Verify `doc_targets` for `data-flow-added-or-modified` includes:
   - `docs/design/architecture/data/data-flows.json`
   - `docs/design/architecture/data-flows.md`
   - `docs/design/architecture/data-flows.view.md` (if it exists and is in the existing map)
4. If any target is missing, add it. If a target points at a file that does not exist (e.g., a stale `agent-inventory.json` reference), correct the entry or open a separate cleanup follow-up issue.
5. Read `docs/INDEX.md`. Verify that the architecture data JSONs and narrative MDs being touched by this mission are listed. They likely already are — INDEX changes are likely none.
6. Read `docs/DEVELOPER_PORTAL.md`. Verify analogous cross-references.
7. Run `python tooling/scripts/validate_docs.py` to confirm cross-references resolve.

**Files**:
- `docs/design/architecture/data/signal-to-doc-map.json`
- Possibly `docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md` (only if updates needed)

**Validation**:
- [ ] `signal-to-doc-map.json` doc_targets for `service-modified` and `data-flow-added-or-modified` are accurate (target files exist)
- [ ] INDEX and Developer Portal cross-references still accurate
- [ ] No `agent-inventory.json` or `agents.md` references remain anywhere in the map (or if they do, they're noted as gaps and filed as a separate cleanup issue)
- [ ] `validate_docs.py` passes against the full set of edits

---

## Definition of Done

- [ ] All 4 subtasks complete with their per-subtask validation items checked.
- [ ] `validate_docs.py` exits cleanly against the full set of doc edits.
- [ ] No uncommitted changes outside this WP's `owned_files`.
- [ ] All three architecture JSONs remain syntactically valid and schema-conformant.
- [ ] Cross-references in INDEX / Portal remain accurate.

## Risks

1. **Schema strictness in validate_docs.py**: a small structural error (extra comma, mistyped field name) blocks the whole gate. Mitigation: run the validator after each subtask, not just at the end.
2. **Signal-to-doc map drift**: if this mission introduces a new change_class that the map doesn't cover, we miss a doc surface. Mitigation: T023 explicitly checks the map; flag any gap.
3. **`service-inventory.json` schema field names**: I used `capabilities` as the field name above (T020 step 2), but the actual schema may use a different name for agent capability lists (e.g., `purpose`, `responsibilities`, `description`). Mitigation: T020 step 1 says "Read end-to-end first" and step 2 explicitly says "or equivalent field". Reviewer verifies the implementer used the right schema field.

## Reviewer guidance

- Read each JSON diff in isolation — small structural errors are easy to miss in a multi-file diff.
- Run `validate_docs.py` yourself; do not trust the implementer's claim it passed.
- Verify the gog `used_by` (or notes) update on service-inventory.json — this is the doc-sync corollary of "gog now has a new consumer path".
- Cross-check the three data-flows.json entries against the spec's three flows in § Documentation Synchronization Requirement — they should match conceptually.
- Confirm `agents.md` narrative reads naturally — no awkward "as added by mission X" phrasings; treat the update as if it were always part of the document.

## Activity Log

- 2026-06-08T10:32:24Z – claude:opus-4-7:curator-carla:curator – shell_pid=28419 – Assigned agent via action command
- 2026-06-08T10:57:29Z – claude:opus-4-7:curator-carla:curator – shell_pid=28419 – Ready for review. Architecture doc-sync per DIR-005: felix-admin-capture + main agent purpose strings extended for calendar/aspiration/Someday routing + clarification reply loop; google-workspace notes records capture-via-main consumer; 3 new data-flows.json entries (inbox-calendar-create, inbox-calendar-clarification-loop, inbox-aspiration-to-journal); data-flows.md gets a new section referencing the 3 flow ids; signal-to-doc-map.json metadata bumped (existing service-added-or-modified and data-flow-added-or-modified entries already cover the touched docs — no stale agent-inventory.json or agents.md refs found). validate_docs.py exits 0. Commit 5a300103.
- 2026-06-08T10:58:26Z – claude:opus-4-7:reviewer-renata:reviewer – shell_pid=34375 – Started review via action command
