# Quickstart — Day-Specific Habit Scheduling with Auto-Skip on Miss

**Mission**: `habit-day-specific-scheduling-01KT48Y6`
**Audience**: Operator (Kent) and the felix-admin-habits agent

---

## What you get

1. **Day-specific habit visibility.** Habits with `designated_weekdays` in `phase3-schedule.yaml` appear in the morning check-in only on their designated weekday. Daily habits (no `designated_weekdays`) appear every day, unchanged.

2. **48hr response window.** Each habit instance stays open for 48 hours after its check-in delivery (7:05 AM ET). Kent can reply to yesterday's check-in on today's morning and the parser correlates correctly.

3. **Daily sweeper.** Runs at 7:30 AM ET. Identifies check-in artifacts >48 hours old with unresolved habits, appends `auto_skipped` events to `habits-history.jsonl`, advances day-specific habits' Vikunja `due_date` to next designated weekday.

4. **Manual reconciliation.** When `designated_weekdays` is changed mid-week, operator runs `set_due_dates.py --reconcile-schedule` to advance affected habits' `due_date` to next new designated weekday.

---

## 30-second health check

```bash
ssh office2-claude 'cat /data/services/openclaw/state/habits/sweeper-tick-$(TZ=America/New_York date +%Y-%m-%d).json | jq "{exit_status, started_at_utc, errors, habits_auto_skipped: [.habits_auto_skipped[] | .task_id]}"'
```

Expected: `exit_status == "success"`, `errors == []`, `started_at_utc` within last ~24 hours.

---

## Edit a habit's day-of-week assignment

1. Edit `scripts/habits/migrations/phase3-schedule.yaml`:
   ```yaml
   - task_id: 17
     title: "Strength training — Wednesday"
     designated_weekdays: ["Wed"]    # ← change this, e.g., to ["Mon"]
     repeat_after_seconds: 604800
   ```
2. Commit + push.
3. On office2: `cd ~/kg-automation && git pull --ff-only`
4. Run reconciliation:
   ```bash
   ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.habits.set_due_dates --reconcile-schedule'
   ```
5. Verify the reconciliation record:
   ```bash
   ssh office2-claude 'ls -1t /data/services/openclaw/state/habits/reconcile-*.json | head -1 | xargs cat | jq "{reconciled_at_utc, habits_reconciled}"'
   ```

---

## Sweeper troubleshooting

| Symptom | First check |
|---|---|
| Sweeper unit failed | `ssh office2-claude 'systemctl --user status felix-habit-sweeper.service --no-pager'` — read the journal for error context. |
| Habit auto-skipped that Kent thinks he replied for | Inspect the relevant check-in's morning-checkin artifact + the reply log. Was the reply within 48hr of check-in delivery? Did the reply parser correlate correctly? See `parse_morning_reply` test fixtures for the canonical reply patterns. |
| Habit NOT auto-skipped when expected | Inspect `sweeper-tick-<date>.json` — was the check-in date in `expired_checkin_dates_evaluated`? Was the habit in `habits_evaluated[]`? Check its `status`. |
| Operator-edit needed | `habits-history.jsonl` is append-only by convention but operator-edits are allowed for rare overrides. Append a new event with explicit `event_type: "operator_override"` describing the correction; don't delete history. |

---

## Force a manual sweeper tick

For testing or dry-run validation:

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.habits.sweeper --dry-run'
```

Inspect the would-be tick artifact at the path printed in stdout.

For production-state tick (rare; the timer normally handles this):

```bash
ssh office2-claude 'systemctl --user start --wait felix-habit-sweeper.service'
```

---

## Cost & token usage

This mission is **fully deterministic** — zero LLM calls. No Anthropic API spend. Per Directive 6 compliance.

---

## Cross-references

- [Spec](./spec.md)
- [Plan](./plan.md)
- [Research](./research.md) — OD-1..OD-5 decisions
- [Data model](./data-model.md)
- [Contracts](./contracts/)
- **Architectural precedent**: [`docs/runbooks/doc-auditor-driver-ops.md`](../../docs/runbooks/doc-auditor-driver-ops.md) (felix-doc-auditor pattern this mission inherits)
- **Mission #282** (helper-scripts refactor that established the Directive 6 pattern for habits)
- **Issue #112** (UTC-vs-ET due_date regression-prevention) — must remain intact (NFR-005)
- **Source issue**: [#408](https://github.com/kentonium3/kg-automation/issues/408)
