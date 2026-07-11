---
work_package_id: WP02
title: Deterministic Sheets helper
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-007
- NFR-001
- NFR-002
tracker_refs: []
planning_base_branch: feat/felix-time-logging
merge_target_branch: feat/felix-time-logging
branch_strategy: Planning artifacts for this mission were generated on feat/felix-time-logging. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-time-logging unless the human explicitly redirects the landing branch.
subtasks:
- T003
- T004
- T005
phase: Phase 1 - Sheets ops
assignee: ''
agent: "claude:sonnet:python-pedro:implementer"
agent_profile: "python-pedro"
shell_pid: "43146"
history:
- at: '2026-07-10T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/google/
create_intent:
- scripts/google/sheets_helper.py
- tests/google/test_sheets_helper.py
execution_mode: code_change
owned_files:
- scripts/google/sheets_helper.py
- tests/google/test_sheets_helper.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before touching any file, load your implementer profile so identity, governance
scope, and boundaries are in force for this session:

```
Skill(spec-kitty-implement-review)   # or: /spk-doctrine-profile-load role=implementer
```

Then read, in order:

1. `kitty-specs/felix-time-logging-01KX79HT/spec.md` — FR-005, FR-007; NFR-001/002.
2. `kitty-specs/felix-time-logging-01KX79HT/plan.md` — **IC-02** (this WP's charter).
3. `kitty-specs/felix-time-logging-01KX79HT/data-model.md` — **TimeEntry** (the row
   shape + `entry_id` idempotency key) and the append-idempotency (F8) note.
4. `kitty-specs/felix-time-logging-01KX79HT/contracts/timelog-cli.md` — **C2**
   (`sheets_helper`) is the authoritative flag/exit-code/behavior surface for this WP.
5. `scripts/google/calendar_helper.py` — the REAL file to mirror (CLI shape,
   exit-code contract, `--self-check`, `--account`, `HelperError`, `_build_service`,
   `_run_execute`, lazy google imports, stdout/`SUMMARY:` discipline).

This WP is **deterministic and code-only. No LLM anywhere in this helper.**

---

## Branch Strategy

- **DEPENDS ON WP01.** WP01 lands `scripts/google/sheets_auth.py` (the per-account,
  Sheets-scoped credential loader) and `tests/google/__init__.py`. Do not start
  implementing this WP until WP01 is merged to `feat/felix-time-logging`.
- Planning/base branch: `feat/felix-time-logging`. Work on this WP's lane branch and
  merge back into `feat/felix-time-logging`.
- **Do NOT create `tests/google/__init__.py`** — WP01 owns it. Import auth from
  WP01's module: `from scripts.google.sheets_auth import ...`.

---

## Objectives & Success Criteria

Build `scripts/google/sheets_helper.py`: the deterministic, mechanical Sheets
operations layer for the time-log feature. It wraps `google-api-python-client`'s
Sheets API and exposes a small CLI mirroring `calendar_helper.py`.

Requirements this WP satisfies:

- **FR-005** — append exactly **one** row to a client's tab
  (`date, hours, client, description, billable` + `logged_at` + `entry_id`).
- **FR-007** — never write a partial/wrong entry; a "logged" result is gated on the
  append being **API read-back-confirmed**.
- **NFR-001** — correctness: the written row matches the passed values exactly.
- **NFR-002** — fail-safe: **a mutation is reported as successful only after the API
  read-back confirms it landed** (the appended row carries its `entry_id`). An API
  error yields a typed error / exit 1 — never a partial or unconfirmed "success".

Success = every C2 operation implemented per contract, exit codes `0`/`1`/`2`
matching `calendar_helper.py`, and full test coverage of the read-back / idempotency
/ no-op / fail-safe behaviors.

**Out of this WP's scope:** NL parsing, client→tab resolution, typed TimelogResult
statuses, pending/ledger state, alerting. That is `timelog.py` (a later WP). This WP
is the low-level Sheets ops only — it keeps the calendar-helper `0/1/2` convention;
the higher-level normalizer wraps it.

---

## Context & Constraints

Mirror `calendar_helper.py` structurally — do not invent a new shape:

- **CLI**: `argparse` subcommands (`append-row`, `create-tab`, `list-tabs`,
  `update-last`, `delete-last`) plus a top-level `--self-check`. Long-form flags.
- **Exit codes** (same as calendar helper): `0` = ok; `1` = operational / Sheets API
  error; `2` = usage (bad/missing args, invalid `--account`). (Auth failure from
  WP01's loader surfaces per its own contract — map it to a non-zero exit; do not let
  a bad-credentials path masquerade as a completed op.)
- **`--account`** — default `personal` (the account that owns the workbook).
- **`HelperError`** — reuse the pattern from `calendar_helper.py` (carries the exit
  code; `_usage_error` / `_operational_error` constructors).
- **Lazy google imports** — import `googleapiclient` **inside** the service-build
  function only, so importing this module never requires the google packages (CI has
  them out of `requirements.txt`). Tests inject fakes via `sys.modules` / a mocked
  service, exactly like the calendar-helper tests.
- **stdout discipline** — machine-readable JSON line(s) then a final `SUMMARY:` line;
  `ERROR:` to stderr. Follow `_emit_json` / `_emit_summary` / `_emit_error`.
- **Workbook id** resolved from `~/.config/felix/timelog/workbook.json`
  (`{"spreadsheet_id": "<id>"}`) — NOT committed. Resolve it once, fail-safe with a
  usage/operational error if missing or malformed. Honor an override env var
  (mirror how the calendar dir honors `FELIX_GOOGLE_DIR`) so tests can point at a
  temp file.
- **NO LLM.** Pure Sheets API + argparse. All judgment lives upstream in `timelog.py`.

Row/column order in a tab (from data-model.md TimeEntry):
`date | hours | client | description | billable` + `logged_at` + `entry_id` as
trailing columns. The caller passes the fully-formed values array; this helper does
not construct business values — it appends what it's given and confirms it landed.

---

## Subtasks & Detailed Guidance

Contract C2 is authoritative. Implement precisely these operations.

### T003 — `append-row` + `create-tab` (the write path)

`scripts/google/sheets_helper.py` — implement:

**`append-row --tab --entry-id --values [--account]`**

```
python3 -m scripts.google.sheets_helper append-row \
    --tab ACME --entry-id <uuid> \
    --values '["2026-07-10",2.5,"ACME","desc",true,"<iso>","<uuid>"]' [--account personal]
```

- Uses the Sheets API `spreadsheets().values().append` with
  `includeValuesInResponse=True` (and `valueInputOption` / `insertDataOption` set so
  a single row is appended to the tab, not merged into an existing row).
- **Read-back-confirm before reporting success (F8, NFR-002).** After the append,
  inspect the API response and confirm the returned/updated row **carries its
  `entry_id`** (the trailing column value). Only then report success and return the
  written range / `row_index` so the caller can record it in the ledger. If the
  response does not confirm the row carries the `entry_id`, treat it as an
  operational failure (exit 1) — **never** report success on an unconfirmed write.
- **Idempotent retry (F8).** Before appending, do a **bounded duplicate lookup by
  `entry_id`**: scan the recent tail of the tab (a `spreadsheets().values().get` over
  the last N rows) for a row already carrying this `entry_id`. If found, report that
  existing row (with its `row_index`) rather than appending a second copy. This makes
  a retry after a transport error stable — the caller passes the same `entry_id`.
  Follow the `IDEMPOTENCY_LOOKBACK`-style bounded-scan pattern from
  `calendar_helper.py`.

**`create-tab --tab [--account]`**

```
python3 -m scripts.google.sheets_helper create-tab --tab ACME [--account personal]
```

- Uses `spreadsheets().batchUpdate` with an `addSheet` request.
- **No-op if the tab already exists (F3).** First read existing sheet titles (reuse
  `list-tabs` logic / a `spreadsheets().get`); if the tab is present, report success
  without calling `batchUpdate`. This keeps retries idempotent.

**Two-step new-client note (F3).** New-client onboarding is `create-tab` **then**
`append-row` — **two separate Sheets calls, non-atomic**. This helper only performs
the individual ops; if `create-tab` succeeds but `append-row` later fails, the tab
exists and the entry is NOT logged. **This helper does not synthesize a
`client_created_entry_failed` status** — the CALLER (`timelog.py`, a later WP)
observes the two exit codes and surfaces `client_created_entry_failed`. Keep each op
independently fail-safe; do not try to roll back the created tab.

### T004 — `list-tabs`, `update-last`, `delete-last`, `--self-check`

**`list-tabs [--account]`** — `spreadsheets().get` → return the sheet titles (the
tabs) as a JSON array. This is the source-of-truth read the caller uses for client
resolution and for the create-tab no-op check.

**`update-last --tab --row --values`** — overwrite the values of a specific,
caller-supplied 1-based `--row` in `--tab` (via `spreadsheets().values().update` on
the computed A1 range). The caller (from its ledger) supplies the row index; this
helper does not decide which row is "last".

**`delete-last --tab --row`** — remove a specific caller-supplied row (via a
`batchUpdate` `deleteDimension` on `ROWS`, or the equivalent). Again, the caller
supplies the target row.

**`--self-check [--account]`** — mirror `calendar_helper.py`'s `_cmd_self_check`: a
bounded `spreadsheets().get` (refreshes creds + confirms the workbook is reachable),
emit a `SUMMARY: op=self-check status=ok ...` line, exit 0. Any auth/reach failure →
non-zero.

All of these keep the `0/1/2` exit-code contract and resolve the workbook id from
`~/.config/felix/timelog/workbook.json`.

### T005 — `tests/google/test_sheets_helper.py`

Mirror the calendar-helper test style: inject a **fake/mock Sheets client** (via
`sys.modules` and/or a fake `service` returned by the build function) so no real
network calls occur. Cover:

- **`append-row` read-back-confirm** — the fake `append` response carries the
  `entry_id` → success + correct `row_index`; and a response **missing** the
  `entry_id` → operational failure (exit 1), no success reported.
- **Idempotent retry** — the recent-tail scan finds a row with the same `entry_id`
  → the existing row is reported, `append` is **not** called again (assert no
  duplicate append).
- **`create-tab` no-op when exists** — the tab is already present → `batchUpdate`
  is **not** called; success reported. And create when absent → `addSheet` called.
- **Two-step create+append where append fails** — `create-tab` succeeds (exit 0),
  then `append-row` on the same tab fails at the API → exit 1, no partial/false
  success. (Confirms the helper leaves the caller to surface
  `client_created_entry_failed`; the helper itself does not claim "logged".)
- **`list-tabs`** — returns the sheet titles from a mocked `spreadsheets().get`.
- **`update-last` / `delete-last`** — issue the right Sheets call for the supplied
  row; usage error (exit 2) on a missing/invalid `--row`.
- **`--self-check`** — bounded `get` → `status=ok`, exit 0; a reach failure → non-zero.
- **Every op fail-safe** — an injected API error (raise from the fake `.execute()`)
  maps to a typed error / exit 1, **never a partial write** and never a false success.
- **Import safety** — importing the module with google packages absent does not raise
  (lazy import), like the calendar-helper tests.

---

## Test Strategy

Run:

```
python3 -m pytest tests/google/test_sheets_helper.py -v --cov=scripts/google --cov-branch
```

- All google API access is mocked at the service boundary — no network, no creds.
- Branch coverage must be met; use `# pragma: no branch` only on genuinely
  unreachable defensive branches (per repo convention), not to paper over untested
  behavior.
- The read-back-confirm, idempotent-retry, and no-op-create-tab paths are the
  load-bearing correctness tests — they must assert both the reported result **and**
  that the mutating API call was / was not made.

---

## Definition of Done

- [ ] `scripts/google/sheets_helper.py` implements C2 exactly: `append-row`,
      `create-tab`, `list-tabs`, `update-last`, `delete-last`, `--self-check`.
- [ ] Structure mirrors `calendar_helper.py`: exit `0/1/2`, `--account` default
      `personal`, `HelperError`, lazy google imports, `_emit_json`/`_emit_summary`/
      `_emit_error` stdout discipline, `--self-check` = bounded `spreadsheets().get`.
- [ ] `append-row` requests `includeValuesInResponse` and **read-back-confirms** the
      appended row carries its `entry_id` before reporting success (F8/NFR-002).
- [ ] Idempotent retry: a bounded duplicate lookup by `entry_id` reports the existing
      row instead of appending a duplicate.
- [ ] `create-tab` is a **no-op** when the tab already exists (F3).
- [ ] Each op is independently fail-safe: any API error → typed error / exit 1, never
      a partial write, never a false success.
- [ ] Workbook id resolved from `~/.config/felix/timelog/workbook.json` (env-override
      for tests); missing/malformed → clean error.
- [ ] `tests/google/test_sheets_helper.py` covers T005's cases; `--cov-branch` passes.
- [ ] Did **not** create `tests/google/__init__.py` (WP01 owns it); imports auth from
      `scripts/google/sheets_auth.py`.
- [ ] No LLM anywhere in the helper.

---

## Risks

- **Idempotency is the fail-safe.** The read-back-before-success is the mechanism that
  prevents a fabricated "logged" (NFR-002 / #683). Do not shortcut it — an append
  whose response is not confirmed to carry the `entry_id` is a failure, not a success.
- **Two-step non-atomic onboarding.** `create-tab` then `append-row` can leave a
  created-but-empty tab if the append fails. This helper must NOT roll back or fake
  success; it exposes the two exit codes so the caller surfaces
  `client_created_entry_failed`. Keep them independent and idempotent.
- **Workbook-id config.** The id lives in an uncommitted config file. A missing /
  malformed file must fail cleanly (not crash, not guess) so higher layers can report
  it. Provide an env override so tests never touch the real path.
- **Bounded duplicate-lookup window.** The tail scan for `entry_id` is bounded; a very
  large tab could push an entry out of the window. Match the `calendar_helper.py`
  bounded-lookback pattern and keep the window generous enough for realistic retry
  latency; document the bound in a constant.

---

## Reviewer Guidance

Verify concretely (not by prose inspection alone):

- **Read-back-before-success** — confirm `append-row` never reports success unless the
  API response confirms the row carries its `entry_id`; the test with a response
  missing the `entry_id` must fail the op (exit 1).
- **Idempotent retry** — confirm a same-`entry_id` retry reports the existing row and
  does **not** issue a second `append` (assert the mock append call count).
- **No-op create-tab** — confirm `create-tab` on an existing tab does **not** call
  `batchUpdate`.
- **Fail-safe** — confirm every op maps an injected API error to a typed error /
  exit 1 with no partial write and no false success.
- **Fidelity to the mirror** — confirm exit codes, `--account` default, `--self-check`
  bounded-get, and stdout/`SUMMARY:` discipline match `calendar_helper.py`.
- **Boundary honored** — confirm this WP added no `tests/google/__init__.py`, imported
  auth from `sheets_auth.py`, and introduced no LLM call or NL parsing.

## Activity Log

- 2026-07-11T01:20:55Z – claude:sonnet:python-pedro:implementer – shell_pid=43146 – Assigned agent via action command
