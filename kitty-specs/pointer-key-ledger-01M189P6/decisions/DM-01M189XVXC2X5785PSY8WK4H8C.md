# Decision Moment `01M189XVXC2X5785PSY8WK4H8C`

- **Mission:** `pointer-key-ledger-01M189P6`
- **Origin flow:** `specify`
- **Slot key:** `specify.ledger.enforcement-surface`
- **Input key:** `enforcement_surface`
- **Status:** `resolved`
- **Created:** `2026-08-30T03:03:08.460133+00:00`
- **Resolved:** `2026-08-30T03:06:35.841112+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Which producers must have a declared key ledger enforced by the test in THIS mission: only the backup pointers (office2 restic now, office4 restic via #913), or all 17 pointer-emitting components in the service inventory?

## Options

- backup-pointers-only-mechanism-generic
- all-17-pointer-components
- Other

## Final answer

backup-pointers-only-mechanism-generic: the contract and its enforcing test helper are built GENERICALLY so any pointer-emitting component can adopt them by declaring a ledger, but enforcement in this mission covers only the restic backup pointers - office2's now, office4's when #913 builds its producer. The other 16 pointer-emitting components in service-inventory.json get a documented adoption path plus a follow-up issue; they are explicitly out of scope here because 16 of them have no deterministic execution harness and several emit from OpenClaw agent steps, so enforcing them would mean building harnesses as the bulk of the work and would degrade the test into asserting a hand-maintained key list - the very defect the contract replaces.

## Rationale

_(none)_

## Change log

- `2026-08-30T03:03:08.460133+00:00` — opened
- `2026-08-30T03:06:35.841112+00:00` — resolved (final_answer="backup-pointers-only-mechanism-generic: the contract and its enforcing test helper are built GENERICALLY so any pointer-emitting component can adopt them by declaring a ledger, but enforcement in this mission covers only the restic backup pointers - office2's now, office4's when #913 builds its producer. The other 16 pointer-emitting components in service-inventory.json get a documented adoption path plus a follow-up issue; they are explicitly out of scope here because 16 of them have no deterministic execution harness and several emit from OpenClaw agent steps, so enforcing them would mean building harnesses as the bulk of the work and would degrade the test into asserting a hand-maintained key list - the very defect the contract replaces.")
