# CLI Contracts

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Date**: 2026-05-22

Each helper exposes both a Python API (contracts/api.md) and a CLI surface for AGENTS.md invocation.

---

## `scripts/habits/morning_checkin_list.py`

### Synopsis

```bash
# Build today's morning list + write artifact + emit WhatsApp message to stdout
python3 -m scripts.habits.morning_checkin_list

# Specify a date explicitly (defaults to today-local)
python3 -m scripts.habits.morning_checkin_list --date 2026-05-23

# Dry-run: emit message + intended artifact path to stdout; write nothing
python3 -m scripts.habits.morning_checkin_list --dry-run
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--date` | optional | YYYY-MM-DD | Defaults to today in America/New_York. |
| `--dry-run` | optional | flag | Skip persistence; emit only. |
| `--state-dir` | optional | path | Defaults to `/data/services/openclaw/state/habits`. |
| `--base-url` | optional | URL | Vikunja API base. Defaults to `http://100.92.197.90:3456/api/v1/`. |
| `--token-path` | optional | path | Defaults to `/data/services/openclaw/secrets/vikunja-api`. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (message emitted to stdout; artifact written unless dry-run) |
| `1` | Vikunja unreachable / API failure |
| `2` | Filesystem write failure (Vikunja step succeeded; artifact persist failed) |
| `3` | Validation / usage error (bad date format, bad flags) |

### Stdout

The formatted WhatsApp message (verbatim what Kent should receive). Example:

```
Morning check-in — Friday, May 23:

1. Wake at 5:00 AM
2. Meditate
3. Morning shoulder PT
4. Get steps in today
5. Read 30 min minimum
6. Evening shoulder PT
7. Morning hip PT
8. Strength training — Friday

Reply with what you've done (e.g., "1 and 2 done, skipping 4")
```

If `habits` is empty: `"All habits complete for today."`.

### Stderr

One structured line per error, JSON-formatted, e.g.:

```json
{"step": "vikunja_fetch", "error": "URLError: timeout"}
```

---

## `scripts/habits/parse_morning_reply.py`

### Synopsis

```bash
# Parse Kent's reply against today's morning list
python3 -m scripts.habits.parse_morning_reply --reply "Skipped 3,7,8 done"

# Specify a different date
python3 -m scripts.habits.parse_morning_reply --reply "all done" --date 2026-05-22

# Read reply from a file
python3 -m scripts.habits.parse_morning_reply --reply-file /tmp/kent-reply.txt
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--reply` | one of `--reply` / `--reply-file` required | str | Kent's reply text. |
| `--reply-file` | one of `--reply` / `--reply-file` required | path | Alternative: read reply text from a file. |
| `--date` | optional | YYYY-MM-DD | Date of the morning list to load. Defaults to today-local. |
| `--state-dir` | optional | path | Where the morning lists live. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Parse succeeded (output `tuples` and possibly `judgment_required`) |
| `1` | I/O error reading reply file |
| `3` | Validation / usage error (bad flags, both `--reply` and `--reply-file`, etc.) |
| `4` | No morning list exists for the date (file not found) |
| `5` | Morning list file is corrupted (JSON parse failed or schema mismatch) |

### Stdout (always JSON)

Full `ParseResult` shape per data-model Entity 2. Even on exit code 4 or 5, stdout MAY emit a partial result with `errors` populated to enable agent introspection.

---

## `scripts/habits/judgment/disambiguate_reply.py`

### Synopsis

```bash
# Disambiguate a judgment_required item — input as JSON via stdin
cat ambiguity.json | python3 -m scripts.habits.judgment.disambiguate_reply

# OR input from file
python3 -m scripts.habits.judgment.disambiguate_reply --input-file /tmp/ambiguity.json
```

### Flags

| Flag | Required | Type | Notes |
|---|---|---|---|
| `--input-file` | optional | path | If not provided, reads input JSON from stdin. |
| `--model` | optional | str | Defaults to `claude-haiku-4-5`. |
| `--api-key-path` | optional | path | Defaults to `/data/services/openclaw/secrets/anthropic`. |
| `--timeout` | optional | seconds | Defaults to 30. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Disambiguator returned a valid response (`chosen` or `clarify`) |
| `1` | LLM API error (network, auth, rate limit) |
| `3` | Validation error (bad input JSON, schema mismatch, malformed LLM response) |
| `5` | LLM returned `chosen_task_id` outside the candidate set |

### Stdin / `--input-file` format

`JudgmentItem` shape per data-model Entity 3 (wrapped in `{ambiguity: ..., reply_text: ...}`).

### Stdout (always JSON)

`DisambiguationResult` shape per data-model Entity 4.

---

## Cross-references

- Mission #309 CLI contract style (mirrored here): `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md`
- Spec FR-001 through FR-011 (each requirement maps to a CLI surface)
- Research D11 (cutover sequence uses these CLI surfaces verbatim for smoke-testing)
