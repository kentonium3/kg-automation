# Decision Moment `01M858MCPTFXEKHDDM7ZCSP4N0`

- **Mission:** `crash-loop-unit-alerting-01M858E8`
- **Origin flow:** `specify`
- **Slot key:** `specify.lifecycle.alert-repeat-clear`
- **Input key:** `alert_lifecycle`
- **Status:** `resolved`
- **Created:** `2026-11-23T22:32:38.874096+00:00`
- **Resolved:** `2026-11-23T22:32:40.211725+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Once a crash loop has alerted, when should it alert again or clear?

## Options

- A (recommended): Once per loop episode, with a cleared entry after K quiet ticks
- B: On every tick while the loop continues
- Other

## Final answer

A: Once per loop episode, with a cleared entry after K quiet ticks (matching the canary dedup)

## Rationale

_(none)_

## Change log

- `2026-11-23T22:32:38.874096+00:00` - opened
- `2026-11-23T22:32:40.211725+00:00` - resolved (final_answer="A: Once per loop episode, with a cleared entry after K quiet ticks (matching the canary dedup)")
