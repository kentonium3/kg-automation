# Decision Moment `01M7TTJYY6XMR4G40CDDQ1K94A`

- **Mission:** `felix-rrule-adaptation-01M7TKNX`
- **Origin flow:** `plan`
- **Slot key:** `plan.credentials.occurrences-token-permission`
- **Input key:** `occurrences_token_permission`
- **Status:** `resolved`
- **Created:** `2026-11-19T21:14:47.622676+00:00`
- **Resolved:** `2026-11-19T21:16:38.339525+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Felix's token (vikunja-api-kent) lacks tasks.occurrences and tasks.occurrences_preview, and Vikunja tokens cannot be edited (create/delete only). Re-issue the token with those permissions before deploy, or build the occurrences/preview features to degrade without them?

## Options

- Kent re-issues the token with the two permissions before deploy
- Build with a Felix-side fallback; grant later
- Drop O1/O4/O5 occurrence use from this mission
- Other

## Final answer

Kent re-issues the token with the two permissions before deploy (Kent 2026-11-19: 'go ahead with the plan', taken as adopting the recommended option A; revisit if Kent says otherwise)

## Rationale

_(none)_

## Change log

- `2026-11-19T21:14:47.622676+00:00` - opened
- `2026-11-19T21:16:38.339525+00:00` - resolved (final_answer="Kent re-issues the token with the two permissions before deploy (Kent 2026-11-19: 'go ahead with the plan', taken as adopting the recommended option A; revisit if Kent says otherwise)")
