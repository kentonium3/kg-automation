---
affected_files: []
cycle_number: 4
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:40:45Z'
reviewer_agent: claude
wp_id: WP01
---

[MAJOR] scripts/research/arms849/serving.py — serialize() sends the registered text raw and ServingConfiguration records chat_template_applied=False — superseded by rubric §3.2 @939d9b29 (design lead, 2026-09-25 00:45Z/00:57Z): the registered text is the single user turn; apply the Qwen chat template CLIENT-SIDE via the cached tokenizer (apply_chat_template(add_generation_prompt=True, tokenize=False)); the templated string is the /completion `prompt`; count_tokens counts that string; record chat_template_applied=True + chat_template_sha256; prompt.verify stays over the registered text; docstring cites 939d9b29 over WP01 T004 step 4.

Source: design-lead read gate (GATE B) on the Codex-approved HEAD 4029e012; recorded as a fix cycle before merge.
