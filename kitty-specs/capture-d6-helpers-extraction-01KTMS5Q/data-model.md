# Data Model: Capture Directive-6 Helpers Extraction

**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`
**Phase**: 1 (Design & Contracts)
**Date**: 2026-06-08

This mission has no database, no schema migration, no new persistent data store. Data shapes are: (a) JSON output from `classify_content`, (b) JSON state file for `handle_clarification_state`, (c) JSON payload contract for `route_calendar_event`.

## ClassificationOutput

Emitted by `classify_content.py` on stdout as a single JSON object.

| Field | Type | Required | Notes |
|---|---|---|---|
| `note_filename` | str | yes | Filename of the input note (basename, no path) |
| `blocks` | array of `Block` | yes | One entry per semantic block in the note's body. May be empty (e.g., empty note). |

### Block (inside ClassificationOutput.blocks)

| Field | Type | Required | Notes |
|---|---|---|---|
| `index` | int | yes | 0-based position in the note's body |
| `kind` | enum literal | yes | One of: `"journal"`, `"calendar"`, `"someday"`, `"github_issue"`, `"vikunja_task"`, `"parse_failure"`, `"ambiguous"` |
| `content` | str | yes | The raw block text (heading + body, or just body if no heading) |
| `confidence` | enum literal | yes | One of: `"high"`, `"medium"`, `"low"`. `"ambiguous"` kind is always `"low"`. |
| `flag` | str | conditional | Present iff `kind == "ambiguous"`. Always `"needs-llm-disambiguation"` in this mission's emission; reserved for future flag values. |

### Example

```json
{
  "note_filename": "Inbox 2026-06-08 0732.md",
  "blocks": [
    {
      "index": 0,
      "kind": "journal",
      "content": "Feeling good about the week. Made progress on Felix.",
      "confidence": "high"
    },
    {
      "index": 1,
      "kind": "calendar",
      "content": "Meet with Rob 3pm Thursday",
      "confidence": "high"
    },
    {
      "index": 2,
      "kind": "ambiguous",
      "content": "Maybe look into rust someday",
      "confidence": "low",
      "flag": "needs-llm-disambiguation"
    }
  ]
}
```

## PendingClarificationState

Persisted by `handle_clarification_state.py` at `~/second-brain/agents/state/pending-calendar-clarifications.json`.

The file is a JSON array of `PendingClarification` objects (top-level array, NOT wrapped in an object — chosen for simplicity).

### PendingClarification

| Field | Type | Required | Notes |
|---|---|---|---|
| `note_filename` | str | yes | Source note (uniqueness key for `match` subcommand) |
| `partial_payload` | object | yes | `CalendarPayload`-shaped, possibly missing required fields |
| `created_at` | str (ISO 8601 UTC) | yes | When the clarification was added. Sweep ages out entries >24h old. |

### Example

```json
[
  {
    "note_filename": "Inbox 2026-06-08 0712.md",
    "partial_payload": {
      "title": "Meet with Rob",
      "start": "2026-06-12T15:00:00-04:00"
    },
    "created_at": "2026-06-08T11:12:00Z"
  }
]
```

### Invariants

- File is JSON-array-of-object format. Top-level is `[...]`, not `{"clarifications": [...]}`.
- File is atomically rewritten on each `add` / `sweep` operation (load → mutate in memory → atomic-write back).
- `match` is read-only.
- File MAY be absent (first run). `sweep` and `match` treat absent as empty array; `add` creates the file (and parent dir) on first write.
- `created_at` uses `Z` suffix (UTC), not local-offset timezone. Aging math uses `datetime.now(timezone.utc)`.

## CalendarPayload

Input contract for `route_calendar_event.py`. Validated via existing `scripts.calendar_routing.validate_calendar_event.validate_payload`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | str | yes | Calendar event title (1-200 chars) |
| `start` | str (ISO 8601) | yes | Event start time; with timezone offset (e.g., `2026-06-12T15:00:00-04:00`) |
| `end` | str (ISO 8601) | optional | Event end time; defaults to start + 1 hour if absent |
| `location` | str | optional | Free-text location |
| `description` | str | optional | Free-text description |

### Validation surface (existing helper)

```python
from scripts.calendar_routing.validate_calendar_event import validate_payload

is_valid, missing = validate_payload(payload)
```

## Helper exit-code contract (all 6 helpers)

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Validation error (invalid input file, missing required CLI args) |
| 2 | Runtime error (Vikunja unreachable, write failure, etc.) |
| 3 | Refusal (e.g., private-path input per C-001) |

Helpers that have additional structured-output-on-stderr cases use the `1` / `2` / `3` codes per the table above.

## State Transitions

This mission has no state machines. Each helper invocation is stateless modulo the explicit state file (`handle_clarification_state` only).

## Externally Visible Events

- `mark_processed` → writes file (filesystem event)
- `route_journal_entry` → creates/appends file (filesystem event)
- `route_someday` → Vikunja task created (Vikunja-side event)
- `route_calendar_event` → no side effect (stdout-only; the prompt-side delegation creates the calendar event)
- `handle_clarification_state add/sweep` → writes state file
- `classify_content` → no side effect (stdout-only)

No webhooks. No HTTP server. No new credentials.
