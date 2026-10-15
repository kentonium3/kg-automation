---
affected_files: []
cycle_number: 1
mission_slug: offhost-deadman-pings-01M50990
reproduction_command:
reviewed_at: '2026-10-15T17:44:12Z'
reviewer_agent: user
wp_id: WP01
---

# WP01 review (reviewer-renata, claude-sonnet-5-5, 2026-10-15): REQUEST-CHANGES
1. MEDIUM: `_canonical` lets an action suffix bypass the check. `/u/fail//`, `/u//`, dot segments, `%` encodings and `FAIL` are all accepted, and `/u/fail//` inverts a success ping into a fail. Reject empty, `.` and `..` segments and any `%`, compare the action check case-insensitively, and add tests.
2. LOW: an invalid port is accepted (fails safe as curl exit 3). Validate `parts.port` and return invalid.
3. LOW: a non-ASCII URL raises UnicodeEncodeError under an ASCII locale. Reject non-ASCII in `_canonical`.
