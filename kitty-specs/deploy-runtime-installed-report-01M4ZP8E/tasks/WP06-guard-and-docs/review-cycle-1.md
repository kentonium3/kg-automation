---
affected_files: []
cycle_number: 1
mission_slug: deploy-runtime-installed-report-01M4ZP8E
reproduction_command:
reviewed_at: '2026-10-15T12:43:40Z'
reviewer_agent: reviewer-renata
wp_id: WP06
---

# WP06 review cycle 1 — reviewer-renata (claude-sonnet-5-5) — APPROVE with findings; implementer chose to fix before approval

1. MEDIUM: _copies matches only Attribute calls on a bare Name, so `from shutil import copy2; copy2(a, b)`, `import shutil as sh; sh.copy2(...)` and `from os import replace` pass the guard. Collect alias/from-import bindings for shutil/os and match bare-name calls; add a non-vacuity case per form.
2. LOW: the stated-limit docstring names only helper-module delegation; also list open(..., "w"), shutil.move/os.rename, subprocess cp/install, and import-without-call (presence check, not proof).
