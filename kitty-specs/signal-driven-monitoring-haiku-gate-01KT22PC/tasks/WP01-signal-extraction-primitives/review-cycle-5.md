---
affected_files: []
cycle_number: 5
mission_slug: signal-driven-monitoring-haiku-gate-01KT22PC
reproduction_command:
reviewed_at: '2026-06-01T18:30:54Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: Multi-file cursor handling re-counts older logs on every cycle.

In `scripts/openclaw/observation/signals/_engine.py`, `run_extraction()` iterates every path returned by `resolve_log_files()`, but applies the saved cursor only to the file whose path+inode matches. Every other resolved file is read from byte 0. Because the seed config uses `/tmp/openclaw/openclaw-*.log`, any older retained log file is re-read and re-counted on every subsequent cycle after the cursor has advanced to the newest file. That violates the incremental extraction contract and will inflate `count_cycle`/`count_rolling` in WP02.

Reproduction I ran in review:

```text
first pass over older(2 matches)+newer(1 match): count_cycle=3, cursor=newer
second pass with that cursor and no new writes: count_cycle=2
```

Expected second pass count is `0`.

Fix by making the persisted cursor semantics sufficient to avoid re-reading already consumed older files. Acceptable approaches include narrowing iteration to the cursor file plus files newer than the cursor, recording per-file cursors, or otherwise skipping resolved files that are known to be fully consumed. Add a regression test with two resolved logs where the second extraction using the first extraction's `new_cursor` returns `count_cycle == 0`.

Downstream impact: WP02 and WP04 depend on WP01. If they have started from this implementation, they should rebase after this fix lands.
