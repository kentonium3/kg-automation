---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:34:01Z'
reviewer_agent: claude
wp_id: WP05
---

[MAJOR] scripts/research/arms849/arm_g.py:345 — Graph objects receive random default UUIDs on every rebuild — equal-score items are selected by UUID, so resume can change the capped selection and context SHA, violating D-15 — assign stable UUIDs from group, kind, and corpus key; test rebuilds with ties spanning the cap.
[MAJOR] scripts/research/arms849/arm_g.py:253 — The “node+edge” configuration also searches episodes directly — unanchored episodes enter hybrid hits and consume the cap before MENTIONS expansion, changing the registered A3 retrieval plan — remove episode_config and test that hybrid search enables only nodes and edges.
[MAJOR] scripts/research/arms849/arm_g.py:330 — Edges without made_at receive ask_time instead of their effective time — actual DECIDED edges derive their time from the source Decision’s decided_at; DEC_F_RESTART’s edges are therefore stamped incorrectly — use the loader’s edge_effective_time derivation before applying an undated-edge fallback.
[MAJOR] scripts/research/arms849/embed.py:44 — Offline operation is optional when HF_HUB_OFFLINE already equals 0 — an existing but incomplete cache can trigger downloads because TextEmbedding receives no local_files_only flag — pass local_files_only=True explicitly and test an incomplete cache with offline mode disabled externally.
[MINOR] scripts/research/arms849/arm_g.py:234 — Description ambiguity is grouped by description prefix rather than matched mention — “the design review” matching two different descriptions produces both anchors but an empty ambiguous_mentions list — group candidates by the actual matched phrase and test distinct descriptions sharing that phrase.

Source: Codex read-only review, WP05 cycle 1, 2026-09-25. VERDICT: REJECT (five, all accepted).
