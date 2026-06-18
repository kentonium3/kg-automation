# Phase 1 Data Model: Felix exec host=gateway directive

This mission introduces **no data entities, schemas, or persistent state**. It
edits static prompt content (`AGENTS.md` standing-orders files).

The only structured artifacts touched are existing and unchanged:

- **AGENTS.md (per agent)** — a Markdown standing-orders document. This mission
  adds one section (`## Tool use — exec host`); no schema or frontmatter change.
- **audited-surfaces.json** — the canonical registry consulted (not modified)
  to confirm the deploy path and affected baseline.

No validation rules, invariants, or state transitions over data apply. The one
behavioral invariant (always `exec host=gateway`) is expressed as a prompt
directive, covered in spec.md (FR-001/FR-003) and the contracts note, not as a
data constraint.
