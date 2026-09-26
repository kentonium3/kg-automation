---
affected_files: []
cycle_number: 17
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-26T01:45:12Z'
reviewer_agent: claude
wp_id: WP04
---

# WP04 REOPEN — design-lead rulings (bus 20260925T220551226384Z4831c24f84, 20260925T220651378865Z5316e3fceb, 20260925T223514053706Zf68055805c)

Reopened after approval, because the ruling makes sampler.py the owner of the FalkorDB process-RSS SERIES FORMAT and both of its ends. This is not a defect in the approved code.
1. One record definition: {ts, rss_mib, container_id}, a 1.0 s interval, STALE_INTERVALS = 5, GAP_INTERVALS = 5.
2. A host-side writer, RssSeriesWriter.
3. A runner-side reader, RssSeriesSampler: the peak plus detail. It fails closed on absent, empty, stale, gap, or container mismatch.
4. W8-3: the samplers the harness binds must carry a REQUIRED `breached` attribute.
5. A round-trip test, plus each fail-closed condition and its boundary.
