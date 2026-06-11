# Contract: calendar event creation payload (PRESERVED FROM main)

**Status**: Preserved 1:1 from `main/AGENTS.md` lines 259–331 as of pre-extraction baseline.
**Owner after extraction**: `felix-admin-calendar`
**Caller**: `felix-admin-capture` (inbox processor) via openclaw-agent dispatch
**Authoritative reference**: `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/capture_to_main_calendar_payload.md`

## Inbound payload

JSON message body delivered via openclaw-agent message:

| Field | Required | Type | Default | Source |
|---|---|---|---|---|
| `action` | yes | string | — | always `"create_calendar_event"` |
| `calendar_id` | yes | string | `"primary"` | resolved by capture |
| `account` | yes | email | `"kent@intentional.biz"` | resolved by capture |
| `summary` | yes | string | — | inbox-extracted |
| `start_rfc3339` | yes | RFC3339 timestamp | — | inbox-extracted + validated |
| `end_rfc3339` | yes | RFC3339 timestamp | — | inbox-extracted + validated |
| `source_inbox_path` | yes | absolute path | — | capture's inbox note path |
| `start_timezone` | no | IANA tz | (none) | inbox-extracted |
| `location` | no | string | (none) | inbox-extracted |
| `description` | no | string | (none) | inbox-extracted |
| `rrule` | no | RFC 5545 RRULE | (none) | inbox-extracted |
| `attendees` | no | list of email | (none) | inbox-extracted |
| `clarification_id` | no | string | `null` | set on self-dispatch from clarification reply handler |

## Behavior (preserved verbatim from current main handler)

1. Parse payload as JSON; use values verbatim.
2. Compose `gog calendar create` invocation with conditional flags.
3. Capture stdout JSON; parse `eventId` and `htmlLink`.
4. Emit structured `log_action` event via `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py` (success or failure variant).
5. Return response envelope.

### gog invocation template

```bash
gog calendar create <calendar_id> \
  --account <account> \
  --summary "<summary>" \
  --from <start_rfc3339> --to <end_rfc3339> \
  [--start-timezone <start_timezone>] \
  [--location "<location>"] \
  [--description "<description>"] \
  [--rrule "<rrule>"] \
  [--attendees "<comma-joined attendees>"] \
  -j
```

### Response envelope

Success (gog exit 0):

```json
{
  "status": "created",
  "gcal_event_id": "<gog eventId>",
  "html_link": "<gog htmlLink>",
  "summary": "<summary>",
  "start_rfc3339": "<start>",
  "rrule": "<rrule or null>"
}
```

Failure (gog non-zero exit, malformed output, or unexpected error):

```json
{
  "status": "error",
  "error": "<gog stderr verbatim>",
  "exit_code": "<gog exit code>"
}
```

## Authentication

`gog` OAuth is wired via the `openclaw-gateway-env` systemd EnvironmentFile and `GOG_KEYRING_PASSWORD`. No per-call credential work is required.

**Note**: this credential surface continues serving the `felix-admin-calendar` process after extraction with no change. The systemd unit `openclaw-gateway-env` is shared by all openclaw agents that run under the gateway.

## Logging contract (preserved)

On success:

```bash
python /home/claude/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-calendar \
  --category routine \
  --action calendar_event_created \
  --target "<gcal_event_id>" \
  --outcome success \
  --context '{"source_inbox_path": "<from payload>", "account": "<from payload>", "calendar_id": "<from payload>", "rrule": "<from payload or null>", "clarification_id": "<from payload or null>"}'
```

On failure:

```bash
python /home/claude/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-calendar \
  --category error \
  --action calendar_event_failed \
  --target "<source_inbox_path>" \
  --outcome error \
  --context '{"error_detail": "<gog stderr>", "exit_code": "<gog exit code>", "clarification_id": "<from payload or null>"}'
```

**Change from current main version**: `--agent` value changes from `main` to `felix-admin-calendar`. This is the ONLY substantive content change relative to the current handler text. All other prose and code blocks move verbatim.

Order: log_action fires before returning the response envelope. If `log_action.py` itself fails (non-zero exit), write a short note to stderr and continue — do not block the response envelope on observability failure.

## Self-dispatch (preserved)

The "Calendar clarification reply handler" performs a self-dispatch into "Calendar event creation" when re-validation succeeds. After the move, this self-dispatch is internal to `felix-admin-calendar/AGENTS.md` (handler A calls into handler B within the same agent's prompt). No openclaw-agent round-trip; the contract is the same JSON payload shape above.
