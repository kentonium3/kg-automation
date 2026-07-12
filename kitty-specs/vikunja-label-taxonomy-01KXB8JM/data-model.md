# Data Model: Vikunja Label Taxonomy

Phase 1 output. Entities, the canonical taxonomy declaration, and the reconcile
outcome model.

## Entities

### Vikunja Label (remote)

The record the API returns/accepts.

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | Server-assigned. Authoritative for mutation (delete). Not known in advance. |
| `title` | str | Display + machine key. The locked taxonomy name (e.g. `f:3-edge`). Matching key. |
| `hex_color` | str | 6 hex digits, **no** leading `#` on read. Normalized (strip `#`, lower-case) for comparison. |

### TaxonomyLabel (declared constant)

An entry the helper intends to exist. Pure data in the module.

| Field | Type | Notes |
|-------|------|-------|
| `title` | str | Locked to the design doc. |
| `hex_color` | str | Bare 6-hex, assigned per the color scheme below. |
| `dimension` | enum | `friction` \| `eisenhower` \| `type` \| `loe` — for reporting/grouping only. |

### LegacyLabel (declared constant)

A title the helper deletes when `--delete-legacy` is set: `personal`,
`intentional`, `Duplicate`. Matched by title, deleted by resolved id.

### ReconcileOutcome (per label, emitted)

| Field | Type | Values |
|-------|------|--------|
| `title` | str | The label acted on. |
| `action` | enum | `created` \| `already-present` \| `color-mismatch` \| `deleted` \| `already-absent` \| `skipped-no-flag` \| `duplicate-title` |
| `id` | int \| null | Resolved/assigned id (null when not applicable). |

### Title→id map (run artifact)

`{ "f:1-flow": 12, "f:2-growth": 13, ... }` for the 12 taxonomy labels, emitted
on success (FR-008). Recorded on issue #715 for #716/#717/#718.

## Canonical taxonomy (locked)

Titles + dimensions MUST match `docs/design/vikunja-configuration-design.md`.
**Colors** are this mission's decision (operator, 2026-07-12); this same set is
written into the design doc's label tables, the helper constants, and the table
below, and the fidelity test asserts all three agree.


| # | title | dimension | hex_color |
|---|-------|-----------|-----------|
| 1 | `f:1-flow` | friction | `4caf50` |
| 2 | `f:2-growth` | friction | `fbc02d` |
| 3 | `f:3-edge` | friction | `fb8c00` |
| 4 | `f:4-overload` | friction | `e53935` |
| 5 | `q:do` | eisenhower | `1565c0` |
| 6 | `q:schedule` | eisenhower | `1e88e5` |
| 7 | `q:delegate` | eisenhower | `42a5f5` |
| 8 | `q:eliminate` | eisenhower | `90caf9` |
| 9 | `t:habit` | type | `8e24aa` |
| 10 | `loe:s` | loe | `bdbdbd` |
| 11 | `loe:m` | loe | `757575` |
| 12 | `loe:l` | loe | `424242` |

Legacy (delete when flagged): `personal`, `intentional`, `Duplicate`.

## Invariants

- **INV-1 (fidelity)**: the 12 declared titles are exactly the design-doc set — no more, no fewer, no spelling/casing drift. Guarded by a fidelity test (C-001).
- **INV-2 (idempotency)**: after a successful full run, a second run performs 0 creates and 0 deletes (NFR-002).
- **INV-3 (create/delete separation)**: no delete occurs without the explicit flag (FR-006); the default run is purely additive.
- **INV-4 (id-based mutation)**: deletion resolves the live id by title, then deletes by id (FR-009).
- **INV-5 (post-state)**: after create + delete passes, the live label set equals exactly the 12 taxonomy labels (SC-001 + SC-002).
- **INV-6 (no ambiguous mutation)**: a title matching >1 live label is never silently resolved. A **taxonomy** title with duplicates → fail non-zero, report all ids (FR-010). A **legacy** title with duplicates under `--delete-legacy` → delete ALL exact-title matches (FR-005).
- **INV-7 (no false success on color)**: an already-present taxonomy label whose normalized color ≠ the declared color → `color-mismatch`, exit non-zero (FR-011). Cannot occur on the first live run (all created fresh); it is the safety net for re-runs against a hand-edited state.
- **INV-8 (delete-404 consistency)**: on `VikunjaNotFoundError` during a delete, re-list; if the title is now absent → `already-absent`; otherwise fail (inconsistent id/title view).

## State transitions (per label, during a run)

```
absent        --create-->      present (taxonomy)
present       --(match)-->     already-present (no-op)
legacy present --delete flag--> absent (deleted)
legacy present --no flag-->    present (skipped-no-flag)
legacy absent --any-->         already-absent (no-op)
```
