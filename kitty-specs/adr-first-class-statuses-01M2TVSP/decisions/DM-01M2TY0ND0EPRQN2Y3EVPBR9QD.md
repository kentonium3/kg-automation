# Decision Moment `01M2TY0ND0EPRQN2Y3EVPBR9QD`

- **Mission:** `adr-first-class-statuses-01M2TVSP`
- **Origin flow:** `specify`
- **Slot key:** `specify.adr-status.deprecation-trigger`
- **Input key:** `adr_deprecation_trigger`
- **Status:** `resolved`
- **Created:** `2026-09-18T18:56:13.216964+00:00`
- **Resolved:** `2026-09-18T18:57:40.606598+00:00`
- **Opened by:** `cli`
- **Other answer:** `true`

## Question

Given the decision log supersedes the whole-ADR-deprecation rule, what triggers deprecation/supersession rather than a log entry?

## Options

- A: topic irrelevant only
- B: topic irrelevant OR central decision reversed
- Other

## Final answer

Other (Kent — the question's framing was rejected). The log is HISTORY and carries NO decision-making authority, so it is never an alternative to a status change and the offered A/B dichotomy was malformed. Correct model, three separated roles: (1) a NEW ADR is the only place decisions are made or reversed; (2) STATUS carries current standing — authoritative and machine-readable, what a reader checks before acting on the body; (3) the LOG records how the standing got there, additively, with no authority to change it. A reversal therefore happens in a new ADR, the prior ADR's status becomes superseded, and its log merely RECORDS that. The hazard raised in discovery (decisions hiding in the log) is impossible by construction under this model, so no guard rule is needed for it. Corollary: ADR-0002 is NOT deprecated and needs no successor — it takes a log entry recording that Q6 was superseded by ADR-0007 on 2026-07-23, and the whole migration case raised earlier dissolves.

## Rationale

_(none)_

## Change log

- `2026-09-18T18:56:13.216964+00:00` — opened
- `2026-09-18T18:57:40.606598+00:00` — resolved (final_answer="Other (Kent — the question's framing was rejected). The log is HISTORY and carries NO decision-making authority, so it is never an alternative to a status change and the offered A/B dichotomy was malformed. Correct model, three separated roles: (1) a NEW ADR is the only place decisions are made or reversed; (2) STATUS carries current standing — authoritative and machine-readable, what a reader checks before acting on the body; (3) the LOG records how the standing got there, additively, with no authority to change it. A reversal therefore happens in a new ADR, the prior ADR's status becomes superseded, and its log merely RECORDS that. The hazard raised in discovery (decisions hiding in the log) is impossible by construction under this model, so no guard rule is needed for it. Corollary: ADR-0002 is NOT deprecated and needs no successor — it takes a log entry recording that Q6 was superseded by ADR-0007 on 2026-07-23, and the whole migration case raised earlier dissolves.")
