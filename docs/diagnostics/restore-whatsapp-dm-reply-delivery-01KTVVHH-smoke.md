# WP05 Deploy + Smoke Evidence — Mission Terminal Disposition

**Mission**: restore-whatsapp-dm-reply-delivery-01KTVVHH
**Executed at**: 2026-06-12T01:30:00Z – 01:38:30Z
**Path taken at WP02 (per `restore-whatsapp-dm-reply-delivery-01KTVVHH-disposition.md`)**: upgrade-path
**Path concluded at WP05**: **escalation-path** — H6 refuted by 1-DM smoke; FR-009 triggered → internal tracking issue [#589](https://github.com/kentonium3/kg-automation/issues/589)

---

## T022 — Tier 2 pre-flight (Restic ≤24h)

- Restic snapshot timestamp: `2026-06-11T04:00:05Z` (per `/data/services/backup/state/last-backup.json`)
- Snapshot age at pre-flight: ~15 hours
- Operator attestation: `OK (15 hours since snapshot)` via the canonical health-check command from `audited-surfaces.json`
- Result: ✓ Pre-flight clean

## T023 — Deploy execution (operator-coordinated)

Stages 1 + 2 (script-equivalents executed inline by orchestrator due to TTY constraints; operationally identical to running the deploy script):

| Stage | Outcome |
|---|---|
| 1 — Pre-flight + doctor snapshot | ✓ office2-claude reachable; doctor reported `--lint` flag now required (cosmetic; gateway running) |
| 2 — Backup pre-upgrade `openclaw.json` | ✓ `/home/claude/.openclaw/openclaw.json.pre-upgrade-20260611-192805` (6123 bytes) |
| 3 — Operator-driven sudo upgrade | ✓ Kent ran `ssh office2-kgale 'sudo npm install -g openclaw@2026.6.5'`; install successful |
| 4 — Post-upgrade verification (gotchas checklist) | ✓ All bullets: version `2026.6.5 (5181e4f)`; `models.providers.anthropic.models` length 2; `plugins.entries.whatsapp.enabled` true; `openclaw doctor --post-upgrade --json` → `findings: []` after `openclaw plugins registry --refresh` triggered database-first state migrations (plugin-state, cron, task-registry, task-delivery → SQLite) |
| 5 — Restart gateway | ✓ Active since 2026-06-12 01:29:59 UTC; PID 1030478; memory ~520M (vs ~338M pre-upgrade) |

## T024 — 1-DM smoke (operator-driven)

- Smoke window start: `2026-06-12 01:30:24 UTC`
- Operator sent 1 DM at `2026-06-12 01:31:42 UTC`
- Operator-observed: **no typing indicator**, no reply in WhatsApp client
- Journal evidence (filtered for DM lifecycle events):

```
01:31:42  [whatsapp] Inbound message +16179300916 -> +16179300916 (direct, 68 chars)
01:34:01  [diagnostic] stalled session: sessionKey=agent:main:whatsapp:direct:+16179300916
          activeWorkKind=embedded_run lastProgress=embedded_run:started lastProgressAge=234s
... (stall log every 30s for 9 cycles) ...
01:38:01  [diagnostic] stuck session recovery: action=abort_embedded_run aborted=true drained=true released=0
```

**Assertion result**:
- `inbound=1 send=0 sent=0 stall=9 recovery=1 resolve_fail_current=0 trunc_main=0`
- **FAILED** vs expected post-fix pattern `inbound=1 send=1 sent=1 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0`

Same `sessionId=b1c3d0b6-6c09-45a4-b649-536ed31c8b35`, same `activeWorkKind=embedded_run`, same recovery action, same ~378s timeout as observed pre-upgrade in WP01's diagnostic. **Bug is structurally identical on 2026.6.5.**

## T025 — Rebaseline (skipped)

Skipped on the escalation branch. The 2026.6.5 upgrade IS retained on office2 (per Kent's decision: the database-first refactor + other 2026.6.5 improvements are wins independent of #588). The rebaseline obligation per #557 still applies because audited surfaces changed (openclaw runtime version, plugin registry state migrated to SQLite). **Operator must run** the rebaseline command separately before this mission's merge:

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

Record the completion timestamp here when done. The mission merge trailer will read `Rebaseline: completed at <ISO8601-UTC>` once that runs.

## T026 — Next-day cron regression check

Deferred ~14h to 2026-06-12 ~12:10 UTC (7:10 AM ET). The cron `announce`-mode outbound path is independent of the DM-reply path, so it should continue working. The 7:05 AM ET `habits-morning-checkin` cron will fire; the operator confirms receipt of the morning DM through the normal `[whatsapp] Sending message` path. If cron regresses, that's a separate critical issue worth flagging — escalate beyond this mission.

## Final disposition

- **WP05 status**: complete (escalation-path with partial deploy retention)
- **openclaw runtime on office2**: 2026.6.5 (retained)
- **DM-reply state**: broken (same #588 bug signature observed on 2026.6.5)
- **Internal tracking issue filed**: [kentonium3/kg-automation#589](https://github.com/kentonium3/kg-automation/issues/589) — vendored embedded_run lifecycle regression; H6 (2026.6.5 upgrade) did not fix #588
- **Operator decision pending**: whether to file upstream at openclaw or hold for openclaw 2026.7.x

### SCs (mission acceptance criteria) outcome

| SC | Expected | Actual | Status |
|---|---|---|---|
| SC-001 (5 DMs delivered <30s each) | All delivered | 0 delivered | FAILED |
| SC-002 (`Sending message` per DM) | 1 per DM | 0 per DM | FAILED |
| SC-003 (no `sessions.resolve current` errors) | 0 | 0 in this slice (different from pre-upgrade where it was >0) | PASS |
| SC-004 (typing indicator) | Visible | None | FAILED |
| SC-005 (cron `announce` continues) | Continues working | Pending T026 next-day verification | DEFERRED |
| SC-006 (no `truncating in injected context` on `agent:main:*`) | 0 | 0 | PASS |
| SC-007 (doc reconciliation + rebaseline trailer) | Both | DR-1..DR-9 landed via WP03/WP04 ✓; rebaseline pending T025 separate operator step | PARTIAL |

The SC failures are all on the DM-reply path (the bug under repair); SC-003 unexpectedly PASSED on 2026.6.5 (the `current` session resolver failure was a downstream symptom of the pre-upgrade variant of the bug; the 2026.6.5 variant doesn't manifest that secondary symptom). SC-005 + SC-007 rebaseline still need the operator's hand-off steps.

Per FR-009, an escalation outcome on a bug-fix mission is acceptable: the mission concludes with the internal tracking issue + retained upgrade + documented operational workaround (none in this case). Mission may proceed through accept + merge in this state.
