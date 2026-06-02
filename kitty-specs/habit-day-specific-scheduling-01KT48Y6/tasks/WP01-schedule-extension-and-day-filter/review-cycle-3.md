---
affected_files: []
cycle_number: 3
mission_slug: habit-day-specific-scheduling-01KT48Y6
reproduction_command:
reviewed_at: '2026-06-02T14:48:06Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: `scripts/habits/set_due_dates.py` no longer works when invoked through the documented script-path CLI.

The new top-level import `from scripts.habits.schedule_loader import ...` fails when the helper is run as `python3 scripts/habits/set_due_dates.py ...`, because Python puts `scripts/habits/` on `sys.path` rather than the repo root. This breaks both the existing load-bearing `--iso-eod-et` mode and the new `--reconcile-schedule` mode before argparse can run.

Reproduction:

```bash
python3 scripts/habits/set_due_dates.py --habit-ids 1 --iso-eod-et 2026-05-15T23:59:59Z --dry-run
```

Observed:

```text
ModuleNotFoundError: No module named 'scripts'
```

Expected: the existing mode should reach the `Z`-suffix validation and return usage error 2, preserving issue #112 regression prevention. The new reconciliation mode should also be runnable via the WP's documented helper path.

Fix by preserving the existing executable surface for `set_due_dates.py` while still supporting package imports in tests, for example by using the local import pattern already common for path-invoked helpers or by adding a small script-safe import fallback. After fixing, verify at minimum:

```bash
python3 scripts/habits/set_due_dates.py --habit-ids 1 --iso-eod-et 2026-05-15T23:59:59Z --dry-run
python3 scripts/habits/set_due_dates.py --reconcile-schedule --dry-run --schedule-path tests/habits/fixtures/schedule_with_day_specific.yaml --reconcile-record-dir /tmp/wp01-reconcile-review
python3 -m pytest tests/habits/test_schedule_loader.py tests/habits/test_query_active_habits_v2_day_of_week.py tests/habits/test_morning_checkin_list_day_of_week.py tests/habits/test_set_due_dates_reconcile.py
```
