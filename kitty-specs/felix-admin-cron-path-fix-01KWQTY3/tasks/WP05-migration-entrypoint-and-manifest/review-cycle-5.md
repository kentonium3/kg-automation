---
affected_files: []
cycle_number: 5
mission_slug: felix-admin-cron-path-fix-01KWQTY3
reproduction_command:
reviewed_at: '2026-07-05T05:11:11Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

SCOPE CHANGE (operator decision A — #659 filed): NARROW WP05 to an inbox-only, non-destructive migration.

- Migrate ONLY the inbox state (inbox-routing.jsonl + pending-calendar-clarifications.* if present) to /data/services/openclaw/state/ with strict perms + the accepted union-merge (divergent ledger) / conflict-abort safety.
- Copy ONLY the top-level inbox forensic logs (agents/logs/inbox-prescan-*.md) to the /home/kgale vault. Do NOT recurse into the per-agent log subdirs (enrichment, felix-admin-*, ...).
- Do NOT inventory / quarantine / remove the /home/claude/second-brain tree. LEAVE IT IN PLACE — it hosts the active observation-digest subsystem (scripts/openclaw/observation/config.py, felix-core-digest) which is out of scope. The FULL decommission is the fast-follow #659.
- Manifest post-checks: verify state migrated + perms + inbox-prescan logs in vault. Do NOT assert /home/claude/second-brain is gone.
- Update tests accordingly: keep union-merge/perms/idempotency; add an assertion that the tree + observation subdirs are LEFT INTACT; drop the quarantine/decommission tests.

See the updated WP05 prompt (Objectives + T016-T018) and spec FR-008/SC-5 (narrowed) for the authoritative scope.
