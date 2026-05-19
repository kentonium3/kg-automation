# Contract — CLI surface

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`

Each helper in `scripts/habits/` exposes a `__main__` CLI per C-006. Same invocation pattern as Phase 2's `state_log` library: `python3 -m scripts.habits.<helper> [args]`.

All helpers default to reading the Vikunja API token from `/data/services/openclaw/secrets/vikunja-api` (felix-bot per Phase 1). All accept `--token-file <path>` to override (mostly for testing).

---

## `identify_workout_task`

### Synopsis

```bash
python3 -m scripts.habits.identify_workout_task [--token-file <path>]
```

### Output

stdout: one JSON object describing the workout task (or `null` if no match):

```json
{"task_id": 17, "title": "Workout", "project_id": 1, "labels": ["personal"], "repeat_after": 0, "due_date": "2026-05-19T08:00:00Z"}
```

stderr: human-readable progress + the candidate IDs searched.

### Exit codes

| 0 | Success — exactly one workout task found (or `null` reported clearly) |
| 1 | Multiple workout-like tasks found (operator must disambiguate manually) |
| 2 | Underlying I/O error |

---

## `migrate_schedule`

### Synopsis

```bash
# Apply schedule (Tier 2: requires pre-flight snapshot confirmed)
python3 -m scripts.habits.migrate_schedule \
    --schedule kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml \
    --snapshot-out /data/services/openclaw/state/habits-pre-phase3-snapshot.json

# Dry-run (no HTTP calls, prints planned changes)
python3 -m scripts.habits.migrate_schedule \
    --schedule kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml \
    --snapshot-out /data/services/openclaw/state/habits-pre-phase3-snapshot.json \
    --dry-run

# Rollback (reverse a prior run)
python3 -m scripts.habits.migrate_schedule \
    --rollback \
    --snapshot-file /data/services/openclaw/state/habits-pre-phase3-snapshot.json
```

### Flags

| Flag | Argument | Required | Notes |
|---|---|---|---|
| `--schedule` | path | yes (unless `--rollback`) | YAML file matching the contracts/config.md schema |
| `--snapshot-out` | path | yes (unless `--rollback`) | Where to write BEFORE-state JSON |
| `--dry-run` | (flag) | no | Print plan; no HTTP; snapshot still written with before_states |
| `--rollback` | (flag) | no | Reverse-apply from snapshot |
| `--snapshot-file` | path | required for `--rollback` | Path to existing snapshot |
| `--token-file` | path | no (default `/data/services/openclaw/secrets/vikunja-api`) | Vikunja API token |

### Output

stdout: per-operation status lines (one per op):

```
[1/11] op=patch task_id=14 (Wake at 5:00 AM): before(repeat_after=0) -> after(repeat_after=86400) [OK]
[2/11] op=patch task_id=15 (Drink water): before(repeat_after=0) -> after(repeat_after=86400) [OK]
...
[8/11] op=retire task_id=17 (Workout): done=true [OK]
[9/11] op=create title="Strength training — Monday" -> task_id=100 [OK]
...

SUMMARY: applied 11/11 operations; snapshot at /data/services/openclaw/state/habits-pre-phase3-snapshot.json
```

For `--rollback`:
```
[1/11] reverse op=create task_id=102 (Strength training — Friday): DELETE [OK]
...
SUMMARY: rollback complete; 11 changes reversed
```

stderr: warnings (e.g., "task 14 already matches target schedule — skipped"), errors.

### Exit codes

| 0 | All operations succeeded (or all reversed during rollback) |
| 1 | Mid-batch failure during apply (snapshot on disk is partial; operator can rollback or retry) |
| 2 | Usage / config / schema validation error (no HTTP issued) |
| 3 | Pre-flight check failure (e.g., token file missing) |

---

## `record_completion`

### Synopsis

```bash
# Stdin = JSON record (same shape as state_log append)
echo '{"task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-20","state":"complete","source":"whatsapp","note":null}' \
    | python3 -m scripts.habits.record_completion
```

Alternative — flag-driven (for shell composability):

```bash
python3 -m scripts.habits.record_completion \
    --task-id 14 \
    --title "Wake at 5:00 AM" \
    --date 2026-05-20 \
    --state complete \
    --source whatsapp
```

### Output

stdout: empty on success.
stderr: error messages on failure (each names which of the three writes failed).

### Exit codes

| 0 | Three writes succeeded (or idempotent no-op detected) |
| 1 | Vikunja write failure (POST done=true or PUT comment) |
| 2 | state_log write failure (Vikunja writes succeeded but JSONL append failed — partial state; operator triages) |
| 3 | Validation / usage error (bad state value, missing required arg, etc.) |

---

## `reconcile_completions`

### Synopsis

```bash
# Standard invocation (uses today's UTC date for drift comparison)
python3 -m scripts.habits.reconcile_completions

# Override the comparison date (for testing or historical re-run)
python3 -m scripts.habits.reconcile_completions --today 2026-05-19
```

### Output

stdout: a summary block at the end:

```
=== reconcile_completions 2026-05-20T12:00:00+00:00 ===
tasks_examined: 10
backfilled: 2
  - task_id=14 date=2026-05-19 source=vikunja-ui
  - task_id=18 date=2026-05-19 source=vikunja-ui
drift: 1
  - DRIFT: task_id=14 (Wake at 5:00 AM): JSONL says complete for 2026-05-20 but Vikunja shows done=false
errors: 0
```

### Exit codes

| 0 | Reconcile completed (with or without drift; drift is informational) |
| 1 | Unrecoverable Vikunja API failure (couldn't enumerate tasks) |
| 2 | Usage error (bad --today value, etc.) |

---

## `query_active_habits_v2`

### Synopsis

```bash
# Print active-today habits as JSONL on stdout
python3 -m scripts.habits.query_active_habits_v2

# Override today
python3 -m scripts.habits.query_active_habits_v2 --today 2026-05-20
```

### Output

stdout: one JSON object per active habit, newline-delimited. Same shape as `query_active_habits.py` (the v1 sibling) for downstream compatibility:

```json
{"id":14,"title":"Wake at 5:00 AM","due_date":"2026-05-20T08:00:00Z","done":false,"repeat_after":86400,"project_id":1,"labels":[...]}
{"id":15,...}
```

Empty stdout if no active habits.

### Exit codes

| 0 | Success (empty result OK) |
| 1 | Vikunja API failure |
| 2 | Usage error |

---

## `exclude_completed_v2`

### Synopsis

```bash
# Accept active-habit list on stdin, emit not-yet-completed-today on stdout
python3 -m scripts.habits.query_active_habits_v2 \
    | python3 -m scripts.habits.exclude_completed_v2

# Override today
python3 -m scripts.habits.query_active_habits_v2 --today 2026-05-20 \
    | python3 -m scripts.habits.exclude_completed_v2 --today 2026-05-20
```

### Output

stdout: subset of the input JSONL — same format, only tasks without today's `complete` JSONL entry.

### Exit codes

| 0 | Success |
| 1 | state_log read failure (rare) |
| 2 | Usage / malformed stdin |

---

## Common conventions across all helpers

- All output UTF-8.
- All timestamps ISO-8601 with UTC offset.
- Non-interactive: never prompts, never reads from a TTY beyond the documented stdin paths.
- `--help` exits 0 with usage info per Python argparse convention.
- All helpers are safe to invoke from cron, systemd timer, Bash exec from an LLM agent, or interactive shell.
- All helpers stable across the v0 lifecycle of this mission — breaking changes require a coordinated migration of Phase 4-5 dependents.
