# F009 Data Model: Habit Completion Tracking

## Entities

### Habit (Vikunja task in Habits project)

| Field | Source | Example |
|-------|--------|---------|
| id | Vikunja task ID (auto) | 14 |
| title | Task title | "Meditate 45 min" |
| description | Completion criteria, frequency notes | "Daily. 45 min minimum." |
| labels | Identity label (personal/intentional/metalcasework) | personal |
| done | Always false (habits don't "complete") | false |
| project | Habits project (resolved by name) | Habits |

**Notes**: Habits are never marked `done: true` in Vikunja. The task
represents the recurring commitment, not a single instance. Frequency is
encoded in the description field (e.g., "Mon/Wed/Fri" or "Daily").

### Completion record (Vikunja task comment)

| Field | Source | Example |
|-------|--------|---------|
| id | Vikunja comment ID (auto) | 42 |
| task_id | Parent habit task ID | 14 |
| comment | Structured text | `[Felix] 2026-03-31 \| complete` |
| created | Comment timestamp (auto) | 2026-03-31T11:05:00Z |

**Comment format**:
```
[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note
```

**States**:
- `complete` — habit was done today
- `rescheduled` — habit will be done at a different time (counts positive)
- `will-not-do` — conscious skip (counts negative in reporting)
- No comment for a scheduled day = `no-response` (counts negative)

### Pattern report (computed, not stored)

| Field | Derivation |
|-------|-----------|
| habit_name | From habit task title |
| this_week_rate | (complete + rescheduled) / scheduled_days for Mon–Sun |
| last_week_rate | Same formula for prior Mon–Sun |
| overall_rate | Same formula across all habits |
| trend | this_week_rate vs. last_week_rate (up/down/same) |

## Vikunja project structure

```
Habits (project — resolve by name)
├── Wake at 5:00 AM          [personal] freq: Mon–Sat
│   └── comments: [Felix] 2026-03-31 | complete
│                  [Felix] 2026-03-30 | complete
│                  ...
├── Meditate 45 min           [personal] freq: Daily
├── Morning shoulder PT        [personal] freq: Daily
├── Strength training 45 min  [personal] freq: Mon/Wed/Fri
├── 10K steps (monthly avg)   [personal] freq: Daily
├── Read 30 min minimum       [personal] freq: Daily (evening)
└── Evening shoulder PT        [personal] freq: Daily
```

## Frequency encoding

Frequency is stored in the task description, not as Vikunja metadata.
The agent parses it to determine which habits are scheduled for today.

| Frequency | Description text | Scheduled days |
|-----------|-----------------|----------------|
| Daily | "Daily" | Mon–Sun |
| Mon–Sat | "Mon–Sat" | Mon, Tue, Wed, Thu, Fri, Sat |
| Mon/Wed/Fri | "Mon/Wed/Fri" | Mon, Wed, Fri |
| Daily (evening) | "Daily (evening)" | Mon–Sun |

## API operations

### Record completion (idempotent)

1. `GET /tasks/{habit_id}/comments?s=YYYY-MM-DD` — search for existing
2. If found: `POST /tasks/{habit_id}/comments/{comment_id}` — update
3. If not found: `PUT /tasks/{habit_id}/comments` — create

### Query history (90 days)

1. `GET /tasks/{habit_id}/comments?per_page=100&order_by=desc`
2. Parse comment text for date, state, optional note
3. Paginate if > 100 days needed

### Completion rate calculation

```
rate = (complete + rescheduled) / (complete + rescheduled + will-not-do + no-response)
```

Where `no-response` = scheduled days with no comment record.
