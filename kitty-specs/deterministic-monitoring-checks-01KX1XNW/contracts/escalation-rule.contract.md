# Contract: Deterministic Escalation Rule

**Function**: `decide_deterministic(context: GateContext) -> GateDecision`
**Replaces**: `gate.decide(context, api_key_path=…, prompt_path=…)` (the Haiku call)

## Escalation truth table (the load-bearing contract)

`ESCALATE_TO_SONNET` if and only if ANY row's condition holds:

| Trigger | Condition |
|---|---|
| Novelty | `len(context.novelty_markers) > 0` |
| Operator contract | `context.heartbeat_md_state == "has_tasks"` |
| Tick error | `len(context.errors) > 0` |

Otherwise **no escalation** (Sonnet is NOT woken), sub-labeled:

| Outcome | Condition |
|---|---|
| `LOG_AND_SKIP` | not escalating AND (`len(context.issues_filed) > 0` OR any evaluated signal has non-zero cycle activity while `threshold_status == "below"`) |
| `HEARTBEAT_OK` | not escalating AND nothing notable |

## Output invariants

- `input_tokens == cache_hit_tokens == output_tokens == 0` (NFR-001).
- `outcome ∈ {HEARTBEAT_OK, LOG_AND_SKIP, ESCALATE_TO_SONNET}`.
- On `ESCALATE_TO_SONNET`: `reason` is non-empty, ≤500 chars, cites each firing
  trigger (novelty marker IDs / "heartbeat contract has tasks" / error types).
- The function is pure and total: it never performs I/O, never imports `anthropic`,
  never raises on a well-formed `GateContext`.

## Historical-fidelity invariant (INV-006)

For every record `r` in a gate-ledger.jsonl:

```
escalate(r.novelty_markers_seen, r.heartbeat_md_state, r.errors)
    == (r.outcome == "ESCALATE_TO_SONNET")
```

**Acceptance**: 0 missed escalations across the full history; over-escalation ≤ 5%.
**Measured at design time**: 0 missed / 0 over on 1748 ticks (2026-06-01 → 2026-07-08).

## Orchestration invariants (unchanged behavior)

- Step 1 (`context.load_context`), step 3 (`escalator.escalate`), step 4
  (`ledger.write_tick_record`) behave exactly as before.
- Fail-safe: any exception in step 1 or step 2 ⇒ `ESCALATE_TO_SONNET` +
  `fallback_invoked=true` + escalate fired + tokens 0 + exit 0.
- On `ESCALATE_TO_SONNET` (non-fallback), `escalator.escalate(decision.reason)` fires
  `openclaw system event --mode now`.
