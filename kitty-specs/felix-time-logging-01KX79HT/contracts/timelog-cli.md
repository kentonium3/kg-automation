# Contract: time-log CLIs (the main↔helper interface)

**Mission**: felix-time-logging-01KX79HT · **Phase**: 1

The load-bearing interface of option A: `main` calls these; their **typed JSON**
drives main's dialog. All follow repo helper conventions (`python3 -m`, stdout =
machine-readable, exit code = status, fail-safe, no LLM).

## C1 — `timelog` (the main-facing entrypoint)

```
python3 -m scripts.google.timelog --message "<raw whatsapp text>" [--account personal] [--json]
# follow-ups (main passes these after a clarification reply, using pending state):
python3 -m scripts.google.timelog --confirm-client "ACME" --account personal
python3 -m scripts.google.timelog --add-client "ACME" --account personal        # new-client onboarding: create tab + log pending
python3 -m scripts.google.timelog --field hours=3 --account personal            # supply a missing field
python3 -m scripts.google.timelog --correct "make it 3h" --account personal     # amend last-write
python3 -m scripts.google.timelog --delete-last --account personal
```

- **Returns** a `TimelogResult` JSON (data-model.md) on stdout: exactly one of
  `logged` / `unknown_client` / `need_field` / `ambiguous` / `error`.
- **Never guesses, never partial-writes.** Only `logged` means a row landed
  (API-confirmed).
- **Exit codes**: `0` = handled (any status incl. a clarification signal — these
  are normal); `2` = usage error (bad args); the helper does not exit non-zero
  merely because it needs clarification.
- **State**: writes `pending-<account>.json` when it returns a clarification
  signal; writes `last-write-<account>.json` on `logged`. Atomic.
- **Deterministic**: parsing is regex over the "log N hrs for <client> [today|<date>] doing <desc>" shape (+ "non-billable"); ambiguity → `ambiguous`/`need_field`, never a guess. NO LLM.

Example returns:
```json
{"status":"logged","tab":"ACME","receipt":"✅ Logged 2.5h for ACME (2026-07-10): onboarding prep","row":{"date":"2026-07-10","hours":2.5,"client":"ACME","description":"onboarding prep","billable":true}}
{"status":"unknown_client","heard":"Acme","closest":"ACME"}
{"status":"need_field","missing":"hours","partial":{"client":"ACME","description":"onboarding prep"}}
{"status":"error","detail":"Sheets API 503; nothing written"}
```

## C2 — `sheets_helper` (deterministic Sheets ops)

```
python3 -m scripts.google.sheets_helper append-row  --tab ACME --values '["2026-07-10",2.5,"ACME","desc",true,"<iso>"]' [--account personal]
python3 -m scripts.google.sheets_helper create-tab  --tab ACME [--account personal]
python3 -m scripts.google.sheets_helper list-tabs   [--account personal]
python3 -m scripts.google.sheets_helper update-last --tab ACME --row 7 --values '[...]'
python3 -m scripts.google.sheets_helper delete-last --tab ACME --row 7
python3 -m scripts.google.sheets_helper --self-check [--account personal]
```

- Wraps `google-api-python-client` Sheets API. `append-row` returns the written
  range/row (from the API response) so the caller can record `last-write`.
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

- **SC-001**: `timelog --message "log 2.5 hrs for ACME today doing X"` → `logged`
  with one row in ACME's tab + a matching `receipt`.
- **SC-002**: unknown client → `unknown_client` (NO write); main asks.
- **SC-003**: Sheets API failure → `error` (NO partial write); main reports it +
  an alert fires.
- **SC-004**: `--add-client ACME` → tab created + the pending entry logged.
- **SC-005**: `--correct "make it 3h"` / `--delete-last` → last-write row
  updated/removed + a corrected receipt.
