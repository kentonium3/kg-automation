# Platform Discovery (Overview)

**Current standard:** Use **Execution Context Identification (ECI)** — local-only machine identity — as the primary mechanism. Presence beacons/heartbeats are **optional** and not required for routing.

## Methods for determining execution context:

1) **Local machine identity** — Each device maintains a private beacon file with its identity. This is the primary method for job routing.
2) **(Optional) Heartbeat** — You may add a shared presence file if ever needed, but ECI is sufficient for routing.
3) **Prompt tags / voice** — Optional hinting for conversational clarity; execution does not depend on them.

## See Also
- `Documentation/execution-context-identification.md` for detailed ECI implementation
- `Documentation/diagrams/eci-sequence.mmd` for workflow visualization
