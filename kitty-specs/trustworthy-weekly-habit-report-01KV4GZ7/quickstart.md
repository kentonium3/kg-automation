# Quickstart: Trustworthy weekly habit report — post-merge verification

This is the operator-facing checklist for confirming the mission ships correctly after `spec-kitty merge` lands the change on `main` and the deploy pipeline applies the cron + agent-prompt changes to office2.

## 1. Local verification (immediately after merge)

```bash
cd /Users/kentgale/repos/kg-automation
git pull
pytest tests/habits/ tests/architectural/test_habits_history_canonical_read.py -v
```

Expected: all green.

Spot-check the architectural test by faking a violation:

```bash
echo "from scripts.common.vikunja_client import VikunjaClient" > /tmp/bad_habit.py
# (just illustrative — don't actually add files to scripts/habits/)
```

The test's negative-control case should already verify this internally.

## 2. Deploy verification (after felix-deployer applies the manifest)

The deploy manifest at `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` reschedules the openclaw cron AND copies the updated AGENTS.md.

After felix-deployer reports success:

```bash
ssh office2-claude '
  # Confirm cron is on the new schedule:
  openclaw cron list --agent felix-admin-habits 2>&1 | grep -E "(0 6|0 22)"

  # Confirm AGENTS.md is updated:
  grep -E "(0 6 \\* \\* 1|Monday 06:00|0 22 \\* \\* 0|Sunday 22:00)" \
    ~/repos/kg-automation/scripts/openclaw/agents/felix-admin-habits/AGENTS.md
'
```

Expected:
- `openclaw cron list` shows `0 6 * * 1` and does NOT show `0 22 * * 0`.
- `grep` on AGENTS.md returns the new schedule lines and NO old-schedule lines.

## 3. Manual smoke (run the helper once on demand)

```bash
ssh office2-claude '
  cd ~/repos/kg-automation
  python3 -m scripts.habits.query_active_habits_weekly --output text
'
```

Expected: stdout shows a WhatsApp-formatted message with non-zero percentages for any habit Kent completed during the prior 7 days. Window label format is `(Mon Jun X–Sun Jun Y)` or equivalent 7-day form.

## 4. First Monday tick — production verification

Monday 06:00 ET after merge: confirm WhatsApp message arrives.

Spot-check the percentages against `habits-history.jsonl` ground truth:

```bash
ssh office2-claude '
  # For a habit Kent completed twice during the prior 7 days:
  TASK_ID=<some habit task_id>
  jq -c "select(.task_id == $TASK_ID)" \
    /data/services/openclaw/state/habits-history.jsonl | tail -10
'
```

Match the count of recent `complete` records against the percentage reported.

## 5. Rebaseline obligation (per #557)

felix-admin-habits AGENTS.md and the deploy manifest are audited surfaces. Run the canonical rebaseline post-deploy:

```bash
ssh office2-claude '
  rm /data/services/security-monitor/baselines/* && \
  sg docker -c /data/services/security-monitor/scripts/audit.sh
'
```

Record `Rebaseline: completed at <ts>` in the mission's merge commit footer (or `Rebaseline: not required — <reason>` if appropriate; here it IS required because both audited surfaces are touched).

## 6. Architecture documentation cross-check

```bash
cd /Users/kentgale/repos/kg-automation
jq -r '.services.felix.agents."felix-admin-habits".purpose' \
  docs/design/architecture/data/service-inventory.json \
  | grep -i "habits-history\|canonical\|done_at"
```

Expected: the description references `habits-history.jsonl` as the canonical-read for the weekly tick and does NOT claim it reads Vikunja `done_at` for completion history.

## 7. Issue closeout

```bash
gh issue close 605 --repo kentonium3/kg-automation --comment "Merged via $(git rev-parse HEAD). Verified: <SC-001 spot-check summary>; cron arrives Monday morning per SC-002; architectural test live per SC-003; golden-week fixture green per SC-004."
```

## Rollback procedure

If the first Monday tick produces wrong percentages, rolling back is straightforward because the helper's input data (`habits-history.jsonl`) was unchanged:

```bash
# On main:
cd /Users/kentgale/repos/kg-automation
git revert <merge_commit_sha>
git push

# Re-deploy the prior cron schedule (manually queue a counter manifest, or rely on git revert to restore the prior deploy state).
```

The bug-class regression that's harder to roll back: the architectural test. If a future commit needs to import VikunjaClient legitimately, add the file to the allowlist with a reason comment in the test.
