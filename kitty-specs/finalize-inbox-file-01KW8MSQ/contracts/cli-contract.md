# CLI Contract — `mark_processed.py` (finalize)

The finalize helper is the existing `scripts/inbox/mark_processed.py`, hardened.
It is the orchestrator-facing contract `felix-admin-capture` Step 5c depends on.

## Invocation (mandatory `-m` module form)

```
python3 -m scripts.inbox.mark_processed --path <absolute-path-to-note>
```

- `--path` (required): absolute path to the note in `01-Inbox/`.
- Run from the repository root (module import resolution; per the helper `-m`
  convention — script-path form is not supported).

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | success, including idempotent re-run on an already-`processed` note |
| `1` | validation failure: missing file · path outside inbox root · missing or unparseable frontmatter |
| `2` | filesystem error: `OSError` on the atomic write (permission denied, write race) — original note uncorrupted |
| `3` | refusal: `--path` under `04-Growth/_private/` |

## stdout

- **Success (exit 0) only**: exactly one line of JSON —
  `{"finalized": true, "already_processed": <bool>, "status": "processed", "file_final_path": "<abs path>"}`.
- Non-zero exits write nothing to stdout.

## stderr

- Errors: single-line JSON `{"error": "<kind>", "detail": "<...>"}` (kinds:
  `missing_file`, `no_frontmatter`, `outside_inbox_root`, `fs_error`, `refused`).
- Existing `INFO: atomic_write <path> mode=<oct> (<kind>)` line on success.

## Orchestrator handling (felix-admin-capture Step 5c)

| Exit | Agent action |
|------|--------------|
| `0` | finalize complete — proceed (note stays in `01-Inbox/`) |
| `1` | validation failure — surface in the run summary; do NOT silently continue |
| `2` | filesystem error — surface/escalate (this is the silent-failure class); note left `unprocessed` |
| `3` | privacy refusal — expected for `_private/`; skip, no escalation |

**Invariant retained**: Step 5 never moves or deletes the note; it stays at its
`01-Inbox/` path. `prescan.py` archives after the 7-day window.

## Guarantees preserved (regression contract)

- Atomic, mode-preserving write (temp + fsync + `os.replace`).
- Idempotent on already-`processed` notes (no write; exit 0).
- Full frontmatter key-order + body round-trip.
- `04-Growth/_private/` refusal before any disk read.
- Stdlib-only; no new dependencies.
