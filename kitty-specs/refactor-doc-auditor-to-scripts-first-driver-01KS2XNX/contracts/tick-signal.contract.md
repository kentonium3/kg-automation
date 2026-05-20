# Contract: Tick Signal artifact

**Mission**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Realizes**: spec FR-007, NFR-002, NFR-004; data-model E-009
**Consumers**: operators (via `cat`/`jq`); future #327 `felix-alert` substrate

The driver writes this artifact at the END of every tick (success or failure paths), and on every entrypoint exit (including unhandled-exception via `try/finally`). The artifact is the load-bearing observation surface for reliability.

## Location

```
/data/services/openclaw/felix-doc-auditor-driver/last-tick.json
```

Parent dir created by deploy script if absent. Owner: `claude:claude`. Mode `0644`.

## Write semantics

- **Atomic**: write to `last-tick.json.tmp`, then `os.rename()`. No reader ever sees a partial write.
- **Current-state, not append-only**: each tick overwrites. History lives in the systemd journal + activity log.
- **Always written**: even when the driver crashes early; the `finally` block writes a `status: failure` artifact with whatever fields could be populated.

## Schema (v1.0)

```json
{
  "schema_version": "1.0",
  "timestamp_utc": "2026-05-20T16:00:00Z",
  "status": "success",
  "exit_code": 0,
  "driver_version": "0.1.0",
  "duration_seconds": 7.3,
  "host": "office2",
  "tick": {
    "signals_seen": 2,
    "signals_processed": 2,
    "audits_processed": [320, 321],
    "pending_approvals_applied": [],
    "pending_approvals_filed": [],
    "tier_a_commits": ["abc1234"],
    "debt_filed": [340],
    "drift_events_consumed": 0
  },
  "judgment": {
    "tier_classification_calls": 3,
    "debt_body_generation_calls": 1,
    "cross_file_implication_calls": 0,
    "input_tokens": 6420,
    "cache_hit_input_tokens": 4180,
    "output_tokens": 540
  },
  "errors": [],
  "next_scheduled_tick_utc": "2026-05-20T17:00:00Z"
}
```

## Field constraints

| Field | Type | Constraint |
|---|---|---|
| `schema_version` | str | Always `"1.0"` for this contract. Bump on breaking schema change. |
| `timestamp_utc` | str | ISO-8601 with `Z` suffix. The tick end time. |
| `status` | str | One of `success` (exit 0, no errors), `partial` (exit 2, some signals processed but some errors), `failure` (exit 1, unrecoverable). |
| `exit_code` | int | 0, 1, or 2. Matches the process exit code. |
| `driver_version` | str | Semver. Bumped per release. |
| `duration_seconds` | float | Wall-clock from process start to artifact write. |
| `host` | str | The host the driver ran on. Currently always `"office2"`. |
| `tick.signals_seen` | int | Count of `Signal` objects enumerated this tick across all adapters. |
| `tick.signals_processed` | int | Count of `Signal` objects whose processing completed (closed audit, applied decision, etc.). |
| `tick.audits_processed` | list[int] | GitHub issue numbers of audit issues touched. |
| `tick.pending_approvals_applied` | list[int] | Issue numbers of pending-approval issues whose decision was applied this tick. |
| `tick.pending_approvals_filed` | list[int] | Issue numbers of NEW pending-approval issues filed this tick. |
| `tick.tier_a_commits` | list[str] | Short git SHAs of Tier-A auto-commits this tick. |
| `tick.debt_filed` | list[int] | Issue numbers of new docs-debt issues filed. |
| `tick.drift_events_consumed` | int | Count of drift events processed (cursor delta). |
| `judgment.tier_classification_calls` | int | LLM-call count for `tier_classification`. |
| `judgment.debt_body_generation_calls` | int | LLM-call count for `debt_body_generation`. |
| `judgment.cross_file_implication_calls` | int | LLM-call count for `cross_file_implication`. |
| `judgment.input_tokens` | int | Sum of input tokens across all LLM calls this tick. |
| `judgment.cache_hit_input_tokens` | int | Subset of input_tokens that were cache hits (≤ input_tokens). |
| `judgment.output_tokens` | int | Sum of output tokens across all LLM calls this tick. |
| `errors` | list[str] | Human-readable error strings. Empty list on success. |
| `next_scheduled_tick_utc` | str | ISO-8601. Computed from systemd timer schedule. |

## Stdout-summary line (companion)

Last stdout line of each tick (for systemd journal greppability):

```
SUMMARY: status=success audits=2 debt=1 tier_a=1 drift=0 dur=7.3s tokens=in:6420(cache:4180)/out:540
```

Format is deterministic; consumers MAY parse it for at-a-glance health. The JSON artifact is the canonical, machine-readable surface; the SUMMARY line is human-readable convenience.

## Consumer expectations

- **Operators**: `cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq` for current health. Per FR-001/SC-002, the artifact must answer "is the auditor healthy?" in under 30 seconds without parsing LLM prose.
- **#327 `felix-alert`** (future): polls or watches the artifact; alerts when `status != success` or `timestamp_utc` is older than 2 ticks' worth (per NFR-002).
- **NFR-001 measurement**: `judgment.input_tokens + output_tokens` summed across representative ticks → cost figure.

## Versioning

- Backward-compatible additions (new fields): no schema_version bump.
- Removals, type changes, renames: bump `schema_version` major.
- Consumers MUST tolerate unknown fields (forward-compat).

## Failure modes

| Scenario | Artifact state |
|---|---|
| Driver exits 0 with no work done | `status: success`, `tick.signals_seen: 0`, `tick.signals_processed: 0` |
| Driver exits 2 (partial — some signals processed, some failed) | `status: partial`, `errors: [...]`, partial counts |
| Driver exits 1 (unrecoverable error) | `status: failure`, `errors: [...]`, counts as far as got |
| Driver crashes mid-tick | `finally` block writes `status: failure` with best-effort counts |
| Driver cannot write the artifact at all | Reflected in absent / stale artifact + non-zero systemd exit code; alerting consumer must watch for timestamp staleness, not just file presence |
