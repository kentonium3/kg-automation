# Decision Moment `01M2TX8V4NQJMGZBMC2TYKYW8D`

- **Mission:** `adr-first-class-statuses-01M2TVSP`
- **Origin flow:** `specify`
- **Slot key:** `specify.adr-status.pointers`
- **Input key:** `adr_pointer_fields`
- **Status:** `resolved`
- **Created:** `2026-09-18T18:43:12.661949+00:00`
- **Resolved:** `2026-09-18T18:50:52.236118+00:00`
- **Opened by:** `cli`
- **Other answer:** `true`

## Question

With status-values-only settled, where do the supersession target and the erratum pointer live — non-status frontmatter fields, or prose in the ADR README index as today?

## Options

- A: no new fields, pointers stay in README prose
- B: superseded_by + erratum_in frontmatter fields
- C: superseded_by field only, errata stay prose
- Other

## Final answer

Other (Kent, better than all three offered): an append-only DECISION LOG TABLE at the bottom of each ADR. It carries unlimited additive updates without losing history, keeps current and historical context in one document, removes the hunt for changed info, and lets the ADR map change slowly and additively. This subsumes the superseded_by/erratum_in pointer fields — they are dropped. Status remains the flat enum from DM-01M2TVTS as the at-a-glance machine-readable standing. Two conditions identified in discovery: (1) the log entry MUST live in the ADR it is ABOUT — the observed failure was an erratum concerning ADR-0008 filed in ADR-0004's log, which never reached a reader of ADR-0008; (2) immutability must be explicitly refined — the DECISION is frozen, the log is append-only annotation that may not alter or contradict the frozen text. Log needs fixed columns so it stays parseable rather than drifting into free prose.

## Rationale

_(none)_

## Change log

- `2026-09-18T18:43:12.661949+00:00` — opened
- `2026-09-18T18:50:52.236118+00:00` — resolved (final_answer="Other (Kent, better than all three offered): an append-only DECISION LOG TABLE at the bottom of each ADR. It carries unlimited additive updates without losing history, keeps current and historical context in one document, removes the hunt for changed info, and lets the ADR map change slowly and additively. This subsumes the superseded_by/erratum_in pointer fields — they are dropped. Status remains the flat enum from DM-01M2TVTS as the at-a-glance machine-readable standing. Two conditions identified in discovery: (1) the log entry MUST live in the ADR it is ABOUT — the observed failure was an erratum concerning ADR-0008 filed in ADR-0004's log, which never reached a reader of ADR-0008; (2) immutability must be explicitly refined — the DECISION is frozen, the log is append-only annotation that may not alter or contradict the frozen text. Log needs fixed columns so it stays parseable rather than drifting into free prose.")
