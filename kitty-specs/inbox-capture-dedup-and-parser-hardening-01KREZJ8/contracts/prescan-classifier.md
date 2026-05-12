# Contract: Prescan Classifier (extended)

**Surface**: extend `scripts/inbox/prescan.py`'s classifier with (a) routing-log-aware dedup and (b) parse-failure as a distinct third classification state.

## Current behavior (mission 027 + the processed_at fix)

Returns JSON like:

```json
{
  "unprocessed_count": <int>,
  "unprocessed_paths": ["/abs/path", ...],
  "archived_count": <int>,
  "archived": [{...}],
  "warnings": [...]
}
```

Per-file classifications today: `unprocessed`, `processed`, `needs-review`, `no-frontmatter` (treated as unprocessed). Mission 027's `_extract_frontmatter_block` handles leading blank lines.

## Extended behavior (this mission)

The classifier returns a NEW field on the JSON:

```json
{
  "unprocessed_count": ...,
  "unprocessed_paths": [...],
  "archived_count": ...,
  "archived": [...],
  "warnings": [...],
  "parse_failures": [
    {"path": "/abs/path", "reason": "leading whitespace before opening ---"},
    {"path": "/abs/path", "reason": "UTF-8 BOM at start of file"},
    ...
  ],
  "dedup_skipped": [
    {"path": "/abs/path", "filename": "...", "existing_issue": 176},
    ...
  ]
}
```

### Dedup filtering (FR-003 / R-003)

Before adding a path to `unprocessed_paths`, the classifier asks `RoutingLogReader.has(basename(path))`:

- If True: add to `dedup_skipped` instead; **do not** include in `unprocessed_paths`.
- If False: continue with existing classification logic.

The agent's view of "what's unprocessed" is the post-dedup list. From the agent's perspective, dedup is invisible — the file just doesn't show up in `unprocessed_paths`.

### Parse-failure classification (FR-005)

Before the existing `unprocessed` / `processed` branch, the classifier checks for malformations in this order:

1. **UTF-8 BOM at start of file** — read raw bytes; if first 3 bytes are `\xEF\xBB\xBF`, classify as `parse_failure` with reason `"UTF-8 BOM at start of file"`.
2. **Leading whitespace before `---`** — read raw text (after BOM strip for measurement); if first non-blank character is not `-` AND the raw text contains `---` within first 50 chars, classify as `parse_failure` with reason `"leading whitespace before opening ---"`. (Distinguishes from no-frontmatter case where there's no `---` at all.)
3. **`_extract_frontmatter_block` returns None when the file clearly intended frontmatter** — if raw text starts with `---` but no closing `---` found: classify as `parse_failure` with reason `"missing closing --- (unterminated frontmatter block)"`. (No-frontmatter remains a separate path — files that don't start with `---` at all are still classified as `unprocessed` for backward compatibility.)
4. **YAML parse error** — wrap the existing `yaml.safe_load()` call. On `yaml.YAMLError`, classify as `parse_failure` with reason `"invalid YAML inside frontmatter block: <message>"`.

For all parse-failure cases:

- Add `{path, reason}` to `parse_failures`
- Do NOT add to `unprocessed_paths`
- The agent sees the file in `parse_failures` and acts per FR-004/006/008.

### Auto-cleanup of stale markers (FR-010 / R-006)

After classification produces a `processed` or `unprocessed` (well-formed frontmatter) result, the classifier checks whether the file body contains a top-of-file `> [!error] felix-capture:` marker. If so, the classifier:

- Adds a `marker_cleanup_needed: [path, ...]` field to its JSON output.
- The agent invokes `strip_parse_error_marker.py <path>` for each such path before its Step 5 frontmatter write.

(Alternative: have prescan directly strip the marker via a write call. Defer to implement-phase per R-006 D-001. Default if undecided: prescan flags; agent strips.)

## Failure modes

- Routing log unavailable: warn, treat all files as if dedup-not-found (existing behavior). FR-003 fail-safe.
- Helper script for marker cleanup not present: agent skips and logs; non-fatal.
- New malformation pattern not in our enumeration: falls back to existing classification (which historically might silently treat as unprocessed). This is the "future undetected malformation" risk — the routing log is the load-bearing backstop.

## Test coverage

`tests/inbox/test_prescan_parse_failure.py` (new) and additions to existing prescan tests:

- Each of the 4 parse-failure cases produces correct classification + reason
- BOM strip behavior: BOM-prefixed file is `parse_failure`, NOT silently treated as well-formed
- Routing-log dedup: file present in routing log appears in `dedup_skipped`, not `unprocessed_paths`
- Mixed: well-formed unprocessed + parse-failure + dedup-skipped + already-processed all show up in expected fields
- Regression: existing mission-027 leading-blank-line case still classifies as `unprocessed` (NOT as `parse_failure`) — Kent's existing notes that have a single blank line before `---` should keep working
- Backward compat: existing `unprocessed_paths`-only consumers (if any) still work because new fields are additive
