# Contract: time-log CLIs (the main↔helper interface)

**Mission**: felix-time-logging-01KX79HT · **Phase**: 1

The load-bearing interface of option A: `main` calls these; their **typed JSON**
drives main's dialog. All follow repo helper conventions (`python3 -m`, stdout =
machine-readable, exit code = status, fail-safe, no LLM).

## C1 — `timelog` (the main-facing entrypoint)

`main` extracts the candidate fields from the natural language and calls
`timelog` with **STRUCTURED args** (F7). The helper does **no NL regex** — it
**validates + resolves client→tab + writes deterministically**. `main` supplies
the conversation correlation (`--channel`/`--conversation`/`--source-msg-id`) so
pending + ledger state key correctly (F5/F4).

```
# primary: main has already extracted the fields
python3 -m scripts.google.timelog \
    --client ACME --hours 2.5 --date today --description "onboarding prep" [--non-billable] \
    --channel whatsapp --conversation <cid> --source-msg-id <mid> [--account personal] [--json]

# follow-ups (main passes these after a clarification reply; correlate to pending state):
python3 -m scripts.google.timelog --confirm-client "ACME" --conversation <cid> --source-msg-id <mid> --account personal
python3 -m scripts.google.timelog --add-client "ACME"     --conversation <cid> --source-msg-id <mid> --account personal   # new-client onboarding: create tab + log pending
python3 -m scripts.google.timelog --field hours=3         --conversation <cid> --source-msg-id <mid> --account personal   # supply a missing field
python3 -m scripts.google.timelog --correct --hours 3     --conversation <cid> --source-msg-id <mid> --account personal   # amend most-recent ledger entry
python3 -m scripts.google.timelog --delete-last           --conversation <cid> --source-msg-id <mid> --account personal
```

- **Returns** a `TimelogResult` JSON (data-model.md) on stdout: exactly one of
  the complete status union —
  `logged` / `unknown_client` / `need_field` / `ambiguous` / `error` /
  `not_timelog` / `no_pending` / `stale_pending` / `client_created_entry_failed` /
  `corrected` / `deleted` / `no_last_write` / `correction_ambiguous`.
- **Main-facing NORMALIZER (F9).** `timelog` **always** emits a TimelogResult
  JSON and **exits `0`** for any *handled* status — including `error`,
  `client_created_entry_failed`, and every clarification signal — so main can
  render it safely. It exits `2` **only** on a usage/arg error (malformed flags).
  It never exits non-zero merely to signal a dialog state. (The lower-level
  `sheets_helper`, C2, keeps the calendar-helper `0/1/2` convention.)
- **Never guesses, never partial-writes.** Only `logged` / `corrected` /
  `deleted` mean a mutation landed (API read-back-confirmed, F8).
  `client_created_entry_failed` means the tab was created but the entry was NOT
  logged (F3) — main must not claim the time was logged.
- **Supported inputs + non-time-log (F6).** A message `main` judges to be
  non-time-log → `main` simply does **not** call the helper (or, if invoked,
  the helper returns `not_timelog`). A genuinely time-like-but-underspecified
  input → `need_field` / `ambiguous`, **never a mis-write**.
- **Auth failure (F9)** surfaces as a typed `error` (not a crash) so main renders
  it safely; it also alerts via #701.
- **State**: writes `pending-<account>.json` (keyed by conversation source, F5)
  when it returns a clarification signal; appends to `ledger-<account>.json` (F4)
  on `logged` / `corrected` / `deleted`. Atomic (temp+rename).
- **Deterministic, no LLM.** All judgment (NL extraction) lives in `main`; the
  helper only validates the structured args, resolves the client, and writes.

Example returns:
```json
{"status":"logged","tab":"ACME","receipt":"✅ Logged 2.5h for ACME (2026-07-10): onboarding prep","row":{"date":"2026-07-10","hours":2.5,"client":"ACME","description":"onboarding prep","billable":true,"entry_id":"..."}}
{"status":"unknown_client","heard":"Acme","closest":"ACME"}
{"status":"need_field","missing":"hours","partial":{"client":"ACME","description":"onboarding prep"}}
{"status":"client_created_entry_failed","tab":"ACME","detail":"tab created; append failed (Sheets 503) — time NOT logged"}
{"status":"correction_ambiguous","reason":"newer_write","candidates":[{"tab":"ACME","row_index":7}]}
{"status":"not_timelog"}
{"status":"error","detail":"Sheets API 503; nothing written"}
```

## C2 — `sheets_helper` (deterministic Sheets ops)

```
python3 -m scripts.google.sheets_helper append-row  --tab ACME --entry-id <uuid> --values '["2026-07-10",2.5,"ACME","desc",true,"<iso>","<uuid>"]' [--account personal]
python3 -m scripts.google.sheets_helper create-tab  --tab ACME [--account personal]   # no-op if the tab already exists
python3 -m scripts.google.sheets_helper list-tabs   [--account personal]
python3 -m scripts.google.sheets_helper update-last --tab ACME --row 7 --values '[...]'
python3 -m scripts.google.sheets_helper delete-last --tab ACME --row 7
python3 -m scripts.google.sheets_helper --self-check [--account personal]
```

- Wraps `google-api-python-client` Sheets API. `append-row` requests
  `includeValuesInResponse` and **read-back-confirms** the appended row carries
  its `entry_id` (F8) before reporting success, returning the written
  range/row + `row_index` so the caller records it in the ledger (F4).
- **Idempotent append (F8).** A retry after a transport error first does a
  bounded duplicate lookup by `entry_id` (scan the recent tail); if the row
  already exists it reports that row rather than appending a duplicate. The
  `entry_id` is passed in by the caller (`timelog`) so retries are stable.
- **New-client onboarding is a TWO-STEP, non-atomic flow (F3).** `create-tab`
  then `append-row` are separate Sheets calls. If `create-tab` succeeds but
  `append-row` fails, the tab EXISTS and the entry is NOT logged — the caller
  (`timelog`) surfaces this as `client_created_entry_failed`, never `logged`.
  Retry is idempotent: `create-tab` is a no-op if the tab already exists, and the
  append dedupes by `entry_id`.
- Exit codes `0` (ok) / `1` (operational failure — e.g. Sheets API error) /
  `2` (usage). `--self-check` = a bounded `spreadsheets().get` (like the calendar
  helper's `--self-check`). Fail-safe: a failure is a typed error, never a
  partial write.
- Workbook id resolved from `~/.config/felix/timelog/workbook.json`.

## C3 — `sheets_auth` (per-account, Sheets-scoped)

Mirrors `scripts/google/calendar_auth.py`: per-account creds under
`~/.config/felix/google/<account>/` (honoring `FELIX_GOOGLE_DIR`); returns
`spreadsheets`-scoped Credentials; **loads without forcing scopes** (uses the
token's granted scope — deploy gotcha #3); `SheetsAuthError` on any auth
problem (fail-safe). The `personal` token is re-minted once with
`calendar + spreadsheets` (one re-consent, IC-05).

## Acceptance-relevant contracts (→ Success Criteria)

- **SC-001**: `timelog --client ACME --hours 2.5 --date today --description "X"`
  (main's extraction of "log 2.5 hrs for ACME today doing X") → `logged` with one
  row in ACME's tab + a matching `receipt`.
- **SC-002**: unknown client → `unknown_client` (NO write); main asks.
- **SC-003**: Sheets API failure → `error` (NO partial write); main reports it +
  an alert fires.
- **SC-004**: `--add-client ACME` → tab created + the pending entry logged
  (`logged`); if the tab is created but the append fails →
  `client_created_entry_failed` (tab exists, entry NOT logged), main reports it
  truthfully + an alert fires. Retry is idempotent (F3).
- **SC-005**: `--correct --hours 3` / `--delete-last` → most-recent ledger row
  updated/removed (`corrected` / `deleted`) + a corrected receipt; a conflicting
  newer write → `correction_ambiguous` (no wrong-row mutation, F4).
