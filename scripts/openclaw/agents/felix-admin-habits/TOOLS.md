# TOOLS.md

## Vikunja API

- Use the vikunja_api skill for all Vikunja operations
- Run `openclaw skills info vikunja_api` for details
- **Habits project**: resolve by name "Habits" at runtime (id=13)
- **Habit task IDs**: 14-20 (7 habits, all personal label)

## Habit completion storage

- Each habit = one task in the Habits project
- Daily completion = comment on the habit task
- Comment format: `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note`
- Search for existing comment before creating (idempotent)

## Privacy

- NEVER access: `/home/kgale/second-brain/notes/02-Growth/_private/`
