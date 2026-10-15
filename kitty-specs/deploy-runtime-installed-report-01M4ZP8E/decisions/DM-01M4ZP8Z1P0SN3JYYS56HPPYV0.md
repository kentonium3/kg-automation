# Decision Moment `01M4ZP8Z1P0SN3JYYS56HPPYV0`

- **Mission:** `deploy-runtime-installed-report-01M4ZP8E`
- **Origin flow:** `specify`
- **Slot key:** `specify.design.enforcement-approach`
- **Input key:** `enforcement_approach`
- **Status:** `resolved`
- **Created:** `2026-10-15T11:48:32.438524+00:00`
- **Resolved:** `2026-10-15T11:48:33.642867+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Which enforcement approach should #1072 build: runtime report from the deploy library, a declared installs: field, a CI lint, or runtime report plus declared fallback?

## Options

- Runtime report
- Declared installs: field
- CI lint only
- Runtime report + declared fallback
- Other

## Final answer

Runtime report. Kent, 2026-10-15 (AskUserQuestion, asked while formalizing #1072): the deploy library reports the repo files it installed; felix-deployer maps them via audited-surfaces.json to baselines and folds them in. Rejected: declared installs: field, CI lint only, runtime+declared fallback.

## Rationale

_(none)_

## Change log

- `2026-10-15T11:48:32.438524+00:00` — opened
- `2026-10-15T11:48:33.642867+00:00` — resolved (final_answer="Runtime report. Kent, 2026-10-15 (AskUserQuestion, asked while formalizing #1072): the deploy library reports the repo files it installed; felix-deployer maps them via audited-surfaces.json to baselines and folds them in. Rejected: declared installs: field, CI lint only, runtime+declared fallback.")
