# Contract: `phase3-schedule.yaml` (extended)

**Path**: `scripts/habits/migrations/phase3-schedule.yaml` (in repo; deployed to office2 via existing deploy pattern)
**Format**: YAML
**Owner**: in-repo; reconciliation runs against the deployed copy

## Schema extension (mission #408)

The existing schedule shape (mission #282) is preserved. This mission adds one optional field per habit entry:

```yaml
- task_id: 17
  title: "Strength training — Wednesday"
  designated_weekdays: ["Wed"]    # NEW (this mission)
  repeat_after_seconds: 604800
  # ...other existing fields...

- task_id: 18
  title: "Strength training — Friday"
  designated_weekdays: ["Fri"]    # NEW
  repeat_after_seconds: 604800

- task_id: 14
  title: "Wake at 5:00 AM"
  # NO designated_weekdays — daily habit (default behavior, no change)
  # ...other existing fields...
```

## Field semantics

| Field | Type | Required | Meaning |
|---|---|---|---|
| `designated_weekdays` | list[`{"Mon","Tue","Wed","Thu","Fri","Sat","Sun"}`] | ✗ | If set: habit is day-specific. The morning check-in helper INCLUDES this habit only when today's ET weekday is in the list. The sweeper applies the auto-skip rule with `original_designated_weekday` populated. If absent or empty: habit is daily; no day filter applied; the auto-skip rule still applies (per the 48hr window). |

## Validation rules (enforced at load time by `schedule_loader.py`)

- Each entry in `designated_weekdays` must be a valid three-letter ISO weekday abbreviation. Unknown values are a load-time error (exit 2).
- Duplicates in the list are silently deduped.
- Cross-validation **warning** (not error): a habit with `designated_weekdays` populated and `repeat_after_seconds != 604800 * N` for some integer N is flagged. The Vikunja-native repeat may not align with the day-of-week semantics; operator should review.
- The full schedule.yaml MUST be parseable as YAML 1.2; invalid YAML is a load-time error (exit 2).

## Backwards compatibility

- All existing entries (without `designated_weekdays`) continue to load and behave as daily habits — no change.
- Existing tests using fixture schedules without `designated_weekdays` MUST pass without modification (NFR-003).
- The `migrate_schedule.py` helper is NOT modified by this mission; it continues to migrate from the v1 schedule shape to v2 without needing to know about `designated_weekdays`.

## Change-control tier

Editing this YAML is Tier 3 (logic/workflow). Deploy via the existing repo→office2 deploy script. After deploy, the operator runs `set_due_dates.py --reconcile-schedule` only when `designated_weekdays` for an existing habit has changed (per FR-010).
