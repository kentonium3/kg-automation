# Research: Felix WhatsApp Time-Logging to Sheets

**Mission**: felix-time-logging-01KX79HT · **Phase**: 0 · **Date**: 2026-07-10

Resolves the open design questions before Phase-1 design. Mirrors the #699
calendar pattern (deterministic helper + per-account OAuth + judgment agent).

---

## D1 — Sheets auth: extend the felix-personal token to add the Sheets scope

**Decision**: Reuse the per-account OAuth substrate (`scripts/google/calendar_auth.py`
pattern — per-account creds under `~/.config/felix/google/<account>/`, honoring
`FELIX_GOOGLE_DIR`, fail-safe). Add a Sheets auth loader (a `sheets_auth.py`, or
factor a shared `google_auth.py`) that returns `spreadsheets`-scoped Credentials
for the same `personal` account. **Re-mint the personal token once with EXACTLY
these two scopes (F11):**

- `https://www.googleapis.com/auth/calendar` — existing (must be preserved).
- `https://www.googleapis.com/auth/spreadsheets` — new (least-privilege for the
  workbook writes).

No other scopes are requested at re-consent. **Post-remint regression (F11,
MANDATORY):** verify BOTH `calendar_helper --self-check` AND
`sheets_helper --self-check` pass on the re-minted token before the deploy is
considered green — the combined-scope token must not break calendar.

**Rationale**:
- The personal token currently grants only `calendar` (verified 2026-07-10:
  `scopes: ['.../auth/calendar']`). Sheets needs `.../auth/spreadsheets`.
- The calendar helper loads credentials **without forcing scopes** (deploy
  gotcha [[reference_felix_deploy_gotchas]] #3: forcing a scope on refresh →
  `invalid_scope`). So a single re-consent that grants `calendar + spreadsheets`
  keeps the calendar helper working AND enables Sheets — **one token per
  account**, both capabilities.
- **Kent-in-the-loop dependency (surfaced at deploy):** the re-consent is a
  browser OAuth grant only Kent (the account owner) can complete. It is a
  MANDATORY STOP in the deploy phase.

**Alternatives rejected**: a separate Sheets-only token (more tokens for the
same account); a Service Account (Kent owns the workbook in a consumer Google
account — OAuth-user is the right model, matching #699).

---

## D2 — Deterministic Sheets helper

**Decision**: `scripts/google/sheets_helper.py` — a CLI mirroring
`calendar_helper.py` (exit codes 0/1/2, `--self-check`, `--account` default
`personal`, `HelperError`, fail-safe, no LLM). Operations via
google-api-python-client Sheets API:
- `append-row` → `spreadsheets().values().append`
- `create-tab` → `spreadsheets().batchUpdate` (`addSheet`)
- `list-tabs` → `spreadsheets().get` (sheet titles)
- `update-last` / `delete-last` (for corrections) → `values().update` /
  `batchUpdate` on a resolved row range
- `--self-check` → `spreadsheets().get` on the workbook (bounded read)

**Rationale**: reuse the exact google-api-python-client stack the calendar
helper already uses (no new dependency like `gspread`); consistent CLI contract
and test seams. The workbook id comes from config (D4).

---

## D3 — Client → tab resolution + the "correction" state

**Decision**: **The workbook's actual tabs are the source of truth** (read via
`list-tabs`), supplemented by a small **aliases config**
(`docs/design/architecture/data/timelog-clients.json`: `canonical → [aliases]`)
so "acme"/"Acme Co" resolve to the `ACME` tab. Resolution = normalize the spoken
name → match a tab title or an alias → tab. No match → **unknown** (helper
returns a typed "no such client" result; the agent asks — FR-003), never a write.

**Correction (FR-006)**: a small **recent-write ledger** (F4) —
`/data/services/timelog/state/ledger-<account>.json` (replacing a single
last-write file) — records recent appends, each with a stable `write_id`, the
source WhatsApp message id/timestamp, the tab + row index, the values, and a TTL
(data-model.md RecentWriteLedger). "make it 3h" / "delete that last one" resolve
to the **most-recent** ledger entry; if a **newer** write exists or the state is
**stale**, the helper returns `correction_ambiguous` rather than mutating the
wrong row (guards against correcting after multiple rapid logs). Atomic write
(the #706/#683 pattern).

**Rationale**: tabs-as-truth avoids a hand-maintained map drifting from reality;
aliases handle the fuzzy-name gap without an LLM in the write path.

---

## D4 — Where the "log time" work runs (LOCKED: option A — main-inline, no sub-agent)

**Decision (operator-confirmed 2026-07-10):** **No separate agent.** `main`
(sonnet — already Kent's conversational WhatsApp agent) recognizes the "log
time" shape and **calls the deterministic time-log helper directly** (its `exec`
form — the same terminal-action mechanism the calendar agent uses to call the
calendar helper). **There is NO main→sub-agent delegation** — that is the exact
link that failed in #679, and eliminating it is the whole point.

**Two-layer split (the #683 principle) — main EXTRACTS, helper VALIDATES+WRITES
(F7):**
- **Extraction = LLM (main).** `main` reads the natural language and extracts the
  candidate fields — `client`, `hours`, `description`, `date`, `billable` — then
  calls the helper with **STRUCTURED args**
  (`--client … --hours … --date … --description … [--non-billable]`). There is
  **NO brittle NL regex in the helper** and **NO LLM in the write path**.
- **Write path = deterministic (helper).** The helper **validates** the
  structured args, **resolves** client→tab (tabs-as-truth + aliases, D3), and
  **writes** the row (read-back-confirmed, F8), returning a result. It **never
  guesses** — when main's extraction is insufficient or the client is unknown it
  returns a **typed clarification signal** instead of writing: `unknown_client`
  (given name + closest tab), `need_field` (which field is missing),
  `ambiguous` (client matches multiple tabs), or a write `error`.
- **Dialog = LLM (main).** main takes the helper's typed signal and conducts the
  natural-language conversation: asks the clarifying question, **relays** the
  receipt on success (it does not author the receipt/reply text — those come from
  the typed result, F1), and on Kent's follow-up **re-invokes the helper** with
  the added info. Unknown-client confirmation, missing-field prompts, new-client
  onboarding, and corrections ("make that 3h") are all main-conducted.

**Supported inputs + a `not_timelog` result (F6).** A message main judges to be
non-time-log → main simply does **not** call the helper (or, if the helper is
invoked on it, it returns `not_timelog`). A genuinely time-like-but-underspecified
message → `need_field` / `ambiguous`, **never a mis-write**. Voice-note input is
out of scope (v1 text only, spec Out-of-Scope) — treated as `not_timelog`.

**Pending state — keyed by conversation source (F5).** The **pending-timelog**
state is keyed by channel + conversation + source-message-id (not merely
per-account), carrying `awaiting` + a nonce/expected-action + created/expires
timestamps (data-model.md PendingTimelog; timeout 30 min). A follow-up only
resumes a pending record it **correlates to**; otherwise the helper returns
`no_pending` (nothing correlates) or `stale_pending` (correlated but expired).
The **recent-write ledger** (D3/F4) drives corrections.

**Prompt budget (F1).** main is at the ~12 KB AGENTS.md cap (from #683). The
time-log addition is a **thin recognizer + field-extraction guidance +
how-to-call-the-helper + how-to-relay-the-typed-signals**; all fixed reply /
receipt text lives in the helper's typed results (main relays, doesn't author),
keeping main's addition minimal. A `main` prompt-compression pass to reclaim
headroom is required PRE-WORK (plan IC-04) before adding any time-log prose. Run
the fleet-guard size test after editing main's prompt (must stay green).

**Rationale**: preserves the full interactive clarifying dialog (Kent's explicit
requirement) while removing the sub-agent delegation that broke #679; keeps the
write path deterministic + fail-safe (NFR-002, ties #683).

---

## D5 — Workbook bootstrap + deploy

**Decision**: one-time bootstrap creates the Felix-owned workbook via the Sheets
helper (`create`), records its id in a config/credential
(`~/.config/felix/timelog/workbook.json`, not committed). Deploy mirrors #699:
a dedicated (or shared google) venv on office2, a `deploys/queued/<name>.yaml`
manifest + entrypoint, and the **Sheets-scope re-consent** (D1) as a MANDATORY
operator step. **NO separate agent (F10):** option A wires only `main`'s prompt
(the recognizer/extractor/dialog) + the helper + the manifest — there is **no
`felix-admin-timelog` agent registration** in openclaw.json.

**Rationale**: reuse the #699 deploy shape end-to-end, minus the separate agent
(option A puts the intent inline in `main`).

---

## Consolidated decisions

| Ref | Decision | Requirement(s) |
|-----|----------|----------------|
| D1 | Extend personal OAuth to `calendar + spreadsheets` (one re-consent) | C-002 |
| D2 | `sheets_helper.py` on google-api-python-client, CLI + fail-safe | FR-005, FR-007, NFR-001/002 |
| D3 | Tabs-as-truth + aliases config; recent-write ledger for corrections | FR-002, FR-006 |
| D4 | **main-inline (no sub-agent, LOCKED opt A)**: main EXTRACTS structured fields + conducts the clarifying dialog, calling the deterministic helper directly; helper validates+resolves+writes and returns typed clarification signals; pending keyed by conversation source; no #679 delegation | FR-001, FR-003, FR-004; NFR-002 |
| D5 | Workbook bootstrap + #699-shape deploy + re-consent stop | C-004 |

## Key risks carried into design

1. **Routing (D4) — RESOLVED to option A (no sub-agent).** The WhatsApp→write
   handoff has **no main→sub-agent delegation** (the #679 failure link), so that
   class is designed out: main calls the deterministic helper directly and
   conducts the dialog itself off the helper's typed signals. Residual risk =
   main's field-extraction quality within its 12 KB budget — post-plan Codex
   should still sanity-check the extraction + structured-args + typed-signal
   contract.
2. **Auth re-consent (D1)** — a Kent-in-the-loop OAuth grant; a MANDATORY deploy
   stop. Combined-scope token must not break the calendar helper.
3. **Correction semantics (FR-006)** — "most-recent entry" must be
   unambiguous (recent-write ledger, F4); a newer write or stale state →
   `correction_ambiguous`, guarding against correcting the wrong row after
   multiple rapid logs.
4. **Fail-safe correctness (NFR-002, ties #683)** — a receipt must reflect the
   actual write; the append must be confirmed by the API response before the
   receipt is composed.
