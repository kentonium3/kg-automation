# Phase 1 Data Model: Inbox Pre-Scan Helper

**Mission**: 027-inbox-pre-scan-helper
**Date**: 2026-04-11

## Entities

### InboxFile

Represents a single markdown file in `{{VAULT_INBOX}}`.

**Fields:**
| Field | Type | Source | Notes |
|---|---|---|---|
| `path` | absolute filesystem path | filesystem | Always absolute |
| `name` | basename | `path` | For log/display only |
| `mtime_utc` | datetime (UTC) | filesystem `os.path.getmtime` | Used for the 7-day archive rule |
| `frontmatter` | dict or None | parsed YAML from the file | `None` if file has no frontmatter block or the block is unparseable |
| `status_raw` | str or None | `frontmatter["status"]` | `None` if frontmatter is absent or the `status` key is missing |
| `classification` | enum | computed | One of: `unprocessed`, `processed-recent`, `processed-stale`, `unknown-treated-as-unprocessed` |

**Classification rules (deterministic):**
1. If `frontmatter is None` OR `status_raw is None`: `classification = unknown-treated-as-unprocessed`
2. Else if `status_raw == "unprocessed"`: `classification = unprocessed`
3. Else if `status_raw == "processed"`:
   a. If `age_days(mtime_utc) > 7`: `classification = processed-stale`
   b. Else: `classification = processed-recent`
4. Else (any other `status_raw` value): `classification = unknown-treated-as-unprocessed`

**Classification effect on the helper's output:**
- `unprocessed` → path appears in `unprocessed_paths` list
- `unknown-treated-as-unprocessed` → path appears in `unprocessed_paths` list; also logged as a warning
- `processed-stale` → file is moved to `{{VAULT_INBOX_PROCESSED}}`; entry appears in `archived` list
- `processed-recent` → no action (stays in inbox silently)

### PrescanResult

The JSON object printed on stdout on successful runs.

**Schema:**
```json
{
  "run_id": "string (ulid or timestamp-based)",
  "started_at_utc": "2026-04-11T12:00:00Z",
  "finished_at_utc": "2026-04-11T12:00:00Z",
  "inbox_path": "/home/kgale/second-brain/notes/01-Inbox",
  "inbox_processed_path": "/home/kgale/second-brain/notes/02-Inbox-Processed",
  "unprocessed_count": 1,
  "unprocessed_paths": [
    "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-11 0930.md"
  ],
  "archived_count": 2,
  "archived": [
    {
      "src": "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-03 1100.md",
      "dst": "/home/kgale/second-brain/notes/02-Inbox-Processed/Inbox 2026-04-03 1100.md",
      "age_days": 8
    }
  ],
  "warnings": [
    {
      "path": "/home/kgale/second-brain/notes/01-Inbox/broken.md",
      "reason": "malformed YAML frontmatter; treated as unprocessed"
    }
  ]
}
```

**Fields:**
| Field | Type | Notes |
|---|---|---|
| `run_id` | string | Ulid-ish string or ISO timestamp with random suffix. Used to correlate helper runs with agent turn logs and the helper's own daily log file. |
| `started_at_utc` | ISO 8601 | UTC |
| `finished_at_utc` | ISO 8601 | UTC |
| `inbox_path` | string | Absolute, resolved from `{{VAULT_INBOX}}` |
| `inbox_processed_path` | string | Absolute, resolved from `{{VAULT_INBOX_PROCESSED}}` |
| `unprocessed_count` | int | `len(unprocessed_paths)` |
| `unprocessed_paths` | list of strings | Absolute paths. Sorted deterministically (alphabetical) for stable agent input. |
| `archived_count` | int | `len(archived)` |
| `archived` | list of dicts | Each: `{src, dst, age_days}` |
| `warnings` | list of dicts | Each: `{path, reason}`. Non-fatal issues. |

### LogEntry

Helper's daily markdown log file is append-only. Each run appends a section:

```markdown
## Run 2026-04-11T12:00:00Z — run_id=01HZ…

- inbox: /home/kgale/second-brain/notes/01-Inbox
- inbox_processed: /home/kgale/second-brain/notes/02-Inbox-Processed
- unprocessed: 1
- archived: 2
- warnings: 0
- duration_ms: 142

### Archived
- Inbox 2026-04-03 1100.md (age 8d)
- Inbox 2026-04-02 0830.md (age 9d)

### Unprocessed handed to agent
- Inbox 2026-04-11 0930.md
```

**Fields written per run:**
- Timestamp header
- run_id (matches the JSON result's `run_id`)
- Inbox + inbox_processed absolute paths
- Counts (unprocessed, archived, warnings)
- Duration in ms
- One sub-section per non-empty category

## State Transitions

**For an individual file in `{{VAULT_INBOX}}`:**

```
  (file written by Wispr Flow / user / agent)
              │
              ▼
   status: unprocessed  ──────agent processes──────▶  status: processed
              │                                              │
              │ (never moved regardless of age)              │
              │                                              │ mtime > 7 days ago
              │                                              │
              ▼                                              ▼
          (stays in inbox)                       moved to {{VAULT_INBOX_PROCESSED}}
```

**Invariants:**
1. An unprocessed file is NEVER moved, regardless of age (C-007 allows no reverse migration; C-002 forbids modifying file contents including frontmatter).
2. A processed file with mtime ≤ 7 days ago stays in `{{VAULT_INBOX}}`.
3. A processed file with mtime > 7 days ago is moved exactly once to `{{VAULT_INBOX_PROCESSED}}` and never touched again by the helper.
4. Files in `{{VAULT_INBOX_PROCESSED}}` are never read, classified, or modified by the helper.

**Boundary rule for "7 days old":** exclusive — a file with mtime exactly 7 days ago is NOT archived. The rule is `age_days > 7`, not `>= 7`. This gives a predictable one-day grace window and makes the test case "7 days old exactly" deterministic.

## Failure States

| State | Helper behavior | Exit code | Agent branch |
|---|---|---|---|
| `paths.json` missing or unreadable | Log error, stderr | 1 | Report error, no processing |
| `{{VAULT_INBOX}}` resolves but does not exist | Log error, stderr | 1 | Report error, no processing |
| `{{VAULT_INBOX_PROCESSED}}` resolves but does not exist | Log error, stderr | 1 | Report error, no processing |
| Individual file unreadable (permissions) | Log warning, treat as unprocessed | 0 | Pass through to agent as unprocessed |
| Individual file has malformed YAML | Log warning, treat as unprocessed | 0 | Pass through to agent as unprocessed |
| Archive move fails (destination already exists) | Log warning, skip move, leave source in place | 0 | Result still valid; agent processes unprocessed list normally |
| Archive move fails (permission denied) | Log warning, skip move | 0 | Result still valid |
| YAML import fails at helper startup | Error, stderr | 1 | Report error, no processing |

## API Contracts

None — the helper is a CLI script. Its only contract is:
- Invocation: `python3 /home/claude/kg-automation/scripts/inbox/prescan.py [--self-check]`
- Stdin: not read
- Stdout: JSON `PrescanResult` (exit 0) or nothing (exit 1)
- Stderr: human-readable log lines
- Exit: 0 (success) or 1 (error)
- Side effects: may move files between `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}`; may append to the daily log file

## Optional `--self-check` Mode

Used by the deploy wrapper's Step 3 to verify the helper can resolve paths and reach the filesystem, without doing any work.

Behavior:
- Resolve `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}`
- Confirm both directories exist and are readable
- Print a minimal JSON to stdout: `{"self_check": "ok", "inbox": "...", "inbox_processed": "..."}`
- Exit 0

If anything fails, exit 1 with a clear error on stderr.

## Privacy Boundary Enforcement

Implemented in the helper's path-resolution step:
- The helper only reads paths returned from `paths.json`
- `paths.json` does not contain any `_private/` entry (by C-001 and mission 026 design)
- The helper never walks a directory that isn't one of the two resolved paths
- If a hypothetical `_private/` subdirectory ever appeared under `{{VAULT_INBOX}}` or `{{VAULT_INBOX_PROCESSED}}`, the helper's listing MUST skip it explicitly (defense-in-depth)
- Unit tests include a case that constructs a fixture inbox with a `_private/` subdirectory and asserts the helper ignores it
