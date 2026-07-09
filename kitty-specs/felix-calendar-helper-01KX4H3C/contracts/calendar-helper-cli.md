# Contract: Calendar Helper CLI

**Module**: `scripts/google/calendar_helper.py`
**Invocation (office2)**: `cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper <subcommand> [flags]`
**Auth module**: `scripts/google/calendar_auth.py`

Conforms to `docs/design/helper-script-conventions.md`: argparse subcommands,
long-form flags, meaningful exit codes, a final `SUMMARY:` line on stdout,
`INFO:`/`WARN:` operational lines, `ERROR:` to stderr.

## Common flags (all subcommands)

| Flag | Default | Meaning |
|---|---|---|
| `--account <name>` | `personal` | Credential set under `~/.config/felix/google/<name>/` |
| `--calendar-id <id>` | `primary` | Target calendar |
| `--json` | off | Emit a JSON result object on **preceding** stdout line(s); the **final** stdout line is always `SUMMARY:` (agent parse anchor). JSON never comes after SUMMARY. |
| `--dry-run` | off | Validate + resolve creds/args, perform **no** mutation (for create/update/delete) |

## Subcommands

### `create`
Create an event. Two input modes (mutually exclusive):
- `--payload-file <path>` — a `create_calendar_event` envelope (data-model.md).
  This is the mode capture / felix-admin-calendar use.
- Explicit flags: `--summary`, `--start <rfc3339>`, `--end <rfc3339>`,
  `--start-timezone`, `--location`, `--description`, `--rrule`,
  `--attendees <a@x,b@y>`.

Additional flags:
- `--send-updates {none,externalOnly,all}` — default **`none`**. The helper never
  emails invitations unless explicitly set. On the inbox path attendees are
  rejected (error, exit 2) unless the caller passes `--allow-attendees` — a note
  should not silently email people from Kent's personal calendar.
- `--idempotency-key <key>` — stamped as `extendedProperties.private.felix_source_key`
  (the inbox path derives it from `source_inbox_path`). On a `create` whose key
  matches an existing event in a bounded lookback, the helper returns that event
  (`status=created idempotent=true`) instead of inserting a duplicate.

Success: `SUMMARY: op=create status=created idempotent=<true|false> event_id=<id> account=<a> calendar=<c>`
+ (`--json`, on a preceding line) `{"status":"created","idempotent":false,"event_id":"…","html_link":"…"}`.

### `list`
`--from <rfc3339>` `--to <rfc3339>` `[--max N]` (default 50). Lists events in the
window. Success: `SUMMARY: op=list status=ok count=<n> account=<a> calendar=<c>`
+ (`--json`, preceding line) a concrete schema:
```json
{"status":"ok","count":2,"events":[
  {"event_id":"abc","summary":"Dentist","start":"2026-07-14T15:00:00-04:00",
   "end":"2026-07-14T16:00:00-04:00","recurring":false}
]}
```
An empty window is `count=0` / `events: []` — **not** an error.

### `update`
`--event-id <id>` + any event fields to change (same flags as `create`'s
explicit mode). **Patch semantics**: only fields explicitly provided are changed;
omitted fields are left untouched (get-then-patch). To **remove** an optional
field, pass `--clear <comma-list>` (e.g. `--clear location,description,attendees`)
— an empty/absent flag never clears. Concurrent-edit protection (ETag/`If-Match`)
is **deferred** for v1 (documented; last-write-wins). **Recurring events**: v1
updates the event id as given (series master); single-occurrence edits of a
recurring series are **out of scope** → `ERROR: recurrence_scope_unsupported`,
exit 2 (future `--recurrence-scope single|series`). Success:
`SUMMARY: op=update status=updated event_id=<id> …`.
A non-existent `event_id` → `ERROR: not_found …`, exit 1.

### `delete`
`--event-id <id>` `[--send-updates {none,all}]` (default `none`). Deletes/cancels
the event id as given. **Recurring**: whole series (the id) in v1; single-instance
cancellation is out of scope (same error as update). Success:
`SUMMARY: op=delete status=deleted event_id=<id> …`.
Non-existent `event_id` → `ERROR: not_found …`, exit 1.

### `--self-check`
Deploy/preflight mode (no subcommand). Loads creds for `--account`, forces a
token refresh, and does a **bounded** `events().list(calendarId=primary,
maxResults=1)` (covered by the `calendar.events` scope — no calendars-list, no
scope trap). Success: `SUMMARY: op=self-check status=ok account=<a>`, exit 0. It
**never** runs an interactive consent flow (office2 is headless); any missing/
invalid token or scope/refresh failure → exit 3 with an actionable
"re-mint token on the Mac with scope <X>" message. Used by the deploy post-flight
gate.

## Exit codes (contract)

| Code | Meaning | Behavior |
|---|---|---|
| `0` | success | mutation (if any) completed; `SUMMARY: … status=<created\|updated\|deleted\|ok>` |
| `1` | operational / API error (4xx/5xx, timeout, `not_found`) | `ERROR: …` stderr; no partial success reported; `SUMMARY: … status=error` |
| `2` | usage error (bad/missing args, invalid `--account` name, both/neither create input modes) | argparse-style `ERROR:` stderr |
| `3` | **auth failure** — missing/invalid token, `invalid_grant`, refresh failure | `ERROR: auth_failed …` stderr; **no mutation**; `SUMMARY: … status=auth_failed` |

The distinct `3` lets agents and the deploy self-check tell "credentials need
(re)staging" apart from a transient API error, and guarantees a failed auth can
never be read as a completed action (FR-006 / SC-004 / no-silent-fallback).

## Invariants

- **Never mutate on auth failure.** Auth is resolved before any `insert/update/
  delete` call; a failure short-circuits to exit 3.
- **Idempotent create for keyed callers.** A `create` carrying an
  `--idempotency-key` (the inbox path always does, from `source_inbox_path`)
  stamps `extendedProperties.private.felix_source_key` and returns the existing
  event on a key match rather than inserting a duplicate — closing the
  insert-succeeds-but-mark-fails retry window. Un-keyed (conversational) creates
  are intentionally not deduped.
- **No accidental invitations.** `--send-updates` defaults to `none`; the inbox
  path rejects attendees unless `--allow-attendees` is passed.
- **No secrets on stdout/stderr.** Tokens are never printed; only event ids/links.
- **Timezone.** RFC3339 offsets carry the zone; `--start-timezone` sets the
  Google `timeZone` field for recurrence correctness. Default operating zone is
  `America/New_York` when a caller omits it.
