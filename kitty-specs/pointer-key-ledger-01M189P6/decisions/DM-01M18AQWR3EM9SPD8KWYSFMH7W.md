# Decision Moment `01M18AQWR3EM9SPD8KWYSFMH7W`

- **Mission:** `pointer-key-ledger-01M189P6`
- **Origin flow:** `plan`
- **Slot key:** `plan.contract.ledger-home`
- **Input key:** `ledger_home`
- **Status:** `resolved`
- **Created:** `2026-08-30T03:17:21.283379+00:00`
- **Resolved:** `2026-08-30T03:18:02.521487+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Where does the per-producer key ledger live: as machine-readable data inside service-inventory.json's health_check block (converting the existing 'expected' prose to data), as a dedicated pointer-ledgers.json under architecture/data covering both hosts, or as a Python declaration module in scripts/canary/?

## Options

- inventory-health-check-block
- dedicated-pointer-ledgers-json
- python-declaration-module
- Other

## Final answer

inventory-health-check-block: the key ledger is declared as machine-readable data inside each component's existing health_check block in docs/design/architecture/data/service-inventory.json, with adjudicated keys carrying explicit good-sets and a diagnostic_only list. The adjudication rules currently written as English prose in health_check.expected become data. probes.py stays convention-generic and reads the declared ledger rather than gaining any component-keyed table, preserving its stated 'do NOT special-case component names' invariant and following the precedent set by success_status_values in #891. The existing blocking architecture-data CI validator is extended to cover the new structure. Consequence to carry into #913: office4's ledger becomes a component entry carrying host: office4, and the inventory has zero office4 entries today, so that placement is confirmed by #913 and is not decided here.

## Rationale

_(none)_

## Change log

- `2026-08-30T03:17:21.283379+00:00` — opened
- `2026-08-30T03:18:02.521487+00:00` — resolved (final_answer="inventory-health-check-block: the key ledger is declared as machine-readable data inside each component's existing health_check block in docs/design/architecture/data/service-inventory.json, with adjudicated keys carrying explicit good-sets and a diagnostic_only list. The adjudication rules currently written as English prose in health_check.expected become data. probes.py stays convention-generic and reads the declared ledger rather than gaining any component-keyed table, preserving its stated 'do NOT special-case component names' invariant and following the precedent set by success_status_values in #891. The existing blocking architecture-data CI validator is extended to cover the new structure. Consequence to carry into #913: office4's ledger becomes a component entry carrying host: office4, and the inventory has zero office4 entries today, so that placement is confirmed by #913 and is not decided here.")
