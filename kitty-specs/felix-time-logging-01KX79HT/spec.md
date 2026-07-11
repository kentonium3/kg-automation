# Feature Specification: Felix WhatsApp Time-Logging to Sheets

**Mission**: felix-time-logging-01KX79HT
**Source issue**: kentonium3/kg-automation#703 (P1-feature, area/felix-core)
**Mission type**: software-dev
**Status**: Draft — pending `/spec-kitty.plan`

## Purpose

**TL;DR**: Log billable time by texting WhatsApp; Felix appends it to the right client tab of a Google Sheet.

Kent's new multi-client commitments (Intentional consulting, spec-kitty fractional-exec role, business-acquisition work) create real time-tracking admin. This mission lets Kent capture time conversationally over WhatsApp — "log 2.5 hrs for ACME today doing X" — and have Felix write it, correctly and observably, to a fresh Felix-owned Google Sheets workbook (one tab per client). It is the first executive-assistant capability built on the just-shipped trust core: time is billing data, so it must be **correct** (#683 no-fabrication) and its failures must be **visible** (#701 alerting).

## Scope decisions (operator-confirmed)

- **Fresh Felix-owned workbook.** This mission creates a NEW Google Sheets workbook in Kent's own account with a Felix-defined structure: **one tab per client**; columns `date | hours | client | description | billable`. (Not integrating a pre-existing sheet.)
- **Unknown client → reject + ask (fail-safe).** If the named client has no tab, Felix does **not** write and does **not** guess — it replies asking Kent to confirm the client or add it, and waits.
- **Write immediately + receipt.** Felix writes the entry, then replies with a receipt of exactly what landed. Corrections happen via a follow-up message.
- **v1 = capture only** — no read-back/reporting, no batch, no voice-note transcription (see Out of Scope).

## User Scenarios & Testing

### Primary scenario

1. **Actor**: Kent, via a WhatsApp DM to Felix.
2. **Trigger**: "log 2.5 hrs for ACME today doing onboarding-call prep".
3. **Happy path**: Felix parses `(client=ACME, hours=2.5, date=today, description="onboarding-call prep")`, resolves `ACME` to its tab, appends one row `(today, 2.5, ACME, "onboarding-call prep", billable=yes, logged-at=<utc>)`, and replies `✅ Logged 2.5h for ACME (2026-07-10): onboarding-call prep`.
4. **Invariant**: Felix records an entry as logged **only if** it resolved the client to a real tab **and** the write actually succeeded — and its reply states only what actually happened.

### Exception — unknown client

- "log 1h for Acme" when no tab matches `Acme` → Felix writes **nothing** and replies "I don't have a tab for 'Acme' — did you mean ACME, or should I add a new client?" and waits for Kent's answer.

### New-client onboarding

- After the reject-and-ask above, Kent replies "add ACME" → Felix creates the tab (Felix-defined columns) and logs the pending entry, then sends the receipt.

### Correction

- Kent follows up "make that 3h" or "delete that last one" → Felix updates/removes the **most recent** entry it logged and replies with a corrected receipt.

### Failure

- The Sheets write fails (API error) → Felix does **not** write a partial/wrong row and replies that it could not log the entry (never a fabricated "logged" confirmation); the failure surfaces via the alert bus.

### Edge cases

- **Ambiguous / aliased client** ("acme", "Acme Co") → resolved via a normalizing client→tab map; if still ambiguous, ask.
- **Missing hours or description** → Felix asks for the missing field rather than writing an incomplete row.
- **Date phrasing** — "today" (default), "yesterday", or an explicit date normalize to a concrete date; unparseable date → ask.
- **Non-billable** — "log 1h non-billable for ACME …" sets `billable=no`; default is `billable=yes`.
- **Non-time-log message** — an ordinary WhatsApp message is not misinterpreted as a time log.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Parse a WhatsApp time-log message into structured fields (client, hours, description, date — default "today"); a non-time-log message is not misinterpreted as a log. | Proposed |
| FR-002 | Resolve the named client to its workbook tab via a normalizing client→tab map (case/alias tolerant). | Proposed |
| FR-003 | Unknown or ambiguous client → do **not** write; reply asking Kent to confirm or add the client; wait for his answer. | Proposed |
| FR-004 | On Kent confirming a new client, create the tab (Felix-defined columns) and then log the pending entry. New-client onboarding is a **two-step, non-atomic** flow: if the tab is created but the row append then fails, report that the tab was created but the time was **not** logged (never a "logged" claim); retry is idempotent. | Proposed |
| FR-005 | Append exactly **one** row to the client's tab: `date, hours, client, description, billable` (default `billable=yes`) + a logged-at UTC timestamp. | Proposed |
| FR-006 | Reply with a receipt matching exactly what was written; support correcting/removing the **most recent** entry on a follow-up ("make it 3h", "delete that last one"). | Proposed |
| FR-007 | On any failure (Sheets API error, parse ambiguity, partial new-client mutation), do **not** write a partial/wrong entry; report what actually happened — never a fabricated "logged" claim. A "logged" confirmation is gated on the row append being **API-confirmed** (read-back); a created tab whose append failed is reported as *not logged*. | Proposed |

### Non-Functional Requirements

| ID | Requirement | Measurable threshold | Status |
|----|-------------|----------------------|--------|
| NFR-001 | Correctness: the written row matches the parsed values exactly. | 0 mis-writes across the regression set. | Proposed |
| NFR-002 | Fail-safe (ties #683): never confirm "logged" for a write that did not happen; the receipt reflects the actual write. | 100% of injected write-failure cases report failure, not success. | Proposed |
| NFR-003 | Observability (ties #701): a Sheets-write failure surfaces via the unified alert bus; reported-vs-actual divergence is detectable. | An alert is emitted on any write failure. | Proposed |
| NFR-004 | Latency: receipt within a few seconds of the message. | ≤ ~5 s typical. | Proposed |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Own-account only: writes solely to a workbook Kent owns in his personal Google account (the "manage yourself" boundary). No client-owned accounts. | Proposed |
| C-002 | Auth: extend the felix-personal OAuth (`kentgale@gmail`, #681/#699) to include the Sheets scope (`https://www.googleapis.com/auth/spreadsheets`). A scope change requires a **one-time re-consent by Kent**. Reuse the `scripts/google/calendar_auth.py` per-account pattern. | Proposed |
| C-003 | Two-layer (#699 pattern): a deterministic Sheets helper + client→tab map; NL intent + fail-safe handled by a judgment agent/skill. **No LLM in the deterministic write path.** | Proposed |
| C-004 | Deploy via the manifest discipline (`deploys/queued/…`) to office2; the time-log intent is wired into the WhatsApp path. | Proposed |
| C-005 | Trust-core dependency: builds on #683 (no fabrication) + #701 (alerting). | Proposed |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | "log 2.5 hrs for ACME today doing X" → exactly one row in ACME's tab (today, 2.5, ACME, X, billable) + a receipt matching. |
| SC-002 | Unknown client ("log 1h for Acme", no matching tab) → **no** write; Felix asks to confirm/add. |
| SC-003 | A Sheets API failure → no partial/wrong write; Felix reports the failure (no false "logged"). |
| SC-004 | New-client confirm → tab created + entry logged + receipt. |
| SC-005 | Correction ("make that 3h" / "delete the last one") → the most recent entry is updated/removed + a receipt. |

## Key Entities

- **Time-log message** — a WhatsApp instruction from Kent to log time.
- **Time entry** — a structured `(date, hours, client, description, billable)` record + logged-at timestamp.
- **Client → tab map** — the normalizing mapping from a spoken client name to a workbook tab.
- **Workbook** — the Felix-owned Google Sheets time-tracking workbook (one tab per client).
- **Receipt** — the WhatsApp confirmation of exactly what was written.

## Assumptions

- The felix-personal Google account (`kentgale@gmail`, from #681/#699) is the account that owns the workbook; extending its OAuth to the Sheets scope is acceptable (a one-time re-consent).
- WhatsApp is the input channel (Felix's existing conversational path); text input in v1.
- The #683 no-fabrication doctrine + #701 alert bus are deployed (they are) and are the trust substrate this builds on.

## Dependencies

- **#683** (no fabrication) + **#701** (alert bus) — the trust core this sits on.
- **#699** calendar-helper pattern + `scripts/google/calendar_auth.py` per-account OAuth substrate.
- felix-personal OAuth Sheets-scope re-consent (Kent-in-the-loop, at deploy).
- The WhatsApp intent-routing path.

## Out of Scope (v1)

- Reading back / querying the sheet, or generating external client reports (v1 is capture only).
- Batch / multi-entry in a single message.
- WhatsApp **voice-note** transcription as an input. v1 accepts **TEXT only**; a voice-note input is treated as `not_timelog` / unsupported (no attempt to transcribe in this mission).
- Client mail / calendar / Slack (client-owned accounts — no OAuth; out of the "manage yourself" boundary).

## Relationship to roadmap

First EA-capability of the post-stabilization phase (Felix roadmap / Bedrock #673), and the exemplar of why the trust core was built first: billing data must be correct and its failures visible. Mirrors the #699 two-layer pattern (deterministic helper + judgment agent).
