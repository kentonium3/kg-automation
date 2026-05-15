# Data Model — habits-checkin-d6-extract

The mission deals with data that already exists in Vikunja (the Habits project) and structured outputs the new helpers produce. No new persistent storage is introduced.

---

## Entities

### Habit

A Vikunja task in the Habits project.

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | int | Vikunja `tasks.id` | Primary identifier passed between helpers |
| `title` | string | Vikunja `tasks.title` | Human-readable habit name (e.g., "Meditate 45 min") |
| `description` | string | Vikunja `tasks.description` | Carries the **frequency descriptor** in plain text (e.g., "Daily", "Mon-Sat", "Mon/Wed/Fri", "Daily (evening)"). May also contain `(PAUSED)` marker for opt-out. |
| `done` | boolean | Vikunja `tasks.done` | If true, habit is excluded from all queries |
| `due_date` | ISO-8601 string \| null | Vikunja `tasks.due_date` | Mutated by `set_due_dates.py` to end-of-day-ET on scheduled days |
| `project_id` | int | Vikunja `tasks.project_id` | Used to filter to Habits project only |

**Validation rules**:
- Tasks with `description` containing `(PAUSED)` (case-insensitive) are excluded by `query_active_habits.py` regardless of other fields
- Tasks with `done = true` are excluded
- Tasks without a recognized frequency descriptor in `description` are skipped with a stderr warning (do not halt)

**Frequency descriptor lexicon** (canonical from current AGENTS.md):

| Frequency text | Scheduled days |
|---|---|
| `Daily` | Mon, Tue, Wed, Thu, Fri, Sat, Sun |
| `Daily (evening)` | Mon, Tue, Wed, Thu, Fri, Sat, Sun |
| `Mon–Sat` (en-dash) and `Mon-Sat` (ascii dash) | Mon, Tue, Wed, Thu, Fri, Sat |
| `Mon/Wed/Fri` | Mon, Wed, Fri |
| Other ad-hoc forms | parse with stderr warning; do not halt |

---

### Completion comment

A Vikunja comment on a habit task recording today's completion state.

| Field | Type | Notes |
|---|---|---|
| `task_id` | int | Habit being commented on |
| `comment` | string | Formatted as: `[Felix] YYYY-MM-DD \| {state} \| optional note` |
| `state` | enum | `complete` \| `rescheduled` \| `will-not-do` (any of these counts as "addressed") |

**Validation rules**:
- The literal prefix `[Felix]` is required for parser recognition
- Date is in `YYYY-MM-DD` format (Eastern time)
- States are normalized lowercase
- Optional note is free text after the third `|`

`exclude_completed.py` consumes these comments to determine "already addressed today" status.

---

### Today context

Output of `compute_today.py`. Passed as inputs to subsequent helpers.

| Field | Type | Example | Notes |
|---|---|---|---|
| `day` | string | `"Wed"` | Three-letter day abbreviation, Eastern time |
| `date` | string | `"2026-05-15"` | `YYYY-MM-DD` Eastern time |
| `et_offset` | string | `"-04:00"` | UTC offset for Eastern time at this moment |
| `iso_eod_et` | string | `"2026-05-15T23:59:59-04:00"` | End-of-day ISO timestamp, used as `due_date` value |

**Validation rules**:
- `day` is one of `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun`
- `et_offset` is either `-04:00` (EDT) or `-05:00` (EST)
- `iso_eod_et` MUST NOT end with `Z` (UTC) — this would re-introduce the #112 bug

---

### Helper output envelopes

Each helper emits JSON to stdout. All envelopes follow a common shape (no formal schema validation required; convention is enforced by tests):

#### `compute_today.py` output

```json
{"day": "Wed", "date": "2026-05-15", "et_offset": "-04:00", "iso_eod_et": "2026-05-15T23:59:59-04:00"}
```

Plus a final `SUMMARY:` line.

#### `query_active_habits.py` output

```json
{
  "habits": [
    {"id": 123, "title": "Meditate 45 min", "description": "Daily", "due_date": "..."},
    {"id": 124, "title": "Strength training 45 min", "description": "Mon/Wed/Fri", "due_date": "..."}
  ],
  "total_in_project": 12,
  "scheduled_today": 2
}
```

#### `set_due_dates.py` output

```json
{
  "succeeded": [123, 124],
  "failed": [{"id": 125, "reason": "HTTP 500: ..."}]
}
```

#### `exclude_completed.py` output

```json
{
  "ready_for_checkin": [123, 124],
  "already_addressed": [{"id": 125, "state": "complete"}],
  "total_checked": 3
}
```

---

## State transitions

The mission does not introduce new state-transition logic. Existing Vikunja state transitions (`done: false → true`, due_date updates, comment additions) are preserved unchanged. The only change is the locus of execution: helpers perform the API calls instead of the agent prompt.

---

## Out-of-scope data concerns

- Habit creation/editing/removal — out of scope (deferred to Phase 4 rank #6)
- Weekly completion-history aggregation — out of scope (deferred to Phase 4 rank #6)
- Goal-relationship linking — never been in habits scope; remains so
- Cross-day completion-state inference — out of scope (single-day check-in only)
