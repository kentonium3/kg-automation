# Contract — Python API

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Module**: `scripts.common.state_log`

This document is the contract any consumer (script or LLM agent calling via `python3 -m`) can depend on. Changes to these signatures or semantics are breaking changes and require a coordinated update across all consumers.

---

## Public functions

### `append(domain, record) -> None`

```python
def append(domain: str, record: dict) -> None:
    """Append a state-log record to the per-domain JSONL file.

    Args:
        domain: One of {"habits", "escalation", "enrichment"}. Must match
            DOMAIN_STATES.keys() exactly.
        record: Dict containing all REQUIRED_FIELDS. `note` is optional.
            The `domain` field on the record MUST match the `domain` argument.

    Returns:
        None. Successful append (or successful idempotent no-op) returns
        normally.

    Raises:
        ValueError: If validation fails — missing required field, wrong type,
            state not in domain enum, malformed date/timestamp, etc. The
            exception message names the offending field and value.
        OSError: If the underlying file I/O fails (permission denied, disk
            full, etc.). Caller decides whether to retry.

    Idempotency:
        If a line already exists in the target file whose (task_id, date,
        state) tuple matches the incoming record, append returns normally
        without writing anything. No exception is raised — successful
        idempotent return is indistinguishable from successful new write.

    Concurrency:
        Multiple processes may call append() against the same domain
        simultaneously. fcntl.LOCK_EX serializes access; all calls observe
        a consistent file state.

    Side effects:
        - Creates `/data/services/openclaw/state/` (mode 0775) if absent.
        - Creates `/data/services/openclaw/state/<domain>-history.jsonl`
          (mode 0664) if absent.
        - On first append, ownership is best-effort claude:secondbrain
          (silent if chown fails — group ownership is advisory).
    """
```

### `read(domain, **filters) -> list[dict]`

```python
def read(domain: str, **filters) -> list[dict]:
    """Read state-log records for a domain, optionally filtered.

    Args:
        domain: One of {"habits", "escalation", "enrichment"}.
        **filters: Optional kwargs filtering the result set. Supported:
            - task_id (int): exact match
            - date (str): exact ISO-8601 date match
            - date_from (str): inclusive lower bound (ISO-8601 date)
            - date_to (str): inclusive upper bound (ISO-8601 date)
            - state (str): exact state value match
            - source (str): exact source value match
            Unknown kwargs raise TypeError (defensive — caller probably typo'd).

    Returns:
        A list of record dicts in append order (file order, top-to-bottom).
        Empty list if no records match or the file does not exist yet.

    Raises:
        ValueError: If domain is unknown.
        TypeError: If an unknown filter kwarg is passed.
        OSError: If the file exists but cannot be read.

    Concurrency:
        read() acquires a shared lock (fcntl.LOCK_SH) for the duration of
        the file scan, so concurrent readers don't block each other but a
        concurrent append() will wait.
    """
```

### `DOMAIN_STATES` (constant, importable)

```python
DOMAIN_STATES: dict[str, frozenset[str]]
```

Exported from `scripts.common.state_log_schema`. Consumers may import this to
discover valid state values for a domain (e.g., for UI dropdown population).
Re-exported from `scripts.common.state_log` for convenience.

### `REQUIRED_FIELDS` (constant)

```python
REQUIRED_FIELDS: tuple[str, ...]
```

Same — importable from either module.

### `validate_record(record, domain) -> None`

```python
def validate_record(record: dict, domain: str) -> None:
    """Validate a record against the schema and the domain's state enum.

    Args:
        record: Record dict to validate.
        domain: Target domain (constrains the allowed state values).

    Raises:
        ValueError: With a specific message naming the offending field and
            value. The first violation encountered short-circuits — multiple
            failures in one record produce one error, not a list.

    Returns:
        None on success.
    """
```

Exposed so consumers (or tests) can pre-validate without committing to a write.

---

## Exceptions raised

| Exception | When |
|---|---|
| `ValueError` | Schema violation, type mismatch, unknown domain, malformed date/timestamp, state not in enum |
| `TypeError` | Unknown filter kwarg in `read()` |
| `OSError` (and subclasses: `PermissionError`, `FileNotFoundError`, etc.) | Underlying file I/O failure |

No custom exception classes are introduced — these stdlib exceptions are precise enough and callers can catch them by type.

---

## Thread / process safety

- All public functions are safe to call from multiple processes simultaneously.
- Within a single process, public functions ARE NOT designed for concurrent use across threads. The fcntl lock is per-process; intra-process serialization is the caller's responsibility if relevant. (In practice, the Felix agents are single-threaded Python.)

---

## Backward compatibility

The library is at v0 — the first release. Once a consumer phase (3, 6, or 7) merges depending on this library, the function signatures above are frozen. Adding new optional parameters or new public functions is non-breaking; renaming or removing is breaking and requires coordinated migration of all consumers.
