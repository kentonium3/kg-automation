# USER.md — about your human

- **Name:** Kent Gale
- **What to call them:** Kent
- **Timezone:** America/New_York (Eastern)
- **Default calendar account:** personal (Kent's kentgale@gmail.com calendar; helper `--account personal`)
- **Default calendar:** primary
- **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
  Building an AI-powered second brain and accountability system.

## Context

Kent uses Google Calendar as his canonical scheduling substrate. Most events
arrive via inbox extraction — capture parses notes from Wispr Flow dictation
and other inbox sources, builds a CalendarEventPayload, and delegates the
write to you. When the inbox payload is incomplete (missing time, date,
duration, etc.), capture prompts him on WhatsApp and you handle the reply
round-trip.

## Date and time handling

- All dates resolve in **America/New_York**, not UTC. office2 runs in UTC —
  use `TZ=America/New_York date` for date math.
- Capture pre-resolves `start_rfc3339` / `end_rfc3339` with the correct
  offset (-04:00 EDT / -05:00 EST). Use them verbatim.
- For clarification replies with relative phrases ("next Tuesday", "tomorrow"),
  resolve against **inbound message receipt time** — not the original
  prompt's `sent_at`. See Resolve and create § tick_iso in AGENTS.md.
- Never use the `Z` (UTC) suffix on calendar event timestamps.

## Calendar conventions

- Default duration when unspecified: 60 minutes.
- Default location: empty (no inference).
- Attendees: empty by default; only populate when explicitly named in the
  source note or clarification reply.
- RRULE: only populate when the source explicitly states recurrence
  ("every Tuesday", "weekly", "biweekly", etc.). Do NOT invent recurrence
  from a single-occurrence event.

## Privacy

Kent's private journal at `04-Growth/_private/` is off-limits. Event
metadata that originated there reaches you only as a sanitized payload
from capture; never follow `source_inbox_path` back into that directory.
