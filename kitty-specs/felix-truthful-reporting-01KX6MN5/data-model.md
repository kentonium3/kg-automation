# Data Model: Felix Truthful Reporting Guardrails

**Mission**: felix-truthful-reporting-01KX6MN5
**Phase**: 1 (Design)

All structures are file-backed (committed baseline + append-only JSONL) or
in-memory value objects. No database.

---

## Entity: ApprovedCron (baseline entry)

The committed allowlist of legitimate crons. Home:
`docs/design/architecture/data/approved-crons.json` (canonical operational-state
JSON per repo convention). Validated by the architecture-data validator if in
scope; at minimum schema-checked by the detector.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Cron name as OpenClaw reports it (e.g., `inbox-5pm`). Primary match key. |
| `agent_id` | string | Owning agent (e.g., `felix-admin-capture`). |
| `schedule_expr` | string | Cron expression (e.g., `0 17 * * *`) + tz where applicable. |
| `purpose` | string | Human note: why this cron is approved. |
| `approved_by` | string | `kent` — provenance. |
| `approved_at` | string (date) | When added to baseline. |

**Invariants**:
- `name` unique within the baseline.
- Adding/removing a legitimate cron edits this file in the same change that
  creates/removes the cron (keeps reality == baseline).

## Entity: LiveCron (observed)

Parsed from `openclaw cron list --json` → `.jobs[]`. Fields used:
`id`, `name`, `enabled`, `agentId`, `schedule.expr`, `createdAtMs`. The detector
treats `name` (+ `agentId`) as the identity for baseline matching; `id`,
`createdAtMs` are carried into the alert for forensics.

### Cron match & diff semantics (Codex finding 4)

- **Match key**: `(name, agent_id)`. A live cron whose `(name, agent_id)` is not
  in the baseline is `unapproved_present` — this also covers the *owner-mismatch*
  case (an approved `name` running under a different `agent_id` is treated as
  unapproved, which is the incident-relevant signal).
- **Diff dimensions** for a matched pair: `schedule.expr`, `schedule.tz`,
  `enabled`.
- A baseline entry with no live match → `approved_missing`.

## Entity: CronDriftFinding

Produced by the drift detector.

| Field | Type | Notes |
|-------|------|-------|
| `kind` | enum | `unapproved_present` \| `approved_missing` \| `schedule_mismatch` \| `enabled_mismatch` |
| `name` | string | Cron name. |
| `agent_id` | string | Owning agent (observed or expected). |
| `cron_id` | string | OpenClaw id (when a live cron is involved). |
| `schedule_expr` | string | Observed schedule (+ `tz`). |
| `expected_schedule_expr` | string | Baseline schedule (for `schedule_mismatch`). |
| `enabled` | bool | Observed enabled state (for `enabled_mismatch`). |
| `created_at_ms` | int | For `unapproved_present` — when it appeared. |

- `unapproved_present` → **error** (the incident class: standing infra nobody
  approved; includes owner-mismatch).
- `approved_missing` → **warn** (a legitimate cron vanished — breakage, not
  fabrication).
- `schedule_mismatch` → **warn** (approved cron running on a different schedule
  than the baseline records — could be an unrequested edit).
- `enabled_mismatch` → **warn** (an approved cron unexpectedly disabled).

## Entity: CompletionAssertion (append-only JSONL record)

**Auto-emitted by the artifact-creation helper on successful creation** (Codex
finding 2) — e.g. `scripts/vikunja/create_task.py` writes one on success; an
agent writes one manually only when it bypasses a wrapped helper. One JSON
object per line. Home: an append-only JSONL under the agent-logs substrate or
`/data/services/trust/assertions/<date>.jsonl` (finalized in quickstart).
`fcntl.LOCK_EX` atomic append (the #706 pattern).

| Field | Type | Notes |
|-------|------|-------|
| `ts` | string (ISO-8601 UTC) | When the assertion was recorded. |
| `agent` | string | Asserting/creating agent (e.g., `main`), when known. |
| `request_summary` | string | Short paraphrase of what was asked for (optional). |
| `request_ref` | string \| null | Correlation ref (conversation/request id) **when available** — null today (no outbound-message log); FR-004 v1 is an artifact-grounding record, not a full request↔outcome pairing (Codex finding 3). |
| `artifact_kind` | enum | `vikunja_task` \| `calendar_event` \| `vault_note` \| `other` |
| `artifact_ids` | list[string] | **One or more** verifiable ids (Codex finding 7 — the 7-task case). Each verified independently. |
| `claim` | string | The completion claim / summary (for the alert body). |

**Invariants**:
- An assertion for a create/do completion MUST carry a non-empty `artifact_kind`
  + non-empty `artifact_ids` unless `artifact_kind == other` (verifier →
  `unverifiable_kind` warn).
- Records are never mutated or deleted by the verifier (append-only; retention
  like the #706 ledger, e.g., 30 days).

## Entity: AssertionFinding

Produced by the verifier.

| Field | Type | Notes |
|-------|------|-------|
| `kind` | enum | `artifact_missing` \| `unverifiable_kind` |
| `agent` | string | Asserting agent. |
| `artifact_kind` | string | From the assertion. |
| `artifact_id` | string | From the assertion. |
| `claim` | string | Carried into the alert. |

- `artifact_missing` (asserted `vikunja_task` id not found via API) → **error**.
- `unverifiable_kind` (`other`, or a kind with no existence check) → **warn**.

## Mapping: Finding → Alert (#701 bus)

Findings are rendered into the shared `Alert` value object
(`scripts/common/alert_bus/model.py`) and emitted through the bus:

| Finding | Severity | Alert title | Detail carries |
|---------|----------|-------------|----------------|
| `unapproved_present` | `error` | `Unrequested cron detected: <name>` | agent_id, cron_id, schedule, created_at |
| `approved_missing` | `warn` | `Approved cron missing: <name>` | expected schedule |
| `schedule_mismatch` | `warn` | `Approved cron schedule changed: <name>` | observed vs expected schedule |
| `enabled_mismatch` | `warn` | `Approved cron disabled: <name>` | agent_id |
| `artifact_missing` | `error` | `Completion claim not grounded: <artifact_kind>` | agent, artifact_id, claim |
| `unverifiable_kind` | `warn` | `Completion claim unverifiable: <artifact_kind>` | agent, claim |
| `drift_resolved` | `info` | `Cron drift cleared: <name>` | first_seen, cleared_at |

Redaction follows the bus's existing render rules (#701/#706): title + action
verbatim; description/details redaction-consistent.

## State & idempotency

- The scan is **stateless per tick** for the raw diff (baseline vs live is a
  pure comparison).
- **Seen-findings state** (Codex finding 6): the runner keeps a small state file
  mapping `finding_fingerprint → {first_seen, last_seen, last_alerted}`. Alert
  cadence:
  - **first observation** → alert immediately;
  - while the finding persists → **re-alert every 24h** (so persistent
    unapproved infra is not silently hidden after the first alert);
  - when a previously-seen finding **disappears** → emit a low-priority
    `drift_resolved` (`info`) event and drop it from state.
  - `first_seen`/`last_seen` are carried into alert detail.
- **Baseline-versioned fingerprints** (Codex finding 5): the finding fingerprint
  includes a hash/version of the approved-cron baseline, so a baseline update
  re-evaluates findings rather than letting stale seen-state suppress a
  now-legitimate (or newly-illegitimate) cron. **Baseline-deploy ordering rule:**
  the committed approved-cron baseline must land on office2 **before or together
  with** the legitimate cron it authorizes, to avoid a transient false-positive
  alert (documented in quickstart).
- Assertion verification advances a **watermark** (last-verified line offset per
  file) so each assertion is verified once. Atomic write.

## Fail-safe (NFR-001) & exit-code discipline (Codex finding 8)

Any exception in load/enumerate/verify/emit is caught, logged, and the tick
returns cleanly — a detector fault degrades to *no alert*, never to a broken
agent or a crash loop. (The agents themselves never call the detector inline;
it is an out-of-band timer.)

**Two run modes with distinct exit-code contracts:**
- **Timer mode** (the systemd `felix-trust-scan.service` target): **always
  exits 0**, reporting fault via `ok:false` + `errors[]` in JSON/logs — so a
  transient fault (e.g., OpenClaw CLI hiccup) does not put the systemd unit into
  a `failed` state or a restart loop.
- **Preflight / explicit-CLI mode** (`--once` / deploy self-test / manual run):
  **may exit 2** when the scan itself could not run (e.g., unreadable baseline),
  so an operator or the deploy entrypoint gets a hard signal. The deploy
  self-test uses this mode.

Finding drift is **never** a non-zero exit in either mode — drift is expected
signal, not a failure.
