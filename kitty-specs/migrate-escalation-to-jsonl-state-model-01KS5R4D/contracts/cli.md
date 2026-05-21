# CLI Contracts

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Date**: 2026-05-21

Each helper exposes both a Python API (contracts/api.md) and a CLI surface for shell/skill invocation. The OpenClaw escalation skill calls the CLI surfaces; pytest tests exercise the Python API directly.

---

## `scripts/escalation/record_completion.py`

### Synopsis

```bash
# JSON record on stdin
echo '<json>' | python3 -m scripts.escalation.record_completion

# Flag-driven
python3 -m scripts.escalation.record_completion \
  --task-id 1234 \
  --project-id 4 \
  --title "Email Q3 board summary" \
  --date 2026-05-21 \
  --state level_sent \
  --level 1 \
  --source agent
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--task-id` | yes (or stdin) | int | Vikunja task id. |
| `--project-id` | yes (or stdin) | int | Vikunja project id. |
| `--title` | yes (or stdin) | str | Task title snapshot. |
| `--date` | yes (or stdin) | YYYY-MM-DD | Local-TZ date of event. |
| `--state` | yes (or stdin) | enum | One of `{level_sent, snoozed, dismissed, done, rescheduled}`. |
| `--source` | yes (or stdin) | enum | One of `{agent, reconcile, backfill, kent_reply, operator_repair}`. |
| `--level` | required if `--state level_sent` | int (1 or 2) | |
| `--snooze-days` | required if `--state snoozed` | int (positive) | |
| `--reschedule-to` | required if `--state rescheduled` | YYYY-MM-DD | |
| `--reason` | optional | str | Free-text on `dismissed`, `done`. |
| `--note` | optional | str | Free-text on any state (Phase 2 library field). |
| `--idempotent` | optional | flag | If set, pre-checks for duplicate; no-op if already exists. |
| `--no-vikunja` | optional | flag | Skip the Vikunja side-effect step. Used by reconcile to write synthetic records without re-sending alerts. |
| `--base-url` | optional | URL | Defaults to `http://100.92.197.90:3456/api/v1/`. |
| `--token-path` | optional | path | Defaults to `/data/services/openclaw/secrets/vikunja-api`. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (three writes done OR idempotent no-op detected) |
| `1` | Vikunja step failure (no JSONL write) |
| `2` | JSONL write failure (Vikunja already committed — operator triages) |
| `3` | Validation or usage error (bad state value, missing required flag, schema violation) |

### Stdout (success path, JSON)

```json
{"ok": true, "jsonl_path": "/data/.../everyday-escalation-history.jsonl", "vikunja_actions": ["comment_PUT"], "deduped": false}
```

### Stderr (failure)

One structured line naming the failed step + the validation error or HTTP code.

---

## `scripts/escalation/reconcile_completions.py`

### Synopsis

```bash
# Reconcile a single project
python3 -m scripts.escalation.reconcile_completions --project-id 4

# Reconcile all escalation-subscribed projects (discovered from existing JSONL files)
python3 -m scripts.escalation.reconcile_completions --all

# Dry-run (no synthetic records written; report only)
python3 -m scripts.escalation.reconcile_completions --all --dry-run
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--project-id` | one of `--project-id`/`--all` required | int | Single-project sweep. |
| `--all` | one of `--project-id`/`--all` required | flag | Sweep every JSONL file in `JSONL_STATE_DIR`. |
| `--dry-run` | optional | flag | Report drift; emit nothing. |
| `--max-tasks` | optional | int | Cap on per-project task count (default: no cap). |
| `--quiet` | optional | flag | Suppress per-task stdout; only emit summary. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Reconcile completed (drift may have been detected and synthetic records emitted) |
| `1` | Vikunja or JSONL fatal error (run aborted; report partial in stderr) |
| `3` | Validation or usage error |

### Stdout (success path)

Per-task line on drift detection (unless `--quiet`):

```
DRIFT task=1234 project=4 reason=vikunja_done emitted_synthetic=done
DRIFT task=5678 project=4 reason=due_date_changed emitted_synthetic=rescheduled
HARDFAIL task=9012 project=4 reason=malformed_jsonl_record bug_url=<url-or-DEDUPED>
```

Summary line at end:

```json
{"project_id": 4, "tasks_scanned": 12, "synthetic_done": 1, "synthetic_rescheduled": 1, "hard_fails": 1, "duration_s": 4.7}
```

---

## `scripts/escalation/backfill_jsonl_from_comments.py`

### Synopsis

```bash
# Single-project backfill
python3 -m scripts.escalation.backfill_jsonl_from_comments --project-id 4

# All escalation-subscribed projects
python3 -m scripts.escalation.backfill_jsonl_from_comments --all

# Dry-run (snapshot still NOT written; full report only)
python3 -m scripts.escalation.backfill_jsonl_from_comments --all --dry-run
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--project-id` | one of `--project-id`/`--all` required | int | |
| `--all` | one of `--project-id`/`--all` required | flag | |
| `--dry-run` | optional | flag | No snapshot, no JSONL writes; full malformed-comment report. |
| `--include-resolved` | optional | flag | Also replay comments on tasks that are currently `done`/`dismissed` (default: skip — terminal tasks don't need replay). |
| `--base-url` | optional | URL | |
| `--token-path` | optional | path | |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Backfill complete (may include malformed comments; check report) |
| `1` | Vikunja fatal error (run aborted) |
| `2` | JSONL or snapshot write failure |
| `3` | Validation or usage error |

### Stdout

Per-malformed-comment line:

```
MALFORMED task=1234 project=4 snippet="<first 80 chars>" reason=<parse-error>
```

Summary block at end (JSON):

```json
{
  "project_id": 4,
  "tasks_scanned": 12,
  "comments_parsed": 47,
  "comments_replayed": 45,
  "comments_malformed": 2,
  "snapshot_path": "/data/.../pre-phase6-snapshot.json",
  "jsonl_path": "/data/.../everyday-escalation-history.jsonl",
  "dry_run": false
}
```

---

## `scripts/escalation/derive_state.py`

### Synopsis

Library-only helper invoked by the other scripts. Has a debugging CLI for operator inspection:

```bash
# Print derived state for one task
python3 -m scripts.escalation.derive_state --task-id 1234 --project-id 4
```

### Output

JSON dump of `EscalationState`:

```json
{
  "task_id": 1234,
  "current_state": "level_1_sent",
  "last_event": {"state": "level_sent", "level": 1, "date": "2026-05-19", ...},
  "snooze_active_until": null,
  "next_eligible_level": 2,
  "last_event_recorded_at": "2026-05-19T12:00:01+00:00"
}
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | JSONL read failure |
| `3` | derive_state raised `EscalationStateError` (Q10 hard-fail surface) — output structured error JSON |
| `4` | Task has zero records in JSONL (caller decides if this is "new" or "phantom subscription") |

---

## Cross-references

- Phase 3 CLI pattern: `scripts/habits/record_completion.py` (mirrored here).
- Spec FR-002 (atomic three-write), FR-009 (dedup CLI behavior via `--idempotent`).
- Research D6 (three-write ordering), D9 (dedup query in hard-fail filing).
