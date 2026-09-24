# Decision Moment `01M3APV8CQ0V90VSXB3PE09WQS`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `specify`
- **Slot key:** `specify.run-scenario.operator-and-envelope`
- **Input key:** `run_operator_and_office4_envelope`
- **Status:** `resolved`
- **Created:** `2026-09-24T21:58:46.935703+00:00`
- **Resolved:** `2026-09-24T22:03:29.878857+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

When the 72-cell primary run executes on office4, who starts and resumes it across session limits, and under what resource envelope — may the 80B model stay resident (~51 GiB GTT, GPU saturated) while you are using the machine, or only in windows you declare?

## Options

- Me under auto-run, model resident whenever needed, any hour
- Me, but only inside windows Kent declares on the bus
- Kent starts each session manually; I only build
- Other

## Final answer

A — office4 session under auto-run runs and resumes the matrix from the ledger; model resident whenever a cell needs it, any hour

## Rationale

_(none)_

## Change log

- `2026-09-24T21:58:46.935703+00:00` — opened
- `2026-09-24T22:03:29.878857+00:00` — resolved (final_answer="A — office4 session under auto-run runs and resumes the matrix from the ledger; model resident whenever a cell needs it, any hour")
