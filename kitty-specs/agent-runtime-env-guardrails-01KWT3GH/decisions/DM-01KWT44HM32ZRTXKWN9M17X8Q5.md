# Decision Moment `01KWT44HM32ZRTXKWN9M17X8Q5`

- **Mission:** `agent-runtime-env-guardrails-01KWT3GH`
- **Origin flow:** `plan`
- **Slot key:** `plan.scope.absolute-path-invocations`
- **Input key:** `include_abspath_invocations`
- **Status:** `resolved`
- **Created:** `2026-07-05T21:49:46.499412+00:00`
- **Resolved:** `2026-07-05T21:53:20.391413+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Should scope include python3 /home/claude/kg-automation/scripts/....py absolute-path invocations (checkout-path axis), not just the 30 -m scripts. calls?

## Options

- include_abspath
- hold_to_m_scripts_only
- Other

## Final answer

include_abspath — scope covers both python3 -m scripts. AND python3 <abs>/scripts/....py invocations (the checkout-path axis); guard flags both, canonical form replaces both

## Rationale

_(none)_

## Change log

- `2026-07-05T21:49:46.499412+00:00` — opened
- `2026-07-05T21:53:20.391413+00:00` — resolved (final_answer="include_abspath — scope covers both python3 -m scripts. AND python3 <abs>/scripts/....py invocations (the checkout-path axis); guard flags both, canonical form replaces both")
