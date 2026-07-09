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
| `--json` | off | Emit a JSON result object on stdout in addition to `SUMMARY:` |
| `--dry-run` | off | Validate + resolve creds/args, perform **no** mutation (for create/update/delete) |

## Subcommands

### `create`
Create an event. Two input modes (mutually exclusive):
- `--payload-file <path>` — a `create_calendar_event` envelope (data-model.md).
  This is the mode capture / felix-admin-calendar use.
- Explicit flags: `--summary`, `--start <rfc3339>`, `--end <rfc3339>`,
  `--start-timezone`, `--location`, `--description`, `--rrule`,
  `--attendees <a@x,b@y>`.

Success: `SUMMARY: op=create status=created event_id=<id> account=<a> calendar=<c>`
+ (`--json`) `{"status":"created","event_id":"…","html_link":"…"}`.

### `list`
`--from <rfc3339>` `--to <rfc3339>` `[--max N]` (default 50). Lists events in the
window. Success: `SUMMARY: op=list status=ok count=<n> account=<a> calendar=<c>`
+ (`--json`) `{"status":"ok","events":[{"event_id","summary","start","end"}, …]}`.
An empty window is `count=0` / `events: []` — **not** an error.

### `update`
`--event-id <id>` + any event fields to change (same flags as `create`'s
explicit mode). Read-modify-update semantics (fetch, apply, patch). Success:
`SUMMARY: op=update status=updated event_id=<id> …`.
A non-existent `event_id` → `ERROR: not_found …`, exit 1.

### `delete`
`--event-id <id>`. Success: `SUMMARY: op=delete status=deleted event_id=<id> …`.
Non-existent `event_id` → `ERROR: not_found …`, exit 1.

### `--self-check`
Deploy/preflight mode (no subcommand). Loads creds for `--account`, forces a
token refresh, lists calendars. Success: `SUMMARY: op=self-check status=ok
account=<a> calendars=<n>`, exit 0. Any auth problem → exit 3 (see below). Used
by the deploy post-flight gate.

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
- **Idempotency-friendly.** `create` is not implicitly deduped (Google assigns a
  fresh id); callers that need dedupe pass a stable client-side key via
  `description`/`source_inbox_path` and check with `list` first. (The inbox path
  already marks notes processed to avoid re-creation.)
- **No secrets on stdout/stderr.** Tokens are never printed; only event ids/links.
- **Timezone.** RFC3339 offsets carry the zone; `--start-timezone` sets the
  Google `timeZone` field for recurrence correctness. Default operating zone is
  `America/New_York` when a caller omits it.
