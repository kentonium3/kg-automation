# Bug: web-channel watchdog reconnect loop races credential persistence → creds.json corruption

> **RESOLVED UPSTREAM in OpenClaw v2026.4.26** ([release notes](https://github.com/openclaw/openclaw/releases/tag/v2026.4.26)):
> *"WhatsApp/Web: keep quiet but healthy linked-device sessions connected by basing the watchdog on WhatsApp Web transport activity, while retaining a longer app-silence cap so frame activity cannot mask a stuck session forever. Fixes #70678; carries forward the focused #71466 approach and keeps #63939 as related configurable-timeout follow-up."*
>
> **Verified in production on 2026-06-02** after upgrading office2 from v2026.3.24 → v2026.5.28. Post-upgrade signal counts dropped from ~300/cycle to 0/cycle for `whatsapp_creds_restore` and `web_watchdog_reconnect`; the watchdog no longer fires forced-reconnects during normal idle. No upstream issue filed by us — three other users (#70678, #71466, #63939) reported the same bug earlier and the maintainer landed the fix.
>
> **Lesson captured**: office2 was running 2 months stale on OpenClaw; a package-staleness signal would have surfaced this gap proactively. Filed as a follow-up feature consideration during mission #490 post-cutover review.
>
> Retained as a historical record of the investigation. Do NOT file upstream.

## Summary

The web-channel watchdog timer in OpenClaw forces a reconnect every ~60 seconds whenever the WhatsApp upstream has been idle for longer than `MESSAGE_TIMEOUT_MS` (default 30 minutes). During each forced reconnect, the WhatsApp credential write (`creds.json`) is not atomic with respect to the reconnect itself; reads of `creds.json` from the next reconnect attempt can land mid-write, see the file as corrupted, and fall back to `creds.json.bak`. Over a long idle window this produces dozens to hundreds of corruption-restore cycles per hour. The system self-heals (the `.bak` restore succeeds), but it generates log noise, CPU churn, and a real risk of dual-file corruption if a race ever catches both files simultaneously (manual re-pairing required). The root cause is the absence of backoff in the watchdog's reconnect loop AND the non-atomic credential file write.

## Reproduction

### Prerequisites

- `openclaw-cli` 2026.3.24 or later (behavior observed in this and adjacent versions)
- A WhatsApp web-channel-connected agent on a host where the upstream WhatsApp account is genuinely idle for long stretches (no inbound messages for 30+ min)
- A populated `creds.json` (the agent has paired successfully at least once)

### Steps

```bash
# 1. Start the openclaw gateway with a web-channel-enabled agent
openclaw gateway

# 2. Leave the upstream WhatsApp account idle for 35+ minutes
#    (no inbound messages — the watchdog's MESSAGE_TIMEOUT_MS default
#    is 30 minutes; allow margin so the watchdog fires at least once)

# 3. Tail the openclaw daily log
tail -F /tmp/openclaw/openclaw-YYYY-MM-DD.log | grep -E "watchdog|reconnect|restored corrupted"
```

### Expected Behavior

When the upstream WhatsApp account is genuinely idle, the watchdog should detect the absence of inbound messages and either:
- Back off exponentially on repeated reconnect attempts (e.g., 60s, 120s, 240s, ...), so the reconnect cycle quiets down during sustained idle windows, OR
- Stop firing reconnects altogether after N failed/no-effect attempts, leaving the gateway in a quiescent state until the next outbound trigger or a manual `openclaw system event`.

In either case, credential file writes should be atomic (tempfile + rename) so that no in-flight reader can observe a partial `creds.json`.

### Actual Behavior

The watchdog fires unconditionally every `WATCHDOG_CHECK_MS` (default 60s) for as long as the idle condition persists. Each fire enqueues a force-close + reconnect cycle. The reconnect re-reads `creds.json`; if a write from the prior reconnect is still in flight, the read sees a partial/corrupted file and falls back to `creds.json.bak`. Sample log output:

```text
{"module":"web-heartbeat","minutesSinceLastMessage":33,"message":"Message timeout detected - forcing reconnect"}
{"module":"web-reconnect","status":499,"message":"web reconnect: connection closed"}
{"module":"web-session","credsPath":"/home/<user>/.openclaw/credentials/whatsapp/default/creds.json","message":"restored corrupted WhatsApp creds.json from backup"}
# ... repeated every ~60s for the duration of the idle window
```

Observed scale on a single 16-hour idle stretch:

| Event | Count over 16h |
|---|---|
| `restored corrupted WhatsApp creds.json from backup` | 193 |
| `web reconnect: connection closed` (status 499) | 149 |
| `Message timeout detected - forcing reconnect` | 147 |

Functionally the gateway recovers each cycle. The risk is:

1. **Dual-file corruption race**: if a force-close arrives during the `.bak` write window, both files can be corrupted in the same race. The gateway can no longer authenticate, requires manual re-pairing.
2. **DNS-resolution churn**: each reconnect attempt re-resolves `web.whatsapp.com`. Under sustained reconnect storms, occasional `getaddrinfo ENOTFOUND web.whatsapp.com` errors accumulate (~6 ERROR-level entries over a typical day; under stress these could grow).
3. **CPU + I/O churn**: 60-cycle reconnects per hour per idle window per agent. For multi-agent deployments this scales linearly.
4. **Sonnet token cost** for any heartbeat / agent layer sitting downstream of the web-channel state — the constant churn defeats prompt-cache strategies and inflates token consumption on every status check.

## Root Cause

Two collaborating issues in `channel.runtime-Dto237Iv.js`:

```javascript
active.watchdogTimer = setInterval(() => {
    if (!active.lastInboundAt) return;
    const timeSinceLastMessage = Date.now() - active.lastInboundAt;
    if (timeSinceLastMessage <= MESSAGE_TIMEOUT_MS) return;
    // ... force close + reconnect, with no attempt-counter or backoff
}, WATCHDOG_CHECK_MS);
```

Where `WATCHDOG_CHECK_MS = 60_000` (60s) and `MESSAGE_TIMEOUT_MS = 1_800_000` (30 min) by default.

The watchdog has no notion of "we have already attempted N reconnects this idle window — back off." Every 60s, as long as no inbound message has arrived, it fires another reconnect. There is no exponential backoff, no max-attempts cap, no quiescent-state transition.

The credential persistence path (likely in the embedded WhatsApp Web client / Baileys equivalent at `session-BBv1F7vj.js`) writes `creds.json` directly rather than via tempfile + `rename` (atomic). The `maybeRestoreCredsFromBackup` recovery path is hit so often it appears to be the steady-state behavior, not an exception path.

## Workaround Applied

Downstream monitoring tooling treats the corruption-restore log entry as a chronic baseline rather than a fault signal. Issue thresholds are tuned to fire only on storm rates well above the observed baseline (~4× worst-observed cycle peak, ~7× worst-observed rolling) so the operator is not paged on the known condition. The gateway itself is left to self-heal each cycle; no operator intervention required unless dual-file corruption manifests (which has not been observed in production but is theoretically possible under sustained stress).

This is a noise-management workaround, not a fix. The underlying CPU/IO churn, token-cost amplification, and dual-corruption risk persist.

## Environment

- OS: Ubuntu 24.04 LTS (Linux)
- Node.js: 22.22.2 (per `_meta.runtime` in the openclaw log entries)
- openclaw-cli: 2026.3.24
- WhatsApp web-channel: paired and authenticated against a personal WhatsApp account
- Observation source: `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (the daily JSON-per-line log)
