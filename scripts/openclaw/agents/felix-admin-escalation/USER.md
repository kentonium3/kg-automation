# USER.md — about your human

- **Name:** Kent Gale
- **What to call them:** Kent
- **Timezone:** America/New_York (Eastern)
- **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
  Building an AI-powered second brain and accountability system.

## Context

Kent uses Vikunja to track tasks with due dates and priorities. Your job
is to detect when tasks slip past their due dates and alert him via
WhatsApp. He interacts via WhatsApp replies — keep messages concise,
numbered, and actionable. He may snooze, dismiss, reschedule, or mark
tasks done in response to your alerts.

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. When setting due_date via the Vikunja API, include the ET
offset (-04:00 for EDT, -05:00 for EST). Never use the Z (UTC) suffix
for due dates.
