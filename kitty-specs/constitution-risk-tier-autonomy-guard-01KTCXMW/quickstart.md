# Quickstart: Constitution Risk-Tier Autonomy Guard

## Implementation Checklist

1. Edit `docs/constitution/FELIX-CONSTITUTION.md` near Directive 2.
2. Add concise wording that autonomy level controls surfacing/execution posture,
   not permission to bypass deployed-change risk-tier gates.
3. Reference `docs/design/architecture/data/change-risk-taxonomy.json` as the
   canonical taxonomy.
4. State that Tier 0 is operator-only regardless of autonomy level, urgency, or
   user phrasing.
5. State that Tier 1 and Tier 2 gates remain binding where applicable.
6. Inspect `CLAUDE.md`, `.kittify/charter/charter.md`, and
   `docs/design/architecture/change-control.md` for concrete inconsistency.

## Validation

```bash
python tooling/scripts/validate_docs.py
```

Targeted inspection:

```bash
rg -n "autonomy|risk-tier|change-risk-taxonomy|Tier 0|Tier 1|Tier 2" docs/constitution/FELIX-CONSTITUTION.md
```
