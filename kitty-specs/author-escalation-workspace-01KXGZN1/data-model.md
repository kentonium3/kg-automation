# Data Model: Author felix-admin-escalation workspace

No database or serialized data model — the "model" is the **content-conservation mapping** for the refactor: every substantive content block, its source file, and its #587-canonical destination. This is the authoritative move-table; the conservation check (NFR-003) verifies each row.

## Content blocks & their canonical owners

| Block | Source (before) | Destination (after) | Transform | FR |
|-------|-----------------|---------------------|-----------|-----|
| `## Voice — write as Kent` (principles, escalation tone, banned phrases) | SOUL | SOUL | **keep** (the keeper); trim only the "Kent has ADD…" justification off the "Structured and chunked" bullet | FR-001 |
| `## Purpose` operational role ("sole purpose is detecting overdue…") | SOUL | AGENTS (`## Authority`/`## Scope` — already present) | **remove from SOUL**; role already owned by AGENTS | FR-002, FR-008 |
| "Insistence is a feature / hold Kent accountable" framing | SOUL `## Purpose` | SOUL | **reduce to a one-line stance** (genuinely voice/stance) | FR-002 |
| `## Privacy boundary` full enforceable rule + path + mission-026 changelog | SOUL | SOUL (one-line stance) + enforceable copy already in AGENTS + TOOLS | **reduce to one-line stance**; drop path + changelog from SOUL; enforceable copy stays in AGENTS/TOOLS | FR-003 |
| Person-view: name / call / timezone / notes ("ADD (managed)") + `## Context` | USER | USER | **keep** | FR-004 |
| `## Date handling` (America/New_York resolution, ET offset, no-Z rule) | USER | TOOLS | **move verbatim-in-substance** | FR-004, FR-005 |
| Vikunja API pointers, key ops, priority table | TOOLS | TOOLS | **keep** | — |
| `project_id NOT IN (11, 13)` overdue-query filter | TOOLS | TOOLS | **edit** → `NOT IN (13)` (drop 11) | FR-006 |
| `11 | Goals` project-exclusion row | TOOLS | — | **delete** (Goals project deleted in #717) | FR-006 |
| `## Privacy` enforceable path line | TOOLS | TOOLS | **keep byte-unchanged** (path canonicalization deferred to #732) | FR-006, C-005 |
| "Goals" saved-filter block (`project = 11 && done = false`) | `setup_vikunja.py` | — | **delete** (dormant script; other filters unchanged) | FR-007 |
| AGENTS.md (all content) | AGENTS | AGENTS | **unchanged** | FR-008 |
| IDENTITY.md (all content) | IDENTITY | IDENTITY | **unchanged** | FR-008 |

## Invariants (must hold post-refactor)

- **INV-A (privacy enforceable home)**: the enforceable `04-Growth/_private/` rule (path + "never access") is present in AGENTS.md AND TOOLS.md. SOUL carries only a stance. → `validate_workspace.py` Invariant A = pass (NFR-001).
- **INV-B (output discipline)**: the Output Discipline block remains present in AGENTS.md (escalation is user-facing WhatsApp). Untouched this mission. → Invariant B = pass (NFR-001).
- **INV-CONSERVE (no silent drop)**: every "keep" / "move" row above is present in its destination after the refactor; every "delete" row is a deliberate #724/#717-justified removal, not a drop. → conservation grep/diff (NFR-003).
- **INV-SCOPE (bounded diff)**: the file set touched = escalation SOUL/USER/TOOLS.md + `scripts/vikunja/setup_vikunja.py` + mission artifacts. Nothing else. → NFR-002.
- **INV-BEHAVIOR (zero runtime change)**: the escalation candidate set and message shape are unchanged (Goals(11) exclusion was already a no-op post-#717; date-handling semantics are identical, only relocated). → smoke test (NFR-004).

## State transitions

None. Static content authoring; no runtime state machine is introduced or altered.
