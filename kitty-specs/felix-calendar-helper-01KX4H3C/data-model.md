# Data Model: Felix Calendar Helper

**Mission**: felix-calendar-helper-01KX4H3C
**Date**: 2026-07-09

This mission is I/O-oriented (a CLI over the Google Calendar API); the "data
model" is the set of value objects the helper reads/writes and the credential
layout, not a persistent schema.

## Entities & value objects

### Account (credential selector)

| Field | Type | Rule |
|---|---|---|
| `name` | string | Selector value; `^[a-z0-9][a-z0-9_-]*$` (validated to prevent path traversal). Default `personal`. |
| `client_secret_path` | path | `~/.config/felix/google/<name>/client_secret.json` (0600) |
| `token_path` | path | `~/.config/felix/google/<name>/token.json` (0600) |

- Resolution: `FELIX_GOOGLE_DIR` (default `~/.config/felix/google`) `/ <name> /`.
  The `FELIX_GOOGLE_DIR` override exists for test isolation.
- Adding an account = create its directory + drop credentials; **no code change**
  (FR-005, SC-005).
- Invariant: the helper refuses a `name` that fails the charset rule (exit 2).

### OAuth credential (per account)

| Field | Type | Rule |
|---|---|---|
| `client_secret.json` | file | Desktop-app OAuth client (from GCP project `felix-personal`). Operator-staged; never committed. |
| `token.json` | file | Authorized-user token incl. `refresh_token`. Minted once (interactive consent on Mac) **with the final scope**, then durable (RFC #681). Auto-refreshed in place (0600). |
| `scopes` | list | `["https://www.googleapis.com/auth/calendar.events"]` — sufficient for event CRUD **and** the bounded `--self-check` (which does `events().list(primary, maxResults=1)`, not a calendars-list). office2 **never** runs interactive consent; a scope/auth failure exits `3` with an actionable "re-mint on the Mac" message. If a future need requires calendar-list, re-mint Mac-side with `calendar` scope and re-stage. |

- **Fail-safe (FR-006)**: if `token.json` is absent, `Credentials` is invalid,
  or a refresh raises `invalid_grant`/`RefreshError`, the helper emits
  `ERROR: auth_failed …` (stderr), `SUMMARY: … status=auth_failed`, mutates
  nothing, and exits **3**.

### Event

The unit created/read/updated/deleted. Google-API request-body shape
(`service.events().insert/update/get/list/delete`):

| Field | Type | Source | Rule |
|---|---|---|---|
| `summary` | string | payload `summary` (from `title`) | required for create |
| `start` | `{dateTime, timeZone?}` | `start_rfc3339` + `start_timezone` | required; RFC3339 with offset |
| `end` | `{dateTime, timeZone?}` | `end_rfc3339` | required; defaulted `start + 1h` upstream when absent |
| `location` | string? | `location` | optional passthrough |
| `description` | string? | `description` | optional passthrough |
| `recurrence` | `["RRULE:…"]`? | `rrule` | optional; RRULE already produced deterministically by `validate_calendar_event.py` |
| `attendees` | `[{email}]`? | `attendees` (comma list) | optional; empty on the default inbox path. **`sendUpdates=none` by default** (no invitation email); inbox-created events reject attendees unless explicitly confirmed (see FR-001 / SC edge case). |
| `extendedProperties.private.felix_source_key` | string? | `source_inbox_path` or `--idempotency-key` | dedupe key stamped on create; used to return an existing event on retry instead of duplicating |
| `id` | string | Google response | returned on create; addressed on update/delete |
| `htmlLink` | string | Google response | surfaced back to the agent/Kent |

### `create_calendar_event` payload (envelope — existing contract, reused)

Produced today by `scripts/inbox/route_calendar_event.py` /
`scripts/calendar_routing/validate_calendar_event.py`; consumed by the new helper
via `--payload-file`. Fields (unchanged except the `account` default):

```json
{
  "action": "create_calendar_event",
  "calendar_id": "primary",
  "account": "personal",                // was "kent@intentional.biz" (D5)
  "summary": "Dentist",
  "start_rfc3339": "2026-07-14T15:00:00-04:00",
  "end_rfc3339":   "2026-07-14T16:00:00-04:00",
  "start_timezone": "America/New_York",  // or null (offset carries the zone)
  "location": null,
  "description": "Source: note-123.md",
  "rrule": null,                          // or "RRULE:FREQ=WEEKLY;BYDAY=MO"
  "attendees": null,
  "source_inbox_path": "/…/01-Inbox/note-123.md",
  "clarification_id": null
}
```

The helper maps `account` → credential set, `calendar_id` → target calendar,
and the remaining fields → the Google event body. It does **not** re-parse
natural language — that stays upstream (deterministic, D4).

## State transitions

Stateless per invocation (the helper holds no cursor). The only persistent
mutation the helper performs is refreshing `token.json` in place (atomic write,
0600). Event lifecycle (create → update → delete) lives in Google Calendar and
is addressed by the returned `id`. The inbox clarification lifecycle is owned by
the agents and unchanged: it is a **JSON array** at
`/data/services/openclaw/state/pending-calendar-clarifications.json` (per
`scripts/inbox/handle_clarification_state.py`) — not a `.jsonl` file. The
clarification-reply handler (felix-admin-calendar) keeps this store and swaps
only its terminal `gog` call for the helper.

## Externally visible effects

| Effect | When | Observability |
|---|---|---|
| Google Calendar event created/updated/deleted | on `create`/`update`/`delete` success | `SUMMARY: op=<op> status=<created\|updated\|deleted> event_id=<id> account=<a> calendar=<c>` + JSON `{status, event_id, html_link}` on stdout |
| `token.json` refreshed | when the loaded token was expired-but-refreshable | silent (0600 in-place write); no secret printed |
| Auth failure | missing/invalid/`invalid_grant` | `ERROR: auth_failed …` stderr, exit 3, no mutation |
| API/operational error | Google API 4xx/5xx, network timeout | `ERROR: …` stderr, exit 1, no partial mutation surfaced as success |
