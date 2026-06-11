# Quickstart: Restore WhatsApp DM Reply Delivery

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Phase**: Plan-phase quickstart — covers (a) the implementation-lane diagnostic ramp and (b) the post-deploy acceptance smoke

This is the runbook the operator follows during implementation and at acceptance time. It does **not** describe how the fix works — that's the implementation lane's deliverable. It describes how to reproduce, how to verify, and how to roll back.

---

## 0. Prereqs

- Mac authoring host with SSH access to office2-claude
- Operator has WhatsApp open on phone, paired with Felix's number (`+16179300916`)
- Restic backup within 24h confirmed (Tier 2 pre-flight per C-003) — operator attests via `--backup-confirmed` flag on the deploy wrapper

---

## 1. Reproduce the bug (read-only)

```bash
# 1.1 — confirm runtime + config baseline
ssh office2-claude 'openclaw --version'
# Expected: OpenClaw 2026.5.28 (e932160)

ssh office2-claude 'jq ".meta, .session, .channels.whatsapp.dmPolicy, (.agents.list | length)" /home/claude/.openclaw/openclaw.json'
# Expected: lastTouchedAt 2026-06-02, dmScope per-channel-peer, dmPolicy "allowlist", 6 agents in list

ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
# Expected: active
```

```bash
# 1.2 — capture baseline journal window
TS_BASELINE=$(date -u +"%Y-%m-%d %H:%M:%S")
echo "BASELINE_TS=$TS_BASELINE"
```

```bash
# 1.3 — send 2 test DMs from phone
# On phone, send: "ping 1" then "ping 2" to +16179300916. Wait 60s.
```

```bash
# 1.4 — observe broken path
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$TS_BASELINE' 2>/dev/null | grep -E '(Inbound|Sending|Sent message|embedded_run|stalled|stuck|sessions\\.resolve.*current)'"
```

Expected pre-fix:
- `[whatsapp] Inbound message` × 2
- `embedded_run:started` (in stall logs)
- NO `[whatsapp] Sending message`
- After ~6 min: `stuck session recovery: action=abort_embedded_run`

This confirms the bug. Use the same `TS_BASELINE` window for "before" comparisons.

---

## 2. Channel-send sanity (already verified, repeat if needed)

```bash
# Direct CLI bypasses gateway DM-dispatch — proves channel-send itself works
ssh office2-claude 'openclaw agent --agent main --channel whatsapp --to "+16179300916" --deliver --message "Direct CLI delivery probe at $(date -u +%H:%M:%SZ)" --json'
```

Expected: operator receives the message in WhatsApp within 1 second. Journal shows `[whatsapp] Sending message` and `[whatsapp] Sent message`. If this fails, the channel itself has degraded — stop and re-pair before continuing diagnosis.

---

## 3. Implementation-lane diagnostic ramp (per `research.md` §5 D1)

Run in order. Stop and apply the fix at the first hypothesis that validates.

### 3.1 — H5: WhatsApp plugin install state

```bash
ssh office2-claude 'openclaw plugins list 2>&1'
# Look for: @openclaw/whatsapp installed
ssh office2-claude 'openclaw plugins info @openclaw/whatsapp 2>&1'
# Note the version
```

If not installed or version is older than 2026-06: reinstall, restart gateway, re-test (step 1.3).

### 3.2 — H4: Config swap probes

```bash
# Probe A: try dmPolicy=pairing (the openclaw doc default)
ssh office2-claude 'jq ".channels.whatsapp.dmPolicy" /home/claude/.openclaw/openclaw.json'
# If allowlist works for inbound but breaks reply, try changing to "pairing" temporarily,
# restart gateway, re-test. Restore allowlist after (we don't want pairing-code interactions).

# Probe B: examine session.dmScope
ssh office2-claude 'jq ".session" /home/claude/.openclaw/openclaw.json'
# Try toggling to "per-channel" or removing the scope key entirely;
# restart gateway, re-test.
```

**Tier-2 pre-flight before each config edit**: confirm Restic backup ≤24h. Use the deploy wrapper's `--backup-confirmed` attestation path per DIR-009.

### 3.3 — H2: Missing field discovery

```bash
# Check openclaw docs for delivery config under channels.whatsapp
ssh office2-claude 'cat /usr/lib/node_modules/openclaw/docs/gateway/configuration.md 2>/dev/null | grep -A 20 "whatsapp"'
ssh office2-claude 'cat /usr/lib/node_modules/openclaw/docs/channels/whatsapp.md 2>/dev/null'
# Look for: delivery.mode, replyDelivery, reply.* keys not present in our config
```

If a missing field is identified: add it; deploy; re-test.

### 3.4 — H3: AGENTS.md behavioral rollback probe

```bash
# Save current main/AGENTS.md
ssh office2-claude 'cp /data/services/openclaw/data/AGENTS.md /tmp/main-AGENTS-current.md'

# Get the pre-#579 version
git show 37b3bf56^:scripts/openclaw/agents/main/AGENTS.md > /tmp/main-AGENTS-pre579.md
scp /tmp/main-AGENTS-pre579.md office2-claude:/data/services/openclaw/data/AGENTS.md

# Restart gateway
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
sleep 5

# Re-test (step 1.3 with a fresh TS_BASELINE)
```

If DM delivery works: H3 is validated. Roll forward to restoring the missing instruction in the post-#579 main/AGENTS.md.

If DM delivery still fails: roll back to current; continue to H1.

```bash
# Roll back the probe regardless of outcome
scp /tmp/main-AGENTS-current.md office2-claude:/data/services/openclaw/data/AGENTS.md
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
```

### 3.5 — H1 escalation: vendored runtime

If H2–H5 all fail, hypothesis H1 (vendored runtime regression) is the standing candidate. Per FR-009 + C-001:
1. File an internal tracking issue with all gathered evidence (link this mission, journal slices, the lifecycle contract in `contracts/embedded-run-lifecycle.md`).
2. Document the operational workaround (currently: there is none — DM-reply is broken; cron `announce` mode continues to work).
3. Conclude the mission.

---

## 4. Deploy + acceptance smoke (assuming a fix was identified)

Deploy script path: `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh` (created by the implementation lane per DIR-004/005).

```bash
# 4.1 — Pre-flight (manual operator step, Tier 2 per DIR-009)
ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-$(date +%Y-%m-%d).log' || \
ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-$(date -d "1 day ago" +%Y-%m-%d).log'
# Confirm a successful Restic snapshot within the last 24h before proceeding.

# 4.2 — Deploy
./scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh --backup-confirmed
# Strict-order safe-deploy per DIR-005: pre-flight → copy artifacts → verify artifacts → edit config → post-flight smoke.

# 4.3 — Smoke window
TS_SMOKE=$(date -u +"%Y-%m-%d %H:%M:%S")
echo "SMOKE_TS=$TS_SMOKE"

# 4.4 — Send 5 test DMs from phone to +16179300916, with ~30s gap each
# (a small mix of habit / calendar / task asks if helpful, but 5 simple "ping <N>" suffice for SC-001)

# 4.5 — Verify acceptance assertions (per contracts/journal-event-assertions.md)
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$TS_SMOKE' --until '$(date -u -d '+5 minutes' +"%Y-%m-%d %H:%M:%S")' 2>/dev/null | awk '/\[whatsapp\] Inbound message/{i++} /\[whatsapp\] Sending message ->/{s++} /\[whatsapp\] Sent message /{sent++} /\[diagnostic\] stalled session/{stall++} /\[diagnostic\] stuck session recovery/{rec++} /sessions\.resolve.*INVALID_REQUEST.*current/{rf++} /truncating in injected context.*sessionKey=agent:main:/{trunc++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail_current=\"rf\" trunc_main=\"trunc}'"
```

Expected post-fix:
```
inbound=5 send=5 sent=5 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0
```

If any assertion fails → roll back via 4.6.

### 4.6 — Rollback (Tier 2 manual)

Rollback is a config-only revert (no schema migration, no data loss). The deploy script prints exact rollback instructions on failure. General shape:
1. Restore the pre-deploy openclaw.json from the per-deploy backup (`/data/services/openclaw/openclaw.json.pre-deploy-<TS>`)
2. `systemctl --user restart openclaw-gateway.service`
3. Re-run smoke (step 4.5) to confirm pre-deploy behavior is fully restored

### 4.7 — Rebaseline obligation (#557)

```bash
# After confirmed fix + smoke pass, reset security-monitor baselines per audited-surfaces.json
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'

# Record the timestamp; the mission's merge commit MUST carry one of:
#   Rebaseline: completed at <ISO8601-UTC>
#   Rebaseline: not required — <reason>   (only valid if no audited surface was touched, which won't be the case here)
```

### 4.8 — Next-day cron regression check (SC-005)

The morning after deploy, at 7:10 AM ET, run:

```bash
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$(date -u -d '15 minutes ago' +"%Y-%m-%d %H:%M:%S")' 2>/dev/null | grep -E '(habits-morning-checkin|\[whatsapp\] Sending message)' | head -10"
```

Expected: the morning habit checkin cron fires and delivers via `[whatsapp] Sending message`. If not, regression — investigate.

---

## 5. Doc reconciliation checklist (FR-012, executed in the implementation lane)

After deploy + smoke pass, per `data-model.md` E4 reconciliation table:

- [ ] DR-1: bump `service-inventory.json#openclaw-gateway.version` to `v2026.5.28`; correct `channels.whatsapp.dm_policy` to `allowlist`; add `session.dmScope: per-channel-peer`
- [ ] DR-2: add `data-flows.json#flows[].name="whatsapp-dm-reply"` entry with the documented path
- [ ] DR-3: verify `audited-surfaces.json` coverage; add/extend patterns if needed
- [ ] DR-4: update `service-inventory.md` narrative to mirror DR-1
- [ ] DR-5: update `data-flows.md` + add Mermaid node/edge to `data-flows.view.md`
- [ ] DR-6: add "DM-reply lifecycle troubleshooting" section to `docs/runbooks/openclaw-agent-setup.md`
- [ ] DR-7: update `docs/INDEX.md` (only if a new runbook was added; DR-6 is an update, not new)
- [ ] DR-8: update memory `project_whatsapp_dmpolicy.md` from `disabled` → `allowlist`
- [ ] DR-9: add new memory `reference_openclaw_dm_reply_lifecycle` capturing the lifecycle markers + stuck-session signature

All reconciliations land in the same mission per FR-012.

---

## 6. Edge cases the smoke does NOT cover (but the mission preserves)

- **Multi-DM burst (scenario 2 in spec)**: covered by the 5-DM smoke; the assertion `inbound=5 send=5 sent=5` proves none were dropped or merged.
- **Subagent chain (scenario 3 in spec)**: covered if at least one of the 5 DMs would normally trigger a subagent (e.g., "what's my check-in"). Add a habit / task / calendar request to the 5-DM mix.
- **Empty subagent reply (edge case 5)**: not covered by smoke — would need a contrived input. Document the expected behavior in the runbook (`DR-6`) but don't gate acceptance on it.
- **Cross-restart (edge case 6)**: not covered. The diagnostic recovery path is intentionally retained — if a genuine hang occurs, the abort path is correct.
- **Vendored-openclaw fork (edge case 7)**: covered by the H1 escalation in §3.5.
