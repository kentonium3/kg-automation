---
work_package_id: WP03
title: timelog normalizer (validate/resolve/typed-union/state)
dependencies:
- WP02
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
- FR-007
- NFR-002
- NFR-003
tracker_refs: []
planning_base_branch: feat/felix-time-logging
merge_target_branch: feat/felix-time-logging
branch_strategy: Planning artifacts for this mission were generated on feat/felix-time-logging. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-time-logging unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 2 - Normalizer
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: "python-pedro"
shell_pid: "49242"
history:
- at: '2026-07-10T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/google/
create_intent:
- scripts/google/timelog.py
- docs/design/architecture/data/timelog-clients.json
- tests/google/test_timelog.py
execution_mode: code_change
owned_files:
- scripts/google/timelog.py
- docs/design/architecture/data/timelog-clients.json
- tests/google/test_timelog.py
role: implementer
tags: []
---

# WP03 — `timelog` normalizer (validate/resolve/typed-union/state)

## ⚡ Do This First: Load Agent Profile

Before writing any code, load your implementer profile so identity, governance
scope, and boundaries are in force:

- Invoke the **`ad-hoc-profile-load`** skill and adopt the **implementer** role
  (`agent: "claude"`, `role: "implementer"` from this WP's frontmatter).
- Read the mission's `spec.md`, `plan.md`, `data-model.md`, and
  `contracts/timelog-cli.md`. **This WP IS the main↔helper contract (C1)** — the
  13-status `TimelogResult` union, `PendingTimelog`, `RecentWriteLedger`, and
  `TimeEntry` in `data-model.md` are load-bearing and must be matched
  **byte-for-byte**. Do not paraphrase status strings.
- Confirm you are on `feat/felix-time-logging` (see Branch Strategy) before you
  touch a file.

Do NOT begin implementation until the profile is loaded and the four artifacts
are read.

## Branch Strategy

- **Current branch at workflow start**: `feat/felix-time-logging`.
- **Planning / base branch for this feature**: `feat/felix-time-logging`.
- **Completed changes must merge into**: `feat/felix-time-logging`.

**This WP DEPENDS ON WP02.** WP02 (`sheets_helper` + `sheets_auth`) must be on
the base branch before this WP runs. This WP imports and calls WP02's
`sheets_helper` operations — **append-row / create-tab / list-tabs /
update-last / delete-last** — as its Sheets write layer. Do **not** re-implement
Sheets I/O here; `timelog.py` is a pure normalizer over WP02's helper.

**WP01 owns `tests/google/__init__.py` — do NOT create it.** It already exists
by the time this WP runs.

## Objectives & Success Criteria

`timelog.py` is the **main-facing normalizer**: `main` (the LLM) has already
extracted the natural-language fields (F7); this WP validates them, resolves the
client to a tab, drives WP02's helper for the write, manages conversation-keyed
state, and returns a typed `TimelogResult` JSON.

Requirements satisfied here:

- **FR-001** — accept the structured fields `main` extracted (client, hours,
  description, date defaulting to "today"); a non-time-log input → `not_timelog`.
- **FR-002** — resolve the client → tab via the normalizing client→tab map
  (case/alias tolerant, tabs-as-truth).
- **FR-003** — unknown/ambiguous client → NO write; return `unknown_client` /
  `ambiguous` so `main` asks.
- **FR-004** — on new-client confirm, create the tab then log the pending entry;
  partial mutation (tab created, append failed) → `client_created_entry_failed`,
  never `logged`; retry idempotent.
- **FR-006** — correct/remove the **most-recent** entry on a follow-up
  (`--correct` / `--delete-last`); a conflicting newer write →
  `correction_ambiguous`.
- **FR-007** — never write a partial/wrong entry; report only what actually
  happened; `logged`/`corrected`/`deleted` only after WP02's read-back-confirmed
  mutation.
- **NFR-002** — fail-safe: a helper error → `error` (NO false `logged`).
- **NFR-003** — a `status: error` / `client_created_entry_failed` renders to a
  `scripts.common.alert_bus` `Alert` (severity `error`); a clarification signal
  is NOT an alert.

**Done means**: all 13 `TimelogResult` statuses are reachable and tested, state
is keyed correctly, corrections are safe, and write failures alert.

## Context & Constraints

**This is a main-facing NORMALIZER — read these constraints carefully; the
reviewer enforces them literally.**

- **Structured input only.** `main` extracts the NL fields (F7). This helper does
  **NO natural-language parsing** — **no NL regex and no LLM anywhere in
  `timelog.py`.** It validates the already-structured args, resolves
  client→tab, calls WP02's helper, and returns a typed result. (The only
  "parsing" allowed is deterministic date-token normalization —
  `today`/`yesterday`/explicit `YYYY-MM-DD` — and numeric/flag validation.)
- **Always emit a `TimelogResult` JSON on stdout, and always exit `0` for any
  *handled* status** — including `error`, `client_created_entry_failed`, and
  every clarification signal — so `main` can render it safely (F9). Exit `2`
  **only** on a usage/arg error (malformed flags). Never exit non-zero merely to
  signal a dialog state.
- **Never guesses, never partial-writes.** Only `logged` / `corrected` /
  `deleted` mean a mutation landed (WP02 read-back-confirmed).
  `client_created_entry_failed` means the tab exists but the entry was NOT
  logged.
- **Atomic state** (temp-file + `os.rename`, `fcntl` exclusive lock) — mirror the
  `scripts/common/alert_bus/ledger.py` pattern (`_append_line` with
  `fcntl.LOCK_EX`, `mkdir(parents=True, exist_ok=True)`, best-effort discipline).
  State lives under `/data/services/timelog/state/`; the directory MUST be
  overridable via an env var (like `FELIX_ALERT_LEDGER_DIR`) so tests point it at
  a tmpdir.
- **Deterministic, no LLM.** All judgment (NL extraction) is `main`'s; this helper
  only validates, resolves, writes via WP02, and manages state.
- **Repo helper conventions**: invoked as `python3 -m scripts.google.timelog`;
  stdout = machine-readable JSON; `--account` defaults to `personal`; import
  `scripts.common.*` and WP02's helper via the package (`-m`) form (never a
  script-path import).
- Wrap the WhatsApp/OpenClaw `exec` form, any `<tag>`-shaped text, and CLI flags
  in backticks in prose so they render cleanly.

## Subtasks & Detailed Guidance

Implement in order. Each subtask cites contract **C1** and the `data-model.md`
entities; match the status strings exactly.

### T006 — validate structured args + resolve client → tab

Parse and validate the primary invocation:

```
python3 -m scripts.google.timelog \
    --client ACME --hours 2.5 --date today --description "onboarding prep" [--non-billable] \
    --channel whatsapp --conversation <cid> --source-msg-id <mid> [--account personal] [--json]
```

- **Validate the structured fields**: `--client`, `--hours` (decimal),
  `--description`, `--date` (default `today`), `--non-billable` (flag → `billable`
  default `true`), plus the correlation trio `--channel` / `--conversation` /
  `--source-msg-id` and `--account` (default `personal`).
- **Missing required field** (`hours` / `description` / `client` / `date`) →
  `need_field` with `missing` + `partial` (the fields present). NO write.
- **Date normalization** (deterministic only): `today` → the current local date,
  `yesterday` → the prior date, explicit `YYYY-MM-DD` passed through; an
  unparseable date is a `need_field` (`missing: "date"`), never a guess.
- **Resolve client → tab** (FR-002): normalize the spoken name (lowercase, trim)
  → exact tab-title match → alias match (via `timelog-clients.json`, T009) →
  else. **Tabs are the source of truth** — read live tabs via WP02's `list-tabs`;
  aliases only bridge fuzzy spoken names.
  - No tab matches → `unknown_client` with `heard` (given name) + `closest` (best
    tab candidate, if any). NO write.
  - The name resolves to **multiple** tabs/aliases → `ambiguous` with
    `candidates`. NO write.
- A malformed flag (e.g. non-numeric `--hours` that is a usage error, unknown
  flag) → **exit `2`** (usage), distinct from the handled `need_field`/`error`
  dialog statuses which exit `0`.

### T007 — the complete 13-status `TimelogResult` union

Implement the union **exactly** as in `data-model.md` / C1 — one of:

`logged` · `unknown_client` · `need_field` · `ambiguous` · `error` ·
`not_timelog` · `no_pending` · `stale_pending` · `client_created_entry_failed` ·
`corrected` · `deleted` · `no_last_write` · `correction_ambiguous`.

Each status carries exactly the fields the data-model specifies (e.g. `logged`
carries `tab`, `row` (the `TimeEntry` incl. `entry_id`), `receipt`;
`unknown_client` carries `heard` + `closest`; `correction_ambiguous` carries
`candidates` + `reason` ∈ {`newer_write`, `stale`}). **Do not add, rename, or
drop fields.**

- **Always-emit + exit-0 normalizer contract (F9)**: every handled status prints
  its `TimelogResult` JSON and exits `0`; only usage errors exit `2`.
- **`logged` gating (NFR-002/#683/F8)**: return `logged` **only after** WP02's
  `append-row` **read-back-confirms** the appended row carries its `entry_id`.
  Generate the `entry_id` (uuid4) once before the append and pass it to WP02 so a
  transport-error retry is idempotent (WP02 dedupes by `entry_id`). If the helper
  reports failure → `error`, never `logged`.
- **`not_timelog`**: `main` normally just doesn't call the helper on a non-time-log
  message; if invoked on one, return `not_timelog` (NO write).
- **New-client onboarding two-step (FR-004/F3)**: `--add-client` creates the tab
  (WP02 `create-tab`, a no-op if it exists) then logs the pending entry. If
  `create-tab` succeeds but the subsequent `append-row` fails → return
  `client_created_entry_failed` (`tab` created + `detail`) — the tab EXISTS but
  the entry was NOT logged; `main` must say the time was not logged. Retry is
  idempotent.

### T008 — conversation-keyed pending state + recent-write ledger

Implement both state files with **atomic writes** (mirror
`alert_bus/ledger.py`).

**`PendingTimelog`** — `/data/services/timelog/state/pending-<account>.json`
(env-overridable dir). Fields per `data-model.md`:
`source` (`{channel, conversation_id, source_message_id}` — the correlation key),
`partial` (the fields so far), `awaiting`
(`client` | `field:<name>` | `new_client_confirm`), `nonce`, `created_at`,
`expires_at` (= `created_at` + **30-min TTL**). The file may hold a small keyed
map when concurrent conversations exist.

Follow-up handling (C1): `--confirm-client` / `--add-client` / `--field` resume a
pending record **only if it correlates** (channel + conversation +
source-msg-id) and the `nonce` matches:

- No correlated pending record → `no_pending` (`awaiting: none`). NO write.
- Correlated but past its 30-min TTL → `stale_pending` (`age_s`); clear the
  record. NO write.

**`RecentWriteLedger`** — `/data/services/timelog/state/ledger-<account>.json`
(env-overridable dir). A **bounded** recent-write ledger (recent N within TTL;
older entries age out), replacing any single last-write file. Fields per
`data-model.md`: `write_id` (uuid4, distinct from the row's `entry_id`),
`entry_id`, `source`, `tab`, `row_index` (1-based), `entry` (the `TimeEntry`),
`written_at`, `expires_at`. Append one record on every `logged` / `corrected` /
`deleted`.

Corrections (FR-006/F4) — `--correct` / `--delete-last` target the **most-recent**
ledger entry:

- Resolve to the single most-recent entry; amend it via WP02's `update-last` or
  remove via `delete-last`, then return `corrected` / `deleted` (with
  `tab`, `row`, `receipt`) — again only after read-back confirmation.
- A **newer** write exists after the target, or ledger state is **stale** (target
  expired) → `correction_ambiguous` (`reason: newer_write` | `stale`,
  `candidates`). Do NOT mutate the wrong row.
- The ledger is **empty** → `no_last_write`. NO write.

### T009 — client aliases config + failure → alert

- **`docs/design/architecture/data/timelog-clients.json`** — schema
  `{ "schema_version": <n>, "clients": { "<canonical>": ["<alias>", ...] } }`
  (canonical tab name → alias list, per `data-model.md` "ClientAliases"). Seed it
  with an empty/minimal `clients` object and a `schema_version`. Resolution
  order: normalize spoken name → exact tab-title match (tabs from WP02
  `list-tabs`) → alias match here → else `unknown_client`.
- **Failure → alert (NFR-003)**: a `status: error` **or**
  `client_created_entry_failed` renders to a `scripts.common.alert_bus` `Alert`:
  `emit(Alert(source="scripts/google/timelog", severity=Severity.ERROR,
  title="Time-log write failed", description=<what happened, redaction-safe>,
  action=<operator guidance>, details={...}))`. Import `emit`, `Alert`,
  `Severity` from `scripts.common.alert_bus`. `emit` never raises — do not
  wrap it in logic that would swallow the returned `TimelogResult`.
- **A clarification signal is NOT an alert.** `unknown_client`, `need_field`,
  `ambiguous`, `not_timelog`, `no_pending`, `stale_pending`, `no_last_write`,
  `correction_ambiguous` are normal dialog — they must **not** emit an alert.

### T010 — tests: `tests/google/test_timelog.py`

Cover **every** status and the fail-safe boundary. **Mock WP02's `sheets_helper`
and the alert bus** — no live Sheets, no live ntfy. Point the state dir at a
tmpdir via the env override.

- One test per status: `logged`, `unknown_client`, `need_field`, `ambiguous`,
  `error`, `not_timelog`, `no_pending`, `stale_pending`,
  `client_created_entry_failed`, `corrected`, `deleted`, `no_last_write`,
  `correction_ambiguous`.
- **Partial mutation**: `create-tab` succeeds, `append-row` fails →
  `client_created_entry_failed` (tab exists, entry NOT logged) + an alert emitted.
- **Pending correlation**: a correlated follow-up resumes; an uncorrelated one →
  `no_pending`; a correlated-but-expired one → `stale_pending` (and clears).
- **Ledger corrections**: `--correct` / `--delete-last` hit the most-recent
  entry; a **newer** write after the target → `correction_ambiguous`
  (`reason: newer_write`); a stale/empty ledger → `stale`/`no_last_write`.
- **`not_timelog`**: invoking on a non-time-log input returns `not_timelog`, no
  write, no alert.
- **Fail-safe (NFR-002)**: WP02's helper returns an error → `timelog` returns
  `error` **and** emits an alert, and **never** a false `logged`.
- **Exit-code contract**: handled statuses exit `0`; a malformed flag exits `2`.
- **Alert boundary**: assert `error` / `client_created_entry_failed` emit an
  alert; assert clarification signals do **not**.

## Test Strategy

- `pytest tests/google/test_timelog.py` with `--cov-branch`; cover every status
  branch and the exit-code split.
- **Mock at the boundary**: patch WP02's `sheets_helper` operations
  (append-row/create-tab/list-tabs/update-last/delete-last) and
  `scripts.common.alert_bus.emit`. Do not touch the network or a real workbook.
- **State isolation**: set the state-dir env override to a `tmp_path` fixture per
  test so pending/ledger files never leak across tests.
- Assert the emitted JSON shape (status + carried fields) matches `data-model.md`
  exactly, and that `logged`/`corrected`/`deleted` appear **only** after a
  confirmed mock mutation.
- Defensive branches guarded by an earlier short-circuit may use
  `# pragma: no branch` to satisfy `--cov-branch`.

## Definition of Done

- [ ] `scripts/google/timelog.py` accepts the structured args + follow-up flags
      per C1 and validates them (no NL regex, no LLM).
- [ ] Client → tab resolves via tabs-as-truth (WP02 `list-tabs`) + the aliases
      config; unknown → `unknown_client`, multi-match → `ambiguous`.
- [ ] **All 13 `TimelogResult` statuses** are reachable and tested, with fields
      matching `data-model.md` byte-for-byte.
- [ ] Every handled status emits JSON + exits `0`; only usage errors exit `2`.
- [ ] `logged` / `corrected` / `deleted` are returned **only** after WP02's
      read-back-confirmed mutation; a helper failure → `error`, never a false
      `logged`.
- [ ] New-client two-step: partial mutation → `client_created_entry_failed`
      (tab exists, entry not logged); retry idempotent.
- [ ] Pending state is **conversation-keyed** (channel + conversation +
      source-msg-id + nonce, 30-min TTL); follow-ups resume only a correlated
      record (`no_pending` / `stale_pending` otherwise). Atomic writes.
- [ ] The recent-write ledger resolves the most-recent entry for corrections and
      returns `correction_ambiguous` on a newer write / stale state,
      `no_last_write` when empty. Atomic writes.
- [ ] `error` / `client_created_entry_failed` emit a `scripts.common.alert_bus`
      `Alert` (severity `error`, title "Time-log write failed"); clarification
      signals do **not** alert.
- [ ] `docs/design/architecture/data/timelog-clients.json` exists with a
      `schema_version` + `{canonical: [aliases]}` structure.
- [ ] `tests/google/test_timelog.py` covers every status, the partial-mutation
      case, pending correlation, ledger corrections, `not_timelog`, and the
      fail-safe path, mocking WP02 + the alert bus.

## Risks

- **Correction ambiguity after rapid logs.** Two quick logs then "make that 3h"
  could hit the wrong row. **Guard**: the recent-write ledger + the
  `correction_ambiguous` (`reason: newer_write`) return — never mutate when a
  newer write exists after the natural target.
- **Pending mis-correlation.** A follow-up from a different conversation must not
  resume an unrelated pending record. **Guard**: the conversation-source key
  (channel + conversation + source-msg-id) + the `nonce` + the 30-min TTL →
  `no_pending` / `stale_pending` rather than a wrong resume.
- **Status-union drift.** The 13-status union, its field names, and the
  `correction_ambiguous.reason` enum MUST match `data-model.md` /
  `contracts/timelog-cli.md` **byte-for-byte** — `main`'s dialog is written
  against these literal strings. Any rename silently breaks the main↔helper
  contract.
- **False `logged` on a partial mutation.** The new-client two-step is
  non-atomic. **Guard**: `client_created_entry_failed` is a distinct status; the
  entry is reported NOT logged, and it alerts.

## Reviewer Guidance

Enforce these literally:

1. **No NL regex, no LLM** anywhere in `timelog.py`. Only deterministic date-token
   normalization + numeric/flag validation are permitted "parsing".
2. **The 13-status union matches `data-model.md` byte-for-byte** — status strings,
   carried field names, and the `correction_ambiguous.reason` enum. Reject any
   drift.
3. **Normalizer exit contract (F9)**: every handled status → JSON + exit `0`;
   exit `2` **only** on a usage/arg error. Verify `error` and
   `client_created_entry_failed` do NOT exit non-zero.
4. **`logged`/`corrected`/`deleted` only after a confirmed mutation.** Trace that
   these statuses are unreachable without WP02's read-back confirmation; a helper
   error must yield `error`, never a false success.
5. **State keying + atomicity**: pending is keyed by conversation source + nonce +
   30-min TTL; the ledger is bounded; both write atomically (temp+rename,
   `fcntl` lock) via an env-overridable dir mirroring `alert_bus/ledger.py`.
6. **Alert boundary**: `error` / `client_created_entry_failed` emit an alert
   (severity `error`, title "Time-log write failed"); clarification signals do
   not. `emit` is imported from `scripts.common.alert_bus` and never crashes the
   result.
7. **Dependency hygiene**: WP02's `sheets_helper` is imported (not
   re-implemented); WP01's `tests/google/__init__.py` is NOT created here.
8. **Tests** exercise every status, the partial mutation, pending correlation,
   ledger corrections, and the fail-safe path, mocking WP02 + the alert bus with
   an isolated state dir.

## Activity Log

- 2026-07-11T01:28:37Z – claude:sonnet:python-pedro:implementer – shell_pid=45777 – Assigned agent via action command
- 2026-07-11T01:40:18Z – claude:sonnet:python-pedro:implementer – shell_pid=45777 – timelog normalizer: 13-status union, conversation-keyed pending+ledger, corrections w/ correction_ambiguous, fail-safe (logged only on read-back), alert on error; 77 tests/97.6% cov; 211 google-suite pass; 3fbbaf01.
- 2026-07-11T01:40:22Z – claude:opus:reviewer-renata:reviewer – shell_pid=49242 – Started review via action command
