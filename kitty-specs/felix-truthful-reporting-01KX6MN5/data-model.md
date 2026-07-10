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

## Entity: CronDriftFinding

Produced by the drift detector.

| Field | Type | Notes |
|-------|------|-------|
| `kind` | enum | `unapproved_present` \| `approved_missing` |
| `name` | string | Cron name. |
| `agent_id` | string | Owning agent (for `unapproved_present`). |
| `cron_id` | string | OpenClaw id (for `unapproved_present`). |
| `schedule_expr` | string | Observed schedule. |
| `created_at_ms` | int | For `unapproved_present` — when it appeared. |

- `unapproved_present` → **error** severity (the incident class: standing infra
  nobody approved).
- `approved_missing` → **warn** severity (a legitimate cron vanished — could be
  breakage, not fabrication).

## Entity: CompletionAssertion (append-only JSONL record)

Emitted by an agent (via a helper) when it reports a delegated create/do request
as complete. One JSON object per line. Home: an append-only JSONL under the
agent-logs substrate or `/data/services/trust/assertions/<date>.jsonl`
(finalized in quickstart). `fcntl.LOCK_EX` atomic append (the #706 pattern).

| Field | Type | Notes |
|-------|------|-------|
| `ts` | string (ISO-8601 UTC) | When the assertion was recorded. |
| `agent` | string | Asserting agent (e.g., `main`). |
| `request_summary` | string | Short paraphrase of what Kent asked for. |
| `artifact_kind` | enum | `vikunja_task` \| `calendar_event` \| `vault_note` \| `other` |
| `artifact_id` | string | The verifiable id/handle (e.g., Vikunja task `id`). |
| `claim` | string | The completion claim made to Kent (for the alert body). |

**Invariants**:
- An assertion for a delegated create/do completion MUST carry a non-empty
  `artifact_kind` + `artifact_id` unless `artifact_kind == other` (which the
  verifier flags as unverifiable → warn).
- Records are never mutated or deleted by the verifier (append-only; retention
  handled like the #706 ledger, e.g., 30 days).

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
| `artifact_missing` | `error` | `Completion claim not grounded: <artifact_kind>` | agent, artifact_id, claim |
| `unverifiable_kind` | `warn` | `Completion claim unverifiable: <artifact_kind>` | agent, claim |

Redaction follows the bus's existing render rules (#701/#706): title + action
verbatim; description/details redaction-consistent.

## State & idempotency

- The scan is **stateless per tick** for drift (baseline vs live is a pure diff).
- To avoid re-alerting every tick on the same standing drift, the runner keeps a
  small **seen-findings** state file (finding fingerprint → first-seen ts) and
  only emits on first observation (or re-emits on a configurable interval). This
  mirrors the "no silent caps / no alert storms" discipline. Atomic write.
- Assertion verification advances a **watermark** (last-verified line offset per
  file) so each assertion is verified once. Atomic write.

## Fail-safe (NFR-001)

Any exception in load/enumerate/verify/emit is caught, logged, and the tick
returns cleanly — a detector fault degrades to *no alert*, never to a broken
agent or a crash loop. (The agents themselves never call the detector inline;
it is an out-of-band timer.)
