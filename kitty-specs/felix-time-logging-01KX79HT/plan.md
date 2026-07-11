# Implementation Plan: Felix WhatsApp Time-Logging to Sheets

**Branch**: `feat/felix-time-logging` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: `kitty-specs/felix-time-logging-01KX79HT/spec.md`

## Summary

Let Kent log billable time over WhatsApp — "log 2.5 hrs for ACME doing X" — and
have Felix append it to the right client tab of a fresh Felix-owned Google Sheet.
Two layers (the #683 principle, mirroring #699): a **deterministic Sheets/time-log
helper** (parse → resolve client→tab → write → return a receipt or a *typed*
need-clarification signal; never guesses, never fabricates a write) and **`main`
(sonnet) conducting the interactive dialog** off those typed signals — with **no
sub-agent delegation** (the #679 failure link is designed out; see
[research.md](./research.md) D4, operator-locked as option A). Builds on the
shipped trust core (#683 no-fabrication + #701 alerting).

## Technical Context

**Language/Version**: Python 3.12 (office2 is `python3`-only; helpers invoked as `python3 -m scripts.google.<mod>`, and by `main` via its OpenClaw `exec` form)
**Primary Dependencies**: `google-api-python-client` (Sheets API — `spreadsheets().values().append`, `.batchUpdate` addSheet, `.get`); the #699 per-account OAuth substrate (`scripts/google/calendar_auth.py` pattern); `scripts/common/alert_bus` (#701) for failure alerts
**Storage**: the Felix-owned Google Sheets workbook (Kent's personal account); committed aliases config (`docs/design/architecture/data/timelog-clients.json`); office2 JSON state — `pending-timelog` (keyed by conversation source) + recent-write `ledger` under `/data/services/timelog/state/` (atomic writes, #706 pattern); workbook-id config `~/.config/felix/timelog/workbook.json` (NOT committed)
**Testing**: pytest `--cov-branch`; mock the Sheets client + auth at the service boundary; deterministic regression scenarios (parse / resolve / each typed signal / write / correct / fail-safe); fleet-guard prompt tests for `main`
**Target Platform**: office2 (Ubuntu 24.04); `main` agent (WhatsApp channel) invokes the helper via `exec`
**Project Type**: single (Python helpers/libraries + agent-prompt integration + deploy manifest)
**Performance Goals**: receipt within ~5 s of the message (NFR-004)
**Constraints**: fail-safe write (never fabricate "logged" — NFR-002/#683); no LLM in the deterministic write path (C-003); `main` AGENTS.md stays within the ~12 KB cap (D4/NFR); own-account only (C-001); failures alert via #701 (NFR-003)
**Scale/Scope**: single operator (Kent); a handful of clients; low write volume

## Charter Check

- **DIRECTIVE_034 Test-First**: helper parse/resolve/write + typed signals are deterministic → TDD-friendly (mock Sheets). **PASS (planned).**
- **DIRECTIVE_010 Spec Fidelity**: v1 scope (capture only) + the option-A routing are recorded explicitly. **PASS.**
- **DIRECTIVE_024 Locality**: new `scripts/google/` modules + a thin `main` prompt addition; no cross-cutting refactor. **PASS.**
- **DIRECTIVE_003 Decision Documentation**: D1–D5 + the routing lock recorded in research.md. **PASS.**
- **Project — Helper/Library/Skill conventions**: deterministic Sheets/time-log helper (CLI, stdout/exit-code contract, atomic state, fail-safe) + `main`'s LLM dialog. **PASS (planned).**
- **Project — Engineering principles** (deterministic work into scripts; LLM for judgment): write path deterministic; LLM only for the dialog. **PASS.**
- **Project — Change-risk taxonomy**: new credential **scope** (Sheets on the personal OAuth) = Tier 2 (credential/state); agent-prompt edit = Tier 3 + audited-but-unmonitored surface (gap #621 → no rebaseline); office2 deploy = Tier 3. **PASS with the Tier-2 re-consent stop.**
- **Project — Deploy discipline**: office2 via `deploys/queued/` + felix-deployer; the Sheets re-consent is a MANDATORY operator step. **PASS (planned).**

No charter violations requiring Complexity Tracking.

## Project Structure

```
scripts/google/
├── sheets_auth.py            # NEW — Sheets-scoped per-account creds (mirrors calendar_auth.py)
├── sheets_helper.py          # NEW — deterministic CLI: append-row / create-tab / list-tabs / update-last / delete-last / --self-check
├── timelog.py                # NEW — validate main's structured args; resolve client→tab (tabs + aliases); typed signals (full union); ledger + conversation-keyed pending state
scripts/openclaw/agents/main/
└── AGENTS.md                 # EDIT — thin "log time" recognizer + how-to-call-the-helper + relay the typed signals (dialog)
docs/design/architecture/data/
└── timelog-clients.json      # NEW — client aliases config (canonical → [aliases])
scripts/deploy/
└── deploy-timelog.py         # NEW — venv/deps + workbook-bootstrap check + wiring verify + self-test (dry-run, no emit — #711 lesson)
deploys/queued/
└── timelog.yaml              # NEW — deploy manifest (not pre-numbered)
tests/google/
└── test_sheets_*.py, test_timelog_*.py, test_sheets_auth.py   # NEW
```

**Structure Decision**: single-project Python; new `scripts/google/` modules alongside the #699 calendar ones (shared per-account auth pattern); the only agent-prompt change is a thin addition to `main` (no new agent — option A). Deploy mirrors #699 end-to-end.

## Complexity Tracking

*No Charter Check violations — table intentionally empty.*

## Implementation Concern Map

### IC-01 — Sheets auth (extend the personal OAuth to the Sheets scope)

- **Purpose**: return `spreadsheets`-scoped Credentials for the `personal`
  account, reusing the #699 per-account substrate; the personal token is
  re-minted once with `calendar + spreadsheets` (one re-consent).
- **Requirements**: C-002.
- **Surfaces**: `scripts/google/sheets_auth.py` (mirror `calendar_auth.py`:
  `FELIX_GOOGLE_DIR`, fail-safe, load WITHOUT forcing scope — deploy gotcha #3).
- **Depends-on**: none (code); the re-consent is a deploy step (IC-05).
- **Risks**: combined-scope token must not break the calendar helper (it loads
  scope-agnostically, so it won't); keep least-privilege = `spreadsheets`.

### IC-02 — Deterministic Sheets helper

- **Purpose**: the mechanical Sheets operations, fail-safe, no LLM.
- **Requirements**: FR-005, FR-007; NFR-001, NFR-002.
- **Surfaces**: `scripts/google/sheets_helper.py` (CLI mirroring
  `calendar_helper.py`: exit 0/1/2, `--self-check`, `--account` default
  `personal`, `HelperError`). Ops: `append-row`, `create-tab`, `list-tabs`,
  `update-last`, `delete-last`. The append confirms via the API response before
  reporting success (NFR-002).
- **Depends-on**: IC-01.
- **Risks**: workbook-id resolution (config); Sheets API error mapping → typed
  `error` (never a partial write).

### IC-03 — Time-log validation, client resolution, typed signals & state

- **Purpose**: the `timelog` normalizer — accept **structured args** extracted by
  `main` (`--client/--hours/--date/--description/[--non-billable]`, F7),
  validate them, resolve client→tab (tabs-as-truth + aliases), and return a
  receipt or a **typed** signal from the complete union (`logged` /
  `unknown_client` / `need_field` / `ambiguous` / `error` / `not_timelog` /
  `no_pending` / `stale_pending` / `client_created_entry_failed` / `corrected` /
  `deleted` / `no_last_write` / `correction_ambiguous`). **No NL regex, no LLM in
  the helper** — extraction is main's job. Maintain `pending-timelog` (keyed by
  conversation source, F5) + the recent-write **ledger** (F4) for corrections.
  Always emit a TimelogResult JSON, exit `0` for any handled status, `2` only on
  usage error (F9).
- **Requirements**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-007; NFR-002.
- **Surfaces**: `scripts/google/timelog.py`; `timelog-clients.json`.
- **Depends-on**: IC-02.
- **Risks**: correction "most-recent entry" must be unambiguous (recent-write
  ledger; newer-write/stale → `correction_ambiguous`, F4); pending correlation by
  conversation source (F5); new-client two-step partial mutation →
  `client_created_entry_failed` (F3).

### IC-04 — `main` prompt integration (option A — extract + dialog, no sub-agent)

- **PRE-WORK (MANDATORY, F1) — `main` prompt-compression pass.** `main` is
  already ~11,960/12,000 bytes. **Before** adding any time-log prose, run a
  compression pass on the existing `main` prompt to reclaim a stated byte budget
  (target **≥ ~600 bytes headroom**); record the reclaimed byte count. Then keep
  the time-log addition minimal by pushing all fixed reply / receipt text into
  the helper's typed results (main **relays** them, does not author them, F1).
  The fleet-guard size test must stay green after both the compression and the
  addition.
- **Purpose**: `main` recognizes the "log time" shape, **extracts the candidate
  fields** (`client`, `hours`, `description`, `date`, `billable`) from the NL and
  calls the helper via `exec` with **structured args** (F7), then conducts the
  clarifying dialog off the typed signals (ask on
  `unknown_client`/`need_field`/`ambiguous`; relay the helper-provided receipt on
  success; resume from pending state on a correlated follow-up; corrections). A
  message judged non-time-log → main simply does not call the helper (F6). **No
  delegation.**
- **Requirements**: FR-001, FR-003, FR-004.
- **Surfaces**: `scripts/openclaw/agents/main/AGENTS.md` (compression + thin
  addition) + its `.tmpl` if present; a fleet-guard prompt test.
- **Depends-on**: IC-03 (the helper CLI + structured-args + typed-signal contract
  must be settled so main's prose references the real shapes).
- **Risks**: main's 12 KB budget (compression pre-work + lean on the typed
  results for all fixed text); audited-but-unmonitored surface (gap #621 → no
  rebaseline).

### IC-05 — Deploy, workbook bootstrap, re-consent & verification

- **Purpose**: office2 deploy — venv/deps, one-time workbook bootstrap (create
  the workbook, record its id), the **Sheets-scope re-consent (MANDATORY
  operator stop)**, wire main's prompt (prompt-sync), a `deploys/queued/`
  manifest + entrypoint (dry-run self-test, no emit — #711), architecture-doc
  updates (service-inventory + credential-manifest + data-flows), and the
  SC-001..005 live verification.
- **Requirements**: C-002, C-004; SC-001..005.
- **Surfaces**: `scripts/deploy/deploy-timelog.py`, `deploys/queued/timelog.yaml`,
  `docs/design/architecture/data/*` + narrative.
- **Depends-on**: IC-01..IC-04.
- **Risks**: the re-consent is Kent-in-the-loop (browser OAuth); fold the
  #699/#711 deploy lessons (chmod +x; dry-run self-test that does NOT emit;
  failing queued manifest fail-loops).
