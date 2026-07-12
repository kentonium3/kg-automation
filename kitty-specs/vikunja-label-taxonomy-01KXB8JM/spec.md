# Feature Specification: Vikunja Label Taxonomy

**Feature**: Vikunja Label Taxonomy
**Status**: Draft

## Overview

Vikunja's label set drifted during Felix's early development. Today it holds
three ad-hoc labels (`personal`, `intentional`, and a stray `Duplicate`) and
none of the structured taxonomy the Felix/Vikunja design calls for. This
mission establishes the canonical four-dimension label taxonomy —
Friction (`f:`), Eisenhower (`q:`), Type (`t:`), and Level of Effort
(`loe:`) — exactly as specified in
[`docs/design/vikunja-configuration-design.md`](../../docs/design/vikunja-configuration-design.md),
and removes the three legacy labels so the label set is clean.

This is **migration-sequence step 2** of the Vikunja configuration reset epic
(kentonium3/kg-automation#714) and its base child (#715). It is a hard
prerequisite for the rest of the chain: project restructure (#716) will point
habit identity at the `t:habit` label produced here (via the
`scripts/common/vikunja_scope.py` seam shipped by #723), task migration (#717)
applies these labels, and saved filters (#718) reference these exact label
names. The label→id map this mission produces is a direct input to those
children.

Labels are created by a deterministic, idempotent, tested helper (a candidate
for `scripts/vikunja/` per helper-script conventions), because label
create/delete is mechanical work with no judgment (Directive 6). The three
deletions modify live application state and are gated behind an explicit flag
and a confirmed backup.

## User Scenarios & Testing

### Scenario 1 — The taxonomy is created (primary)

An operator runs the label helper against the live Vikunja instance. The helper
reads the current label set, creates any of the 12 taxonomy labels that do not
yet exist (each with its assigned name and color), skips those already present,
and prints a per-label outcome plus the resulting label→id map. After the run,
all 12 taxonomy labels exist with names and colors matching the design doc.

### Scenario 2 — Legacy labels are cleared (primary, destructive)

The operator confirms a recent Restic backup exists, then runs the helper with
its explicit delete flag. The helper deletes exactly the three legacy labels
(`personal`, `intentional`, `Duplicate`) — removing them from any tasks that
carried them — and reports each deletion. After the run, the label set contains
only the 12 taxonomy labels.

### Scenario 3 — Re-run is a no-op (idempotency)

The operator runs the helper a second time. It reports every taxonomy label as
already present and every legacy label as already absent, makes zero changes,
and exits successfully. Idempotency is what makes the helper safe to re-run and
suitable for later reproduction of the taxonomy elsewhere.

### Scenario 4 — Downstream can consume the ids

After the run, the operator records the label→id map on issue #715. #716/#717/#718
read those ids (e.g. to move habit identity onto `t:habit`, to bulk-apply labels
during migration, and to reference labels in saved-filter queries).

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The system MUST create the 12 taxonomy labels with titles matching the design doc exactly: `f:1-flow`, `f:2-growth`, `f:3-edge`, `f:4-overload`, `q:do`, `q:schedule`, `q:delegate`, `q:eliminate`, `t:habit`, `loe:s`, `loe:m`, `loe:l`. | Draft |
| FR-002 | Each created label MUST carry its assigned color per the locked scheme (friction green→red gradient; Eisenhower blue family; type purple; LOE gray light→dark). | Draft |
| FR-003 | Label creation and deletion MUST be performed by a single deterministic, tested helper invocation — not by agent-improvised API calls or ad-hoc scripting. | Draft |
| FR-004 | The helper MUST be idempotent: creating a label that already exists (matched by title) is a no-op, and a second full run makes zero changes and exits successfully. | Draft |
| FR-005 | The helper MUST delete exactly the three legacy labels — `personal`, `intentional`, `Duplicate` — leaving no label outside the taxonomy. | Draft |
| FR-006 | Deletion (destructive state change) MUST require an explicit opt-in flag; the default run is create-only and performs no deletions. | Draft |
| FR-007 | The helper MUST report a per-label outcome for every label it touches (created / already-present / deleted / already-absent). | Draft |
| FR-008 | The helper MUST emit the resulting taxonomy label→id map on success, so downstream work can consume the ids. | Draft |
| FR-009 | Label reads MUST paginate the Vikunja label list until exhausted (the API caps `per_page` at 50) and MUST reference labels by `id`, never by display title, for mutation. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The helper is covered by automated tests including create, skip-existing, delete, idempotent re-run, and failure modes (store unreachable, partial pre-existing state). | Each path independently tested; failure modes asserted | Draft |
| NFR-002 | A second full run of the helper against the resulting state makes no changes. | 0 create and 0 delete operations on re-run | Draft |
| NFR-003 | The helper completes a full run within one operator window. | ≤ 30 seconds under normal Vikunja latency | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Label names and colors are locked to the design doc. Felix skill/briefing queries and the #718 saved-filter definitions reference these exact strings, so spelling, casing, and prefixes MUST NOT drift. | Draft |
| C-002 | The three deletions modify Vikunja application state (a label delete cascades off every task carrying it) — a Tier-2 change. A recent Restic backup (within 24h) MUST be confirmed before the delete pass; if none exists, one MUST be triggered first. | Draft |
| C-003 | `area:` labels (e.g. `area:health`, `area:felix`) are deferred per the design doc's "Deferred Dimensions" and MUST NOT be created here. The deleted `personal`/`intentional` labels are the informal precursor of that dimension; it will be reintroduced deliberately later, not carried over. | Draft |
| C-004 | Every Felix behavior that reads or acts on this taxonomy — the task-intake validation loop, habit prompting, Edge/Overload handling, LOE-based scheduling — is out of scope and belongs to the future Felix/Vikunja integration epic. | Draft |
| C-005 | The helper is the deterministic infrastructure layer (Directive 6): it builds on the existing canonical Vikunja access rather than introducing a new HTTP dependency, and its selectors/values are explicit constants matching the design doc. | Draft |

## Success Criteria

- **SC-001**: The live Vikunja label list contains all 12 taxonomy labels, each with the exact name and color from the design doc.
- **SC-002**: The live Vikunja label list contains no label outside the taxonomy — the three legacy labels are gone.
- **SC-003**: A second run of the helper reports all-present / all-absent and performs zero create and zero delete operations.
- **SC-004**: The helper is committed under `scripts/vikunja/` with automated tests, and the resulting label→id map is recorded on issue #715.
- **SC-005**: A recent Restic backup was confirmed (or triggered) before the deletion pass ran.

## Key Entities

- **Vikunja Label** — a label record with `id` (numeric, authoritative for mutation), `title` (display string, the locked taxonomy name), and `hex_color` (color without leading `#`).
- **Taxonomy dimension** — one of Friction (`f:`), Eisenhower (`q:`), Type (`t:`), Level of Effort (`loe:`); each contributes a fixed set of labels.
- **Label→id map** — the run's output artifact mapping each taxonomy title to the id Vikunja assigned; consumed by #716/#717/#718.

## Assumptions

- The Vikunja API is reachable at the canonical base URL and the `vikunja-api` token has full read/write scope (confirmed: escalation and habit crons update tasks daily with it).
- The helper runs where the canonical Vikunja base-URL config and token resolve (office2, via `ssh office2-claude`) or with those provided explicitly.
- office2 has a working Restic backup cadence that can be confirmed or triggered before the deletion pass.
- Live audit (2026-07-12) confirmed the current label set is exactly `personal` (id 1), `intentional` (id 2), `Duplicate` (id 4); the helper matches legacy labels by title so it stays correct if ids differ at run time.

## Domain Language

- **Friction (`f:`)** — internal resistance / nervous-system response to a task (flow → growth → edge → overload). Orthogonal to effort and importance.
- **Eisenhower (`q:`)** — strategic quadrant (do / schedule / delegate / eliminate).
- **Type (`t:`)** — behavioral classification; today only `t:habit`.
- **Level of Effort (`loe:`)** — coarse execution size (s / m / l).
- **Label vs custom field** — LOE and Eisenhower are implemented as labels, not custom fields, because Vikunja's current query language cannot filter on custom fields.

## Out of Scope

- `area:` labels and any other deferred dimension.
- Project restructure (#716), task migration (#717), saved filters + dashboard default (#718).
- Migrating habit identity off project-id 13 onto `t:habit` — that is #716's configuration edit, which consumes the label this mission creates.
- Any Felix runtime behavior that reads or validates these labels (future integration epic).
