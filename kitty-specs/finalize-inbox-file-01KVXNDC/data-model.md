# Data Model: Atomic inbox-file finalize helper

This helper operates on filesystem artifacts, not a database. The "entities" are
on-disk files and their states.

## Entities

### InboxFile

A Markdown note with YAML frontmatter.

| Field | Source | Notes |
|-------|--------|-------|
| `path` | CLI argument | Must resolve under the inbox root (C-001) |
| `frontmatter.status` | YAML frontmatter | `unprocessed` → `processed` (FR-003) |
| `basename` | derived | Idempotence key for move + log (D-04) |
| `location` | filesystem | `01-Inbox/` (pre) → `02-Inbox-Processed/` (post) |

**Validation rules**: file exists; resolves under inbox root; frontmatter present
and parseable via `yaml.safe_load` (FR-002). Failure → exit 1.

### DailyProcessingLog

`02-Inbox-Processed/inbox-processing-<YYYY-MM-DD>.md` (UTC date, FR-005/C-003).

| Field | Notes |
|-------|-------|
| frontmatter | standard; written on file creation if absent |
| line per file | `filename \| routed_by \| finalized_at_utc` |

**Validation rules**: at most one line per `filename` per day (FR-006 / NFR-002).

### VaultPathRegistry

`scripts/vault/paths.json` — `{version, updated, paths}`. Read-only here; supplies
inbox root and processed-dir paths. Env override for hermetic tests (D-02).

## State transitions (per file)

```
                 ┌─────────────────────────────────────────────┐
                 │                                             │
 [01-Inbox,      │  set status     [01-Inbox,      move        ▼  append log   [02-Processed,
  unprocessed] ──┼──(idempotent)──► processed]  ──(idempotent)──► processed]──(idempotent)──► processed + logged]
                 │                                                                                    │
                 └── re-invocation enters at the first not-yet-done step; completed steps are no-ops ─┘
```

Terminal state = file in `02-Inbox-Processed/` with `status: processed` AND a
daily-log line present. Any step failure stops forward progress and exits non-zero
without leaving a partially-written artifact (NFR-001).

## Invariants

- **INV-1 (atomicity)**: no reader ever observes a half-written frontmatter file
  or a half-moved file (temp+rename, `os.rename`).
- **INV-2 (idempotency)**: N invocations ⇒ same end state and exactly one log line.
- **INV-3 (observability)**: success ⇒ exit 0 + JSON stdout; failure ⇒ non-zero +
  stderr message. Never silent.
- **INV-4 (no cross-FS copy)**: a cross-filesystem move fails (exit 2), never
  degrades to copy+unlink.
