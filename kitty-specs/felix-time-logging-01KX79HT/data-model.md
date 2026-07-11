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

Row column order in the tab: `date | hours | client | description | billable` (+ `logged_at` as a trailing column).

## Entity: TimelogResult (typed helper → main signal)

The single value the `timelog` CLI returns to `main`. `status` drives main's dialog.

| `status` | Meaning | Carries |
|----------|---------|---------|
| `logged` | Row written + confirmed by the API. | `tab`, `row` (the TimeEntry), `receipt` (the exact confirmation string). |
| `unknown_client` | No tab matched. | `heard` (spoken name), `closest` (best tab candidate, if any). NO write. |
| `need_field` | A required field is missing. | `missing` (`hours`\|`description`\|`client`), `partial` (what parsed). NO write. |
| `ambiguous` | Multiple plausible clients/interpretations. | `candidates`. NO write. |
| `error` | Sheets API / auth failure. | `detail`. NO partial write. Alerts via #701. |

**Invariant (NFR-002/#683):** `logged` is returned **only after** the Sheets
append is confirmed by the API response. Every other status means **nothing was
written**, and main must reflect that truthfully.

## Entity: ClientAliases (committed config)

`docs/design/architecture/data/timelog-clients.json` — `{ canonical: [aliases...] }`.
Resolution: normalize the spoken name (lowercase, trim) → exact tab-title match →
alias match → else `unknown_client`. **Tabs are the source of truth** (read via
`list-tabs`); aliases only bridge fuzzy spoken names.

## Entity: PendingTimelog (state)

`/data/services/timelog/state/pending-<account>.json` — the in-flight entry
awaiting a clarification reply (unknown-client / missing-field / new-client),
so a follow-up resumes deterministically. Cleared on resolution or timeout.

| Field | Type | Notes |
|-------|------|-------|
| `partial` | TimeEntry (partial) | Fields parsed so far. |
| `awaiting` | enum | `client` \| `field:<name>` \| `new_client_confirm`. |
| `ts` | ISO-8601 UTC | For staleness. |

## Entity: LastWrite (state)

`/data/services/timelog/state/last-write-<account>.json` — the most-recent append,
so "make that 3h" / "delete that last one" (FR-006) resolve to a concrete row.

| Field | Type | Notes |
|-------|------|-------|
| `tab` | string | Client tab. |
| `row_index` | int | 1-based sheet row of the appended entry. |
| `entry` | TimeEntry | The values written. |
| `ts` | ISO-8601 UTC | When written. |

## Entity: WorkbookConfig (uncommitted)

`~/.config/felix/timelog/workbook.json` — `{ "spreadsheet_id": "<id>" }`, recorded
at the one-time bootstrap. Never committed (like the calendar creds).

## Failure → Alert (#701)

A `status: error` (Sheets/auth failure) renders to a `scripts.common.alert_bus`
`Alert` (severity `error`, title `Time-log write failed`, detail redaction-
consistent) so a silent write failure is visible (NFR-003). A `need_clarification`
signal is NOT an alert (it is the normal dialog).
