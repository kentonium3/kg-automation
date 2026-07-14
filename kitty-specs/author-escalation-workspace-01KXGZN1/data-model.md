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
| Reschedule example `"...T00:00:00Z"` | TOOLS (`:38`) | TOOLS | **fix** → ET-offset form (`-04:00`, note `-05:00` for EST) | FR-010 |
| "Goals" saved-filter block (`project = 11 && done = false`) | `setup_vikunja.py` | — | **delete** (dormant script; other filters unchanged) | FR-007 |
| Reschedule example `"<YYYY-MM-DD>T00:00:00Z"` | AGENTS (`:232-233`) | AGENTS | **fix** → ET-offset form (narrow AGENTS edit #1) | FR-010, FR-008 |
| Enforcement sentence "…enforced in SOUL.md, AGENTS.md, and TOOLS.md" | AGENTS (`:305-308`) | AGENTS | **fix** → "enforced in AGENTS.md and TOOLS.md (SOUL carries a stance)" (narrow AGENTS edit #2) | FR-012, FR-008 |
| AGENTS.md (all other content) | AGENTS | AGENTS | **unchanged** (only the two edits above) | FR-008 |
| IDENTITY.md (all content) | IDENTITY | IDENTITY | **unchanged** | FR-008 |
| Candidate-model Goals(11) lines | SKILL.md (`:50, :60`) | SKILL.md | **remove** the "NOT 11 (Goals)" / "Goals project (ID 11)" refs (helper `[13]` is authoritative) | FR-011 |
| Goals(11) exclusion prose | escalation-ops.md (`:31, :34`) | escalation-ops.md | **remove** Goals/11 from the excluded-projects prose | FR-011 |
| Generic exclusion test using `project_id=11` / `[11,13]` | test_enumerate_candidates.py (`:169-170`) | same | **switch to a non-Goals excluded id** (preserve the mechanism assertion) | FR-011 |

## Invariants (must hold post-refactor)

- **INV-A (privacy enforceable home — non-fakeable)**: the enforceable `04-Growth/_private/` path token is present in **BOTH** AGENTS.md AND TOOLS.md AND **absent** from SOUL.md (SOUL carries only a stance). This is stronger than `validate_workspace.py`'s either-owner check (MED-6). → escalation-scoped validator `ok: true` (NFR-001) + the both-and-absent check (NFR-003).
- **INV-B (output discipline)**: the Output Discipline block remains present in AGENTS.md (escalation is user-facing WhatsApp). Untouched this mission. → Invariant B = pass (NFR-001).
- **INV-CONSERVE (no silent drop)**: every "keep" / "move" / "fix" row above is present (in its destination / corrected form) after the refactor; every "delete"/"remove" row is a deliberate #724/#717-justified removal, not a drop. → row-by-row conservation checklist (NFR-003).
- **INV-SCOPE (bounded diff)**: the file set touched = escalation SOUL/USER/TOOLS/AGENTS.md (AGENTS narrowly) + SKILL.md + escalation-ops.md + `setup_vikunja.py` + test_enumerate_candidates.py + mission artifacts. Nothing else. → NFR-002.
- **INV-BEHAVIOR (zero runtime change)**: the escalation candidate set and message shape are unchanged (Goals(11) exclusion was already a no-op post-#717; date-handling semantics are identical, only relocated). → smoke test (NFR-004).

## State transitions

None. Static content authoring; no runtime state machine is introduced or altered.
