# Decision Moment `01KX8TY3N10EQT1V81Z8DJCMRZ`

- **Mission:** `felix-canary-registry-01KX8T7B`
- **Origin flow:** `plan`
- **Slot key:** `plan.datamodel.freshness-threshold`
- **Input key:** `freshness_threshold`
- **Status:** `resolved`
- **Created:** `2026-07-11T14:57:34.881748+00:00`
- **Resolved:** `2026-07-11T15:00:54.165094+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Should per-component freshness be a machine-readable max_age_seconds field on health_check, or parsed from the prose expected clause?

## Options

- machine-readable-field
- parse-prose
- Other

## Final answer

Machine-readable optional max_age_seconds field added to health_check in service-inventory.json; runner reads it directly, validator can enforce; no prose parsing.

## Rationale

_(none)_

## Change log

- `2026-07-11T14:57:34.881748+00:00` — opened
- `2026-07-11T15:00:54.165094+00:00` — resolved (final_answer="Machine-readable optional max_age_seconds field added to health_check in service-inventory.json; runner reads it directly, validator can enforce; no prose parsing.")
