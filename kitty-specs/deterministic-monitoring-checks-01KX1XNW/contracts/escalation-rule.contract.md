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
  trigger (novelty marker IDs / "heartbeat contract has tasks" / error types), and
  contains **no action/recommendation framing** (no "so Sonnet can…"/"should" —
  Codex #8). It reports triggers, it does not prescribe.
- The function is pure: it never performs I/O and never imports `anthropic`.

## Totality invariant (Codex finding #2 — load-bearing)

`decide_deterministic` MUST be **total over every `GateContext` that
`context.load_context` can produce** — it must NOT raise `TypeError`/`ValueError`/etc.
on malformed-but-loaded data (e.g. a `signals_evaluated` entry missing a field, a
non-list `errors`). Rationale: `run.py` step 2 currently catches only
`GateRoutingError` + `FileNotFoundError` [run.py:204]; an uncaught exception escapes to
the emergency path (exit 1, minimal fallback), which CONTRADICTS the spec's
"step 1/2 failure → `fallback_invoked=true`, escalate, exit 0" (spec FR-007).

**Required in tasks — choose and implement:**
- (a) make `decide_deterministic` defensively total (coerce/guard all field access), AND/OR
- (b) broaden `run.py` step-2 `except` to catch `Exception` → the existing fallback path.

Ship a test with a malformed-but-loaded tick payload proving the fail-safe fires
(`fallback_invoked=true`, exit 0), not the emergency exit-1 path.

## Historical-fidelity invariant (INV-006)

For every record `r` in a gate-ledger.jsonl:

```
escalate(r.novelty_markers_seen, r.heartbeat_md_state, r.errors)
    == (r.outcome == "ESCALATE_TO_SONNET")
```

**Acceptance**: 0 missed escalations across the full history; over-escalation ≤ 5%.
**Measured at design time**: 0 missed / 0 over on 1748 ticks (2026-06-01 → 2026-07-08).

**Scope of the ledger replay (Codex #3/#4)**: the ledger persists only the
escalation-relevant fields (`novelty_markers_seen`, `heartbeat_md_state`, `errors`) —
NOT `issues_filed` or per-signal counts. So the live replay validates the **escalate
vs. not-escalate** boolean ONLY (the sole cost-bearing decision). The
`LOG_AND_SKIP` ↔ `HEARTBEAT_OK` sub-label split is NOT validated by the replay and the
plan must not claim it is; that split is verified separately via **synthetic
`GateContext` fixtures** in the unit tests (cases: `issues_filed != []` with empty
`novelty_markers` → `LOG_AND_SKIP`; non-zero-but-below signal activity → `LOG_AND_SKIP`;
fully quiet → `HEARTBEAT_OK`). Neither label affects whether Sonnet is woken.

## Orchestration invariants (unchanged behavior)

- Step 1 (`context.load_context`), step 3 (`escalator.escalate`), step 4
  (`ledger.write_tick_record`) behave exactly as before.
- Fail-safe: any exception in step 1 or step 2 ⇒ `ESCALATE_TO_SONNET` +
  `fallback_invoked=true` + escalate fired + tokens 0 + exit 0.
- On `ESCALATE_TO_SONNET` (non-fallback), `escalator.escalate(decision.reason)` fires
  `openclaw system event --mode now`.
