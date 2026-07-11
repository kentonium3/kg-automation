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
for the same `personal` account. **Re-mint the personal token once with the
combined scopes** `calendar` (existing) **+** `spreadsheets` (new).

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

**Correction (FR-006)**: a small **last-write state** file
(`/data/services/timelog/state/last-write.json`) records the most-recent append
(tab + row index + values) so "make it 3h" / "delete that last one" resolve
deterministically to that row. Atomic write (the #706/#683 pattern).

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

**Two-layer split (the #683 principle):**
- **Write path = deterministic (helper).** The helper parses the structured
  fields (regex for the common "log N hrs for <client> [today] doing <desc>"
  shape), resolves client→tab, writes the row, and returns a result. It **never
  guesses** — when it cannot proceed it returns a **typed need-clarification
  signal** instead of writing: `unknown_client` (with the spoken name + closest
  tab), `need_field` (which field is missing), `ambiguous`, or a write `error`.
- **Dialog = LLM (main).** main takes the helper's typed signal and conducts the
  natural-language conversation: asks the clarifying question ("no tab for
  'Acme' — did you mean ACME, or add a new client?"), relays the receipt on
  success, and on Kent's follow-up **re-invokes the helper** with the added
  info. Unknown-client confirmation, missing-field prompts, new-client
  onboarding, and corrections ("make that 3h") are all main-conducted.

**Pending state.** A small **pending-timelog** state file (mirrors calendar's
pending-clarifications) holds the in-flight entry so a follow-up reply resumes it
deterministically. The **last-write** state (D3) drives corrections.

**Prompt budget.** main is at the ~12 KB AGENTS.md cap (from #683), so the new
main prose is a **thin recognizer + how-to-call-the-helper + how-to-relay-the-
typed-signals** — the helper's typed results carry the logic, keeping main's
addition minimal. Run the fleet-guard size test after editing main's prompt.

**Rationale**: preserves the full interactive clarifying dialog (Kent's explicit
requirement) while removing the sub-agent delegation that broke #679; keeps the
write path deterministic + fail-safe (NFR-002, ties #683).

---

## D5 — Workbook bootstrap + deploy

**Decision**: one-time bootstrap creates the Felix-owned workbook via the Sheets
helper (`create`), records its id in a config/credential
(`~/.config/felix/timelog/workbook.json`, not committed). Deploy mirrors #699:
a dedicated (or shared google) venv on office2, the `felix-admin-timelog` agent
registered in openclaw.json, a `deploys/queued/<name>.yaml` manifest + entrypoint,
and the **Sheets-scope re-consent** (D1) as a MANDATORY operator step.

**Rationale**: reuse the #699 deploy shape end-to-end.

---

## Consolidated decisions

| Ref | Decision | Requirement(s) |
|-----|----------|----------------|
| D1 | Extend personal OAuth to `calendar + spreadsheets` (one re-consent) | C-002 |
| D2 | `sheets_helper.py` on google-api-python-client, CLI + fail-safe | FR-005, FR-007, NFR-001/002 |
| D3 | Tabs-as-truth + aliases config; last-write state for corrections | FR-002, FR-006 |
| D4 | **main-inline (no sub-agent, LOCKED opt A)**: main recognizes the shape + conducts the clarifying dialog, calling the deterministic helper directly; helper returns typed clarification signals; no #679 delegation | FR-001, FR-003, FR-004; NFR-002 |
| D5 | Workbook bootstrap + #699-shape deploy + re-consent stop | C-004 |

## Key risks carried into design

1. **Routing (D4) — RESOLVED to option A (no sub-agent).** The WhatsApp→write
   handoff has **no main→sub-agent delegation** (the #679 failure link), so that
   class is designed out: main calls the deterministic helper directly and
   conducts the dialog itself off the helper's typed signals. Residual risk =
   main's recognizer prompt quality within its 12 KB budget — post-plan Codex
   should still sanity-check the recognizer + typed-signal contract.
2. **Auth re-consent (D1)** — a Kent-in-the-loop OAuth grant; a MANDATORY deploy
   stop. Combined-scope token must not break the calendar helper.
3. **Correction semantics (FR-006)** — "most-recent entry" must be
   unambiguous (per-account last-write state); guard against correcting the
   wrong row after multiple rapid logs.
4. **Fail-safe correctness (NFR-002, ties #683)** — a receipt must reflect the
   actual write; the append must be confirmed by the API response before the
   receipt is composed.
