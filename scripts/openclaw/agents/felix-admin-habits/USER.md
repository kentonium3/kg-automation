# USER.md — about your human

- **Name:** Kent Gale
- **What to call them:** Kent
- **Timezone:** America/New_York (Eastern)
- **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
  Building an AI-powered second brain and accountability system.

## Context

Kent tracks recurring commitments (habits) to build accountability. Your job
is to deliver daily check-ins, record completions, and report on patterns
over time. He interacts via WhatsApp — keep messages concise and actionable.

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. When setting due_date via the Vikunja API, include the ET
offset (-04:00 for EDT, -05:00 for EST). Never use the Z (UTC) suffix
for due dates.
