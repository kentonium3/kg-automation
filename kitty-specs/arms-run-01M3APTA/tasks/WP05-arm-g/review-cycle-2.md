---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:56:04Z'
reviewer_agent: claude
wp_id: WP05
---

[MAJOR] scripts/research/arms849/arm_g.py:400 — MENTIONS edges still receive `created_at=ask` — e00009 occurred at 09:12 but its arms_A links are stamped 09:15, violating the required event-time metadata despite the EntityEdge fix — retain each episode’s timestamp and use it for its EpisodicEdge saves; assert saved timestamps in a regression test.

Source: Codex read-only review, WP05 cycle 2, 2026-09-25. VERDICT: REJECT (cycle-1 five + design-lead three confirmed fixed; one new — MENTIONS edges stamped with ask_time, not the episode time). Design-lead APPROVE at 077bf7dd carries to the fold.
