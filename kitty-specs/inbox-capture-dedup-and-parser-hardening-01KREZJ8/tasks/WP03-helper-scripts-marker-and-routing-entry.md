---
work_package_id: WP03
title: 'Helper scripts: marker inject/strip + routing-log append CLI'
dependencies:
- WP01
requirement_refs:
- C-004
- C-005
- FR-001
- FR-002
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
- T011
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: scripts/inbox/
execution_mode: code_change
owned_files:
- scripts/inbox/inject_parse_error_marker.py
- scripts/inbox/strip_parse_error_marker.py
- scripts/inbox/append_routing_entry.py
- tests/inbox/test_callout_marker.py
tags: []
---

# WP03 — Helper scripts (marker inject / strip + routing-log append CLI)

## Objective

Three small, shell-invokable Python helpers that the agent calls during its turn:

- `inject_parse_error_marker.py <filename> <issue_number>` — inserts/refreshes a callout marker at the top of a malformed note.
- `strip_parse_error_marker.py <filename>` — removes the marker when a note now parses cleanly.
- `append_routing_entry.py <filename> <issue_number> <vikunja_task_id_or_dash> [excerpt]` — appends one JSONL line to the routing log.

Each is a thin Python script with idempotent behavior, atomic file writes, and clear failure modes.

## Context

- **Spec** anchors: FR-008/FR-009 (marker shape + idempotency), FR-010 (auto-cleanup), FR-001/FR-002 (routing log).
- **Contracts** anchors: `contracts/callout-marker.md`, `contracts/routing-log.md`.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`

## Subtasks

### T008 — Implement `inject_parse_error_marker.py`

**Purpose**: Insert or refresh the Obsidian callout error marker at the top of a malformed note's body.

**Steps**:

1. Create `scripts/inbox/inject_parse_error_marker.py` (executable shebang + argparse):
   ```python
   #!/usr/bin/env python3
   """Inject (or refresh) the felix-capture parse-error callout marker.

   See contracts/callout-marker.md for spec.
   """
   from __future__ import annotations

   import argparse
   import os
   import sys
   import tempfile
   from datetime import datetime, timezone
   from pathlib import Path

   MARKER_PREFIX = "> [!error] felix-capture:"
   MARKER_TEMPLATE = (
       "> [!error] felix-capture: could not parse frontmatter on {date}. "
       'See issue #{issue} ("Inbox quality" issue for this run).'
   )
   ```

2. Implementation:
   - Read the full file content with `errors="replace"` to be tolerant of byte issues.
   - Detect frontmatter delimiters: if file starts with `---` (after optional BOM + leading whitespace) AND a closing `---` is detectable, insertion point is after the closing `---` plus one blank line if present.
   - Otherwise: insertion point is line 0.
   - Scan the next ~3 lines from insertion point looking for `MARKER_PREFIX`. If found: replace that line. If not found: insert a new marker line followed by a blank line.
   - Atomic write: write to `<filename>.tmp.<pid>` then `os.replace`.

3. CLI surface (`argparse`):
   - `--filename` (positional, required) — absolute path to the note.
   - `--issue` (positional, required, int) — the "Inbox quality" issue number.
   - `--date` (optional, default UTC today as `YYYY-MM-DD`) — for deterministic test invocations.
   - Exit 0 on success; exit 1 with stderr message on failure.

4. Make executable: `chmod +x scripts/inbox/inject_parse_error_marker.py`.

**Files**: `scripts/inbox/inject_parse_error_marker.py` (create, ~120 lines, executable).

**Validation**: covered in T011.

---

### T009 — Implement `strip_parse_error_marker.py`

**Purpose**: Remove the marker line from a note that now parses cleanly (FR-010 auto-cleanup).

**Steps**:

1. Create `scripts/inbox/strip_parse_error_marker.py`:
   ```python
   #!/usr/bin/env python3
   """Strip the felix-capture parse-error callout marker if present.

   No-op if no marker is detected. See contracts/callout-marker.md.
   """
   ```

2. Implementation:
   - Read the file.
   - Scan the first ~5 lines for `MARKER_PREFIX` (same constant as inject script — consider extracting to a shared module if duplication grows).
   - If found: remove that line. If the line immediately after is blank, remove it too (cleanup the orphan blank that inject inserts).
   - If not found: exit 0 (no-op).
   - Atomic write.

3. CLI: `--filename` (positional, required). Exit 0 on success.

4. Make executable.

**Files**: `scripts/inbox/strip_parse_error_marker.py` (create, ~80 lines, executable).

---

### T010 — Implement `append_routing_entry.py`

**Purpose**: CLI wrapper around `routing_log.RoutingLogWriter.append`. The agent invokes this after each successful route.

**Steps**:

1. Create `scripts/inbox/append_routing_entry.py`:
   ```python
   #!/usr/bin/env python3
   """Append one entry to the routing log.

   Thin CLI wrapper around routing_log.RoutingLogWriter.append.
   Used by felix-admin-capture AGENTS.md §Step 5.
   """
   from __future__ import annotations

   import argparse
   import sys
   from pathlib import Path

   # Make `routing_log` importable when invoked from any cwd.
   SCRIPT_DIR = Path(__file__).resolve().parent
   if str(SCRIPT_DIR) not in sys.path:
       sys.path.insert(0, str(SCRIPT_DIR))

   from routing_log import RoutingLogWriter


   def main(argv: list[str] | None = None) -> int:
       parser = argparse.ArgumentParser(description="Append one entry to the inbox routing log.")
       parser.add_argument("filename", help="Inbox note filename (basename only).")
       parser.add_argument("issue_number", type=int, help="GitHub issue number filed for this note.")
       parser.add_argument("vikunja_task_id", help="Vikunja task ID, or '-' if no task was created.")
       parser.add_argument("excerpt", nargs="?", default="", help="Short note excerpt (≤120 chars).")
       args = parser.parse_args(argv)

       task_id = None if args.vikunja_task_id == "-" else int(args.vikunja_task_id)
       writer = RoutingLogWriter()
       try:
           entry = writer.append(
               filename=args.filename,
               issue_number=args.issue_number,
               vikunja_task_id=task_id,
               note_excerpt=args.excerpt,
           )
       except OSError as exc:
           print(f"ERROR: could not write routing log: {exc}", file=sys.stderr)
           return 1
       print(f"Appended routing log entry: {entry.filename} -> #{entry.issue_number}")
       return 0


   if __name__ == "__main__":
       sys.exit(main())
   ```

2. Make executable: `chmod +x scripts/inbox/append_routing_entry.py`.

**Files**: `scripts/inbox/append_routing_entry.py` (create, ~50 lines, executable).

---

### T011 — Tests for the marker helpers

**Purpose**: Lock the inject + strip behavior. Use tmp_path notes with realistic body content.

**Steps**:

1. Create `tests/inbox/test_callout_marker.py`.
2. Import the helper functions (consider exposing the core inject/strip logic as Python functions in addition to the CLI; tests call functions directly to avoid subprocess noise). Pattern:
   ```python
   # In inject_parse_error_marker.py — expose a function:
   def inject_marker(path: Path, issue_number: int, date_str: str) -> bool:
       """Returns True if the file was modified (insert or replace); False if no change."""
       ...

   # main() wraps inject_marker() with argparse.
   ```
3. Cases for inject:
   - `test_inject_into_well_formed_frontmatter_inserts_after_closing_fence`
   - `test_inject_into_no_frontmatter_inserts_at_top`
   - `test_inject_when_marker_exists_replaces_in_place_no_duplicate`
   - `test_inject_when_marker_exists_updates_date_and_issue`
   - `test_inject_preserves_body_content`
   - `test_inject_uses_atomic_write` — verify intermediate `.tmp` file doesn't persist; verify the original file's content is consistent at every observable moment (best effort — `os.replace` semantics).
4. Cases for strip:
   - `test_strip_when_marker_present_removes_marker_line`
   - `test_strip_when_marker_present_removes_following_blank_line`
   - `test_strip_when_marker_absent_is_noop`
   - `test_strip_preserves_other_content`
   - `test_strip_does_not_strip_non_felix_capture_callouts` — file has `> [!warning] something else` at top; strip leaves it alone.
5. Also smoke-test `append_routing_entry.py` via subprocess:
   - `test_append_routing_entry_writes_jsonl_line` — invoke the script, verify the routing log file has one new line with expected fields.
   - `test_append_routing_entry_handles_dash_task_id` — pass `-` as task_id, verify `vikunja_task_id` is null in the JSON.

**Files**: `tests/inbox/test_callout_marker.py` (create, ~200 lines).

**Validation**: `pytest tests/inbox/test_callout_marker.py -v` — all green.

---

## Definition of Done

- All four subtasks complete.
- All three scripts are `chmod +x` (verified with `git ls-files --stage` showing mode `100755`).
- `pytest tests/inbox/ -v` total green (WP01 + WP02 + WP03 tests).
- Commit prefix: `feat(WP03):` referencing #185.

## Risks

- **Marker location detection**: must handle weird file shapes (empty files, files with only frontmatter and no body, files with frontmatter but no closing fence). Each path should either inject correctly or exit cleanly — never crash.
- **Atomic write semantics**: `os.replace` is atomic on POSIX. Tests can't directly verify atomicity but should confirm the script uses `os.replace` not a direct write.
- **`MARKER_PREFIX` duplication**: defined in two scripts (inject + strip). Acceptable for v1; consider extracting to a shared `scripts/inbox/_markers.py` module if a third consumer appears.

## Reviewer guidance

- Verify: all three scripts have `#!/usr/bin/env python3` shebang and are executable.
- Verify: marker writes use `os.replace` (atomic).
- Verify: idempotency tests (T011's `test_inject_when_marker_exists_replaces_in_place_no_duplicate`) actually re-invoke and check zero duplication.
- Verify: `append_routing_entry.py` correctly translates `-` task_id to JSON null.
- Verify: scripts are stdlib-only (no `requests`, no `pyyaml` in inject/strip — those are pure file I/O).

## Suggested implement command

```bash
spec-kitty agent action implement WP03 --agent <name>
```
