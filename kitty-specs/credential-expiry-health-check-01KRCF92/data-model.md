# Data Model — Credential Expiry Health Check

**Mission**: `credential-expiry-health-check-01KRCF92`
**Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md)

This system has **no persistent application state**. All state lives in three external systems read at runtime:

1. `credential-manifest.json` (read-only, the inputs)
2. The GitHub issue queue at `kentonium3/kg-automation` (the dedup-and-audit-trail surface)
3. The Vikunja task store on office2 (the action-driver surface)

The check is **stateless** between cycles — no on-disk state, no database. This is intentional and load-bearing for FR-007 (dedup-via-GitHub-state) and NFR-002 (deterministic replay).

---

## Entities

### `Credential` (read-only, from manifest)

**Shape**: one entry in `credentials[]` in `docs/design/architecture/data/credential-manifest.json`.

| Field | Type | Required for v1 | Meaning |
|---|---|---|---|
| `name` | string | yes | Stable identifier; used as the dedup key in GitHub issue titles. |
| `type` | string | no | Informational only (e.g., `api-token`, `oauth2`). |
| `scope` | string | no | Informational only; used in issue body context. |
| `storage` | string | yes | Where the credential lives; reproduced in issue body. |
| `host` | string | no | Informational. |
| `used_by` | string[] | no | Informational; used in issue body to remind Kent which agents/services depend on this credential. |
| `expiry_policy` | string | no | Cadence taxonomy bucket (`none`, `rolling`, `manual-rotation`, `system-managed`, `session`). Used together with `review_cadence` to pick the alert mode. |
| `review_cadence` | string | yes | Drives the check's behavior. Values: `annual` (fixed-interval), `monitor-activity`, `on-revocation`, `n/a`, `session`. |
| `last_reviewed` | ISO-8601 date | yes when `review_cadence` is a fixed interval | The anchor for cadence-boundary math. |
| `expiry_notes` | string | yes | Rotation procedure; reproduced verbatim in issue body. |
| `created_date` | ISO-8601 date | no | Used as an alternative anchor if `last_reviewed` is missing and the cadence is fixed-interval. |

**Validation** (FR-012):

A credential entry is **well-formed** for the check's purposes when:

- `name` is a non-empty string
- `review_cadence` is one of the documented values
- If `review_cadence` is a fixed interval (`annual` for v1; extensible), then `last_reviewed` (or fallback `created_date`) is a parseable ISO-8601 date

Entries failing validation are batched into a single per-cycle "manifest quality" issue (R-007) and skipped for cadence-based processing.

### `CadenceBoundary` (computed, not stored)

**Shape**: `(credential_name, boundary_date)`.

Computed at check time as:

| `review_cadence` | Boundary computation |
|---|---|
| `annual` | `last_reviewed + 365 days` (calendar arithmetic, ignores DST — Python `datetime.timedelta(days=365)`) |
| `monitor-activity` | N/A — uses the `ActivitySignal` path instead |
| `on-revocation` / `n/a` / `session` | N/A — never alerts |

The boundary is **never persisted**. It is recomputed every cycle. This is what makes the check stateless and replayable (NFR-002).

### `ActivitySignal` (read at runtime, from external tools)

**Shape**: per-credential.

For `monitor-activity` credentials in v1 (research §R-001):

| Credential | Signal source | Alert when |
|---|---|---|
| `tailscale-auth` | `tailscale status --json` | `BackendState != "Running"` |
| `whatsapp-session` | `openclaw channels status` (parsed) | `connected != true`, OR `running != true`, OR `linked != true`, OR `in:<duration> > 14 days`, OR `out:<duration> > 14 days` |

Activity signals do **not** participate in the "30 days before boundary" warning window — they trigger on the staleness threshold itself. The semantics are different (state observation vs. forecast), so the alert body distinguishes them.

### `PendingAlert` (state, lives in GitHub)

**Shape**: an open GitHub issue in `kentonium3/kg-automation` whose title starts with the stable prefix.

| Variant | Title prefix |
|---|---|
| Cadence-based alert | `Credential review: <name> due <YYYY-MM-DD>` |
| Activity-staleness alert | `Credential staleness: <name>` (no date — activity drift is not a forecast) |
| Manifest-quality batch | `Credential manifest quality: <N> entries with issues — <YYYY-MM-DD>` |

The set of open issues with these prefixes **is** the dedup state. The check queries this set at the start of each cycle.

### `VikunjaTask` (state, lives in Vikunja)

**Shape**: one task per cadence alert. Activity-staleness alerts do NOT create Vikunja tasks in v1 — they file a GitHub issue only. (Rationale: activity drift is a "go look at it now" signal, not a "in N days you need to rotate" signal. The escalation engine's due-date model doesn't fit activity drift.)

| Field | Value |
|---|---|
| `title` | `Rotate credential: <name>` |
| `due_date` | `boundary - 7 days` (cadence boundary minus one week) |
| `description` | Plain text with: link to the GitHub issue URL, restated rotation procedure summary, target rotation deadline (the boundary date). |
| Project | Vikunja `Inbox` project (default — see deferred decision D-001) |

### `CycleLog` (audit trail, lives in systemd journal)

**Shape**: structured log lines written by the check, captured by the systemd journal.

| Field | Type | Meaning |
|---|---|---|
| `timestamp` | ISO-8601 UTC | When the log line was emitted. |
| `cycle_id` | string | Per-cycle UUID; lets multiple log lines from one run be correlated. |
| `credential_name` | string \| null | Empty for cycle-level events (start/end, manifest read, errors). |
| `event` | enum | `cycle_start`, `manifest_read`, `credential_evaluated`, `alert_filed`, `alert_deduped`, `manifest_quality_filed`, `error`, `cycle_end`. |
| `details` | object | Event-specific structured payload (e.g., `{boundary: "2027-05-11", warning_window_days: 30, action: "filed"}`). |

Inspected via `journalctl --user -u credential-health-check --since today` (per R-002).

---

## State transitions

The system's behavioural state is fully captured by the GitHub issue set. Diagram:

```
   credential.review_cadence is fixed-interval
                   │
                   ▼
        ┌─────────────────────┐
        │  No open issue for  │
        │  this credential    │
        └──────────┬──────────┘
                   │
                   │ each cycle:
                   │ boundary − today <= 30 days?
                   │
        ┌──────────┴──────────┐
        │                     │
        │ no                  │ yes
        │ (within cadence)    │ (warning window)
        │                     │
        ▼                     ▼
   (no action)        ┌─────────────────────┐
                      │ File GitHub issue   │
                      │ + Vikunja task      │
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │ Open issue exists   │
                      │  (subsequent cycles │
                      │   detect dedup → no │
                      │   new artefacts)    │
                      └──────────┬──────────┘
                                 │
                                 │ Kent rotates credential,
                                 │ updates last_reviewed,
                                 │ closes issue + completes task
                                 │
                                 ▼
                       (no open issue;
                        next cycle recomputes
                        and finds within-cadence)
```

For `monitor-activity` credentials, the same model holds but the trigger is the activity-signal threshold instead of the boundary date, and no Vikunja task is created (one-way notification only).

---

## Why no internal datastore

Three converging reasons:

1. **NFR-002 (deterministic replay)** is much simpler when state lives outside the process. The check is a pure function of (manifest + GitHub state + Vikunja state + current date) → (set of new artefacts to file). No SQLite, no JSON state files, no race conditions across restarts.
2. **GitHub issue state IS the audit trail** that Kent already needs to consult during rotation work. Co-locating dedup state with audit trail eliminates a class of "agent thinks X is open but issue is actually closed" bugs.
3. **Crash resilience for free.** If the check crashes mid-cycle after filing the issue but before filing the task, the next cycle will see the open issue, dedup it, and not file a duplicate task. Some manual cleanup may be needed (an orphaned issue with no matching task) but the failure surface is bounded and visible.
