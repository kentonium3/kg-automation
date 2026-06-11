# Contract: Embedded Run Lifecycle (gateway-internal)

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Source of truth**: `/usr/lib/node_modules/openclaw/dist/{runs-*.js, diagnostic-run-activity-*.js, reply-run-registry-*.js}` on office2 (vendored, READ-ONLY per C-001)
**Why this contract exists**: the fix must not break the lifecycle invariant; the smoke test asserts against it.

## States

| State | Marker (in `Session.lastProgressReason`) | Setter |
|---|---|---|
| Run started | `embedded_run:started` | `markDiagnosticEmbeddedRunStarted(params)` — called by `setActiveEmbeddedRun` (runs-*.js:419) and `reply-run-registry`:68 |
| Tool call active | `tool.execution.started` → `tool.execution.completed` | dispatched via `onInternalDiagnosticEvent` listener |
| Model call active | `model.call.started` → `model.call.completed` | dispatched via `onInternalDiagnosticEvent` listener |
| Run completed | `embedded_run:ended` | `markDiagnosticEmbeddedRunEnded(params)` — called by `clearActiveEmbeddedRun` (runs-*.js:454) or `forceClearEmbeddedAgentRun` (runs-*.js:476) |

## Required transitions for a healthy DM-initiated run

1. `embedded_run:started` (within ≤2s of `[whatsapp] Inbound message`)
2. ≥1 `model.call.*` pair (model invocation; we observed agent text output, so this should happen)
3. **`embedded_run:ended`** ← currently MISSING for DM-initiated runs

## Failure mode signature (current bug)

- `embedded_run:started` fires
- NO `model.call.*` events are tracked as active (journal classifies `activeWorkKind=embedded_run`, not `model_call`)
- `embedded_run:ended` never fires
- After ≥378s (the gateway's `stuckSessionAbortMs` threshold), `forceClearEmbeddedAgentRun(..., reason="stuck_recovery")` fires
- Run is aborted; reply payload never reaches the channel-send subsystem

## Acceptance assertion (post-fix)

For every DM-initiated session within the smoke window:
- `embedded_run:ended` MUST fire via `clearActiveEmbeddedRun` (NOT `forceClearEmbeddedAgentRun`)
- `Session.state` MUST return to `idle` with `reason="run_completed"` (NOT `reason="stuck_recovery"`)
- The terminal log line MUST be either:
  - `log session state change: state=idle reason=run_completed` (healthy), OR
  - the run is purely a model call that completes without entering the embedded path (does not apply here because all DM routes go through embedded)

## Out-of-scope (per C-001)

This contract is **observed**, not modified. The mission MAY NOT change the runtime code that owns these state transitions. The mission MAY:
- Add openclaw.json config that influences which code path the runtime takes (H2 in research §4)
- Modify agent prompts (AGENTS.md) that influence what the agent emits (H3)
- Reinstall the `@openclaw/whatsapp` plugin (H5)

The mission MAY NOT:
- Edit `/usr/lib/node_modules/openclaw/dist/*` files
- Apply a runtime patch
- Replace `setActiveEmbeddedRun` / `clearActiveEmbeddedRun` / `forceClearEmbeddedAgentRun`

If diagnosis confirms the runtime itself fails to call `clearActiveEmbeddedRun` along the DM-reply path, the mission concludes per FR-009 with an internal tracking issue.
