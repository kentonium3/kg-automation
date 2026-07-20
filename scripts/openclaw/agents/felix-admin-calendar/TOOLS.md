# TOOLS.md

## calendar helper (deterministic Google Calendar CLI)

- Sole calendar-write tool. This agent has **no `gog` skill** — the terminal
  create/update/delete is the deterministic helper `scripts.google.calendar_helper`,
  invoked via the standard `exec` tool. Write the fully-resolved
  `create_calendar_event` payload to a tempfile and pass `--payload-file` (never
  hand-build event bodies). Invocation template (deploy venv, run from
  `/home/claude/kg-automation`):

  ```bash
  /data/services/openclaw/felix-calendar/venv/bin/python \
    -m scripts.google.calendar_helper create \
    --payload-file <tmp> --account <account> \
    --idempotency-key "<source_inbox_path>" --json
  ```

  The helper reads `summary`, the start/end pair (`start_rfc3339`/`end_rfc3339`,
  or all-day `start_date`/`end_date`), and `start_timezone`/`location`/
  `description`/`rrule` from the payload file; it refuses `attendees` unless
  `--allow-attendees` (a note must not silently email people).
- Authoritative flag/exit-code contract:
  `kitty-specs/felix-calendar-helper-*/contracts/calendar-helper-cli.md`.
  Payload (event-body) contract:
  `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/calendar-event-payload.md`.
- `--json` is required for the response envelope: the helper emits a JSON line
  (`{"status": "created", "event_id": …, "html_link": …}`) *before* its final
  `SUMMARY:` line. Parse the JSON line.
- `--idempotency-key "<source_inbox_path>"` de-dupes re-runs of the same source
  note so a retry never double-creates.
- Exit codes: `0` success · `1` operational/API error · `2` usage error ·
  `3` auth failure. A non-zero exit writes `ERROR: …` to stderr and never
  mutated the calendar — surface it verbatim (never fake a created event, #683;
  there is no `gog` fallback).
- OAuth is per-account (credential-set selector `--account`, default `personal`),
  resolved inside the helper from `~/.config/felix/google/<account>/`. Do NOT
  prompt for credentials or run any auth flow in-handler — that's an operator
  surface. An expired/invalid token surfaces as exit `3`.

## State file: pending-calendar-clarifications.json

- Path: `/data/services/openclaw/state/pending-calendar-clarifications.json`
- Format: a JSON **array** of PendingClarification objects
  (`{"note_filename", "partial_payload", "created_at"}`). Managed by
  `scripts.inbox.handle_clarification_state` (`add` / `sweep` / `match`).
  Schema context:
  `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/pending_clarification_record.md`.
- Do NOT hand-roll parsing — use the `handle_clarification_state match` helper to
  match a reply, and let the 24h `sweep` age out resolved/stale entries. The
  helper writes atomically (temp + `os.replace`). Commands (run from
  `/home/claude/kg-automation`):

  ```bash
  # Match an inbound reply to the most-recent open record (prints the entry, or null):
  python3 -m scripts.inbox.handle_clarification_state match --reply-content "<inbound message body>"

  # Remove a resolved record by note filename (prints removed=N):
  python3 -m scripts.inbox.handle_clarification_state remove --note-filename "<matched note_filename>"
  ```

## Validator: validate_calendar_event.py

- Path: `/home/claude/kg-automation/scripts/calendar_routing/validate_calendar_event.py`
- Reads merged candidate block JSON from stdin; emits `complete: true|false`
  plus `missing_fields` and (when complete) `calendar_event_payload`. Invoke
  (from `/home/claude/kg-automation`):

  ```bash
  echo "<merged candidate block JSON>" | python3 scripts/calendar_routing/validate_calendar_event.py
  ```
- Owns deterministic field validation. The LLM job is signal extraction
  from natural-language reply text; the validator does the math.

## log_action

- Path: `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py`
- Every calendar-create attempt emits a structured `log_action` event before the
  response envelope returns (run from `/home/claude/kg-automation`):

  ```bash
  # On success:
  python3 scripts/openclaw/observation/log_action.py \
    --agent felix-admin-calendar --category routine \
    --action calendar_event_created --target "<gcal_event_id>" --outcome success \
    --context '{"source_inbox_path": "<from payload>", "account": "<from payload>", "calendar_id": "<from payload>", "rrule": "<from payload or null>", "clarification_id": "<from payload or null>"}'

  # On failure:
  python3 scripts/openclaw/observation/log_action.py \
    --agent felix-admin-calendar --category error \
    --action calendar_event_failed --target "<source_inbox_path>" --outcome error \
    --context '{"error_detail": "<helper stderr>", "exit_code": <helper exit code>, "clarification_id": "<from payload or null>"}'
  ```
- Clarification resolution ALSO emits `calendar_event_clarification_resolved`:

  ```bash
  python3 scripts/openclaw/observation/log_action.py \
    --agent felix-admin-calendar --category routine \
    --action calendar_event_clarification_resolved \
    --target "<clarification_id>" --outcome success \
    --context '{"source_file": "<source_inbox_path>", "gcal_event_id": "<from helper response>"}'
  ```
- If `log_action.py` itself fails, write a short note to stderr and continue —
  don't block the response envelope on observability failure.

## Privacy

NEVER access `/home/kgale/second-brain/notes/04-Growth/_private/`. The
pending-clarifications state file holds `source_inbox_path` values — if any
ever resolve into `_private/`, treat it as a misrouted payload and abort
without reading the source note.
