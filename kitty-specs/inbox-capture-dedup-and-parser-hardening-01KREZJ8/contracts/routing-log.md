# Contract: Routing Log

**Surface**: read/append/dedup against `~/second-brain/agents/state/inbox-routing.jsonl`.

**Module**: `scripts/inbox/routing_log.py` (new).

## Inputs / outputs

### `RoutingLogReader.routed_filenames() -> set[str]`

- Reads the JSONL file (one read per cron tick — cache the set in memory).
- Returns a Python `set` of all `filename` values seen.
- If the file does not exist: returns empty set (fail-safe per FR-001 edge case).
- If a line is malformed (non-JSON, missing required fields): skip that line, emit a warning to stderr, continue.

### `RoutingLogReader.has(filename: str) -> bool`

- Returns `True` if `filename` appears as a `filename` value in any line.
- O(1) after the initial read (set membership).

### `RoutingLogWriter.append(filename, issue_number, vikunja_task_id, note_excerpt) -> None`

- Appends one JSON line to the routing log file.
- Creates parent directory `~/second-brain/agents/state/` if absent (mode 0700 for the directory, 0600 for the file on first creation).
- Adds `routed_at: <UTC ISO-8601>` automatically from `datetime.now(timezone.utc).isoformat()`.
- Writes are atomic at the OS-append level (`open(path, "a") + write(json_line + "\n")`). No lock needed because there's only ever one agent process active per cron tick.

## Helper script

`scripts/inbox/append_routing_entry.py <filename> <issue_number> <vikunja_task_id_or_dash> [note_excerpt]`

- Thin CLI wrapper around `RoutingLogWriter.append`. The agent invokes this after successfully creating the GitHub issue.
- `vikunja_task_id_or_dash`: pass `-` if no task was created (e.g., a routing target that doesn't get a Vikunja task).
- Exit 0 on success; exit 1 with stderr message on failure.

## Failure modes

- File doesn't exist on first read: not a failure; returns empty set. First write creates the file.
- File contains malformed lines: warn to stderr, skip line. Don't raise.
- File can't be written (permissions, full disk): raise `OSError`. The CLI wrapper exits 1; the agent surfaces this in its turn output. The bug-fix value is preserved: no routing log entry means the next tick will re-route → duplicate. This is a real failure mode worth surfacing, not silently swallowing.

## Test coverage

- Unit tests in `tests/inbox/test_routing_log.py`:
  - Empty / missing file → `routed_filenames()` returns empty set
  - Single line → `has(filename)` true for that filename, false for others
  - Multiple lines, duplicate filename → `has` still works (set semantics)
  - Malformed line → skipped with warning; subsequent valid lines still returned
  - Append creates parent dir if missing
  - Append produces a parseable JSON line with all required fields
  - Append on subsequent call appends (does not truncate)
