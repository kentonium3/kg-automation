# Data Model — Atomic in-place inbox finalize

Phase 1. This mission has no database; the "data model" is the inbox note's
frontmatter contract, the CLI exit-code contract, and the stdout/stderr payload
shapes.

## Entity: Inbox note

A `.md` file under the registry-resolved inbox root (`01-Inbox/`) with YAML
frontmatter.

| Field | Type | Notes |
|-------|------|-------|
| `status` | string | finalize target: `unprocessed` → `processed`. Idempotent if already `processed`. |
| `processed_at` | string (ISO-8601 UTC) | set alongside `status` on a real write; untouched on idempotent no-op. |
| *(all others)* | preserved | key order + values round-tripped verbatim; body preserved verbatim. |

**Invariants**
- **In place**: the note's path does not change (no move to `02-Inbox-Processed/`).
- **Atomicity**: on-disk note is always either the original or the fully-written new
  version — never partial (temp + fsync + `os.replace`, original mode preserved).
- **Privacy**: a path under `04-Growth/_private/` is refused before any read.

## Exit-code contract (state → code)

| Code | Meaning | Trigger |
|------|---------|---------|
| `0` | success / idempotent no-op | write succeeded, or note already `processed` |
| `1` | validation failure | missing file · path outside inbox root · missing/unparseable frontmatter |
| `2` | filesystem error | `OSError` during the atomic write (perm denied, write race); original uncorrupted |
| `3` | privacy refusal | path under `04-Growth/_private/` (fires before disk read) |

## stdout (success only) — single line JSON

```json
{"finalized": true, "already_processed": false, "status": "processed", "file_final_path": "/abs/path/01-Inbox/Inbox 2026-06-28 0915.md"}
```

- `already_processed: true` on the idempotent no-op path (no write performed).
- Exactly one line; no trailing diagnostics on stdout (NFR-004).

## stderr (failure + INFO) — single line JSON / INFO

```json
{"error": "fs_error", "detail": "<OSError repr>"}          # exit 2
{"error": "outside_inbox_root", "detail": "<path>"}        # exit 1
{"error": "no_frontmatter", "detail": "<reason>"}          # exit 1
{"error": "missing_file", "detail": "<path>"}              # exit 1
{"error": "refused", "detail": "path is under 04-Growth/_private/"}  # exit 3
```

(`INFO: atomic_write … mode=…` remains on stderr from the existing helper.)

## State transitions

```
unprocessed --finalize(success)--> processed        (exit 0, real write, stdout finalized)
processed   --finalize(noop)-----> processed        (exit 0, already_processed=true)
unprocessed --finalize(fs-error)-> unprocessed      (exit 2, note uncorrupted)
*           --validation-fail-----> (unchanged)      (exit 1)
_private/*  --refusal-------------> (unread)          (exit 3)
```
