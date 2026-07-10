# Data Model: Unified Alert Bus

The bus is stateless; these are in-memory value objects plus the fixed severity mapping.

## Entity: `Alert`

The uniform alert value object every emitter constructs. Fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | str | yes | Component + specific function/phase issuing the alert, e.g. `"felix-deployer/apply"`. |
| `severity` | `Severity` | yes | One of `info`/`warn`/`error`/`critical`. Drives priority + tags. |
| `title` | str | yes | Short human-readable error title, e.g. `"felix-deployer failed: felix-calendar-helper"`. |
| `description` | str | yes | Plain-language account of what happened (no bare phase codes). |
| `action` | str \| None | no | The operator's next step / recovery command, when known. |
| `details` | dict[str, str] | no | Structured extras: ids, paths, exit codes, and — for failures — the **actual error/stderr** (FR-003). |
| `timestamp` | datetime | auto | Set at construction if not supplied; rendered as UTC + local. |

**Invariants**
- `source`, `severity`, `title`, `description` are always present and non-empty (a malformed Alert is a
  programming error, caught by the constructor).
- A missing optional field (`action`, empty `details`) still yields a deliverable, readable message
  (NFR-003) — rendering omits absent sections rather than emitting placeholders.
- `details` values are redacted (secrets) before truncation during rendering (D8).

## Enum: `Severity`

`info` < `warn` < `error` < `critical` (ordered).

## Severity map

The single source of truth mapping severity → ntfy `Priority` header + `Tags` header. Monotonic
priority gradient so criticality is visually distinct on one thread (FR-004).

| Severity | ntfy Priority | ntfy Tags | Intended use |
|---|---|---|---|
| `info` | `low` (2) | `information_source` | FYI / successful-but-notable events |
| `warn` | `default` (3) | `warning` | Degraded but not failing; attention soon |
| `error` | `high` (4) | `rotating_light` | A component operation failed (most migrated alerts) |
| `critical` | `max` (5) | `rotating_light,sos` | Urgent — needs immediate operator action |

Notes:
- ntfy priority accepts the names above (or 1–5). The bus emits the numeric or named value in the
  `Priority` header; tags are comma-separated shortcodes in the `Tags` header (as today's emitters do).
- Existing emitters hardcode "high" today; at migration each call site chooses the severity that fits
  (deployer failure → `error`; unexpected-drift/critical-gate → `critical`; security summary → `warn`
  or `error` by alert count; health-check failure → `error`).

## Value object: `AlertResult`

Returned by `emit()`; the fail-safe contract (D7).

| Field | Type | Notes |
|---|---|---|
| `ok` | bool | True iff the ntfy POST succeeded (curl rc == 0). |
| `reason` | str \| None | Failure reason when `ok` is False (e.g. `NTFY_MISSING_TOPIC`, `CURL_TIMEOUT`, `CURL_CONNECT`). |
| `topic_configured` | bool | False when `FELIX_ALERT_NTFY_TOPIC` is unset/blank. |

`emit()` never raises; callers inspect `AlertResult`.

## Configuration

| Key | Where | Notes |
|---|---|---|
| `FELIX_ALERT_NTFY_TOPIC` | env-file `/home/claude/.config/felix/alert-bus/env` (out-of-band; in `credential-manifest.json`) | The single canonical topic id (secret, high-entropy). Only the bus reads it. |
| ntfy base URL | constant in `delivery.py` (default `https://ntfy.sh`) | Matches existing emitters. |
