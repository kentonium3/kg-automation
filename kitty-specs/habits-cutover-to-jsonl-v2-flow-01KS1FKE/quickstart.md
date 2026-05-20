# Quickstart — operator deploy walkthrough for Phase 5 cutover

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Audience**: Kent (operator deploying the cutover post-merge)

---

## Pre-flight

- This mission merged to main (the AGENTS.md edit is in the repo).
- Phase 4 backfill is complete (`habits-history.jsonl` has 31 records as of 2026-05-19).
- felix-bot token present at `/data/services/openclaw/secrets/vikunja-api`.
- openclaw-gateway active on office2.
- Restic snapshot exists from the last 24 hours.

---

## Step 1 — Pull latest on the laptop

The repo's `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` is now the v2 version. Verify:

```bash
cd /Users/kentgale/repos/kg-automation
git pull --rebase origin main
shasum -a 256 scripts/openclaw/agents/felix-admin-habits/AGENTS.md
```

Note the local hash (you'll compare it to the deployed hash in Step 3).

---

## Step 2 — Deploy via the runbook sync command

Per `docs/runbooks/habits-ops.md` § Update workspace files:

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

Expected: 5 lines of silent ssh exits. No output means success.

---

## Step 3 — Verify the deploy

```bash
LOCAL=$(shasum -a 256 scripts/openclaw/agents/felix-admin-habits/AGENTS.md | awk '{print $1}')
REMOTE=$(ssh office2-claude 'sha256sum /data/services/openclaw/habits-agent/AGENTS.md' | awk '{print $1}')
echo "Local:  $LOCAL"
echo "Remote: $REMOTE"
[ "$LOCAL" = "$REMOTE" ] && echo "VERIFIED" || echo "MISMATCH"
```

Expected: `VERIFIED`. If mismatch, re-run Step 2 and re-check.

---

## Step 4 — Wait for the next morning cron tick

The `habits-morning-checkin` cron runs daily at 7:00 AM ET (11:00 UTC). The next tick after Step 2 deploys will be the first to use the v2 workflow.

If you want to validate before waiting for the next-day cron, you can trigger the cron manually:

```bash
ssh office2-claude 'openclaw cron list 2>&1 | grep habits-morning-checkin'
# Get the UUID, then:
ssh office2-claude 'openclaw cron run <UUID-from-above>'
```

This triggers an off-schedule run. You'll receive a WhatsApp message immediately (assuming the cron-mode runs against your live phone number — verify the cron's `--to` flag if uncertain).

---

## Step 5 — Smoke-test the next cron output

After the cron tick:

1. **Check the WhatsApp message arrived** and has the expected structure (identity line, habit list, plus invitations to confirm completions).
2. **Inspect the cron run's session log**:

   ```bash
   ssh office2-claude 'ls -lt ~/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -3'
   ```

   Open the most recent session log and verify the agent invoked the v2 helpers in order:
   - `reconcile_completions` (Step 0)
   - `query_active_habits_v2` (Step 1)
   - `exclude_completed_v2` (Step 4 in the new numbering — gap-preserved)
   - `record_completion` (only after Kent's reply, in the response-handling flow)

3. **Check the JSONL log after Kent responds**:

   ```bash
   ssh office2-claude 'tail -3 /data/services/openclaw/state/habits-history.jsonl'
   ```

   After Kent confirms completions, the tail should show new records with `source="whatsapp"` and today's date.

---

## Step 6 — Verify the Tuesday structural fix

On the next Tuesday morning (7:00 AM ET), the cron should produce a check-in WITHOUT a workout task in the list. Wednesday's check-in should include "Strength training — Wednesday" (task id 76). Same for Friday (task 77) and the following Monday (task 75).

---

## Soak period (2-3 days)

During the 2-3 day soak, the operator monitors the morning check-ins for behavior parity:

- Are all habits surfacing correctly?
- Does Kent's natural-language response get recorded correctly?
- Are there any drift entries from the daily reconcile?
- Does the weekly report (Sunday 6 PM ET) consume the JSONL data correctly?

**Fail-forward posture (per spec C-007)**: non-catastrophic issues during soak become forward-fix follow-up commits or micro-issues. The mission's main commit is NOT reverted. Only catastrophic failures (cron silent for 24+ hours, agent crashes on every invocation, JSONL data corruption) trigger the rollback procedure below.

---

## Soak observation log (operator notes)

For each day of the soak, capture:

- Day N: did the morning check-in fire on time?
- Day N: did Kent respond? Did the response get recorded in JSONL?
- Day N: any drift warnings in reconcile output?
- Day N: any operator-side fix-up commits filed?

Soak ends when the operator declares it passed (default: 2-3 calendar days).

---

## Catastrophic rollback (high bar, expected unused)

If the cutover catastrophically fails:

```bash
cd /Users/kentgale/repos/kg-automation
git revert <cutover-commit-hash>
git push origin main
# Then re-sync to office2:
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

This restores the v1 workflow. The v1 scripts (`query_active_habits.py`, `exclude_completed.py`, `set_due_dates.py`) are still present on disk (C-001), so the cron resumes the v1 path on its next tick.

File an incident triage issue and step away from the cutover until root-cause understood.

---

## Post-soak (separate follow-up mission)

After the soak passes, a separate post-soak mission (filed as a new GitHub issue) handles the decommission:

- Delete v1 scripts (`query_active_habits.py`, `exclude_completed.py`, `set_due_dates.py` if not needed elsewhere)
- Rename `_v2.py` files to canonical names (per Q3=A discovery decision)
- Update AGENTS.md to drop the `_v2` suffix in the helper invocations
- Update `data-flows.json` to remove legacy-v1 entries
- Update `service-inventory.json` registrations
- Remove now-dead v1 tests

This is OUT OF SCOPE for the current mission. Don't combine the two.
