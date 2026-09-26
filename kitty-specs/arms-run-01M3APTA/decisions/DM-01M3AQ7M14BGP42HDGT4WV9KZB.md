# Decision Moment `01M3AQ7M14BGP42HDGT4WV9KZB`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `specify`
- **Slot key:** `specify.rules.oracle-isolation`
- **Input key:** `oracle_isolation_enforcement`
- **Status:** `resolved`
- **Created:** `2026-09-24T22:05:32.068856+00:00`
- **Resolved:** `2026-09-24T22:06:25.186331+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

The rule that must always hold: no arm may see the hidden oracle. Today that is a convention. Should the run enforce it structurally, and how?

## Options

- Harness refuses to start if any arm module references the oracle path, AND arms execute in a worktree where oracle/ is absent
- Static check only: harness scans arm code for the oracle path before the run
- Convention plus code review is sufficient
- Other

## Final answer

A — enforce structurally twice: harness refuses to start if any arm module references the oracle path, AND arms execute from an environment where oracle/ physically does not exist

## Rationale

_(none)_

## Change log

- `2026-09-24T22:05:32.068856+00:00` — opened
- `2026-09-24T22:06:25.186331+00:00` — resolved (final_answer="A — enforce structurally twice: harness refuses to start if any arm module references the oracle path, AND arms execute from an environment where oracle/ physically does not exist")
