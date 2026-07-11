# Data Model: Felix WhatsApp Time-Logging to Sheets

**Mission**: felix-time-logging-01KX79HT · **Phase**: 1

File/Sheets-backed; no database. Atomic JSON state (temp+rename, #706 pattern).

## Entity: TimeEntry (one appended row)

| Field | Type | Notes |
|-------|------|-------|
| `date` | string (YYYY-MM-DD) | Normalized from "today"/"yesterday"/explicit. |
| `hours` | number | Parsed decimal hours. |
| `client` | string | Canonical client name (= tab title). |
| `description` | string | Free text. |
| `billable` | bool | Default `true`; "non-billable" → `false`. |
| `logged_at` | string (ISO-8601 UTC) | When Felix wrote it. |
| `entry_id` | string (uuid4) | **Stable per-entry idempotency key** (F8). Generated once before the append; written as a trailing column so a retry after a transport error detects the existing row by key instead of duplicating. |

Row column order in the tab: `date | hours | client | description | billable` (+ `logged_at` and `entry_id` as trailing columns).

**Append idempotency (F8, ties NFR-002).** The append is verified by read-back
before `logged` is returned: the write requests `includeValuesInResponse`, and
the returned row is confirmed to carry the `entry_id`. A retry after a transport
error first performs a bounded duplicate lookup by `entry_id` (scan the recent
tail of the tab) — if the row already exists, the retry reports `logged` for the
existing row rather than appending a second copy. Only an API-confirmed row
carrying its `entry_id` yields `logged`.

## Entity: TimelogResult (typed helper → main signal)

The single value the `timelog` CLI returns to `main`. `status` drives main's
dialog. The status set is a **complete union** covering every dialog state main
can reach; `main` never authors the confirmation/receipt text — it relays the
typed result's own strings (F1). The helper receives STRUCTURED fields already
extracted by `main` (F7) — it validates, resolves client→tab, and writes; it
does NOT re-parse natural language.

| `status` | Meaning | Carries |
|----------|---------|---------|
| `logged` | Row appended + read-back-confirmed by the API (carries its `entry_id`). | `tab`, `row` (the TimeEntry incl. `entry_id`), `receipt` (the exact confirmation string). |
| `unknown_client` | No tab matched the given client. | `heard` (given name), `closest` (best tab candidate, if any). NO write. |
| `need_field` | A required field is missing from the structured args. | `missing` (`hours`\|`description`\|`client`\|`date`), `partial` (fields present). NO write. |
| `ambiguous` | The given client matches multiple tabs/aliases. | `candidates`. NO write. |
| `error` | Sheets API / auth failure (incl. auth-failure). | `detail`. NO partial write. Alerts via #701. |
| `not_timelog` | The input is not a time-log request (`main` normally just doesn't call the helper; returned if the helper is invoked on a non-time-log message). | — . NO write. |
| `no_pending` | A follow-up (confirm/add-client/field) arrived but no pending record correlates to it. | `awaiting` (none). NO write. |
| `stale_pending` | A correlated pending record exists but has expired past its TTL. | `age_s`. NO write; pending cleared. |
| `client_created_entry_failed` | New-client onboarding created the tab but the row append then failed (**partial mutation** — F3). | `tab` (created), `detail`. Tab EXISTS; entry NOT logged. main must say the time was **not** logged. Retry is idempotent (create-tab no-ops). Alerts via #701. |
| `corrected` | The most-recent ledger entry was amended (`--correct`), read-back-confirmed. | `tab`, `row`, `receipt`. |
| `deleted` | The most-recent ledger entry was removed (`--delete-last`), confirmed. | `tab`, `row` (removed), `receipt`. |
| `no_last_write` | A correction/delete arrived but the recent-write ledger is empty. | — . NO write. |
| `correction_ambiguous` | A correction/delete cannot resolve a single target — a newer write exists, or the ledger state is stale (F4). | `candidates`, `reason` (`newer_write`\|`stale`). NO write. |

**Invariant (NFR-002/#683/F3):** `logged` / `corrected` / `deleted` are returned
**only after** the Sheets mutation is API-confirmed by read-back (carrying the
`entry_id`, F8). `client_created_entry_failed` means the tab was created but the
entry was **not** logged — main must report that truthfully and never claim the
time was logged. Every non-terminal status means **nothing was written**, and
main must reflect that truthfully.

## Entity: ClientAliases (committed config)

`docs/design/architecture/data/timelog-clients.json` — `{ canonical: [aliases...] }`.
Resolution: normalize the spoken name (lowercase, trim) → exact tab-title match →
alias match → else `unknown_client`. **Tabs are the source of truth** (read via
`list-tabs`); aliases only bridge fuzzy spoken names.

## Entity: PendingTimelog (state)

`/data/services/timelog/state/pending-<account>.json` — the in-flight entry
awaiting a clarification reply (unknown-client / missing-field / new-client).
**Keyed by conversation source (F5)** — channel + conversation + the
source-message-id of the request — not merely per-account, so a follow-up only
resumes a pending record it **correlates to**. An uncorrelated follow-up →
`no_pending`; a correlated-but-expired record → `stale_pending` (both clear the
record). File may hold a small keyed map when concurrent conversations exist.

| Field | Type | Notes |
|-------|------|-------|
| `source` | object | `{channel, conversation_id, source_message_id}` — the correlation key. A follow-up must match to resume. |
| `partial` | TimeEntry (partial) | Fields present so far. |
| `awaiting` | enum | `client` \| `field:<name>` \| `new_client_confirm`. |
| `nonce` | string | Expected-action token echoed by main's follow-up call (guards a mismatched resume). |
| `created_at` | ISO-8601 UTC | When opened. |
| `expires_at` | ISO-8601 UTC | `created_at` + TTL. **Timeout: 30 min** (past it → `stale_pending`). |

## Entity: RecentWriteLedger (state)

`/data/services/timelog/state/ledger-<account>.json` — a small **recent-write
ledger** (F4), replacing the single last-write file, so `--correct` /
`--delete-last` resolve to the most-recent entry unambiguously and can detect a
conflicting newer write. Bounded (recent N entries within TTL); older entries
age out.

| Field | Type | Notes |
|-------|------|-------|
| `write_id` | string (uuid4) | Stable ledger id for this write (distinct from the row's `entry_id`). |
| `entry_id` | string | The written row's idempotency key (F8), for read-back correlation. |
| `source` | object | `{channel, conversation_id, source_message_id}` of the WhatsApp message that caused the write. |
| `tab` | string | Client tab. |
| `row_index` | int | 1-based sheet row of the appended entry. |
| `entry` | TimeEntry | The values written. |
| `written_at` | ISO-8601 UTC | When written. |
| `expires_at` | ISO-8601 UTC | `written_at` + TTL. |

**Correction resolution (F4).** `--correct` / `--delete-last` target the
most-recent ledger entry. If a **newer** write exists after the entry a
correction would naturally target, or the ledger state is **stale** (target
expired / empty), the helper returns `correction_ambiguous` (`reason:
newer_write`\|`stale`) rather than mutating the wrong row; an empty ledger →
`no_last_write`.

## Entity: WorkbookConfig (uncommitted)

`~/.config/felix/timelog/workbook.json` — `{ "spreadsheet_id": "<id>" }`, recorded
at the one-time bootstrap. Never committed (like the calendar creds).

## Failure → Alert (#701)

A `status: error` or `status: client_created_entry_failed` (Sheets/auth failure,
including the partial-mutation case of F3) renders to a `scripts.common.alert_bus`
`Alert` (severity `error`, title `Time-log write failed`, detail redaction-
consistent) so a silent write failure is visible (NFR-003). The clarification /
dialog statuses (`unknown_client`, `need_field`, `ambiguous`, `not_timelog`,
`no_pending`, `stale_pending`, `no_last_write`, `correction_ambiguous`) are NOT
alerts — they are the normal dialog.
