---
affected_files: []
cycle_number: 10
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:33:06Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:599 — Mount validation unconditionally accepts `/etc/hostname` — an excluded file bound there escapes source/content validation and all denied-path checks; the extracted mount-check code accepts this case (Docker reproduction unavailable) — verify Docker-managed mount identities and add a negative test mounting an excluded file at `/etc/hostname`.

Source: Codex read-only review, WP02 cycle 10, 2026-09-25. VERDICT: REJECT (cycle-9 confirmed fixed; one new — docker-managed /etc binds accepted unconditionally). Disposition: verify their mount SOURCE identity via /proc/self/mountinfo (…/containers/<64hex>/<name>) plus content sanity; live negative binds an excluded file at /etc/hostname.
