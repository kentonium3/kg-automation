---
title: Time-Log Operations
doc_type: runbook
status: approved
owners: ["@kentonium3"]
created: '2026-07-11'
last_updated: '2026-07-11'
updated_by: 'felix-time-logging-01KX79HT (#703)'
audience: agents_and_humans
tags: [703, 699, 711, 681]
---

# Time-Log Operations

Operational runbook for the **Felix time-logging** feature — a WhatsApp
"log time" workflow that appends billable/non-billable time entries to a
Felix-owned Google Sheets workbook, deterministically, with no false-success
reporting. Delivered by mission `felix-time-logging-01KX79HT` (#703).

- **Authoritative service record**: `services[felix-timelog-helper]` in
  [`../design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>)
  (narrative: [`service-inventory.md`](<../design/architecture/service-inventory.md>) §Felix Time-Log Helper).
- **Authoritative credential record**: `felix-google-personal-calendar` in
  [`../design/architecture/data/credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
  (this credential now carries **both** `calendar.events` and `spreadsheets`
  scopes — see the re-consent procedure below).
- **Authoritative data-flow record**: `whatsapp-timelog-to-sheets` in
  [`../design/architecture/data/data-flows.json`](<../design/architecture/data/data-flows.json>).

> **Relationship to the calendar helper (#699)**: this feature shares the
> same uv venv (`/data/services/openclaw/felix-calendar/venv`) and the same
> per-account OAuth credential as the Felix calendar helper — the personal
> token is re-minted **once** with the combined `calendar + spreadsheets`
> scopes rather than minting a second credential. The two helpers remain
> independent modules (`calendar_helper.py` / `sheets_helper.py`); only the
> venv and the underlying token are shared.

---

## What it is

- **Source**: `scripts/google/timelog.py` (the `main`-facing normalizer:
  validate → resolve client → typed signal → write) and
  `scripts/google/sheets_helper.py` (deterministic Sheets CLI:
  `append-row` / `create-tab` / `list-tabs` / `update-last` / `delete-last`
  + `--self-check`), backed by `scripts/google/sheets_auth.py` (per-account
  OAuth load/refresh, scope-agnostic).
- **Invocation model**: **on-demand only** — no long-running service, no
  systemd unit, no cron. `main` recognizes the "log time" shape directly
  (option A — extraction + dialog, **no sub-agent delegation**), extracts
  the candidate fields from the natural-language message, and calls
  `timelog` via `exec` with structured args. `main` relays the helper's
  typed results verbatim; it authors no fixed reply/receipt text itself.
- **No LLM in the helper.** All NL judgment lives in `main`; `timelog.py`
  and `sheets_helper.py` are pure validation + Sheets API calls.

---

## Venv location and invocation

Shared with the #699 calendar helper (office2's system `python3` cannot
import the Google client libraries and has no `pip`):

```
/data/services/openclaw/felix-calendar/venv
```

Invoke in module form from the checkout root:

```
cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.timelog \
  --client <name> --hours <n> --date <date> --description <text> [--non-billable] \
  --channel whatsapp --conversation <id> --source-msg-id <id> --json
```

```
cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.sheets_helper --self-check --account personal
```

---

## Sheets re-consent procedure (MANDATORY operator stop)

The Sheets scope is added to the **existing** `felix-google-personal-calendar`
credential — this is a **one-time, browser-OAuth, Kent-only** step. office2
never runs interactive consent.

1. On the **Mac**, re-mint the `personal` Google token with the **combined**
   scopes:
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/spreadsheets`

   Do **not** force a narrower scope on refresh — both `calendar_auth.py`
   and `sheets_auth.py` load tokens **without** forcing scopes
   (`Credentials.from_authorized_user_file` uses whatever scopes the token
   was actually minted with); forcing a mismatched scope makes the refresh
   fail `invalid_scope`.
2. Copy the refreshed `token.json` to office2 at the same per-account path,
   mode **0600**:
   ```
   ~/.config/felix/google/personal/token.json
   ```
   (`client_secret.json` is unchanged — the same GCP OAuth client covers
   both scopes.)
3. **Verify BOTH self-checks return ok** — the combined-scope token must
   not break the calendar helper:
   ```
   cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.sheets_helper --self-check --account personal
   cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper --self-check --account personal
   ```
   Both must exit `0`. If either fails, the token was not re-minted with
   the full combined scope — redo step 1.

---

## One-time workbook bootstrap (MANDATORY operator stop)

Create the Felix-owned time-tracking workbook and record its id **before**
the deploy manifest can apply cleanly (`sheets_helper` reads this config on
every invocation and fails with a usage error, exit 2, if it is absent).

1. Create a new Google Sheets workbook (via the Google Sheets UI, or a
   one-off `sheets_helper` bootstrap call once the workbook exists and you
   have its id from the URL: `https://docs.google.com/spreadsheets/d/<id>/edit`).
2. Record the id at `~/.config/felix/timelog/workbook.json` (0600) on
   office2:
   ```json
   {"spreadsheet_id": "<id>"}
   ```
   (Override the config directory via `FELIX_TIMELOG_CONFIG_DIR` for test
   isolation only — never in production.)
3. **Seed known client tabs** — for each known client, run `create-tab`
   (no-op/idempotent if the tab already exists, F3):
   ```
   cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.sheets_helper create-tab --tab <ClientName> --account personal
   ```
   Client aliases (so "Acme" / "ACME" / "acme corp" all resolve to the same
   tab) are configured in
   [`../design/architecture/data/timelog-clients.json`](<../design/architecture/data/timelog-clients.json>).
4. Confirm the bootstrap with `list-tabs`:
   ```
   cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.sheets_helper list-tabs --account personal
   ```

---

## Deploy

`deploys/queued/timelog.yaml` (Tier 2 — touches the credential scope — with
a Tier-2 `verification:` block) is picked up by `felix-deployer` within ~5
minutes of merge to `main`. The entrypoint
(`scripts/deploy/deploy-timelog.py`) runs, halt-on-error:

1. **Venv/deps gate** — confirms the shared uv venv + pinned google deps
   (idempotent; reuses the #699 venv rather than provisioning a new one).
2. **Creds + workbook-config presence** — verifies the re-consented token
   and the workbook-id config are staged. **Fails cleanly** with a
   "complete the re-consent / bootstrap first" message if either
   precondition above has not been completed — this manifest will
   otherwise keep failing (and re-attempting) every ~5-min tick.
3. **No-emit dry-run self-test + gate (#711).** Runs `sheets_helper
   --self-check --account personal` (no write) and `timelog` against a
   client guaranteed not to resolve to any tab (returns `unknown_client`
   without ever reaching `append-row`, and without emitting an alert —
   `unknown_client`/`ambiguous` never call the alert path). If either is
   not clean, the deploy **fails here** with nothing enabled/synced, so no
   false alert ever fires.
4. **Prompt-sync trigger + verify** (only after the self-test is clean) —
   triggers `agent-prompt-sync.service`, then verifies the time-logging
   recognizer (`## Time-logging (option A, direct helper call)`) landed in
   deployed `main`'s `AGENTS.md`.
5. **Report via the `#701` alert bus.**

**Rebaseline: not required** — `main`'s `AGENTS.md` is an *unmonitored*
audited surface (gap #621; `audit.sh` does not hash deployed `AGENTS.md`)
and `scripts/google/**` here is not a hashed baseline.

---

## Rollback

Remove the "log time" recognizer heading
(`## Time-logging (option A, direct helper call)`) from
`scripts/openclaw/agents/main/AGENTS.md`, merge, and let prompt-sync
re-deploy — the helper is inert without `main` calling it. The workbook and
credentials are Kent's; there is no destructive teardown (the workbook and
staged token are left in place).

---

## Live-verification checklist (SC-001..005) — with Kent

Run each of these as a real WhatsApp DM exchange with Felix and confirm the
stated outcome:

- **SC-001 — log → row + receipt.** "log 2.5 hrs for ACME today doing X" →
  one new row appears in ACME's tab; Felix relays a receipt confirming the
  logged entry (client, hours, date, description).
- **SC-002 — unknown client → ask, no write.** "log 1h for Acmee" (typo/no
  matching tab) → Felix asks for clarification; confirm **no row is
  written** to any tab while the clarification is pending.
- **SC-003 — forced Sheets error → failure reported + alert, no partial
  write.** Temporarily point the workbook config at a bad/inaccessible
  spreadsheet id (or revoke access), attempt a log → Felix reports the
  failure honestly (never a false "logged"); confirm an alert fires via the
  `#701` bus and **no partial row** is left in any tab. Restore the correct
  workbook id afterward.
- **SC-004 — new-client confirm → tab created + entry logged.** "add ACME"
  (or equivalent new-client confirmation) → a new tab is created for the
  client AND the pending entry is logged into it. Confirm the two-step
  create-then-append sequence completes fully (not just tab creation).
- **SC-005 — correction → most-recent entry updated/removed.** After a
  successful log, "make that 3h" → the most recent entry updates in place
  (not a new row); then "delete that last one" → the entry is removed.
  Confirm both operations target the correct (most recent) row via the
  recent-write ledger, and that a stale/ambiguous correction is rejected
  rather than silently applied to the wrong row.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `sheets_helper` exits 2 with "workbook config not found" | Workbook bootstrap not completed | Run the one-time bootstrap above. |
| `sheets_helper --self-check` exits 1 (auth) | Token not re-minted with `spreadsheets` scope, or expired | Re-run the re-consent procedure above; verify BOTH self-checks. |
| `calendar_helper --self-check` starts failing after the Sheets re-consent | Scope was forced instead of loaded as-minted | Re-mint the combined scope from scratch on the Mac; never force a scope on refresh. |
| Deploy manifest fails every tick | One or both operator preconditions incomplete | Complete re-consent + bootstrap, confirm via the two self-checks, then let the next tick retry — no manual retry command needed. |
| Felix reports "logged" but no row appears | Should not happen — `timelog` only reports `logged` after an API-confirmed read-back (#683) | Treat as a trust-defect bug; file an issue with the `TimelogResult` JSON. |

---

## Related

- [`calendar-helper-ops.md`](<./calendar-helper-ops.md>) — the sibling
  Google Calendar helper (#699); shares this feature's venv and credential.
- [`deploy/discipline.md`](<./deploy/discipline.md>) — manifest-driven
  deploy pattern used to gate this deploy.
- RFC #681 (accepted) — Felix-owned direct Google Workspace APIs.
