# Contract — CLI surface

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Entry point**: `python3 -m scripts.habits.backfill_jsonl_from_comments [flags]`

---

## Synopsis

```bash
# Live run
python3 -m scripts.habits.backfill_jsonl_from_comments

# Dry-run (no JSONL writes)
python3 -m scripts.habits.backfill_jsonl_from_comments --dry-run

# Explicit token file path
python3 -m scripts.habits.backfill_jsonl_from_comments --token-file /custom/path

# Explicit Vikunja base URL
python3 -m scripts.habits.backfill_jsonl_from_comments --base-url http://localhost:3456/api/v1/
```

---

## Flags

| Flag | Argument | Required | Default | Notes |
|---|---|---|---|---|
| `--dry-run` | (flag) | no | False | Print summary report only; issue no `state_log.append` calls; no `.bak` snapshot. |
| `--token-file` | path | no | `/data/services/openclaw/secrets/vikunja-api` | Path to the felix-bot API token. Read-only file expected. |
| `--base-url` | URL | no | `http://100.92.197.90:3456/api/v1/` | Vikunja API base. The default targets office2's Tailscale IP. |

---

## Output

### stdout

Plain-text summary report at end of run (dry or live). Structure per data-model.md Entity 4. Mid-run progress lines (e.g., "Resolved Habits project id=13", "Fetching comments for task 14...") may also appear on stdout — these are operator-facing informational lines, not machine-parseable.

### stderr

- Empty on success.
- Error messages on failure: includes the failing API URL, HTTP status code, exception class. Token contents NEVER appear in stderr.

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (dry or live; even with anomalies or unmapped-state values — those are surfaced in the report but don't fail the run) |
| 1 | Vikunja API error during project resolution or task enumeration (unrecoverable; report includes what was achieved before the failure) |
| 2 | Usage / config error (e.g., token file missing, malformed flag, Habits project not uniquely resolvable by title) |
| 3 | Snapshot copy failure on live run (e.g., disk full, permission denied) — backfill aborts BEFORE any JSONL writes |
| 4 | state_log internal failure mid-backfill (rare; report includes partial state up to the failure point) |

---

## Examples

### Dry-run

```bash
$ python3 -m scripts.habits.backfill_jsonl_from_comments --dry-run
Resolved Habits project: id=13 title="Habits"
Enumerating habit tasks (filter: is_archived=false)... 11 tasks
Fetching comments for task 14 (Wake at 5:00 AM)... 8 comments, 8 [Felix] matches
Fetching comments for task 15 (Meditate)... 5 comments, 5 [Felix] matches
...
Fetching comments for task 77 (Strength training — Friday)... 0 comments

=== Backfill summary ===
Mission: backfill-habits-jsonl-from-comments-01KS0Y4F
Run mode: dry-run
...
Records:
  Planned: 24
  ...
```

Exit 0.

### Live run

```bash
$ python3 -m scripts.habits.backfill_jsonl_from_comments
Resolved Habits project: id=13 title="Habits"
Snapshot created: /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak
Enumerating habit tasks... 11 tasks
Fetching comments for task 14 (Wake at 5:00 AM)... 8 comments, 8 [Felix] matches, 8 appended
...

=== Backfill summary ===
Mission: backfill-habits-jsonl-from-comments-01KS0Y4F
Run mode: live
...
Records:
  Appended: 24
  ...
Snapshot:
  /data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak
```

Exit 0.

### Re-run (idempotency check)

```bash
$ python3 -m scripts.habits.backfill_jsonl_from_comments
...

=== Backfill summary ===
Run mode: live
Records:
  Appended: 0
  Skipped (dedup with existing JSONL): 24
  ...
```

Exit 0 (no-op).

### Token file missing

```bash
$ python3 -m scripts.habits.backfill_jsonl_from_comments --token-file /nonexistent
ERROR: token file not found: /nonexistent
```

Exit 2.

---

## Common conventions

- All output is UTF-8.
- All timestamps in stderr/stdout are ISO-8601 with UTC offset.
- Non-interactive: never prompts, never reads from TTY.
- Safe to invoke from a shell, a Bash exec inside an LLM agent, or a one-off cron entry (though there's no expected use case for cron-scheduling backfill).
- Token contents never logged.

---

## Help text

```bash
python3 -m scripts.habits.backfill_jsonl_from_comments --help
```

Prints a synopsis of all flags + exit codes + a 1-line reference to
`docs/design/architecture/data/agent-state-log-schema.md` for the JSONL
schema and to the mission's spec.md.
