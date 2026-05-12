# Data Model — Inbox Capture Dedup and Parser Hardening

**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`
**Spec**: [spec.md](./spec.md) · **Research**: [research.md](./research.md)

State surfaces:

1. The routing log JSONL file on disk (the only new persistent state).
2. Per-cycle in-memory records inside `prescan.py` and the agent runtime.
3. External state we *read* (inbox notes) or *write* (GitHub issues, Vikunja tasks).

---

## Entities

### `Credential` … wait, wrong mission. This is inbox-capture. Entities:

### `InboxNote` (read-mostly external artefact)

| Field | Source | Notes |
|---|---|---|
| `path` | `os.path.join("/home/kgale/second-brain/notes/01-Inbox/", filename)` | The absolute file path. Used by prescan; the agent receives this in `unprocessed_paths`. |
| `filename` | basename of `path` | The dedup key. E.g., `Inbox 2026-04-16 1919.md`. |
| `frontmatter_status` | YAML field `status` inside the note's frontmatter | Authoritative for "has this been processed?" pre-FR-001. Values: `unprocessed`, `processed`, `needs-review`, or missing. After this mission, the routing log is the load-bearing dedup; status is informational/grep-friendly belt. |
| `body` | everything after the closing `---` | Read by the agent for content classification (Step 2). |

### `RoutingLogEntry` (new persistent state)

Each line of `~/second-brain/agents/state/inbox-routing.jsonl` is a single JSON object with this shape (per FR-002):

```json
{
  "filename": "Inbox 2026-04-16 1919.md",
  "issue_number": 176,
  "vikunja_task_id": 46,
  "routed_at": "2026-04-17T02:00:12Z",
  "note_excerpt": "First-paragraph-snippet up to 120 chars for human cross-reference..."
}
```

Mandatory fields: `filename`, `issue_number`, `routed_at`. Optional: `vikunja_task_id` (null if no task was created), `note_excerpt` (empty string if extraction failed).

**Append-only.** Existing lines are never edited. Duplicate-filename lines are tolerated by the read path (R-003 — dedup-via-prescan filters out any `unprocessed_paths` entry whose basename matches any routing-log entry's `filename`).

### `ParseFailure` (in-memory only, per cron tick)

Produced by `prescan.py`'s extended classifier when a note fails one of the FR-005 malformation checks. Lives only in the JSON output of one prescan invocation; never persisted to disk by prescan itself (the persistent surface is the "Inbox quality" GitHub issue + the callout marker on the note).

```json
{
  "path": "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-01 0742.md",
  "reason": "missing closing --- (unterminated frontmatter block)"
}
```

Set of recognised reasons (FR-005):

- `leading whitespace before opening ---`
- `UTF-8 BOM at start of file`
- `missing closing --- (unterminated frontmatter block)`
- `invalid YAML inside frontmatter block: <yaml.YAMLError message>`

### `InboxQualityIssue` (external state, GitHub)

A GitHub issue in `kentonium3/kg-automation`. Stable title prefix: `Inbox quality:`. Filed at end-of-cron-run if any `ParseFailure` records exist AND no open issue with the prefix already exists (FR-006/007).

| Field | Value |
|---|---|
| Title | `Inbox quality: <N> notes with parse errors — <cycle_date>` |
| Labels | `area/content` |
| Body | A markdown table of `\| filename \| reason \|` rows + a link to the per-run activity log + the callout marker convention. |
| State | open until Kent fixes the notes. |

### `CalloutMarker` (in-note, transient)

The Obsidian callout line injected by `inject_parse_error_marker.py` (FR-008) into a malformed note's body. Format:

```
> [!error] felix-capture: could not parse frontmatter on YYYY-MM-DD. See issue #<N> ("Inbox quality" issue for this run).
```

**Location**: after the closing `---` if frontmatter delimiters are detectable; otherwise at the very top of the file.

**Idempotency** (FR-009): the script searches for an existing line starting with `> [!error] felix-capture:` near the top of the file. If found: replace in place. If not: insert.

**Auto-cleanup** (FR-010): when `prescan.py` reads a note that parses cleanly AND has a top-of-file marker, the next agent action that mutates the note (Step 5 `status: processed` write OR a dedicated `strip_parse_error_marker.py` call) removes the marker line.

### `ActivityLogEntry` (existing surface, extended)

Pre-existing artefact at `~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`. This mission adds new event types:

| Event | Trigger | Recorded fields |
|---|---|---|
| `dedup-skip` | Prescan filters a file from `unprocessed_paths` because routing log has an entry | filename, existing_issue_number |
| `parse-halt` | Prescan classifies a file as parse-failure | filename, reason |
| `marker-inject` | `inject_parse_error_marker.py` succeeds | filename, issue_number |
| `marker-cleanup` | A marker is stripped because the file now parses cleanly | filename |
| `inbox-quality-filed` | A new "Inbox quality" issue is filed | issue_number, parse_failure_count |
| `routing-log-append` | A new routing log entry is appended | filename, issue_number |

---

## State transitions

Per inbox note, the lifecycle now has three terminal states instead of two:

```
                 [Note appears in 01-Inbox/]
                          │
                          ▼
              ┌─────────────────────────┐
              │  prescan classifies     │
              └────┬───────┬───────┬────┘
                   │       │       │
        (well-     │       │       │ (malformed
         formed,   │       │       │  per FR-005)
         status=   │       │       │
         unproc'd) │       │       ▼
                   │       │   parse_failure
                   │       │       │
                   │       │       ▼
                   │       │  Agent halts. Files (or
                   │       │  dedupes) Inbox quality
                   │       │  issue. Injects marker.
                   │       │       │
                   │       │       │ Kent fixes frontmatter
                   │       │       ▼
                   │       │   Note re-classifies on next tick.
                   │       │   Marker auto-stripped.
                   │       │
        (status=   │       │
         processed │       │
         OR        │       │
         routing   │       │
         log hit)  │       │
                   │       ▼
                   │   Skipped silently
                   │
                   ▼
            Agent routes:
            1. file GitHub issue
            2. file Vikunja task (existing flow)
            3. append routing log entry
            4. atomic status:processed write
                          │
                          ▼
            (subsequent ticks: dedup-skip on
             routing log OR status check)
```

The routing log is the **stable** dedup surface — even if `status: processed` write fails or frontmatter gets re-corrupted, the routing log entry from this run prevents future duplicates.

---

## Why no internal datastore beyond the routing log

Same shape as the credential-health-check rationale:

1. **NFR-003 (idempotent operation)** is much simpler when state lives in one well-defined file (JSONL) read by one function.
2. **The routing log IS the audit trail** that Kent consults when investigating "did this note route?"
3. **Crash resilience for free**: if the agent crashes after appending to the routing log but before writing `status: processed`, the next tick sees the routing log entry and dedupes. No duplicates.
4. **No coordination across cron ticks**: each tick is a fresh agent invocation with no carry-over state needed beyond what's on disk.
