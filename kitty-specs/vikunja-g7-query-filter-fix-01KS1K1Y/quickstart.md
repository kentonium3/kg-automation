# Quickstart — operator deploy walkthrough for G7 fix

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Audience**: Kent (operator deploying the fix post-merge)

---

## Pre-flight

- This mission has merged to main.
- AGENTS.md hotfix (commit `4e7177c`) is already deployed to office2 (sha256 `3dbcf506…cb0b7eb`).
- felix-bot token present at `/data/services/openclaw/secrets/vikunja-api`.
- openclaw-gateway active on office2.

---

## Step 1 — Pull latest on the laptop

```bash
cd /Users/kentgale/repos/kg-automation
git pull --rebase origin main
shasum -a 256 scripts/habits/query_active_habits_v2.py
```

Note the local hash for Step 3.

---

## Step 2 — Deploy the updated helper to office2

The helpers live under `/home/claude/kg-automation/scripts/habits/` on office2. Sync just the modified file:

```bash
scp scripts/habits/query_active_habits_v2.py \
  office2-claude:/home/claude/kg-automation/scripts/habits/query_active_habits_v2.py
```

(Alternative: full repo sync via `git pull` on office2 if a kg-automation working tree is maintained there. As of 2026-05-20 the canonical mechanism is scp.)

---

## Step 3 — Verify the deploy

```bash
LOCAL=$(shasum -a 256 scripts/habits/query_active_habits_v2.py | awk '{print $1}')
REMOTE=$(ssh office2-claude 'sha256sum /home/claude/kg-automation/scripts/habits/query_active_habits_v2.py' | awk '{print $1}')
echo "Local:  $LOCAL"
echo "Remote: $REMOTE"
[ "$LOCAL" = "$REMOTE" ] && echo "VERIFIED" || echo "MISMATCH"
```

Expected: `VERIFIED`. If mismatch, re-run Step 2.

---

## Step 4 — Manual smoke-test of the helper

Invoke the helper directly on office2 to confirm it returns 200 + JSONL:

```bash
ssh office2-claude "cd /home/claude/kg-automation && python3 -m scripts.habits.query_active_habits_v2 --today \$(date -u +%Y-%m-%d)"
```

Expected:
- Exit code 0.
- Stdout: one JSON object per line (newline-delimited) describing today's active habit tasks. Example:
  ```
  {"id": 14, "title": "Wake at 5:00 AM", ...}
  {"id": 15, "title": "Meditate", ...}
  ...
  ```
- No HTTP 400 error.

If exit code != 0 OR stderr mentions HTTP 400: the fix failed. Inspect output, file an issue, and consider rollback.

---

## Step 5 — Trigger the morning cron manually (optional, end-to-end test)

If you want to validate the full check-in flow before waiting for tomorrow's 7 AM tick:

```bash
ssh office2-claude 'openclaw cron run 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

This triggers an off-schedule run. You'll receive a WhatsApp check-in immediately.

Check the session log for Step 2 success (no HTTP 400):

```bash
ssh office2-claude 'ls -lt /home/claude/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -1'
# Note the path, then:
ssh office2-claude 'grep -c "HTTP 400" <path>'
# Expected: 0
```

---

## Step 6 — Wait for next scheduled cron tick (recommended)

The next `habits-morning-checkin` cron tick is daily at 11:00 UTC (7:00 AM ET). The first tick post-deploy will exercise the v2 path end-to-end with no fallback.

---

## Rollback (high bar, expected unused)

If the helper change breaks something:

```bash
cd /Users/kentgale/repos/kg-automation
git revert <merge-commit>
git push origin main
# Then re-deploy the now-reverted version:
scp scripts/habits/query_active_habits_v2.py \
  office2-claude:/home/claude/kg-automation/scripts/habits/query_active_habits_v2.py
```

The v1 sibling (`query_active_habits.py`) is still on disk per #308 C-001, so the agent can fall back to v1 via the Step 4.5 helper-failure protocol if needed.
