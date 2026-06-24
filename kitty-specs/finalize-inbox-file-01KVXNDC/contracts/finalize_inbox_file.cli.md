# CLI Contract: scripts/inbox/finalize_inbox_file.py

This helper has a CLI contract (not an HTTP API). The contract below is the
acceptance surface for the test suite (NFR-004).

## Invocation

```
python3 scripts/inbox/finalize_inbox_file.py <inbox_file_path> [--routed-by <agent-id>]
```

- `<inbox_file_path>` (positional, required): path to the inbox Markdown file.
- `--routed-by <agent-id>` (optional): caller identity recorded in the daily-log
  line. Defaults to a generic/unknown marker if omitted.

Hermetic-test override: the vault path registry location is overridable via the
same environment variable mechanism `prescan.py` uses, so tests point at a tmp
vault. (Exact env var name reconciled with prescan in the tasks phase.)

## Behavior (ordered, each step idempotent)

1. Validate: path exists, resolves under inbox root, frontmatter parseable.
2. Set frontmatter `status: processed` (no-op if already processed) — atomic
   temp-write + fsync + rename.
3. Move file to `02-Inbox-Processed/` via `os.rename` (no-op if already there by
   basename).
4. Append `filename | routed_by | finalized_at_utc` to
   `inbox-processing-<YYYY-MM-DD>.md` (UTC), creating it with frontmatter if
   absent (no-op if a line for the filename already exists).

## Exit codes

| Code | Meaning | stderr | Agent action |
|------|---------|--------|--------------|
| `0` | success OR already-finalized | — | record complete |
| `1` | validation failure (bad path, outside inbox root, missing/malformed frontmatter) | reason | content defect; do not retry; surface |
| `2` | filesystem failure (permission denied, cross-FS rename, rename race) | specific `OSError` | environmental; surface for operator; do not mark complete |

## stdout (success only)

Single-line JSON, matching the `prescan.py` convention:

```json
{"finalized": true, "steps_executed": ["status", "move", "log"], "file_final_path": "/abs/path/02-Inbox-Processed/<name>.md"}
```

- `steps_executed` lists only steps that actually mutated state this invocation
  (empty-ish on a fully-idempotent re-run, where `finalized` is still `true`).
- On non-zero exit, stdout carries no result object; diagnostics go to stderr.

## Test matrix (maps to acceptance scenarios 1–8 / NFR-004)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Happy path (unprocessed → final) | exit 0; status processed; in processed dir; one log line; JSON stdout |
| 2 | Already finalized | exit 0; no changes; no duplicate log line |
| 3 | Partial recovery (moved+status, no log) | exit 0; only log line appended |
| 4 | Permission denied (file write) | exit 2; OSError on stderr; no partial file |
| 5 | Permission denied (dir write) | exit 2; OSError on stderr |
| 6 | Missing frontmatter | exit 1 |
| 7 | Malformed YAML | exit 1 |
| 8 | Cross-filesystem rename | exit 2 (no copy fallback) |
