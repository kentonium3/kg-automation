# Feature Specification: Goal and Outcome Structure

**Feature Branch**: `006-goal-and-outcome-structure`
**Created**: 2026-03-29
**Status**: Draft
**Input**: F006 Goal and Outcome Structure — establish the foundational goal declaration system

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Define and Document Goal Declaration Format (Priority: P1)

Kent needs a single, canonical format for declaring goals that the entire Felix
system recognizes. The format — "On [date], I have [outcome] as evidenced by
[proof]" — must be documented in the Obsidian constitution (`01-Constitution/`)
with a template that makes the three required elements explicit and hard to omit.

**Why this priority**: Without a defined format, goals are just free-text
intentions. The format is the contract that all downstream features (capture,
evaluation, briefings, escalation) depend on. Everything else in F006 builds
on this.

**Independent Test**: Read `01-Constitution/Goals-MOC.md` and the goal
declaration template on office2. Verify the format is documented, the three
required elements are explicit, and at least one example declaration
demonstrates correct usage.

**Acceptance Scenarios**:

1. **Given** the Obsidian vault on office2, **When** Kent opens
   `01-Constitution/Goals-MOC.md`, **Then** the canonical goal declaration
   format is documented with all three required elements (date, present-tense
   outcome, observable evidence) and at least one example.
2. **Given** the documented format, **When** Kent writes a new declaration
   following the template, **Then** the template makes it easy to include all
   three elements and obvious when one is missing.
3. **Given** a declaration that uses future tense ("I will") or lacks a
   specific date, **Then** the template guidance makes it clear this is not
   a valid declaration.

---

### User Story 2 — Store Goals in Vikunja as Structured Records (Priority: P1)

Kent needs a dedicated place in Vikunja to store goal declarations as structured
records distinct from regular tasks. Each goal must carry: the full outcome
statement, the target date as the task due date, evidence criteria, and an
identity label (personal, intentional, or metalcasework). A saved filter must
show all active goals sorted by target date.

**Why this priority**: Vikunja is the machine-readable task store. Without
structured goal records, future automation (API skills, briefings, escalation)
has nothing to query against. This is co-equal with the format definition
because it makes goals actionable by the system.

**Independent Test**: Log into Vikunja web UI. Verify a Goals project exists
with at least one goal declaration task. Verify the task carries outcome
statement, due date, evidence criteria, and identity label. Verify the
"Goals" saved filter shows active goals sorted by target date. Verify
visibility on mobile via Tailscale.

**Acceptance Scenarios**:

1. **Given** the Vikunja instance, **When** Kent navigates to the Goals project,
   **Then** goal declarations are stored as tasks with outcome statement in the
   description, target date as due date, evidence criteria in the description,
   and an identity label applied.
2. **Given** multiple active goals with different target dates, **When** Kent
   opens the "Goals" saved filter, **Then** goals are displayed sorted by
   target date (nearest first).
3. **Given** a goal declaration without an identity label, **Then** the ops
   runbook clearly states this is invalid and must be corrected.
4. **Given** the Vikunja web UI accessed via Tailscale on mobile, **When** Kent
   opens the Goals filter, **Then** active goals are visible and readable.

---

### User Story 3 — Goals-MOC as Human-Readable Reference (Priority: P2)

`01-Constitution/Goals-MOC.md` in the Obsidian vault must become the
human-readable canonical reference for all active goal declarations. It must
be readable standalone — someone reading it should have a complete picture of
Kent's active declared outcomes. Future agents will read this file for goal
context.

**Why this priority**: P2 because it depends on the format (Story 1) and is
the human-facing complement to Vikunja (Story 2). It is the agent context
ceiling — future agents from F008 onward read Goals-MOC.md to understand
Kent's priorities.

**Independent Test**: Read `01-Constitution/Goals-MOC.md` on any synced device.
Verify it contains at least one real goal declaration in the standard format,
the structure is clean and extensible, and it is readable without needing to
cross-reference any other document.

**Acceptance Scenarios**:

1. **Given** the Obsidian vault, **When** Kent opens `01-Constitution/Goals-MOC.md`,
   **Then** it contains at least one real declared goal in the standard format
   ("On [date], I have [outcome] as evidenced by [proof]").
2. **Given** Goals-MOC.md with multiple goals, **Then** goals are organized
   clearly (by identity context or target date) and the structure supports
   adding more goals without restructuring.
3. **Given** a new goal is added to Vikunja, **Then** the ops runbook documents
   the requirement to also add it to Goals-MOC.md (manual sync until automated
   in a later feature).

---

### User Story 4 — Goals Operations Runbook (Priority: P2)

An ops runbook at `docs/handbooks/goals-ops.md` must document: the goal
declaration format, how to add a goal manually (both Vikunja and Obsidian),
how to close a goal when achieved, how to retire an abandoned goal, and what
constitutes a valid vs invalid declaration.

**Why this priority**: P2 because without operational documentation, the goal
system depends on tribal knowledge. The runbook ensures Kent can operate the
system without re-reading the spec.

**Independent Test**: Read `docs/handbooks/goals-ops.md`. Verify it covers all
five operations (format reference, manual add, close, retire, validation rules)
and is actionable without external context.

**Acceptance Scenarios**:

1. **Given** the runbook, **When** Kent wants to add a new goal, **Then** the
   runbook provides step-by-step instructions for both Vikunja and Goals-MOC.md.
2. **Given** a goal whose target date has passed and was achieved, **When** Kent
   follows the runbook's "close" procedure, **Then** the goal is marked complete
   in Vikunja and moved to an archive section in Goals-MOC.md.
3. **Given** a goal Kent decides to abandon, **When** he follows the "retire"
   procedure, **Then** the goal is clearly marked as retired (not just deleted)
   in both systems.

---

### Edge Cases

- What happens when a goal has no identity label? The system treats it as
  invalid. The ops runbook documents this; the Vikunja structure does not
  enforce it programmatically in F006 (enforcement comes with API skills in
  later features).
- What happens when Goals-MOC.md and Vikunja diverge? Until automated sync
  exists (later feature), the ops runbook documents the two-step manual process
  and the source-of-truth rules: Vikunja for state, Goals-MOC.md for narrative.
- What happens when a goal's target date passes without being achieved? The goal
  remains active in Vikunja (overdue). Kent decides whether to extend, retire,
  or close it. The system does not auto-retire.
- What happens when too many goals accumulate? The ops runbook advises periodic
  review and retirement. No system limit is imposed.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-001 | The canonical goal declaration format "On [date], I have [outcome] as evidenced by [proof]" MUST be documented in the Obsidian vault at `01-Constitution/` | Approved |
| FR-002 | A goal declaration template MUST make the three required elements (specific date, present-tense outcome, observable evidence) explicit and provide at least one example | Approved |
| FR-003 | Vikunja MUST have a dedicated Goals project that holds goal declarations as tasks, distinct from regular task projects | Approved |
| FR-004 | Each goal declaration task in Vikunja MUST carry: outcome statement and evidence criteria in the description, target date as the due date, and an identity label (personal, intentional, or metalcasework) | Approved |
| FR-005 | A saved filter in Vikunja MUST show all active (incomplete) goal declarations sorted by target date | Approved |
| FR-006 | `01-Constitution/Goals-MOC.md` MUST contain all active goal declarations in the standard format and be readable standalone | Approved |
| FR-007 | Goals-MOC.md MUST contain at least one real declared goal by feature completion | Approved |
| FR-008 | An ops runbook at `docs/handbooks/goals-ops.md` MUST document: format reference, manual goal creation (Vikunja + Obsidian), goal closure, goal retirement, and validation rules | Approved |
| FR-009 | Architecture documentation (`data/service-inventory.json`) MUST be updated to note the Goals project structure added by F006 | Approved |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
| --- | --- | --- | --- |
| NFR-001 | Goal declarations MUST be viewable on the Vikunja web UI from both desktop and mobile (via Tailscale) | Accessible on all synced devices | Approved |
| NFR-002 | Goals-MOC.md MUST sync across Mac, iPhone, and office2 via Obsidian Sync without manual intervention | Available on all devices within normal Obsidian Sync latency | Approved |
| NFR-003 | The goal format MUST be parseable by future agents without ambiguity | Three elements extractable via pattern matching | Approved |

### Constraints

| ID | Constraint | Status |
| --- | --- | --- |
| C-001 | No new services, ports, or credentials are introduced — this is configuration and content only | Approved |
| C-002 | `02-Growth/_private/` is never accessed by any agent or script | Approved |
| C-003 | Goals that arise from private work may be captured in the standard format without referencing their origin context | Approved |
| C-004 | WhatsApp voice capture (original func-spec requirement 4) is explicitly deferred to a follow-on feature | Approved |
| C-005 | Goal evaluation prompt (original func-spec requirement 5) is explicitly deferred to a follow-on feature | Approved |
| C-006 | No programmatic enforcement of goal validity in F006 — validation is documented in the ops runbook for manual use | Approved |

### Key Entities

- **Goal Declaration**: An outcome Kent has declared using the canonical format.
  Attributes: outcome statement (present-tense), target date (specific calendar
  date), evidence criteria (observable proof), identity context (personal,
  intentional, or metalcasework), status (active, achieved, retired).
- **Goals Project**: A dedicated Vikunja project that holds goal declaration
  tasks, distinct from regular task/action projects.
- **Goals-MOC**: The Obsidian markdown file (`01-Constitution/Goals-MOC.md`)
  serving as the human-readable canonical reference for active goals.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Kent can declare a new goal by following the documented format and
  template without needing to consult the spec or ask for help.
- **SC-002**: All active goal declarations are visible in a single Vikunja
  filter view, sorted by target date, accessible from desktop and mobile.
- **SC-003**: Goals-MOC.md contains at least one real goal declaration and is
  readable standalone as a complete picture of Kent's active outcomes.
- **SC-004**: The ops runbook covers the full goal lifecycle (create, close,
  retire) with step-by-step instructions that are actionable without external
  context.
- **SC-005**: Architecture documentation is updated to reflect the new Vikunja
  Goals project structure.

## Assumptions

- The Vikunja instance on office2 is operational and accessible (established
  by F001).
- The Obsidian vault on office2 syncs to Mac and iPhone via Obsidian Sync
  (established infrastructure).
- `01-Constitution/Goals-MOC.md` exists and has been reset to a clean slate
  (per func-spec: reset 2026-03-29, legacy content backed up).
- The existing Vikunja project structure, labels, and saved filters from F001
  are intact and documented in `docs/handbooks/vikunja-ops.md`.
- Kent will seed at least one real goal declaration during implementation
  (candidate: Intentional consulting income goal).

## Out of Scope

- WhatsApp voice capture for goal declarations (deferred, builds on OpenClaw
  skill patterns once established)
- Goal evaluation prompt when adding new commitments (deferred)
- Automated sync between Goals-MOC.md and Vikunja (manual two-step for now)
- Habit tracking or recurring commitment management (F008)
- Goal progress measurement or trend analysis (F017)
- Calendar time-blocking for goal work (F014)
- Any access to `02-Growth/_private/`
