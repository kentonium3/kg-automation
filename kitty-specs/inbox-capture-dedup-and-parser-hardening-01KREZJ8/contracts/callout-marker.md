# Contract: Callout Marker Inject / Strip

**Surface**: insert/refresh/remove the Obsidian callout marker on malformed inbox notes.

**Helpers**:

- `scripts/inbox/inject_parse_error_marker.py <filename> <issue_number>` (new)
- `scripts/inbox/strip_parse_error_marker.py <filename>` (new)

## Marker shape

The literal line inserted into the note body:

```
> [!error] felix-capture: could not parse frontmatter on YYYY-MM-DD. See issue #<N> ("Inbox quality" issue for this run).
```

Where `<YYYY-MM-DD>` is the cycle date (UTC) and `<N>` is the "Inbox quality" issue number for the current run.

## Insertion logic (`inject_parse_error_marker.py`)

1. Read the file content.
2. **Find insertion point**:
   - If the file starts with `---` (possibly preceded by a BOM or whitespace) AND a closing `---` is detectable: insertion point is the first non-blank line **after** the closing `---`.
   - Otherwise: insertion point is the very top of the file (line 0).
3. **Idempotency** (FR-009): scan the next ~3 lines from the insertion point looking for a line that starts with `> [!error] felix-capture:`.
   - If found: **replace that line in place** with the new marker (refresh date + issue#).
   - If not found: **insert a new marker line** at the insertion point, followed by a single blank line for visual separation.
4. Write the file atomically: write to `<filename>.tmp`, then `os.replace(<filename>.tmp, <filename>)`.
5. Exit 0 on success; exit 1 with stderr on failure.

## Strip logic (`strip_parse_error_marker.py`)

1. Read the file content.
2. Scan the first ~5 lines for a line starting with `> [!error] felix-capture:`.
   - If found: remove that line. If the line immediately after it is blank, remove that blank line too (so we don't leave orphan whitespace from the inject step).
   - If not found: exit 0 silently (no-op).
3. Write the file atomically (same as inject).
4. Exit 0 on success; exit 1 with stderr on failure.

## Auto-cleanup invocation

Per R-006 (D-001 deferred decision): the **default** path is — prescan classification flags `marker_cleanup_needed` for any file that (a) parses cleanly AND (b) has the marker; the agent invokes `strip_parse_error_marker.py` for each before its Step 5 frontmatter write.

The alternative path (prescan strips directly) is decided in implement phase.

## Failure modes

- File not found: exit 1 with stderr message.
- File not writable: exit 1.
- File contains marker but at unexpected location (deeper than line ~5): inject-script ignores it (treats as user-authored content); future-Kent would need to clean up manually. This is a defensive choice to avoid the agent stripping content it didn't write.

## Test coverage

`tests/inbox/test_callout_marker.py`:

- Inject into a file with well-formed frontmatter: marker lands after closing `---` + blank line
- Inject into a file with no frontmatter: marker lands at top
- Inject when marker already exists: replace-in-place (no duplication)
- Inject preserves all other content (body unchanged)
- Strip when marker present: marker removed, blank-after-marker removed if present
- Strip when marker absent: no-op, file unchanged
- Strip preserves all other content
- Atomic write: corrupted intermediate state never observable (verify via `os.replace` use; not directly testable but documented)
