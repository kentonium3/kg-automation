# Data Model: Documentation Developer Portal

**Mission**: documentation-developer-portal-01KSJ75K
**Date**: 2026-05-26

This mission has no application data model. It produces markdown documents
and a helper script. The "model" below documents the structured inputs and
outputs the helper script operates on, plus the markdown contract for the
generated block in the portal.

---

## Inputs

### Runbook frontmatter (read-only)

For each file under `docs/runbooks/**/*.md`, the relevant YAML frontmatter
fields are:

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | Used as the display label in the generated filter |
| `audience` | enum | recommended | One of `agents`, `humans`, `agents_and_humans`. Missing values surface in the "Unclassified" bucket. |

All other frontmatter fields are ignored for filter purposes.

### Existing repo conventions consumed

- `tooling/scripts/validate_docs.py` ALLOWED_VALUES['audience'] is the canonical enum source for filter buckets. The helper script must read its buckets in a way that stays in sync with that enum (either by importing it, or by matching its literal set).

## Outputs

### Generated runbook-filter block

Markdown structure emitted between the two HTML comment markers in
`docs/DEVELOPER_PORTAL.md`:

```markdown
<!-- begin:runbook-filter (generated; do not edit) -->

### Agent-executable
- [Title](relative/path.md)
- ...

### Dual-audience
- [Title](relative/path.md)
- ...

### Human-only
- [Title](relative/path.md)
- ...

### Unclassified
- [Title](relative/path.md) — missing `audience:` frontmatter
- ...

<!-- end:runbook-filter -->
```

Rules:

- Each bucket is alphabetized by display title.
- Empty buckets (e.g., no `Unclassified` files) are still emitted with an explicit "(none)" line, so the absence is visible.
- Relative paths are written from the portal's location (`docs/DEVELOPER_PORTAL.md`) for portability.
- Lines outside the marker pair are untouched by the writer.

### Drift-detection contract

- Default invocation (`python tooling/scripts/build_runbook_filter.py`) reads the runbooks, builds the expected block in memory, compares against the current marker-bounded section in `docs/DEVELOPER_PORTAL.md`, and:
  - exit 0 if they match
  - exit non-zero with a unified diff printed to stdout if they differ
- `--write` invocation rewrites the section to match the expected block, exits 0.
- `--check-only` is the same as default (kept as an explicit alias for CI scripts that want a flag).

## State transitions

The script is stateless. Each invocation re-reads the runbooks and emits a
fresh block. No caching, no persistence beyond the portal markdown itself.

## Validation rules

- The marker pair must exist exactly once in `docs/DEVELOPER_PORTAL.md`. Zero pairs or duplicate pairs cause the script to exit non-zero with a clear error.
- Any runbook frontmatter with an `audience:` value not in the allowed enum is reported as an error (not silently routed to "Unclassified"), pointing at the offending file.

## Out of model

- No database, no API.
- No tracking of "which runbook was added when" — version control already records that.
- No dependency graph between docs — that was explicitly removed in blueprint v1.2.
