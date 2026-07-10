# TOOLS.md

## calendar helper (deterministic Google Calendar CLI)

- Sole calendar-write tool. This agent has **no `gog` skill** — the terminal
  create/update/delete is the deterministic helper `scripts.google.calendar_helper`,
  invoked via the standard `exec` tool. Invocation template lives in the Calendar
  event creation handler in `AGENTS.md` (Calendar helper invocation section).
- Deploy venv path on office2:
  `/data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper`.
  Run from `/home/claude/kg-automation`.
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
  helper writes atomically (temp + `os.replace`).

## Validator: validate_calendar_event.py

- Path: `/home/claude/kg-automation/scripts/calendar_routing/validate_calendar_event.py`
- Reads merged candidate block JSON from stdin; emits `complete: true|false`
  plus `missing_fields` and (when complete) `calendar_event_payload`.
- Owns deterministic field validation. The LLM job is signal extraction
  from natural-language reply text; the validator does the math.

## log_action

- Path: `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py`
- All calendar-create attempts (success or failure) log via this helper
  before the response envelope returns. See Logging subsection in AGENTS.md.

## Privacy

NEVER access `/home/kgale/second-brain/notes/04-Growth/_private/`. The
pending-clarifications state file holds `source_inbox_path` values — if any
ever resolve into `_private/`, treat it as a misrouted payload and abort
without reading the source note.
