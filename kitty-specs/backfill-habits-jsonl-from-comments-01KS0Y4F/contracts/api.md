# Contract — Python API

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Module**: `scripts.habits.backfill_jsonl_from_comments`

---

## Public functions

### `backfill(api_base_url, token, *, dry_run=False, today=None) -> dict`

```python
def backfill(
    api_base_url: str,
    token: str,
    *,
    dry_run: bool = False,
    today: str | None = None,
) -> dict:
    """One-shot historical backfill of habits JSONL from [Felix] comments.

    Args:
        api_base_url: Vikunja API base URL (e.g.,
            "http://100.92.197.90:3456/api/v1/").
        token: felix-bot API token (read from
            /data/services/openclaw/secrets/vikunja-api).
        dry_run: If True, no JSONL writes occur. The function returns the
            same summary dict but with `records_appended` set to 0 and
            `records_planned` populated.
        today: Unused for backfill itself; reserved for symmetry with other
            habits helpers in case future test fixtures need a clock-pin.

    Returns:
        Summary dict matching the shape printed by the CLI (see data-model.md
        Entity 4). Keys: run_mode, comments_fetched, records_appended (or
        records_planned in dry-run), records_skipped_dedup,
        records_skipped_unmapped, records_skipped_malformed, anomalies,
        by_task (dict[int, int]), by_state (dict[str, int]),
        unmapped_state_values (list of dicts), snapshot_path (str or None).

    Side effects:
        - Resolves the "Habits" Vikunja project via GET /projects.
        - GET /projects/<habits_id>/tasks?filter=is_archived=false to
          enumerate habit tasks.
        - GET /tasks/<task_id>/comments per task.
        - On live run with at least one append planned: shutil.copy2 of
          /data/services/openclaw/state/habits-history.jsonl to
          /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak
          (skipped if the source file doesn't exist).
        - On live run: state_log.append("habits", record) per record with
          source="historical-backfill" and timestamp from comment.created.

    Raises:
        OSError: If the Vikunja API is unreachable, returns non-2xx for the
            project resolution or task enumeration, or if the .bak snapshot
            copy fails. Per-comment fetch failures are caught and reported as
            anomalies (do not raise).
        ValueError: If the Habits project cannot be uniquely resolved (zero
            or multiple matches by exact title "Habits").
    """
```

### `HISTORICAL_STATE_MAP` (constant, importable)

```python
HISTORICAL_STATE_MAP: dict[str, str]
```

The current locked content:

```python
{"complete": "complete", "will-not-do": "skipped"}
```

Consumers (other than backfill itself) MAY import this to discover what
historical mappings exist. They MUST NOT mutate it.

---

## Exceptions raised

| Exception | When |
|---|---|
| `ValueError` | Habits project resolution fails (0 or >1 exact-title match); invalid arg types caught at the function boundary. |
| `OSError` (incl. `urllib.error.URLError`, `urllib.error.HTTPError`, `PermissionError`, `FileNotFoundError`) | Vikunja API errors during project/task enumeration; snapshot copy failure; state_log internal I/O failure. |

Per-comment HTTP fetch failures are NOT raised — they're caught, logged in
`anomalies`, and the loop continues. This matches the spec FR-009 expectation
that anomalies surface in the summary rather than aborting the run.

---

## Thread / process safety

- Single-threaded, single-process. Not designed for concurrent invocation.
- Phase 2's state_log handles its own fcntl locking, so even if a Phase 5
  cron tick somehow ran simultaneously with backfill, the JSONL appends
  would interleave safely. But there's no expected use case for that.

---

## Backward compatibility

The backfill helper is a one-shot tool. Once executed in production
(post-Phase-4 merge), it is not re-invoked unless an operator-initiated
rollback + re-run is needed. Therefore, the API signature is NOT considered
stable for downstream re-use; it can change without breakage.
