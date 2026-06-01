# Contract: `last-gate-decision.json` (heartbeat gate tick)

**Path**: `/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json`
**Format**: JSON, single document, overwritten atomically each tick.
**Producer**: `scripts/openclaw/heartbeat_gate/gate.py`
**Consumer**: operator (manual `cat | jq`), `openclaw system heartbeat last` integration if available.

## Schema

```json
{
  "schema_version": 1,
  "tick_id": "01J6XYZAB1234567890XYZABCD",
  "started_at_utc": "2026-06-01T17:30:00Z",
  "gate_latency_ms": 1240,
  "digest_snapshot_at_utc": "2026-06-01T17:15:00Z",
  "heartbeat_md_state": "empty",
  "novelty_markers_seen": ["whatsapp_creds_restore"],
  "outcome": "ESCALATE_TO_SONNET",
  "reason": "Signal whatsapp_creds_restore tripped both cycle and rolling thresholds in last tick (12 / 35). Filed issue #491. Escalating to Sonnet to assess whether an additional action (e.g., WhatsApp alert to Kent) is warranted given the ongoing pattern.",
  "escalated_event_id": "evt_01J6XYZAB1234567890EVT",
  "gate_input_tokens": 1820,
  "gate_cache_hit_tokens": 1450,
  "gate_output_tokens": 180,
  "fallback_invoked": false,
  "errors": []
}
```

## Field definitions

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Bump on breaking schema change. Currently 1. |
| `tick_id` | str (ULID) | Unique per tick. |
| `started_at_utc` | str (ISO 8601, UTC, trailing Z) | Tick start. |
| `gate_latency_ms` | int | Wall-clock from tick start to outcome decision (excludes Sonnet escalation work). |
| `digest_snapshot_at_utc` | str (ISO 8601) | Timestamp of the signal-extraction tick the gate consumed. |
| `heartbeat_md_state` | enum `{"empty", "has_tasks"}` | `empty` = template content only OR missing. `has_tasks` = at least one actionable line. |
| `novelty_markers_seen` | list[str] | Signal IDs from the most-recent signal-extraction tick whose `threshold_status != "below"`. |
| `outcome` | enum `{"HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"}` | The gate's decision. |
| `reason` | str (≤500 chars) | Required for ESCALATE; recommended (but optional) for OK/SKIP. |
| `escalated_event_id` | str \| null | OpenClaw event id from `openclaw system event --mode now --json`, if outcome is ESCALATE. |
| `gate_input_tokens` | int | Tokens billed to Haiku (0 if fallback or no API call). |
| `gate_cache_hit_tokens` | int | Cache-hit tokens within `gate_input_tokens` (billed at 10%). |
| `gate_output_tokens` | int | Output tokens from Haiku. |
| `fallback_invoked` | bool | `true` if the gate hit an error and fell back to invoking the expensive-tier path directly per FR-011. |
| `errors` | list[`{error_type, error_message}`] | Per-tick errors. Empty list = clean. |

## Outcome semantics

| Outcome | Effect |
|---|---|
| `HEARTBEAT_OK` | Nothing further happens. Sonnet is NOT invoked. Record-only. |
| `LOG_AND_SKIP` | Same as `HEARTBEAT_OK` in effect, but the gate explicitly flagged the digest as "looked unusual but not worth escalating." Operator may notice in the ledger. |
| `ESCALATE_TO_SONNET` | Gate invokes `openclaw system event --mode now --text "<reason>"` to wake the `main` agent with the reason as context. Sonnet path runs unchanged from today. |

## Fallback behavior (FR-011)

If the Haiku gate fails for any reason (Anthropic API error, malformed response, gate process crash before write):
- Gate writes a partial `last-gate-decision.json` with `outcome = "ESCALATE_TO_SONNET"`, `fallback_invoked = true`, and the error in `errors[]`.
- Gate still invokes `openclaw system event --mode now --text "Gate fallback — see ledger"` so observation is not lost.
- Operator alert path (future): a `fallback_invoked = true` tick is itself a signal worth surfacing.

## Health-check contract

A healthy gate tick has:
- `errors == []`
- `started_at_utc` within the last ~35 minutes (30 min cadence + slack)
- `fallback_invoked == false` (sustained `true` rate indicates gate-side problem)

## Atomicity

Written via `<path>.tmp` + `os.rename(tmp, final)`. Same convention as the signal-extraction tick file.
