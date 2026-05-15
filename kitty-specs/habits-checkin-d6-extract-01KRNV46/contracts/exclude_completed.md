# Contract: `scripts/habits/exclude_completed.py`

**FR**: FR-004 (Completion exclusion helper)
**Invocation tier**: Helper
**Run frequency**: Once per `habits-morning-checkin` cron invocation

---

## Purpose

For each scheduled habit ID, query its Vikunja comments and determine whether it has already been addressed today (state of `complete`, `rescheduled`, or `will-not-do`). Return the subset of habit IDs that are NOT yet addressed — these become the check-in message.

Exists because the current agent prompt encodes the comment-format parser (`[Felix] YYYY-MM-DD | state | optional note`) — high-criticality (wrong filter sends duplicate check-ins to Kent for already-done habits), high hallucination risk (comment format is format-sensitive, easy to misparse).

---

## CLI

```
python3 scripts/habits/exclude_completed.py --habit-ids <comma-separated-int-list>
                                            --today <YYYY-MM-DD>
                                            [--vikunja-token-path <path>]
                                            [--vikunja-base-url <url>]
```

| Flag | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `--habit-ids` | string | YES | — | Comma-separated integers. From `query_active_habits.py` output (after `set_due_dates.py`). |
| `--today` | string | YES | — | `YYYY-MM-DD` in Eastern time. From `compute_today.py` output `date` field. |
| `--vikunja-token-path` | path | No | `/data/services/openclaw/secrets/vikunja-api` | Override for testing. |
| `--vikunja-base-url` | URL | No | `https://office2.tail0f5f56.ts.net/api/v1` | Override for testing. |

---

## Output

### stdout (JSON object, then SUMMARY line)

```json
{
  "ready_for_checkin": [123, 124],
  "already_addressed": [{"id": 125, "state": "complete", "comment_id": 9876}],
  "total_checked": 3
}
```

```
SUMMARY: total=3 ready=2 addressed=1 complete=1 rescheduled=0 will-not-do=0
```

**Field contract:**
- `ready_for_checkin`: ordered list (ascending by id) of habit IDs that should appear in today's check-in message
- `already_addressed`: list of habits already addressed today. Each item has `id`, `state` (one of `complete`/`rescheduled`/`will-not-do`), and `comment_id` (which Vikunja comment recorded the state — useful for audit-trail)
- `total_checked`: count equal to `len(habit_ids)` from input

### stderr

Used for warnings on malformed `[Felix]` comments (skipped, don't halt):

```
WARN: habit 125 comment 9999 has malformed Felix prefix; ignoring
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (any number of habits returned, including all-addressed) |
| 1 | Operational error (Vikunja unreachable, comment fetch failed) |
| 2 | Usage error (malformed `--today`, malformed habit IDs) |

---

## Side effects

Read-only. No Vikunja mutations. Idempotent by definition.

---

## Comment parsing rules

Per [`data-model.md` § Completion comment](../data-model.md#completion-comment):

- Comment must start with literal prefix `[Felix]` (case-sensitive); other comments ignored
- Format: `[Felix] YYYY-MM-DD | {state} | optional note`
- State is matched case-insensitively against the lexicon: `complete`, `rescheduled`, `will-not-do`
- A habit is "addressed" if ANY of its comments matches this format AND has `YYYY-MM-DD == --today` AND `state ∈ lexicon`
- Multiple addressed-comments on the same habit: use the most recent (highest `comment_id`); only that one is reported in `already_addressed`
- Comments with malformed `[Felix]` prefix produce a stderr WARN but don't halt processing

---

## Test coverage (NFR-005)

Tests at `tests/habits/test_exclude_completed.py`:

| Test | Scenario |
|---|---|
| `test_no_comments_all_ready` | Mock: habits with no comments; all in `ready_for_checkin` |
| `test_complete_today_addressed` | Mock: habit has `[Felix] 2026-05-15 \| complete`; habit in `already_addressed` with state `complete` |
| `test_rescheduled_today_addressed` | Mock: habit has `[Felix] 2026-05-15 \| rescheduled \| this afternoon`; habit in `already_addressed` |
| `test_will_not_do_today_addressed` | Mock: habit has `[Felix] 2026-05-15 \| will-not-do \| rest day`; habit in `already_addressed` |
| `test_yesterday_comment_ignored` | Mock: habit has `[Felix] 2026-05-14 \| complete`; habit in `ready_for_checkin` (yesterday doesn't count) |
| `test_non_felix_comment_ignored` | Mock: habit has comment `Random user note`; doesn't match; habit in `ready_for_checkin` |
| `test_multiple_addressed_uses_most_recent` | Mock: habit has 2 today-comments; helper reports the higher `comment_id` |
| `test_malformed_felix_prefix_warned` | Mock: habit has `[Felix YYYY-MM-DD]` (missing pipe); stderr WARN, habit treated as ready |
| `test_empty_habit_ids` | `--habit-ids ""`; exit 0 with all-empty arrays |
| `test_vikunja_unreachable` | Mock: connection error; exit 1 |
