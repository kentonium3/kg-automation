# Quickstart: Documentation Developer Portal

**Mission**: documentation-developer-portal-01KSJ75K

After this mission lands, contributors interact with the portal via two
commands. Both run from the repo root.

---

## Verify the portal is up to date

```
python tooling/scripts/validate_docs.py
```

This is the existing umbrella check. After this mission, it also fails if
the runbook-filter block in `docs/DEVELOPER_PORTAL.md` is stale. The error
message points at the refresh command.

## Refresh the runbook filter

```
python tooling/scripts/build_runbook_filter.py --write
```

Run this after adding a runbook, removing a runbook, or changing a
runbook's `audience:` frontmatter. It rewrites only the auto-generated
block between the marker comments; nothing else in the portal is touched.

`python tooling/scripts/build_runbook_filter.py` (no `--write`) does a
drift check without modifying the file.

---

## Onboarding (the portal itself)

Open `docs/DEVELOPER_PORTAL.md`. It is the guided sitemap — start there
for any first-time orientation in this repo.
