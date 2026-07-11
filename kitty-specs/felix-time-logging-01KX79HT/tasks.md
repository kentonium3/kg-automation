# Tasks: Felix WhatsApp Time-Logging to Sheets

**Mission**: felix-time-logging-01KX79HT · **Issue**: #703 · **Branch**: `feat/felix-time-logging`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Data model**: [data-model.md](./data-model.md) · **Contracts**: [contracts/timelog-cli.md](./contracts/timelog-cli.md)

Tests required (DIRECTIVE_034; NFR-002 fail-safe must be proven). Deploy to office2 is **post-merge, operator-run** (Sheets re-consent + workbook bootstrap are Kent-in-the-loop). Post-plan Codex (12 findings) folded.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `sheets_auth.py` — per-account, `spreadsheets`-scoped, load-without-forcing-scope, `SheetsAuthError`, fail-safe | WP01 | |
| T002 | `tests/google/__init__.py` + auth unit tests (mock creds; fail-safe paths) | WP01 | |
| T003 | `sheets_helper.py` — `append-row` (idempotent by `entry_id` + read-back-confirm), `create-tab` (no-op if exists) | WP02 | |
| T004 | `sheets_helper.py` — `list-tabs`, `update-last`, `delete-last`, `--self-check`; exit 0/1/2; workbook-id config | WP02 | |
| T005 | Sheets helper unit tests (mock Sheets client; idempotent append, read-back, two-step create+append, fail-safe) | WP02 | |
| T006 | `timelog.py` — validate main's structured args; resolve client→tab (tabs-as-truth + `timelog-clients.json` aliases) | WP03 | |
| T007 | `timelog.py` — full 13-status typed union; always-JSON, exit 0 (usage=2); `not_timelog`/`need_field`/`ambiguous` | WP03 | |
| T008 | `timelog.py` — conversation-keyed pending state (nonce + TTL) + recent-write ledger; corrections + `correction_ambiguous` | WP03 | |
| T009 | `timelog-clients.json` (aliases) + `error`→#701 alert rendering | WP03 | |
| T010 | timelog unit tests (each status; partial-mutation `client_created_entry_failed`; pending correlate/stale; ledger corrections) | WP03 | |
| T011 | **PRE-WORK**: compress `main/AGENTS.md` to reclaim ≥~600 bytes headroom (meaning-preserving); record reclaimed count | WP04 | |
| T012 | Add thin "log time" recognizer + extract-fields + call `timelog` + relay the typed signals (dialog) to `main/AGENTS.md` (+ `.tmpl`) | WP04 | |
| T013 | Fleet-guard test: recognizer/dialog present in main; all AGENTS.md within budget | WP04 | |
| T014 | `deploy-timelog.py` — venv/deps + **dry-run self-test (NO emit, #711)** + prompt-sync verify + report (#701) | WP05 | |
| T015 | `deploys/queued/timelog.yaml` manifest (not pre-numbered) | WP05 | |
| T016 | Architecture docs: service-inventory + credential-manifest + data-flows (new Sheets scope + timelog flow) | WP05 | [P] |
| T017 | Ops runbook + SC-001..005 live-verification checklist (re-consent + workbook bootstrap steps) | WP05 | |

## Work Packages

### WP01 — Sheets auth (per-account, spreadsheets scope)
- **Goal**: `scripts/google/sheets_auth.py` mirroring `calendar_auth.py`; returns `spreadsheets`-scoped Credentials, fail-safe. **Deps**: none. **Requirements**: C-002.
- [x] T001 sheets_auth loader (WP01)
- [x] T002 tests/google pkg + auth tests (WP01)

### WP02 — Deterministic Sheets helper
- **Goal**: `scripts/google/sheets_helper.py` CLI (append idempotent+read-back, create-tab no-op, list-tabs, update/delete-last, self-check). **Deps**: WP01. **Requirements**: FR-005, FR-007; NFR-001, NFR-002.
- [ ] T003 append-row + create-tab (WP02)
- [ ] T004 list-tabs/update-last/delete-last/self-check (WP02)
- [ ] T005 helper tests (WP02)

### WP03 — timelog normalizer (validate/resolve/typed-union/state)
- **Goal**: `scripts/google/timelog.py` — main-facing normalizer; validates structured args, resolves client, full typed union, ledger + pending state, corrections. **Deps**: WP02. **Requirements**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-007; NFR-002, NFR-003.
- [ ] T006 validate + resolve client→tab (WP03)
- [ ] T007 typed-signal union + exit-0 normalizer (WP03)
- [ ] T008 pending state + ledger + corrections (WP03)
- [ ] T009 aliases config + #701 alert on error (WP03)
- [ ] T010 timelog tests (WP03)

### WP04 — main prompt integration (option A; no sub-agent)
- **Goal**: compress main's prompt, then add the recognizer + extract + call-helper + relay-dialog. **Deps**: WP03 (contract). **Requirements**: FR-001, FR-003, FR-004.
- [ ] T011 PRE-WORK compression (≥600 bytes) (WP04)
- [ ] T012 recognizer + dialog prose (WP04)
- [ ] T013 fleet-guard test (WP04)

### WP05 — deploy, docs & verification
- **Goal**: office2 deploy (dry-run-no-emit self-test), manifest, arch-doc reconcile, runbook + SC checklist (re-consent + workbook bootstrap are operator steps). **Deps**: WP01-04. **Requirements**: C-002, C-004; SC-001..005.
- [ ] T014 deploy entrypoint (WP05)
- [ ] T015 deploy manifest (WP05)
- [ ] T016 architecture docs (WP05) [P]
- [ ] T017 runbook + SC checklist (WP05)

## Dependencies & lanes
- Chain: WP01 → WP02 → WP03 → WP04; WP05 depends on WP01–WP04.
- WP01 is the independent start; the rest sequence on the contract/impl chain.

## MVP
WP01+WP02+WP03 (the deterministic write path + normalizer) are the core; WP04 wires the conversation; WP05 ships it.
