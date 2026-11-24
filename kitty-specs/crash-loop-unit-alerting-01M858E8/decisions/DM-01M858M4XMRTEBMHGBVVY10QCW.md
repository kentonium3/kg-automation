# Decision Moment `01M858M4XMRTEBMHGBVVY10QCW`

- **Mission:** `crash-loop-unit-alerting-01M858E8`
- **Origin flow:** `specify`
- **Slot key:** `specify.signal.loop-threshold`
- **Input key:** `loop_threshold`
- **Status:** `resolved`
- **Created:** `2026-11-23T22:32:30.900404+00:00`
- **Resolved:** `2026-11-23T22:32:32.267519+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

What restart rate counts as a crash loop?

## Options

- A: Any increase in NRestarts between two checks
- B (recommended): N restarts within a window, global default (e.g. >=3 in 15 min)
- C: A per-unit threshold kept in service-inventory.json
- Other

## Final answer

B: N restarts within a window, one global default (e.g. >=3 in 15 min); a single restart does not alert

## Rationale

_(none)_

## Change log

- `2026-11-23T22:32:30.900404+00:00` - opened
- `2026-11-23T22:32:32.267519+00:00` - resolved (final_answer="B: N restarts within a window, one global default (e.g. >=3 in 15 min); a single restart does not alert")
