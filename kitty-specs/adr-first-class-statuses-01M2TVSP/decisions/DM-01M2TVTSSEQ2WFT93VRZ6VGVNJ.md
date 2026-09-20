# Decision Moment `01M2TVTSSEQ2WFT93VRZ6VGVNJ`

- **Mission:** `adr-first-class-statuses-01M2TVSP`
- **Origin flow:** `specify`
- **Slot key:** `specify.adr-status.representation`
- **Input key:** `adr_status_representation`
- **Status:** `resolved`
- **Created:** `2026-09-18T18:18:03.950980+00:00`
- **Resolved:** `2026-09-18T18:43:00.990064+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should ADR lifecycle facts be represented: status values only, structured pointer fields only, or a coarse status plus pointer fields carrying the detail?

## Options

- A: status values only
- B: small status set + pointer fields
- C: coarse status + pointer fields for detail
- Other

## Final answer

A: status values only. Additionally: partially_superseded MUST NOT exist — if any part of an ADR is superseded, the whole ADR is deprecated and a new ADR carries forward the surviving part (one ADR = one wholly-binding-or-wholly-dead decision). And 'approved' is retained over 'accepted' because approved carries a stated authority, which can matter.

## Rationale

_(none)_

## Change log

- `2026-09-18T18:18:03.950980+00:00` — opened
- `2026-09-18T18:43:00.990064+00:00` — resolved (final_answer="A: status values only. Additionally: partially_superseded MUST NOT exist — if any part of an ADR is superseded, the whole ADR is deprecated and a new ADR carries forward the surviving part (one ADR = one wholly-binding-or-wholly-dead decision). And 'approved' is retained over 'accepted' because approved carries a stated authority, which can matter.")
