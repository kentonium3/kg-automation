---
affected_files: []
cycle_number: 6
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-21T15:18:29Z'
reviewer_agent: codex:gpt-5:spec-kitty-review:reviewer
verdict: rejected
wp_id: WP10
---

**Issue 1**: `docs/design/architecture/data/data-flows.json` now contains the post-#343 `direct-claude-api`, `tick-signal-write`, and `doc-audit-credential-read` active flows, but the Markdown data-flow views were not refreshed. `docs/design/architecture/data-flows.md` still has no `felix-doc-auditor` / `last-tick.json` / direct Anthropic flow coverage, and `docs/design/architecture/data-flows.view.md` / `.mmd` still render only the older core flows. This violates the WP review requirement to confirm Markdown views match the authoritative architecture JSON sources. Update the data-flow Markdown and Mermaid views so they reflect the new direct API, credential-read, drift-event read, and tick-signal-write paths documented in `data/data-flows.json`.

Validation notes:
- `python3 -m json.tool` passed for `service-inventory.json`, `data-flows.json`, and `credential-manifest.json`.
- `python3 tooling/scripts/validate_docs.py` currently fails on `docs/design/architecture/baselines/cutover-log.md` frontmatter (`status: active`, `level: 1`), which appears to be WP09-owned and outside this WP10 isolation review.
