---
affected_files: []
cycle_number: 1
mission_slug: deploy-runtime-installed-report-01M4ZP8E
reproduction_command:
reviewed_at: '2026-10-15T12:24:19Z'
reviewer_agent: reviewer-renata
wp_id: WP04
---

# WP04 review cycle 1 — reviewer-renata (claude-sonnet-5-5) — REQUEST-CHANGES

1. HIGH (test gap on C-002): no test pins that a source matching only surfaces WITHOUT host_paths contributes nothing. Mutating `if not hosts: continue` to also add that surface's baselines left all 20 tests green. Add real-registry tests: (a) scripts/openclaw/openclaw.json or requirements.txt installed to a scratch dest → baselines == [], rejected False; (b) same source with a dest under host_paths → still nothing.
2. LOW: mapper relies on read_report enforcing absolute paths; optionally reject non-absolute paths in the mapper too (defence in depth).
3. LOW (informational): a future-dated last_fold_utc would extend grace; unreachable today (only writer uses now_iso). No change.
