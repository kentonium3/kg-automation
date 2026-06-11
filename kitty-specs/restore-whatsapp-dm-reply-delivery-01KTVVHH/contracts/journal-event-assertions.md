# Contract: Journal Event Assertions (acceptance harness)

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Substrate**: `journalctl --user -u openclaw-gateway` on office2
**Why this contract exists**: the smoke test (SC-001 through SC-007) lives in this substrate; we need explicit grep patterns the operator can run and that the runbook can codify.

## Event patterns (POSIX ERE)

| Event class | Pattern | Notes |
|---|---|---|
| `inbound` | `\[whatsapp\] Inbound message ` | A DM was received |
| `bootstrap` | `\[agent/embedded\] workspace bootstrap` | Agent injection start; check for truncation warnings here |
| `truncation_warning` | `\[agent/embedded\].*truncating in injected context.*sessionKey=agent:main:` | FR-006 regression — must be ZERO post-fix |
| `agent_output` | `^[^|]+ Sent by [a-z-]+:[a-z0-9-]+$` | Agent stdout marker; presence confirms agent ran, absence does NOT confirm it didn't |
| `whatsapp_send` | `\[whatsapp\] Sending message ->` | Channel dispatch — MUST appear post-fix for each DM |
| `whatsapp_sent` | `\[whatsapp\] Sent message [A-F0-9]+ -> sha256:` | Channel ack |
| `stalled_session` | `\[diagnostic\] stalled session: .*classification=stalled_agent_run.*lastProgress=embedded_run:started` | Bug signature — must be ZERO post-fix |
| `stuck_recovery` | `\[diagnostic\] stuck session recovery: .*action=abort_embedded_run` | Bug terminal — must be ZERO post-fix |
| `sessions_resolve_fail_current` | `\[ws\] ⇄ res ✗ sessions\.resolve .*errorCode=INVALID_REQUEST.*errorMessage=No session found: current` | Downstream symptom — must be ZERO post-fix |
| `agentdir_missing` | `agentDir.*does not exist` or `ENOENT.*agents/[^/]+/agent` | Sanity — must be ZERO (Stage 3b idempotent setup should prevent this for new agents) |

## Smoke-test assertions (SC-001…SC-007 derivation)

For a 5-DM smoke session executed within a 5-minute window `[T0, T0+5min]`:

```
INBOUND_COUNT  = grep -c "\[whatsapp\] Inbound message " <slice>
OUT_COUNT      = grep -c "\[whatsapp\] Sending message ->" <slice>
SENT_COUNT     = grep -c "\[whatsapp\] Sent message " <slice>
STALL_COUNT    = grep -c "\[diagnostic\] stalled session:" <slice>
RECOVERY_COUNT = grep -c "\[diagnostic\] stuck session recovery:" <slice>
RESOLVE_FAIL   = grep -cE "sessions\.resolve .*errorCode=INVALID_REQUEST.*current" <slice>
TRUNC_COUNT    = grep -cE "truncating in injected context.*sessionKey=agent:main:" <slice>
```

| Success criterion | Assertion |
|---|---|
| SC-001 (5 DMs delivered) | `INBOUND_COUNT >= 5` AND operator received 5 WhatsApp messages in WhatsApp client |
| SC-002 (Sending/Sent fires per DM) | `OUT_COUNT >= 5` AND `SENT_COUNT >= 5` |
| SC-003 (no `sessions.resolve current` errors) | `RESOLVE_FAIL == 0` |
| SC-004 (typing indicator) | operator-observed (not asserted from journal) |
| SC-005 (cron `announce` no regression) | next-day morning checkin (`habits-morning-checkin` cron at 7:05 AM ET) delivers normally; assert by running the smoke harness at 7:10 AM ET the day after deploy |
| SC-006 (no truncation warning on main) | `TRUNC_COUNT == 0` |
| SC-007 (doc reconciliation) | merge commit carries `Rebaseline: completed at <ts>` AND DR-1 through DR-9 are landed |

**Additional invariants** (bug-signature assertions — not in SC but derived from the lifecycle contract):
- `STALL_COUNT == 0` for the smoke window
- `RECOVERY_COUNT == 0` for the smoke window

## Smoke-test operator command (single-line, copy-paste)

```bash
ssh office2-claude "journalctl --user -u openclaw-gateway --since '<T0>' --until '<T0+5min>' 2>/dev/null | awk '/\[whatsapp\] Inbound message/{i++} /\[whatsapp\] Sending message ->/{s++} /\[whatsapp\] Sent message /{sent++} /\[diagnostic\] stalled session/{stall++} /\[diagnostic\] stuck session recovery/{rec++} /sessions\.resolve.*INVALID_REQUEST.*current/{rf++} /truncating in injected context.*sessionKey=agent:main:/{trunc++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail_current=\"rf\" trunc_main=\"trunc}'"
```

Expected post-fix output:
```
inbound=5 send=5 sent=5 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0
```

Pre-fix output (per current observation):
```
inbound=5+ send=0 sent=0 stall=N recovery=≥1 resolve_fail_current=≥1 trunc_main=0
```

## Why grep, not pytest

Per Decision §5 D5 in `research.md`: the WhatsApp pairing requires QR-driven auth on a real phone session; no test harness can simulate inbound DMs without re-pairing. Per `feedback_live_integration_tests` memory, do not propose `--live-probe` workarounds. The smoke test is operator-driven by design.
