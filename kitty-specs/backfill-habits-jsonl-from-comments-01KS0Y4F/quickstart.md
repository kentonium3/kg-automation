# Quickstart — operator walkthrough for Phase 4 backfill

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Audience**: Kent (operator running the backfill once, post-Phase-4 merge)

---

## Pre-flight

- Phase 4 mission merged to main (this mission).
- Phase 3 Tier-2 migration applied (mission #40, commit `188268d`); 11 habit tasks exist in Vikunja.
- felix-bot token in place at `/data/services/openclaw/secrets/vikunja-api` (Phase 1 outcome).
- `/data/services/openclaw/state/habits-history.jsonl` exists (Phase 2 substrate; may be empty if no Phase 3 writes have happened yet).
- `scripts/common/state_log.py` importable (Phase 2 #305).

---

## Step 1 — Pull latest on office2

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull --rebase origin main'
```

Verify the backfill helper is present:

```bash
ssh office2-claude 'ls /home/claude/kg-automation/scripts/habits/backfill_jsonl_from_comments.py'
```

---

## Step 2 — Dry-run

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.backfill_jsonl_from_comments --dry-run'
```

Review the summary report. Confirm:

- **Records planned**: expected number for the current dataset (~24 with the locked `HISTORICAL_STATE_MAP`).
- **Unmapped state values**: should be empty (or only known-deferred values, e.g., `"will-not-do"` if that has somehow not yet been mapped).
- **Comments skipped as malformed**: should be 0 or very small (single digits).
- **Anomalies**: should be empty.

If the report names new unmapped state values, decide whether to:
1. Update `HISTORICAL_STATE_MAP` and re-dry-run (recommended for high-volume unmapped values).
2. Accept the unmapped values (those comments stay in Vikunja but don't land in JSONL).

---

## Step 3 — Live run

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.backfill_jsonl_from_comments'
```

Expected output:
- `Snapshot created: /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak`
- Per-task progress lines
- Final summary with `Records: Appended: <N>`

Verify exit code 0.

---

## Step 4 — Verify the JSONL log

```bash
ssh office2-claude 'wc -l /data/services/openclaw/state/habits-history.jsonl'
```

The line count should equal `Records: Appended: <N>` from the live run output (assuming the file was empty before).

Spot-check a few records:

```bash
ssh office2-claude 'head -3 /data/services/openclaw/state/habits-history.jsonl | python3 -m json.tool'
```

Each record should:
- Have `domain="habits"`.
- Have `source="historical-backfill"`.
- Have a `timestamp` that looks like a real past date (e.g., `"2026-04-10T07:00:00Z"`).
- Have a `state` value in `{complete, incomplete, skipped}`.

---

## Step 5 — Verify idempotency

Run the live command a second time:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.backfill_jsonl_from_comments'
```

Expected output in the summary:
- `Records: Appended: 0`
- `Records: Skipped (dedup with existing JSONL): <N>` (same N as the first run)

This confirms the dedup tuple is working as expected.

---

## Step 6 — Cleanup (optional, days later)

Once confident the backfill is correct, remove the `.bak` snapshot:

```bash
ssh office2-claude 'rm /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak'
```

This is optional — the snapshot is small and can stay indefinitely. Removing it is a tidiness gesture, not a requirement.

---

## Rollback (NO-GO recovery)

If the backfill went wrong (e.g., an unmapped state value got mis-mapped after editing `HISTORICAL_STATE_MAP`, and you want to start over):

```bash
ssh office2-claude 'cp /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak /data/services/openclaw/state/habits-history.jsonl'
```

This restores the JSONL log to its pre-backfill state. The `.bak` is preserved (no rename). Then fix `HISTORICAL_STATE_MAP` and re-run from Step 2.

Alternative: filter-based rollback (preserves Phase 5 forward writes if any have happened, which they shouldn't in Phase 4):

```bash
ssh office2-claude 'python3 -c "
import json, pathlib
path = pathlib.Path(\"/data/services/openclaw/state/habits-history.jsonl\")
lines = path.read_text().splitlines()
keep = [l for l in lines if l.strip() and json.loads(l).get(\"source\") != \"historical-backfill\"]
path.write_text(\"\\n\".join(keep) + (\"\\n\" if keep else \"\"))
print(f\"Kept {len(keep)} of {len(lines)} lines\")
"'
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Exit 2 with "Habits project not uniquely resolvable" | A second project also titled "Habits" exists, or the Habits project was renamed | Resolve via `GET /projects` to confirm; rename to restore uniqueness |
| Many "unmapped state values" in report | Production data has values not in HISTORICAL_STATE_MAP | Edit the map + re-run; or accept the unmapped values |
| Exit 3 with snapshot copy failure | Disk full, or `.bak` already exists with read-only perms | Free disk; remove or unlock `.bak` |
| Re-run shows non-zero Appended | Either (a) new comments were added to Vikunja between runs (expected), or (b) HISTORICAL_STATE_MAP was extended between runs (expected) | Both are normal; verify the deltas make sense |
| Vikunja API timeouts | office2 ↔ Vikunja network blip | Retry; consider extending HTTP_TIMEOUT_SECONDS in the helper if persistent |
