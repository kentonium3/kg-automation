# Quickstart / Verification: Deterministic escalation + weekly-report crons

## Local (offline, in CI)
```bash
make test   # includes the 3 new suites:
python3 -m pytest tests/common/test_vikunja_scope.py tests/escalation/test_enumerate_candidates.py tests/habits/test_weekly_report_driver.py -q
```
All deterministic — fake VikunjaClient + fake subprocess/send; no network, no LLM.

## Live probe (office2, read-only) — enumeration fidelity
```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.escalation.enumerate_candidates'
```
Expect a JSON array of qualifying tasks (or `[]`). Cross-check a couple against the Vikunja UI (overdue, priority>=2, not in Goals/Habits).

## Live probe (office2) — weekly driver dry-run (no send)
```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.weekly_report_driver --dry-run'
```
Expect: the composed message printed (attribution line + verbatim report), `openclaw message send --dry-run` payload, no state written.

## Post-deploy live verification (SC-001..004)
- Trigger the escalation cron on-demand; assert no tool error and `openclaw-cron-state` reports `escalation-daily` healthy.
- Start the weekly unit once: `systemctl --user start felix-habits-weekly.service`; assert a fresh `last-tick.json` and a delivered WhatsApp report.
- Canary: `felix-habits-weekly` fresh; `habit-checkin` healthy (now scoped to `habits-morning-checkin`); both formerly-failing services no longer `failed`.
- #714 swap rehearsal (SC-003): flip `habit_selector` to a label form in a throwaway config and assert selection logic needs no code edit (unit test proves it).
