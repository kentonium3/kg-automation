# TOOLS.md

## Vikunja API

- Use the vikunja_api skill for all Vikunja operations
- Run `openclaw skills info vikunja_api` for details
- **Habits project**: the canonical project-id source is `scripts/common/vikunja_refs.json` — the deterministic habit helpers resolve the Habits project there. Do NOT inline numeric ids here (they churn; #715/#717 already moved them once).
- For your own ad-hoc habit operations (add/pause/resume/remove), resolve the project by name "Habits" via the `vikunja_api` skill.

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. When setting due_date via the Vikunja API, include the ET
offset (-04:00 for EDT, -05:00 for EST). Never use the Z (UTC) suffix
for due dates.

## Habit completion storage

- Each habit = one task in the Habits project
- Daily completion = comment on the habit task
- Comment format: `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note`
- Search for existing comment before creating (idempotent)
