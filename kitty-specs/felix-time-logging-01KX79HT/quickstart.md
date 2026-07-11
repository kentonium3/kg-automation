# Quickstart: Felix WhatsApp Time-Logging to Sheets

**Mission**: felix-time-logging-01KX79HT

## What ships

1. **`scripts/google/sheets_auth.py`** — Sheets-scoped per-account creds (mirrors `calendar_auth.py`).
2. **`scripts/google/sheets_helper.py`** — deterministic Sheets CLI (append/create-tab/list-tabs/update-last/delete-last/self-check).
3. **`scripts/google/timelog.py`** — parse + resolve + typed signals + state; the `main`-facing entrypoint.
4. **`docs/design/architecture/data/timelog-clients.json`** — client aliases.
5. **`scripts/openclaw/agents/main/AGENTS.md`** — thin "log time" recognizer + dialog (option A; no sub-agent).
6. **Deploy** — `deploys/queued/timelog.yaml` + `scripts/deploy/deploy-timelog.py`.

## Local dev / test

```
python3 -m pytest tests/google -v --cov=scripts/google --cov-branch
# dry-run the parse+resolve without writing (mock/omit workbook):
python3 -m scripts.google.timelog --message "log 2.5 hrs for ACME today doing X" --json
```

## Deploy to office2 (post-merge, operator-run — mandatory stops flagged)

> Follows the #699/#711 deploy discipline. Do not hand-crank on office2.

1. Merge the mission to `feat/felix-time-logging`, run the **post-merge Codex
   review** of the full diff, fold, then merge `feat → main`.
2. **⛔ MANDATORY OPERATOR STOP — Sheets scope re-consent.** Re-mint the
   `personal` Google token with `calendar + spreadsheets` scopes (browser OAuth
   grant — only Kent can complete it). Stage the refreshed token at
   `~/.config/felix/google/personal/` on office2. Verify: `sheets_helper
   --self-check` = ok AND `calendar_helper --self-check` still = ok (combined
   scope must not break calendar).
3. **⛔ Workbook bootstrap (one-time).** Create the Felix-owned time-tracking
   workbook (via `sheets_helper` create) and record its id in
   `~/.config/felix/timelog/workbook.json` (0600). Seed any known client tabs.
4. felix-deployer applies `deploys/queued/timelog.yaml`: the entrypoint verifies
   deps/venv, runs a **`--dry-run` self-test (NO emit — #711)**, triggers
   `agent-prompt-sync.service` + verifies main's deployed prompt carries the
   time-log recognizer, and reports via the #701 bus.
5. **Rebaseline: not required** — main's AGENTS.md is an unmonitored audited
   surface (gap #621); `scripts/google/**` is not a hashed baseline. Merge
   commit records `Rebaseline: not required — <reason>`.

## Verify live (SC-001..005) — with Kent

- **SC-001** — DM "log 2.5 hrs for ACME today doing X" → one row in ACME's tab + receipt.
- **SC-002** — "log 1h for Acme" (no/typo tab) → Felix asks; no write.
- **SC-004** — "add ACME" → tab created + the pending entry logged.
- **SC-005** — "make that 3h" then "delete that last one" → corrected/removed + receipt.
- **SC-003** — force a Sheets error (temporarily bad workbook id) → Felix reports failure + an alert fires; no partial write.

## Rollback

- Remove the "log time" recognizer from main's prompt + re-sync (the helper is inert without the recognizer).
- The workbook + creds are Kent's; no destructive teardown.

## Key gotchas folded in (#699/#711/#683)

- Don't force OAuth scope on refresh (use the token's granted scope).
- Deploy self-test must **`--dry-run`** (no emit) and dry-run-verify before going live (#711).
- office2 is `python3`-only; `main` calls the helper via its `exec` form.
- Fail-safe: only an API-confirmed append returns `logged`; every other path writes nothing and is reported truthfully (#683).
