---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T18:23:01Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP08
---

# WP08 review cycle 1: REJECT (reviewer: Codex gpt-6.1-sol, 2026-11-20)

1. MAJOR | Valid ordinal rules fail verification | scripts/vikunja/create_task.py:193; scripts/common/vikunja_client.py:1202 | For FREQ=MONTHLY;BYDAY=+1MO, the server returns structured by_day=["1mo"]. The comparator treats these equivalent forms as different. Probe reproduced exit 1 after successful creation and VikunjaServerError from end_series. | Canonicalize weekday ordinals before comparison; add server-shaped create and end-series regressions.

2. MAJOR | Strict validation prevents clearing supported read-only rules | scripts/common/vikunja_client.py:1199 | A valid server response containing repeats_rrule="FREQ=YEARLY;BYEASTER=0" and repeat.read_only=true now makes end_series fail before writing. The pinned server explicitly supports clearing these rules with repeat:null. Local parser limitations do not make the response malformed. | Preserve shape/presence checks while accommodating read-only projections and server-supported text; test successful clearing without weakening malformed-response controls.

Validation: 547 focused tests passed; strict architecture validation passed. Full suite was interrupted after prolonged inactivity around 72%; its result remains unverified.
VERDICT: REJECT
Orchestrator note: item 6 (rule_repair) stays out of WP08; it moved to the post-consolidation pass.
