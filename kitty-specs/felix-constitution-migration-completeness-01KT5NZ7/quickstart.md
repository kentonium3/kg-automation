# Quickstart: Felix Constitution — Migration Completeness Directive

**Mission**: `felix-constitution-migration-completeness-01KT5NZ7`

How to verify the directive locally.

## Local verification

```bash
cd /Users/kentgale/repos/kg-automation

# SC-001: Directive 7 exists exactly once
grep -nE "^## Directive 7:" docs/constitution/FELIX-CONSTITUTION.md

# SC-001 (positioning): Directive 7 sits between Directive 6 and the Privacy section
grep -nE "^## Directive [0-9]+:|^## Privacy and Communication Boundaries" docs/constitution/FELIX-CONSTITUTION.md

# SC-003: rationale cites the documented incidents
grep -nE "#309|#376|v2026\.5\.28" docs/constitution/FELIX-CONSTITUTION.md
```

Expected: SC-001 grep returns exactly one match. The positioning grep returns the existing Directives 1–6, then the new Directive 7, then the Privacy section. The incident-citation grep returns at least three hits inside the Directive 7 prose.

## Future-migration confirmation

This mission's SC-004 is operational, not local: the next migration-shaped mission's `/spec-kitty.specify` or `/spec-kitty.plan` run should pick up Directive 7 via charter context and route the spec author to enumerate transitional artifacts. That confirmation happens in a future session, not this one.

## Rollback

If a problem surfaces post-merge, revert the merge commit on `main`. No state migration; no code change; no downstream regen needed.
