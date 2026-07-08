# Data Model: Deterministic Monitoring Checks

**Mission**: deterministic-monitoring-checks-01KX1XNW

This mission changes *behavior*, not data shapes — the existing structs are reused.
The one genuinely new element is the pure decision function and the health-check
result classification.

## Existing entities (reused unchanged)

### GateContext (`context.py`) — INPUT, unchanged
Deterministically assembled per tick. The sole input to the new rule.

| Field | Type | Role in the rule |
|---|---|---|
| `tick_id` | str | identity |
| `digest_snapshot_at_utc` | str | provenance (ledger) |
| `signals_evaluated` | list[dict] | source of `novelty_markers`; non-zero-but-below activity → `LOG_AND_SKIP` |
| `issues_filed` | list[dict] | non-empty → `LOG_AND_SKIP` (not an escalation trigger) |
| `errors` | list[dict] | **non-empty → ESCALATE** |
| `heartbeat_md_state` | `"empty"` \| `"has_tasks"` | **`has_tasks` → ESCALATE** |
| `novelty_markers` | list[str] | **non-empty → ESCALATE** |

### GateDecision (`gate.py`) — OUTPUT, shape unchanged
Produced now by `decide_deterministic`. Token fields are always `0`.

| Field | Type | Value on deterministic path |
|---|---|---|
| `outcome` | `HEARTBEAT_OK` \| `LOG_AND_SKIP` \| `ESCALATE_TO_SONNET` | per the rule |
| `reason` | str (≤500) | deterministic template citing triggers |
| `input_tokens` / `cache_hit_tokens` / `output_tokens` | int | **0** |

### GateTickRecord (`ledger.py`) — LEDGER, unchanged
Written by step 4 every tick. Carries `novelty_markers_seen`, `heartbeat_md_state`,
`errors`, `outcome`, `fallback_invoked`, zeroed `gate_*_tokens`. Also the historical
corpus for INV-006 (the escalation-relevant fields are all persisted here).

## New logical element — the escalation rule (pure function)

```
decide_deterministic(context: GateContext) -> GateDecision

escalate := (len(context.novelty_markers) > 0)
            or (context.heartbeat_md_state == "has_tasks")
            or (len(context.errors) > 0)

if escalate:
    outcome = "ESCALATE_TO_SONNET"
    reason  = build_reason(context)          # deterministic, ≤500 chars
else:
    notable := (len(context.issues_filed) > 0) or any_nonzero_below_activity(context)
    outcome = "LOG_AND_SKIP" if notable else "HEARTBEAT_OK"
    reason  = short factual note (optional for HEARTBEAT_OK)

tokens (input/cache/output) = 0
```

**Invariant (INV-006)**: for every historical ledger record, `escalate ==
(record.outcome == "ESCALATE_TO_SONNET")`. Verified: 0 missed / 0 over on 1748 ticks.

**State transitions**: none — the function is stateless and pure. The orchestrator's
step 3 (escalate) and step 4 (ledger) are unchanged; only step 2's producer changes.

## New entity — HealthCheckResult (logical, in the wrapper)

The health-check wrapper classifies the bash script's stdout:

| Field | Type | Source |
|---|---|---|
| `status` | `ALL_HEALTHY` \| `FAILURES_DETECTED` \| `UNKNOWN` | grep of `health-check.sh` stdout |
| `raw_output` | str | full stdout/stderr |
| `ran_at_utc` | str | wrapper clock |

**Behavior**:
- `ALL_HEALTHY` → stamp a signal/state file (observability), no alert (matches
  today's `delivery.mode: none`).
- `FAILURES_DETECTED` (or `UNKNOWN` / non-zero exit) → push `raw_output` to ntfy.
- Exit 0 on a completed run regardless of health status (the *check ran* — a health
  failure is data, not a runner error); non-zero only if the wrapper itself fails.

## Fail-safe (preserved, unchanged)

Any exception in `run_tick` steps 1–2 → `outcome=ESCALATE_TO_SONNET`,
`fallback_invoked=true`, error captured, tokens 0, escalate fired. The new
deterministic decide raises nothing on valid input; malformed context still routes
through the existing fail-safe.
