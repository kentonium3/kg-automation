---
affected_files: []
cycle_number: 5
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:57:59Z'
reviewer_agent: claude
wp_id: WP01
---

[MAJOR] scripts/research/arms849/serving.py:308 — `**config.sampling` overwrites the verified templated prompt — reproduced with `sampling["prompt"]="UNTEMPLATED"` while `chat_template_applied=True`; all 17 tests still pass — reject unregistered sampling keys, protect authoritative request fields, and add an override regression test.

Source: Codex read-only review, WP01 cycle 4, 2026-09-25, on 092427a3. VERDICT: REJECT (one MAJOR). Design-lead verdict on the same HEAD: APPROVE with three hygiene nits (text.py prefix docstring; dead default=str; importlib.reload → subprocess) — folded into the same fix commit.
