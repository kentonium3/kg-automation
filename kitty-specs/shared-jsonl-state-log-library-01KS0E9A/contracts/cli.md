# Contract — CLI surface

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Entry point**: `python3 -m scripts.common.state_log <subcommand> ...`

The CLI exists so LLM agents (running via OpenClaw's Bash tool) and shell-scripted consumers can call the library without importing it. Same semantics as the Python API; just a different invocation surface.

---

## Subcommand: `append`

### Synopsis

```bash
python3 -m scripts.common.state_log append --domain <name>
```

A complete JSON record is read from stdin (one line, terminated by newline). The record's `domain` field MUST equal `--domain`.

### Example

```bash
echo '{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-19T11:05:11+00:00"}' \
  | python3 -m scripts.common.state_log append --domain habits
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Append succeeded OR idempotent no-op |
| 1 | Validation failure (stderr message names the field + value) |
| 2 | Underlying I/O error (stderr has the OSError detail) |
| 3 | Usage error (e.g., missing `--domain`, no record on stdin, malformed JSON) |

### Output

- **stdout**: empty on success
- **stderr**: human-readable error on failure (validation or I/O), or empty on success

### Side effects

- Same as the Python `append()` function (creates dir + file as needed).

---

## Subcommand: `read`

### Synopsis

```bash
python3 -m scripts.common.state_log read --domain <name> [filter flags...]
```

### Filter flags

| Flag | Argument | Meaning |
|---|---|---|
| `--task-id` | int | Exact match on `task_id` |
| `--date` | YYYY-MM-DD | Exact ISO-8601 date match |
| `--date-from` | YYYY-MM-DD | Inclusive lower bound |
| `--date-to` | YYYY-MM-DD | Inclusive upper bound |
| `--state` | str | Exact state value match |
| `--source` | str | Exact source value match |

Filters are AND-combined. Omitting all filters returns the entire log for the domain.

### Output

- **stdout**: matching records, one JSON object per line, in append order (file order). Empty stdout if no matches.
- **stderr**: empty on success; error message on usage failure.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Read succeeded (empty result is success) |
| 2 | Underlying I/O error |
| 3 | Usage error (unknown flag, malformed value, unknown domain) |

### Example

```bash
# All habits records for task 14 in May 2026
python3 -m scripts.common.state_log read --domain habits \
  --task-id 14 \
  --date-from 2026-05-01 \
  --date-to 2026-05-31
```

---

## Common conventions

- All output is UTF-8.
- All timestamps in stderr are ISO-8601 with UTC offset.
- The CLI is non-interactive: never prompts, never reads from a TTY beyond stdin for `append`.
- Suitable for invocation from cron, systemd timer, Bash exec from an LLM agent, or interactive shell.
- Stable across the library's v0 lifecycle — breaking changes require a coordinated migration.

---

## Help text

```bash
python3 -m scripts.common.state_log --help
python3 -m scripts.common.state_log append --help
python3 -m scripts.common.state_log read --help
```

Each prints the relevant subset of this contract document.
