---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T00:51:57Z'
reviewer_agent: claude
wp_id: WP01
---

[MAJOR] scripts/research/arms849/prompt.py:108 — Question substitution searches already-inserted context — a block containing `{question_text}` is altered while the actual question slot remains unfilled — substitute both slots in one pass over the original template.
[MAJOR] scripts/research/arms849/text.py:141 — Record digest uses load order instead of required key order — the actual corpus produces different digests under these orderings, contradicting T001 — sort record keys when hashing and assert the independently calculated digest.
[MAJOR] scripts/research/arms849/text.py:73 — Block accepts mutable `bytearray` data — reproduced mutation changes its SHA after construction, violating the frozen-bytes contract — require `bytes` and test rejection of `bytearray`.

Source: Codex read-only review (gpt-6-astra), cycle 1, 2026-09-25 00:47Z. VERDICT: REJECT. Fixed in lane-a @95489899.
