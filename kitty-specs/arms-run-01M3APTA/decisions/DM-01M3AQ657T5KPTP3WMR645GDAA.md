# Decision Moment `01M3AQ657T5KPTP3WMR645GDAA`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `specify`
- **Slot key:** `specify.run-scenario.error-cell-handling`
- **Input key:** `error_cell_retry_policy`
- **Status:** `resolved`
- **Created:** `2026-09-24T22:04:44.154502+00:00`
- **Resolved:** `2026-09-24T22:05:30.496005+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

The most common exception in a multi-hour run: a cell fails for an infrastructure reason (llama-server crash, FalkorDB connection drop, OOM) rather than a model answer. What must the harness do — retry the cell automatically (how many times), record error and move on, or halt the run until an operator looks?

## Options

- Retry up to 2 times after a substrate health check, then record error and continue
- Record error and continue immediately; a later resume re-attempts error cells
- Halt the run on any infrastructure error and post blocked to the bus
- Other

## Final answer

A — retry a cell up to 2 times after a substrate health check passes; then record error and continue; the ledger records every attempt

## Rationale

_(none)_

## Change log

- `2026-09-24T22:04:44.154502+00:00` — opened
- `2026-09-24T22:05:30.496005+00:00` — resolved (final_answer="A — retry a cell up to 2 times after a substrate health check passes; then record error and continue; the ledger records every attempt")
