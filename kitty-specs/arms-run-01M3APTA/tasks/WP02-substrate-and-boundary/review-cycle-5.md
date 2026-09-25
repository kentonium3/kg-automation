---
affected_files: []
cycle_number: 5
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:00:52Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:579 — Mount validation accepts a checkout bind at `/dev/shm` — the allowlisted destination passes even with an unexpected filesystem/source, exposing excluded material without detection — validate mount types and bind identities; add this negative case.
[MAJOR] tests/research/test_arms849_isolation.py:55 — Numeric expressions still bypass isolation scanning — reproduced `f"{110 + 1:c}racle"` evaluating to the forbidden string while both checks pass — preserve typed constants through supported arithmetic and add regression coverage.
[MAJOR] scripts/research/arms849/substrate.py:77 — Runner-image identity ignores `requirements-arms849.txt` — changing dependency pins leaves the tag unchanged, so `_ensure_runner_image()` reuses an image with stale dependencies — hash both Dockerfile and requirements when deriving the tag.

Source: Codex read-only review, WP02 cycle 5, 2026-09-25. VERDICT: REJECT (cycle-4 three confirmed fixed; three new — allowlisted-destination bind not identity-checked; arithmetic on numeric constants not folded; image tag ignores requirements).
