# Contract: Audit Log JSONL Schema

**Path**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`
**Format**: One JSON object per line (JSONL), UTF-8 encoded, no header, no trailer.
**Mode**: Append-only. Helper opens with `"a"` mode. No `r+`, no `w`, no `seek`.

## Record types

All records share the following base fields:

| Field | Type | Always present |
|---|---|---|
| `timestamp` | ISO-8601 UTC `str` ending in `Z` | yes |
| `tick_id` | UUID4 `str` (36 chars with hyphens) | yes |
| `kind` | `str` literal | yes |

The `kind` field discriminates the record type. Five kinds are defined.

### kind = "copy"

Emitted when a per-file MD5 mismatch triggered an atomic copy.

| Field | Type | Notes |
|---|---|---|
| `agent_slug` | `str` | e.g., `felix-admin-capture` |
| `filename` | `str` | e.g., `AGENTS.md` |
| `src_md5` | hex `str` (32 chars) | MD5 of source file content |
| `dst_md5_before` | hex `str` (32 chars) OR `null` | MD5 of destination before copy; `null` if destination did not exist |
| `dst_path` | `str` | Absolute deploy path, e.g., `/data/services/openclaw/inbox-agent/AGENTS.md` |

Example:
```json
{"timestamp":"2026-06-08T20:13:31Z","tick_id":"a1b2c3d4-e5f6-7890-1234-56789abcdef0","kind":"copy","agent_slug":"felix-admin-capture","filename":"AGENTS.md","src_md5":"b93950dc85733b9de2d156738636612b","dst_md5_before":"d4f52c558703c6aa7e5389ac8b547670","dst_path":"/data/services/openclaw/inbox-agent/AGENTS.md"}
```

### kind = "skip"

Emitted when source and destination MD5s match — no write performed.

| Field | Type | Notes |
|---|---|---|
| `agent_slug` | `str` | |
| `filename` | `str` | |
| `src_md5` | hex `str` (32 chars) | |
| `dst_md5_before` | hex `str` (32 chars) | Always equals `src_md5` for a skip |

### kind = "error"

Emitted when an attempt to sync a specific file raised an exception.

| Field | Type | Notes |
|---|---|---|
| `agent_slug` | `str` | |
| `filename` | `str` | |
| `error` | `str` | Human-readable error message; class name + key info from the exception |
| `error_class` | `str` | Python exception class name, e.g., `OSError`, `PermissionError` |

### kind = "git_pull_failed"

Emitted when `git fetch` or `git pull --ff-only origin main` returned non-zero. NO file copies are attempted in this tick.

| Field | Type | Notes |
|---|---|---|
| `stage` | `str` enum | `"fetch"` or `"pull"` |
| `git_exit_code` | `int` | Exit code returned by the git subprocess |
| `error` | `str` | Captured stderr (trimmed to ~2000 chars) |

Example:
```json
{"timestamp":"2026-06-08T20:13:31Z","tick_id":"a1b2c3d4-e5f6-7890-1234-56789abcdef0","kind":"git_pull_failed","stage":"pull","git_exit_code":1,"error":"fatal: Not possible to fast-forward, aborting."}
```

### kind = "warning"

Non-fatal anomalies. Iteration continues.

| Field | Type | Notes |
|---|---|---|
| `agent_slug` | `str` | When the warning is agent-scoped |
| `error` | `str` | Description, e.g., `"missing source_in_repo field; agent skipped"` or `"source directory does not exist: scripts/openclaw/agents/foo/"` |

### kind = "tick_summary"

Emitted as the last line of every tick (including ticks that exited with `git_pull_failed`).

| Field | Type | Notes |
|---|---|---|
| `agents_processed` | `int` | Count of agents iterated (skipped-due-to-missing-field NOT counted) |
| `files_copied` | `int` | Count of `kind: copy` actions in this tick |
| `files_skipped` | `int` | Count of `kind: skip` actions in this tick |
| `files_errored` | `int` | Count of `kind: error` actions in this tick |
| `git_head_after_pull` | `str` (40-char hex) OR `null` | HEAD SHA after pull; `null` if pull failed |
| `exit_code` | `int` | Process exit code (0/1/2) |
| `duration_ms` | `int` | Wall-clock from process start to summary-emit |

## Ordering guarantees

- All records within a tick share the same `tick_id`.
- The `tick_summary` record is always the LAST record for its `tick_id`.
- Per-file records appear in iteration order: agents in inventory order, files in `is_in_scope`-iteration order.
- Concurrent ticks cannot occur (timer uses `OnUnitInactiveSec`, not `OnCalendar`).

## Backwards-compatibility commitment

Schema is part of the helper's external contract. Adding a NEW field to an existing record kind is non-breaking. Adding a NEW kind value is non-breaking. Removing or renaming a field, or repurposing an existing kind, is a breaking change and must ship as a separate mission with a versioned migration.

## Test contract

| Test | Asserts |
|---|---|
| `test_audit_copy_record_shape` | A `copy` action emits the required fields and only those fields |
| `test_audit_skip_record_shape` | A `skip` action emits the required fields and only those fields |
| `test_audit_error_record_shape` | An `error` action includes `error_class` and `error` |
| `test_audit_git_pull_failed_shape` | `git_pull_failed` includes `stage`, `git_exit_code`, `error` |
| `test_audit_warning_no_agent_slug` | A warning without an agent scope omits `agent_slug` |
| `test_audit_tick_summary_is_last` | Within a `tick_id`, `tick_summary` is the last entry by file order |
| `test_audit_append_only` | Two ticks back-to-back: file size after tick 2 > file size after tick 1 |
| `test_audit_creates_missing_dir` | Audit log path's parent dir is created on first run |
