# Phase 1 Data Model: Vikunja client + habits weekly report

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT`
**Spec**: [spec.md](./spec.md) (revision 2) | **Plan**: [plan.md](./plan.md) (revision 2) | **Research**: [research.md](./research.md)

Entities and their lifecycle. The deterministic surfaces (client + helper) are well-specified; the agent's rendering surface is stochastic but constrained by the JSON contract and the output-discipline Hard Rules.

---

## Entity: VikunjaClient (new, persistent within a single process)

Public API surface of `scripts/common/vikunja_client.py`. Stateless per-instance: each instantiation reads the token + base URL freshly OR receives them as constructor arguments.

| Field / method | Type | Notes |
|---|---|---|
| `base_url` | str | Resolved at construct time via `get_vikunja_base_url()` unless overridden. Trailing slash stripped. |
| `token` | str | Resolved at construct time from `/data/services/openclaw/secrets/vikunja-api` unless overridden. Cached in memory; never logged. |
| `timeout` | float | Default 30.0 seconds; overridable per-call. |
| `get(path, params=None, timeout=None)` | method | Returns parsed JSON or raises typed exception. |
| `post(path, json=None, params=None, timeout=None)` | method | Returns parsed JSON or raises typed exception. |
| `put(path, json=None, params=None, timeout=None)` | method | Returns parsed JSON or raises typed exception. |
| `delete(path, params=None, timeout=None)` | method | Returns parsed JSON (often empty dict) or raises typed exception. |

**Validation rules**:
- `base_url` must match the canonical Vikunja API base URL pattern (`https?://[^/]+/api/v1`); ValueError on malformed.
- `token` must be a non-empty string; ValueError on empty.
- `timeout` must be positive; ValueError on non-positive.

**Lifecycle**:
1. Created via `VikunjaClient()` (defaults) or `VikunjaClient(base_url=..., token=..., timeout=...)`.
2. Per-call methods compose the full URL, attach the Authorization header, execute via `urllib.request.urlopen`, parse JSON, return result OR raise.
3. No state survives between method calls beyond the construct-time captured `base_url`, `token`, `timeout`.

---

## Entity: VikunjaError hierarchy (new exception classes)

All exceptions inherit from `VikunjaError(Exception)`. Each carries `path` (the request path that triggered the error), default-redacted body content (opt-in verbose mode for debugging).

| Class | Maps to | Notes |
|---|---|---|
| `VikunjaError` | (base) | Base class; never raised directly. |
| `VikunjaHttpError` | Unhandled HTTP error codes | Catch-all for HTTP failures not covered by specific classes. |
| `VikunjaAuthError` | 401 | Token expired or invalid. |
| `VikunjaNotFoundError` | 404 | Resource not found. |
| `VikunjaBadRequestError` | 400 | Malformed request (often filter syntax error per memory `reference_vikunja_filter_gotchas.md`). |
| `VikunjaServerError` | 5xx | Vikunja down or returning errors. |
| `VikunjaTimeoutError` | Network timeout | Request exceeded `timeout` seconds. |

**Validation rules**:
- All exceptions carry `path: str` and `status: int | None` (None for timeout). Default `__str__` returns `f"{type(self).__name__}: {self.path}"` — no body content.
- Verbose mode opt-in via `str(exc.verbose_message())` or similar — included for ad-hoc debugging, never logged by default.

---

## Entity: HabitClassifier (new, pure function in the weekly helper)

Pure function in `scripts/habits/query_active_habits_weekly.py`. Takes a Vikunja task dict, returns the habit kind.

| Function | Signature | Notes |
|---|---|---|
| `classify_habit(task: dict) -> HabitKind` | Returns `"daily"`, `"weekday-in-title"`, or `"other"` | Per FR-004 rules. |
| `scheduled_days_for_window(kind, title, window_start, window_end) -> int` | Returns the number of scheduled days within the window | Daily → number of complete days; weekday-in-title → number of matched-weekday occurrences. |
| `parse_weekday_in_title(title) -> set[str] \| None` | Returns ISO weekday names found in the title, or None | Regex match against `(Mon\|Tue\|Wed\|Thu\|Fri\|Sat\|Sun)(day)?` (case-insensitive). |

**Rules** (per FR-004):
- `repeat_after == 86400 AND parse_weekday_in_title(title) is None → kind = "daily"`. Scheduled_days = 7 per week.
- `repeat_after == 0 AND parse_weekday_in_title(title) is not None → kind = "weekday-in-title"`. Scheduled_days = count of matched weekdays in the window.
- `repeat_after == 0 AND parse_weekday_in_title(title) is None → kind = "other"`. Filtered out per FR-006 (non-habit).
- `repeat_after > 0 AND repeat_after != 86400 → kind = "other"`. Defer to plan-phase rule; defaults to "other" (filtered out) unless documented otherwise.

---

## Entity: HabitCompletion (transient, in the helper)

Internal data structure during helper execution. Not exposed in the output JSON; consumed during aggregation.

| Field | Type | Notes |
|---|---|---|
| `habit_title` | str | The canonical habit title from Vikunja. |
| `habit_kind` | str | `"daily"`, `"weekday-in-title"`, or `"other"`. |
| `done_at` | datetime | When the task was marked done. |
| `task_id` | int | The Vikunja task id (useful for audit trail). |

**Lifecycle**:
1. Built by the helper from each task returned by `?filter=done=true` whose `done_at` falls in the current OR prior window.
2. Aggregated by `habit_title` to produce the WeeklyHabitReport row.

---

## Entity: WeeklyHabitReport (new, JSON output of the helper)

The structured payload the agent consumes for rendering. Helper writes to stdout; agent parses.

```json
{
  "window_start_iso": "2026-06-01T00:00:00Z",
  "window_end_iso": "2026-06-08T00:00:00Z",
  "prior_window_start_iso": "2026-05-25T00:00:00Z",
  "prior_window_end_iso": "2026-06-01T00:00:00Z",
  "habits": [
    {
      "habit_title": "Meditate",
      "habit_kind": "daily",
      "scheduled_days_current": 7,
      "completed_events_current": 6,
      "percent_current": 85.7,
      "scheduled_days_prior": 7,
      "completed_events_prior": 5,
      "percent_prior": 71.4
    },
    {
      "habit_title": "Strength training — Monday",
      "habit_kind": "weekday-in-title",
      "scheduled_days_current": 1,
      "completed_events_current": 1,
      "percent_current": 100.0,
      "scheduled_days_prior": 1,
      "completed_events_prior": 0,
      "percent_prior": 0.0
    }
  ],
  "overall_percent_current": 78.5,
  "overall_percent_prior": 62.1
}
```

**Validation rules**:
- `window_start_iso` < `window_end_iso`; `prior_window_end_iso` == `window_start_iso`.
- `habits` is sorted by some canonical order (plan-phase decides: alphabetical, by habit_kind first, etc.).
- `percent_current` and `percent_prior` are floats in [0, 100].
- `scheduled_days_current` and `scheduled_days_prior` are integers ≥ 0.
- `completed_events_current` and `completed_events_prior` are integers ≥ 0.

---

## Entity: log_action event types (existing, extended)

Existing observability stream at `~/second-brain/agents/logs/observation/*.jsonl` (per `log_action.py`). Extended with new action types:

| Action type | Category | Context fields |
|---|---|---|
| `weekly_report_generated` | routine | `window_start_iso`, `window_end_iso`, `habit_count`, `overall_percent_current` |
| `weekly_report_failed` | error | `error_class`, `error_detail`, `path` (Vikunja path that failed) |
| `weekly_report_sent` | routine | `window_start_iso`, `window_end_iso`, `habit_count`, `whatsapp_target` |

---

## Relationship diagram (textual)

```
Vikunja API (existing)
  │
  └─→ VikunjaClient (new — scripts/common/vikunja_client.py)
        │
        └─→ query_active_habits_weekly.py (new helper)
              │
              ├─→ HabitClassifier (pure function)
              │     └─→ identifies daily / weekday-in-title / other
              │
              ├─→ aggregation
              │     └─→ rolls up done_at events by habit_title
              │
              └─→ WeeklyHabitReport (JSON to stdout)
                    │
                    └─→ felix-admin-habits agent
                          │
                          ├─→ render to WhatsApp turn-summary
                          └─→ log_action: weekly_report_sent
```

---

## Validation invariants (cross-entity)

1. **Non-habit tasks NEVER appear in the report**: enforced by HabitClassifier returning "other" for any task that's neither daily nor weekday-in-title; "other" tasks are filtered before aggregation.
2. **Per-habit percentage math is deterministic**: same `done_at` events + same window → same percentage. NFR-004 idempotency.
3. **Helper failure → typed exception → agent surfaces it**: per FR-007 / NFR-002, no silent drops; the agent's render step catches `VikunjaError` subclasses and emits the failure message in the turn-summary.
4. **Morning check-in untouched**: `query_active_habits_v2.py` and its tests are NOT modified; the cache discipline established in #556's `363685ea` is preserved.
