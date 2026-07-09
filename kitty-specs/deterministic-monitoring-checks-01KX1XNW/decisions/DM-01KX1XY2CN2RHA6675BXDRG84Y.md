# Decision Moment `01KX1XY2CN2RHA6675BXDRG84Y`

- **Mission:** `deterministic-monitoring-checks-01KX1XNW`
- **Origin flow:** `plan`
- **Slot key:** `plan.healthcheck.runner-mechanism`
- **Input key:** `healthcheck_runner_mechanism`
- **Status:** `resolved`
- **Created:** `2026-07-08T22:35:18.293172+00:00`
- **Resolved:** `2026-07-08T22:36:24.298244+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should the twice-daily health-check run off the Sonnet main agent: a systemd user timer (matches felix-core-digest deterministic posture) or a non-agent openclaw cron (keeps existing WhatsApp delivery)?

## Options

- systemd user timer
- non-agent openclaw cron
- let research decide

## Final answer

systemd user timer — matches the felix-core-digest deterministic reference posture; fully removes the agent; result delivery re-implemented off the agent path (ntfy or direct notify, to be finalized in research against office2).

## Rationale

_(none)_

## Change log

- `2026-07-08T22:35:18.293172+00:00` — opened
- `2026-07-08T22:36:24.298244+00:00` — resolved (final_answer="systemd user timer — matches the felix-core-digest deterministic reference posture; fully removes the agent; result delivery re-implemented off the agent path (ntfy or direct notify, to be finalized in research against office2).")
