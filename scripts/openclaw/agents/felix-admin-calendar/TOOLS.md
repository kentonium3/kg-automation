# TOOLS.md

## gog (Google Calendar CLI)

- Sole calendar-write tool. Invocation template lives in the Calendar event
  creation handler in `AGENTS.md` (gog command synthesis section).
- Authoritative payload contract:
  `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/calendar-event-payload.md`.
- Run via the standard exec tool. `-j` flag is required for the response
  envelope (gog emits JSON on stdout with `eventId` and `htmlLink`).
- OAuth is pre-wired: `openclaw-gateway-env` systemd EnvironmentFile injects
  `GOG_KEYRING_PASSWORD`. Do NOT prompt for credentials or run `gog auth`
  in-handler — that's an operator surface, not an agent surface.
- Refresh-token health is tracked separately (#572 weekly probe). Failures
  surface as gog non-zero exit; the response envelope conveys the stderr
  verbatim per the contract.

## State file: pending-calendar-clarifications.jsonl

- Path: `~/second-brain/agents/state/pending-calendar-clarifications.jsonl`
- Format: JSONL, one record per line. Schema:
  `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/pending_clarification_record.md`.
- Write protocol: `fcntl.LOCK_EX` + atomic `.tmp` + `os.rename` (see Resolve
  and create step 3 in AGENTS.md). Same protocol as capture's append-record.

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
