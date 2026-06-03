---
affected_files: []
cycle_number: 6
mission_slug: habit-day-specific-scheduling-01KT48Y6
reproduction_command:
reviewed_at: '2026-06-02T15:06:21Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: `scripts/habits/migrations/phase3-schedule.yaml` only seeds `designated_weekdays` for `Strength training — Friday` (`task_id: 15`). WP01 T001, `tasks.md`, `spec.md`, and `contracts/schedule-config.contract.md` all require the production runtime schedule to seed the two known day-specific habits: Wednesday and Friday strength training. With the current schedule, a Vikunja task titled `Strength training — Wednesday` is not represented as day-specific, so `query_active_habits_v2.py` will treat it as an unscheduled habit and pass it through as daily fallback. That preserves the original bug for the Wednesday task.

Fix: add the current production Wednesday strength-training task to the `habits:` runtime schedule with `designated_weekdays: ["Wed"]` and `repeat_after_seconds: 604800`, or provide concrete evidence that no Wednesday production task exists and update the mission artifacts accordingly. The referenced snapshot path was not available in this review environment, but the mission spec and contract explicitly identify Wednesday as in scope.

Validation notes: the cycle-1 direct-script import fix passes for `set_due_dates.py` and `query_active_habits_v2.py`. The claimed `morning_checkin_list.py` direct-script failure is pre-existing on `main` (`ModuleNotFoundError: No module named 'scripts'` from the existing `exclude_completed_v2` import). `python3 -m pytest tests/habits/ -q` passed with `546 passed`.
