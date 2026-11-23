# Decision Moment `01M858MA4V9RNQFF2PAN0XY563`

- **Mission:** `crash-loop-unit-alerting-01M858E8`
- **Origin flow:** `specify`
- **Slot key:** `specify.latency.detection-window`
- **Input key:** `detection_latency`
- **Status:** `resolved`
- **Created:** `2026-11-23T22:32:36.251046+00:00`
- **Resolved:** `2026-11-23T22:32:37.590594+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How fast must a crash-loop alert land?

## Options

- A (recommended): Within one canary tick (<=15 min), using the persistent restart counter
- B: Within 5 min (faster cadence or event-driven hook)
- Other

## Final answer

A: Within one canary tick (<=15 min), using the persistent NRestarts counter

## Rationale

_(none)_

## Change log

- `2026-11-23T22:32:36.251046+00:00` - opened
- `2026-11-23T22:32:37.590594+00:00` - resolved (final_answer="A: Within one canary tick (<=15 min), using the persistent NRestarts counter")
