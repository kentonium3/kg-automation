# Data Model

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Phase**: 1 (design)

This document defines the data entities specific to the backfill helper. Most schemas are inherited from prior phases — see references.

---

## Entity 1 — `HISTORICAL_STATE_MAP`

Module-level constant in `scripts/habits/backfill_jsonl_from_comments.py`. Maps historical `[Felix]` comment state strings to the Phase 2 strict enum.

```python
HISTORICAL_STATE_MAP: dict[str, str] = {
    "complete": "complete",       # identity (already in Phase 2 enum)
    "will-not-do": "skipped",     # semantic: intentional skip (e.g., sick, travel)
}
```

### Source

2026-05-19 production probe across all 8 habit tasks (IDs 14, 15, 16, 17, 18, 19, 20, 65):
- 24 comments with `state="complete"`
- 2 comments with `state="will-not-do"`
- 0 other distinct state values

### Mapping policy

- A comment's parsed state goes through `HISTORICAL_STATE_MAP.get(state)`.
- If found: the mapped target is the JSONL `state` field. The append succeeds (assuming other validation passes).
- If NOT found: the comment is logged in the summary's `unmapped-state-values` section. NO `state_log.append` call is made.
- The Phase 2 `DOMAIN_STATES["habits"]` enum is **not** extended. Adding a new historical value requires editing this dict + re-running.

### Update procedure

When the summary report names an unmapped state value:
1. Operator decides the semantic mapping (e.g., `"partial"` → `"complete"` or `"incomplete"`).
2. Edit `HISTORICAL_STATE_MAP` in `scripts/habits/backfill_jsonl_from_comments.py`.
3. Re-run the backfill — the previously-unmapped comments now get appended; previously-mapped ones are no-ops (Phase 2 dedup).

---

## Entity 2 — JSONL record (inherited from Phase 2 #305)

Each record this helper appends:

```json
{
  "domain": "habits",
  "task_id": <int — Vikunja task ID>,
  "title": "<str — Vikunja task's current title at backfill time>",
  "date": "<str — YYYY-MM-DD parsed from [Felix] comment body>",
  "state": "<str — mapped state from HISTORICAL_STATE_MAP>",
  "source": "historical-backfill",
  "note": "<str|null — optional from [Felix] comment's note segment>",
  "timestamp": "<str — ISO-8601 datetime from Vikunja comment.created>"
}
```

### Field provenance

| Field | Source | Notes |
|---|---|---|
| `domain` | Hardcoded `"habits"` | Single-domain helper |
| `task_id` | Vikunja task `id` | Integer, from the GET response |
| `title` | Vikunja task `title` at backfill run time | Denormalization caveat per research D6 |
| `date` | `[Felix]` comment body | Parsed via `FELIX_COMMENT_PATTERN` (named group `date`) |
| `state` | `[Felix]` comment body via `HISTORICAL_STATE_MAP` | Original captured by the regex's `state` group; mapped before append |
| `source` | Hardcoded `"historical-backfill"` | Distinguishes backfill records from forward writes (`whatsapp`, `vikunja-ui`, `cron`, `manual`) |
| `note` | `[Felix]` comment body (optional 3rd segment) | Pattern's `note` group, or `null` if no third segment |
| `timestamp` | Vikunja comment `created` field | Pass-through; verbatim ISO-8601 with timezone |

### Validation

Goes through `state_log.validate_record(record, "habits")` before append. Failures (e.g., malformed timestamp, state somehow not in the Phase 2 enum despite the map) are logged in the summary's `anomalies` section and the record is dropped.

---

## Entity 3 — Pre-backfill `.bak` snapshot

Created by the helper before the first `state_log.append` in a live run.

### Path

`/data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak`

### Content

Byte-for-byte copy of `/data/services/openclaw/state/habits-history.jsonl` immediately before the first append. Created via `shutil.copy2` (preserves mtime + permissions).

### Mode + ownership

Same as the source: 0664 claude:secondbrain (inherited from the source file via copy2).

### Lifecycle

- Created: once per live run, just before the first append.
- Skipped: if `habits-history.jsonl` doesn't exist yet.
- Preserved indefinitely on disk; operator removes manually after confirming the backfill is correct (e.g., 1-2 days post-run).
- Rollback: `cp <bak> <source>` restores. Trivial.

---

## Entity 4 — Summary report (stdout output)

Plain-text block printed at the end of every run (dry-run + live). The dry-run form is identical except for the header and the "Records appended" → "Records planned" relabeling.

```
=== Backfill summary ===
Mission: backfill-habits-jsonl-from-comments-01KS0Y4F
Run mode: live
Run started: 2026-05-19T20:30:00+00:00
Run finished: 2026-05-19T20:30:15+00:00

Vikunja API:
  Habits project resolved: id=13 title="Habits"
  Habit tasks enumerated: 11
  Comments fetched: 26

Records:
  Appended: 24
  Skipped (dedup with existing JSONL): 0
  Skipped (unmapped state): 2
  Skipped (malformed comment): 0
  Skipped (validation failure): 0

Records by task:
  task_id=14 (Wake at 5:00 AM): 8 appended
  task_id=15 (Meditate): 5 appended
  task_id=16 (Morning shoulder PT): 4 appended
  task_id=17 (Workout 45 min): 3 appended
  task_id=18 (Get steps in today): 0 appended (no [Felix] comments)
  task_id=19 (Read 30 min minimum): 4 appended
  task_id=20 (Evening shoulder PT): 0 appended
  task_id=65 (Morning hip PT): 0 appended
  task_id=75 (Strength training — Monday): 0 appended (new MWF task, no history)
  task_id=76 (Strength training — Wednesday): 0 appended (new MWF task)
  task_id=77 (Strength training — Friday): 0 appended (new MWF task)

Records by state (post-mapping):
  complete: 24

Unmapped state values:
  (none in this run)

Comments skipped as malformed: 0

Anomalies: 0

Snapshot:
  Pre-backfill snapshot: /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak
  (To rollback: cp <snapshot> /data/services/openclaw/state/habits-history.jsonl)
```

(Example output; actual numbers vary with production data.)

### "Unmapped state values" section format

When non-empty:

```
Unmapped state values:
  task_id=17 date=2026-05-12 state="partial" — "[Felix] 2026-05-12 | partial | tweaked back"
  task_id=18 date=2026-05-15 state="halfway" — "[Felix] 2026-05-15 | halfway"

  These comments were skipped (no JSONL append). To include them, add an
  entry to HISTORICAL_STATE_MAP in scripts/habits/backfill_jsonl_from_comments.py
  and re-run the backfill.
```

### "Anomalies" section format

When non-empty (e.g., a comment with no `created` field, or a task fetch error):

```
Anomalies:
  task_id=17 comment_id=503: missing 'created' field; record skipped
  task_id=65: HTTP 404 fetching comments; no records appended for this task
```

---

## Schemas inherited from prior phases (references)

### Phase 2 state_log JSONL line format

See `docs/design/architecture/data/agent-state-log-schema.md` (Phase 2 deliverable). One JSON object per line, UTF-8, LF-terminated.

### Phase 2 DOMAIN_STATES["habits"]

```python
DOMAIN_STATES["habits"] = frozenset({"complete", "incomplete", "skipped"})
```

Locked per the 2026-05-19 discovery decision. Phase 4 does NOT extend this enum (C-002).

### FELIX_COMMENT_PATTERN regex

Defined in `scripts/habits/exclude_completed.py` (untouched per C-001):

```python
FELIX_COMMENT_PATTERN = re.compile(
    r"^\[Felix\]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+\|\s+(?P<state>[\w-]+)"
    r"(?:\s+\|\s+(?P<note>.*))?$",
    re.MULTILINE,
)
```

Named groups: `date`, `state`, `note` (optional). The backfill helper imports this constant and uses its `.search()` method on each comment's text.

---

## Forward compatibility

- **Adding a historical state value**: 1-line edit to `HISTORICAL_STATE_MAP`. No schema change. Re-run is idempotent for already-backfilled records; the new mapping captures previously-unmapped comments.
- **Adding a new domain (e.g., escalation in Phase 6)**: out of scope here. Phase 6 would have its own backfill helper if needed; this one is habits-specific.
- **Removing a historical state value from the map** (e.g., "will-not-do" rename): the records already in the JSONL are unchanged. New comments with the removed state would land in `unmapped-state-values` until re-mapped. Safe.
- **Changing the source attribution from `"historical-backfill"`**: existing JSONL records keep their original `source` value. Future records use the new value. The Phase 2 dedup tuple doesn't include `source`, so changing it doesn't affect dedup behavior.
