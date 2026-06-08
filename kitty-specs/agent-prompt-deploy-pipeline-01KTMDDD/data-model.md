# Data Model: Agent Prompt Deploy Pipeline

**Mission**: `agent-prompt-deploy-pipeline-01KTMDDD`
**Phase**: 1 (Design & Contracts)
**Date**: 2026-06-08

This mission has no persistent data store and no database schema. All data is either (a) read from existing JSON files maintained outside this mission's scope, (b) written as append-only JSONL audit records, or (c) ephemeral in-process dataclasses. This document captures the minimal projections and record types the helper uses.

## Entities

### AgentInventoryEntry (in-process)

The minimal projection of `services[openclaw].agents.<slug>` that the helper requires. Read once per tick from `docs/design/architecture/data/service-inventory.json` and held as a frozen dataclass.

| Field | Type | Source | Notes |
|---|---|---|---|
| `slug` | `str` | dict key under `services[openclaw].agents` | e.g., `felix-admin-capture`, `main` |
| `source_in_repo` | `Path` | `<entry>.source_in_repo` | Repo-relative; resolved against `/home/claude/kg-automation` at runtime. e.g., `scripts/openclaw/agents/felix-admin-capture/` |
| `workspace` | `Path` | `<entry>.workspace` | Absolute deploy path on office2. e.g., `/data/services/openclaw/inbox-agent` |

**Validation**:
- An entry with missing or empty `source_in_repo` OR missing or empty `workspace` is skipped at iteration time, logged as a `warning` audit action.
- An entry with `source_in_repo` pointing to a non-existent directory is skipped at sync time, logged as a `warning` audit action with `agent_slug` set.

**Invariants**:
- Frozen at construction (immutable dataclass).
- `slug` is the canonical agent identifier and is used as the dictionary key in audit records.

### SyncAction (audit record)

One JSONL line per file-level action. Append-only at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `timestamp` | ISO-8601 UTC `str` | yes | e.g., `2026-06-08T20:13:31Z` |
| `tick_id` | UUID4 `str` | yes | Same value for all entries within one tick (correlate with TickSummary) |
| `kind` | `enum` literal `str` | yes | One of: `copy`, `skip`, `error`, `git_pull_failed`, `warning` |
| `agent_slug` | `str` | when applicable | Omitted for `git_pull_failed`; required otherwise |
| `filename` | `str` | when applicable | Omitted for `git_pull_failed`; required for `copy`/`skip`/`error` |
| `src_md5` | hex `str` (32 chars) | for `copy`/`skip` | MD5 of the source file at sync time |
| `dst_md5_before` | hex `str` or `null` | for `copy`/`skip` | MD5 of the destination at sync time; `null` if destination did not exist |
| `error` | `str` | for `error`/`git_pull_failed`/`warning` | Human-readable error string |

**Allowed `kind` values and their semantics**:

- `copy` — drift detected (src_md5 != dst_md5_before), source bytes copied to destination atomically. Always followed by no immediate corresponding skip.
- `skip` — no drift (src_md5 == dst_md5_before), no write performed.
- `error` — exception occurred while syncing a specific file (e.g., disk full, permission denied). Other files in the tick may still succeed.
- `git_pull_failed` — `git fetch` or `git pull --ff-only` returned non-zero. No file copies attempted in this tick. `stage` field added to indicate which git command failed.
- `warning` — non-fatal anomaly (e.g., agent missing `source_in_repo` field, source dir does not exist on disk).

**Append-only invariant**: The helper never seeks, never rewrites existing lines. Concurrent writers within one tick (impossible by design, since the tick is a single-process oneshot) would be the only failure mode.

### TickSummary (audit record)

One JSONL line per tick, emitted as the last line before process exit.

| Field | Type | Required | Notes |
|---|---|---|---|
| `timestamp` | ISO-8601 UTC `str` | yes | Tick end timestamp |
| `tick_id` | UUID4 `str` | yes | Matches all SyncAction entries in this tick |
| `kind` | literal `"tick_summary"` | yes | Distinguishes from per-file SyncAction lines |
| `agents_processed` | `int` | yes | Count of agents iterated (excludes skipped-due-to-missing-field) |
| `files_copied` | `int` | yes | Count of `copy` actions emitted this tick |
| `files_skipped` | `int` | yes | Count of `skip` actions emitted this tick |
| `files_errored` | `int` | yes | Count of `error` actions emitted this tick |
| `git_head_after_pull` | `str` or `null` | yes | The 40-char SHA of HEAD post-pull, or `null` if pull failed |
| `exit_code` | `int` | yes | Process exit code (0/1/2 per FR-010) |
| `duration_ms` | `int` | yes | Wall-clock time from process start to summary-emit |

## External Data Sources (Read-Only)

### `docs/design/architecture/data/service-inventory.json`

Read once per tick by the helper. The helper consumes only the path:
```
services[openclaw].agents.<slug>.{source_in_repo, workspace}
```
No other fields are read. No fields are written.

**Schema stability assumption** (per Assumption in spec.md): The shape of `services[openclaw].agents` (object with slug keys and source_in_repo / workspace fields per entry) is treated as stable for this mission. If a future schema migration changes this shape, the helper's `iter_agents` function will need a corresponding migration.

### Office2 filesystem state (read + write)

- **Read**: `/home/claude/kg-automation/scripts/openclaw/agents/<slug>/<filename>` (after `git pull --ff-only`).
- **Write**: `/data/services/openclaw/<deploy-dir>/<filename>` (atomic, via temp + os.replace).
- **Write**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` (append-only).
- **Write**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl.tmp.<pid>` (transient temp file during atomic-copy operations against other files; cleaned up by `os.replace` success or left harmlessly on failure).

## State Transitions

This helper is stateless — each tick is a fresh process. There are no in-memory state machines, no persisted state cursors, no resume semantics.

The only "state" the helper carries between ticks is implicit in the deployed file contents. If a tick fails partway, the next tick treats the partial state as the new baseline and resumes from there (idempotent: a file already deployed correctly is a no-op skip).

## Invariants

| Invariant | Enforcement Surface |
|---|---|
| `tick_id` is unique per tick and is propagated to every audit record emitted by that tick. | Generated once at top of `main()`, passed into all `audit_record` calls. |
| `git_pull_failed` and any file-level `copy` action cannot co-occur in the same tick. | `main()` early-exits on `git_pull_failed` before invoking `sync_agent`. |
| Destination file mode is preserved when the destination existed prior to copy. | `atomic_copy` reads `dst.stat().st_mode` before write, applies via `os.chmod` to the temp file before `os.replace`. |
| Excluded filename patterns (`HEARTBEAT.md`, `*.tmpl`, `*.bak*`, `GOVERNANCE.md`) are never the source or target of a `copy` action. | `is_in_scope(filename)` is the single gate; tested explicitly per-pattern in `test_is_in_scope_excludes_*`. |
| Audit log file is never rewritten in-place. | Helper opens in `"a"` mode only; no `r+`, no `w`, no `seek`. |
| Source files removed from the repo dir do not cause deployed files to be removed. | `sync_agent` iterates source files (not deployed files); a deployed file with no source counterpart is never touched. |

## Externally Visible Events

This helper emits no webhooks, no notifications, no Vikunja tasks, no GitHub issues, no WhatsApp messages. It updates files on disk and appends to a log. All operator visibility flows through:

1. The JSONL audit log (`/data/services/openclaw/deploy/agent-prompt-sync.jsonl`).
2. The systemd journal (`journalctl --user -u agent-prompt-sync.service`).
3. The deployed file states themselves (MD5-comparable).
4. The systemd timer status (`systemctl --user list-timers`).

No external integrations. No identity surfaces. No new credentials required.
