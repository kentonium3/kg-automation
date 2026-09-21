---
affected_files: []
cycle_number: 1
mission_slug: adr-first-class-statuses-01M2TVSP
reproduction_command:
reviewed_at: '2026-09-18T22:38:23Z'
reviewer_agent: user
wp_id: WP02
---

# WP02 review feedback #1 — REQUEST CHANGES

**Reviewer**: Codex (read-only, advisory) · **Diff**: `bd33e00b`

Four findings, all accepted. Two were demonstrated concretely rather than asserted, and all three
material ones are the same class: **the generator can damage content it does not own** — exactly the
property the contract's invariant 3 exists to guarantee.

**M1 — `render_schema` replaces the whole top-level `allOf`.** Any unrelated constraint added to the
schema later would be silently deleted. The schema has no other `allOf` today, which is why no test
caught it. → Mark the generated clause and replace only that, preserving every other entry.

**M2 — bootstrap searches the entire document for the vocabulary line.** Demonstrated: with the
`### status` section stale, the generated region was inserted into an `### appendix` section instead.
→ Require exactly one `### status` heading and locate the target line within that section's bounds.

**M3 — sentinels are matched as substrings, not standalone lines.** Demonstrated: `before <!-- …
START --> KEEP-HEAD` lost `KEEP-HEAD`. A fenced example containing the marker would make arbitrary
prose a writable region. → Match full lines only; reject embedded occurrences.

**m4 — the preservation test is too weak.** It checks selected top-level keys and property *names*, so
it would pass if a property definition changed or an `allOf` were erased. It also omits the
no-`doc_type` case, which the review confirmed is the subtlest branch. → Deep-compare the schema minus
the generator-owned parts, and assert the absent-`doc_type` behaviour explicitly.

**Confirmed correct**: the negative conditional. With `doc_type` absent, the inner `required` fails,
`not` succeeds, and the default set applies — while the root schema independently rejects the missing
required field.
