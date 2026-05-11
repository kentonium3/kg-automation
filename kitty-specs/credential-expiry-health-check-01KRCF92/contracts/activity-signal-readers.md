# Contract: Activity Signal Readers

**Surface**: per-credential helpers that query external tools for activity state and return a "should alert" decision.

Each `monitor-activity` credential needs exactly one reader.

## Identity

All shell invocations run as the `claude` user. No sudo required for any signal queried in v1.

---

## Reader 1: `tailscale_auth_signal`

### Inputs

- `credential: Credential` (the `tailscale-auth` entry — used only for context in the failure object)

### Outputs

- `Optional[ActivitySignalFailure]` — `None` if signal is healthy; a failure object if the alert should fire.

### Behaviour

1. Run `tailscale status --json` (5-second subprocess timeout).
2. On non-zero exit or timeout: return `ActivitySignalFailure(reason="tailscale status command failed: <stderr summary>")`. Note: this distinguishes "we couldn't query the signal" from "we queried and the signal is bad" — both should alert, but the reason text differs.
3. Parse the JSON. Extract `BackendState`.
4. If `BackendState != "Running"`: return `ActivitySignalFailure(reason="tailscale BackendState is <value>, expected Running")`.
5. Otherwise: return `None`.

### Test fixtures

- `tests/fixtures/tailscale-status-running.json` — `BackendState: "Running"` (captured live from office2).
- `tests/fixtures/tailscale-status-needs-login.json` — `BackendState: "NeedsLogin"` (synthetic; documented Tailscale state).
- `tests/fixtures/tailscale-status-stopped.json` — `BackendState: "Stopped"` (synthetic).

---

## Reader 2: `whatsapp_session_signal`

### Inputs

- `credential: Credential` (the `whatsapp-session` entry)

### Outputs

- `Optional[ActivitySignalFailure]` — `None` if healthy; failure object if alert should fire.

### Behaviour

1. Run `openclaw channels status` (10-second subprocess timeout — slightly longer because gateway probes can be slower).
2. On non-zero exit or timeout: return `ActivitySignalFailure(reason="openclaw channels status command failed: <stderr summary>")`.
3. Parse the output. The default channel's line looks like:
   ```
   - WhatsApp default: enabled, configured, linked, running, connected, in:38m ago, out:38m ago, dm:allowlist, allow:+16179300916
   ```
   Extract: `linked`, `running`, `connected`, `in:<duration>`, `out:<duration>`.
4. Apply thresholds (in order; first match wins):
   - If `linked` not present: alert with `reason="WhatsApp default channel not linked"`.
   - If `running` not present: alert with `reason="WhatsApp default channel not running"`.
   - If `connected` not present: alert with `reason="WhatsApp default channel not connected"`.
   - If `in:` duration > 14 days: alert with `reason="WhatsApp default channel last inbound activity <duration> ago, exceeding 14-day staleness threshold"`.
   - If `out:` duration > 14 days: alert with `reason="WhatsApp default channel last outbound activity <duration> ago, exceeding 14-day staleness threshold"`.
5. Otherwise: return `None`.

### Duration parsing

`openclaw channels status` emits durations like:

- `38m ago` → 38 minutes
- `2h 14m ago` → 2 hours 14 minutes
- `3d 5h ago` → 3 days 5 hours
- `2w ago` → 2 weeks = 14 days exactly

Implement a small parser that converts these to `datetime.timedelta`. Unit-test against each shape.

### Test fixtures

- `tests/fixtures/openclaw-channels-status-healthy.txt` — current healthy state (captured live).
- `tests/fixtures/openclaw-channels-status-not-connected.txt` — synthetic.
- `tests/fixtures/openclaw-channels-status-stale.txt` — synthetic, `in:` exceeds 14 days.

---

## Why these readers are separate from the GitHub/Vikunja writers

Layering keeps the system testable:

- **Readers** return decisions (signal healthy / signal failing + reason).
- **Writers** turn decisions into artefacts.

Mocking the readers in tests lets the orchestrator be tested without touching `tailscale` or `openclaw`. Mocking the writers in tests lets the readers be exercised against fixtures without touching GitHub or Vikunja.

---

## Extensibility

If a future credential needs an activity-signal check, add a new reader function and register it in the orchestrator's `MONITOR_ACTIVITY_READERS: dict[str, Callable]` mapping (keyed by credential `name`). No other code path changes. This keeps the alert-decision logic for each `monitor-activity` credential self-contained.
