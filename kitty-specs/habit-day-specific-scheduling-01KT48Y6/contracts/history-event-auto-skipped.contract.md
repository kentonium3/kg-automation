# Contract: `habits-history.jsonl` `auto_skipped` event

**Path**: `/data/services/openclaw/state/habits-history.jsonl` (existing file, append-only)
**Format**: JSON Lines, one event per line
**Producer**: `scripts/habits/sweeper.py`
**Consumer**: existing readers (notably `exclude_completed_v2.py` and the morning check-in pipeline) — MUST tolerate the new `event_type` value

## Event schema for `event_type: "auto_skipped"`

```json
{"event_type": "auto_skipped", "task_id": 17, "original_checkin_date_et": "2026-05-31", "original_designated_weekday": "Wed", "tick_id": "01KT4ABC7XYZ123456789DEFG", "recorded_at_utc": "2026-06-02T11:30:01Z"}
```

## Field definitions

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_type` | str | ✓ | Always literal string `"auto_skipped"` for this contract. |
| `task_id` | int | ✓ | Vikunja task id. |
| `original_checkin_date_et` | str (YYYY-MM-DD) | ✓ | The ET date of the morning-checkin artifact the habit appeared in. |
| `original_designated_weekday` | str (three-letter ISO) \| null | ✓ (null if daily) | If the habit was day-specific, the designated weekday on `original_checkin_date_et`. Null/absent if the habit was daily. |
| `tick_id` | str (ULID) | ✓ | The sweeper tick that emitted this event. Cross-reference to `sweeper-tick-<date>.json`. |
| `recorded_at_utc` | str (ISO 8601 with `Z`) | ✓ | Wall-clock when the event was appended. |

## Idempotency contract

Multiple sweeper ticks evaluating the same `(task_id, original_checkin_date_et)` pair MUST produce only ONE `auto_skipped` event in `habits-history.jsonl`. The sweeper enforces idempotency by scanning history for an existing `auto_skipped` event with the matching pair before appending a new one.

## Reader behavior

Existing readers (`exclude_completed_v2.py` and any other consumers of `habits-history.jsonl`) MUST:

1. **Recognize `auto_skipped` as exclusion-eligible** — for the purpose of building the daily check-in's "habits already addressed today" filter, `auto_skipped` is equivalent to `skipped`. The habit does NOT re-appear in subsequent check-ins until its Vikunja `due_date` advances.

2. **Tolerate unknown future `event_type` values** — readers that filter on known types must use a permit-list (treat unknown as no-op), not a deny-list. This makes future schema extensions safe.

Plan-phase research (OD-4) confirms whether `exclude_completed_v2.py` already exhibits this tolerance; if not, the reader gains an explicit case for `auto_skipped` as part of WP1.

## No back-fill

The sweeper does NOT back-fill `auto_skipped` events for missed-but-not-recorded habits from before this mission's cutover. Existing habits in a stale `not yet reported` state remain so until either Kent marks them or the schedule changes their visibility. Cleaning up the pre-cutover state is out of scope per spec §9.
