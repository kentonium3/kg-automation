# Decision Moment `01M7Q8RGRANSNEQX84JP7JEAEB`

- **Mission:** `arms849-live-runtime-host-endpoints-01M7Q8F3`
- **Origin flow:** `plan`
- **Slot key:** `plan.architecture.endpoint-carrier`
- **Input key:** `endpoint_carrier`
- **Status:** `resolved`
- **Created:** `2026-11-18T12:05:32.042933+00:00`
- **Resolved:** `2026-11-18T12:07:01.092194+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should live endpoints reach the runtime's connections: (A) an endpoint pair carried on the existing Resources record with in-network defaults, threaded to arm G's bridge, the serving facade and the health check; or (B) separate keyword arguments added to each factory/facade/health call?

## Options

- A: endpoint pair on Resources
- B: per-call keyword arguments
- Other

## Final answer

A: endpoint pair on Resources; Engineering Alignment confirmed by Kent 2026-11-18

## Rationale

_(none)_

## Change log

- `2026-11-18T12:05:32.042933+00:00` - opened
- `2026-11-18T12:07:01.092194+00:00` - resolved (final_answer="A: endpoint pair on Resources; Engineering Alignment confirmed by Kent 2026-11-18")
