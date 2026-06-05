# Data Model: Constitution Risk-Tier Autonomy Guard

No repository data model, schema, API model, or taxonomy structure changes are
planned.

## Referenced Concepts

| Concept | Source | Implementation Treatment |
|---|---|---|
| Autonomy level | `docs/constitution/FELIX-CONSTITUTION.md` Directive 2 | Clarify that autonomy controls activity surfacing and routine execution posture. |
| Risk tier | `docs/design/architecture/data/change-risk-taxonomy.json` | Reference as canonical; do not duplicate the full table. |
| Tier 0 | Canonical taxonomy JSON | State operator-only status regardless of autonomy, urgency, or user phrasing. |
| Tier 1 / Tier 2 gates | Canonical taxonomy JSON and governance runbooks | State that required gates remain binding where applicable. |

## Validation Notes

- The taxonomy JSON remains unchanged.
- The constitution amendment must not introduce new autonomy levels or promotion
  rules.
- Companion-doc inspection must be recorded in implementation notes or review
  evidence.
