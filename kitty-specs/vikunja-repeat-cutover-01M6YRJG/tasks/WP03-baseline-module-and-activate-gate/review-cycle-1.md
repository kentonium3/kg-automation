---
affected_files: []
cycle_number: 1
mission_slug: vikunja-repeat-cutover-01M6YRJG
reproduction_command:
reviewed_at: '2026-11-09T20:30:31Z'
reviewer_agent: claude::reviewer-renata
wp_id: WP03
---

**Issue 1 (MATERIAL): the real migration table contains a non-numeric ID.**

`scripts/deploy/vikunja_release/baseline.py` accepts only `[0-9]+` migration IDs (`_ID`, used by `_ids` and by `validate`). The deployed database's `migration` table includes the row `SCHEMA_INIT`, as xormigrate creates, alongside numeric IDs. It is one of the expected 155 pre-upgrade IDs.

Failure: `build()` raises on it, and `compare()` returns `GATE_MIGRATIONS_MISMATCH` on every attempt, so a real cutover can never pass the gate.

Fix:
- Pre-upgrade IDs accept digits or exactly `SCHEMA_INIT`. Keep the strict sorted, unique validation (digits sort before `S`).
- Added IDs stay numeric only; `SCHEMA_INIT` in the added list is refused.
- Make every synthetic fixture that models a real pre-upgrade database include `SCHEMA_INIT`, in `tests/deploy/test_vikunja_release_baseline.py` and `tests/deploy/test_deploy_vikunja_release_activate.py`.
- Add tests: a snapshot with `SCHEMA_INIT` passes when the baseline lists it; missing it, or an unlisted non-numeric ID, is `GATE_MIGRATIONS_MISMATCH`; a baseline whose added list contains `SCHEMA_INIT` is refused by validation.

Reviewed by Claude Sonnet 5.5 and confirmed against private data by Claude Opus 5.5. No other MATERIAL findings.
