# Decision Moment `01M3AX1NPS0QW9VGAQYQ0H4J09`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `plan`
- **Slot key:** `plan.arm-r.index-unit`
- **Input key:** `arm_r_index_unit`
- **Status:** `resolved`
- **Created:** `2026-09-24T23:47:08.633365+00:00`
- **Resolved:** `2026-09-24T23:49:26.959432+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

What is R's retrieval unit and embedded text: one event per chunk as its rendered JSON line, one entity per chunk, both, or a rendered natural-language form? And is the top-k assembled by rank only or also by ask_time order?

## Options

_(none)_

## Final answer

Per design lead 23:48Z Q4: R = full ENTITY SET as of ask_time included as records (structured half, always present, placed AFTER events like D) + top-k vector retrieval over EVENTS, one event per chunk, embedded from the same natural-language rendering used for D's dump (one text form for every arm); k counts events only; retrieved events RE-SORTED into ask_time order before insertion (chronological, then entities) so R's layout matches D's and its cache prefix is meaningful; retrieval rank order recorded in the ledger per cell, not shown to the model

## Rationale

_(none)_

## Change log

- `2026-09-24T23:47:08.633365+00:00` — opened
- `2026-09-24T23:49:26.959432+00:00` — resolved (final_answer="Per design lead 23:48Z Q4: R = full ENTITY SET as of ask_time included as records (structured half, always present, placed AFTER events like D) + top-k vector retrieval over EVENTS, one event per chunk, embedded from the same natural-language rendering used for D's dump (one text form for every arm); k counts events only; retrieved events RE-SORTED into ask_time order before insertion (chronological, then entities) so R's layout matches D's and its cache prefix is meaningful; retrieval rank order recorded in the ledger per cell, not shown to the model")
