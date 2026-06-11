---
work_package_id: WP05
title: Deploy + Smoke + Rebaseline
dependencies:
- WP02
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-005
- FR-006
- FR-008
- FR-010
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
- T026
agent: claude
history:
- event: created
  timestamp: '2026-06-11T18:50:00Z'
  by: /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-smoke.md
execution_mode: planning_artifact
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
owned_files:
- docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-smoke.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned profile:

```
/ad-hoc-profile-load implementer-ivan
```

This sets your identity, governance scope, and boundaries for this work package. Adopt the profile fully before proceeding.

---

## Objective

Execute the deploy script produced by WP02 on office2, run the operator-driven smoke, apply the #557 rebaseline, and complete the next-day cron regression check. The mission's acceptance criteria (SC-001 through SC-007) close here.

This WP handles **three branches** based on WP02's `terminal-disposition.md`:

- **Upgrade-path branch** (H6): execute the deploy script that performs the openclaw upgrade, then verify via the 5-DM operator smoke
- **Edit-path branch** (H2/H3/H4/H5): execute the deploy script that syncs the config/AGENTS.md/plugin change to office2, then verify via the 5-DM smoke
- **Escalation-path branch** (H1): NO-OP execution; write `deploy-smoke-evidence.md` documenting the no-deploy disposition and link to the internal tracking issue

You succeed when:
- (Upgrade or Edit path) `deploy-smoke-evidence.md` documents a successful deploy + smoke + rebaseline + next-day check, with all assertions passing per `contracts/journal-event-assertions.md`
- (Escalation path) `deploy-smoke-evidence.md` documents the no-op disposition with link to the issue

## Context

Read these BEFORE starting:

1. [`research.md`](../research.md) — especially `## Discovery Findings (WP01 — ...)` Decision Record
2. [`terminal-disposition.md`](../terminal-disposition.md) — WP02's authoritative output (which path)
3. [`spec.md`](../spec.md) — SC-001 through SC-007 (your acceptance criteria), C-003 (Tier 2 + #557)
4. [`contracts/journal-event-assertions.md`](../contracts/journal-event-assertions.md) — POSIX-ERE patterns + the 5-DM smoke awk one-liner
5. [`quickstart.md`](../quickstart.md) §4 — canonical deploy + smoke + rebaseline + next-day sequence
6. `docs/design/architecture/data/audited-surfaces.json` — `rebaseline_command` is canonical
7. Existing deploy scripts as conventions reference (read-only)

## Detailed guidance per subtask

### T022 — Tier 2 pre-flight (Restic ≤24h attestation per DIR-009)

**Purpose**: Operator attests that a Restic snapshot ≤24h exists before any mutation.

**Steps**:
```bash
# Check today's backup log
ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-$(date +%Y-%m-%d).log' 2>/dev/null || \
ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-$(date -d "1 day ago" +%Y-%m-%d).log'

# OR check the freshness via the canonical health-check from service-inventory.json:
ssh office2-kgale "jq -er 'if .snapshot_timestamp_utc == null then \"FAIL\" else (now - (.snapshot_timestamp_utc | fromdateiso8601)) as \$age | if (\$age > 100800) then \"FAIL: stale\" else \"OK\" end end' /data/services/backup/state/last-backup.json"
```

Operator confirms "OK" output (or triggers a manual Restic snapshot if the latest is stale). Record the snapshot timestamp into `deploy-smoke-evidence.md` (T024 owns that file; for now just keep a note).

**Escalation-path special-case**: SKIP this subtask. Document in disposition.

### T023 — Execute deploy via scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh

**Purpose**: Run the deploy script with the `--backup-confirmed` operator-ack flag.

**Pre-execution** (read `terminal-disposition.md`):
- If `path-taken: escalation-path` → SKIP this subtask
- If `path-taken: upgrade-path` → operator MUST be ready to manually run the `sudo npm install -g openclaw@<TARGET>` step when the deploy script pauses (per WP02's Stage 3)
- If `path-taken: edit-path-*` → no sudo needed; script runs fully automated

**Execution**:
```bash
# From Mac (repo root)
./scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh --backup-confirmed 2>&1 | tee /tmp/deploy-$(date -u +%Y%m%d-%H%M%S).log
```

**Capture FULL output** (stdout + stderr) for the evidence file. If the deploy script exits non-zero, follow the printed rollback instructions and STOP (do not proceed to T024). The mission may need WP02 retry.

### T024 — Operator smoke (5 DMs, 5-min window) + journal assertion

**Purpose**: After T023's deploy script reports SUCCESS, operator runs the full 5-DM acceptance smoke per the spec's SC-001 through SC-003.

**Steps**:

```bash
# 1. Capture the smoke window start time
TS_SMOKE=$(date -u +"%Y-%m-%d %H:%M:%S"); echo "SMOKE_TS=$TS_SMOKE"

# 2. OPERATOR: send 5 test DMs to +16179300916 within the next 5 minutes
#    Mix of intents: 1-2 simple "ping <N>", 1 habit query, 1 calendar query, 1 task query
#    Wait ~30s between each (gives the gateway time to process)

# 3. After 5 minutes, run the assertion
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$TS_SMOKE' --until '$(date -u -d '+5 minutes' +"%Y-%m-%d %H:%M:%S")' 2>/dev/null | awk '/\\[whatsapp\\] Inbound message/{i++} /\\[whatsapp\\] Sending message ->/{s++} /\\[whatsapp\\] Sent message /{sent++} /\\[diagnostic\\] stalled session/{stall++} /\\[diagnostic\\] stuck session recovery/{rec++} /sessions\\.resolve.*INVALID_REQUEST.*current/{rf++} /truncating in injected context.*sessionKey=agent:main:/{trunc++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail_current=\"rf\" trunc_main=\"trunc}'"
```

**Expected post-fix output**:
```
inbound=5 send=5 sent=5 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0
```

**If assertion fails**:
- Operator captures the actual output + the full journal slice
- Roll back via the deploy script's printed instructions
- Append failure to `deploy-smoke-evidence.md`
- Surface to Kent; this WP fails until WP02 retry

**Operator-observed assertions** (cannot be journal-asserted):
- ✓ All 5 DMs received in WhatsApp client within the smoke window
- ✓ Typing indicator fired during the agent runs (SC-004)
- ✓ Reply content matches the DM intent (not garbled)

### T025 — #557 rebaseline: reset security-monitor baselines; record timestamp

**Purpose**: Per #557 + C-003, the mission's merge commit MUST carry the rebaseline trailer because we touched audited surfaces.

**Steps**:
```bash
# Canonical command from audited-surfaces.json#rebaseline_command
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'

# Verification per audited-surfaces.json#rebaseline_verification
ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l && tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
# Expected: 14 baseline files; audit log ends with a clean run

# Capture the completion timestamp for the merge trailer
REBASELINE_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ"); echo "REBASELINE_TS=$REBASELINE_TS"
```

Record `REBASELINE_TS` in `deploy-smoke-evidence.md`. The merge commit (at mission close-out via spec-kitty merge gate) MUST include:
```
Rebaseline: completed at <REBASELINE_TS>
```

**Escalation-path special-case**: SKIP. Document in disposition (no surface change → no rebaseline needed).

### T026 — SC-005 next-day cron regression check (deferred ~14h)

**Purpose**: Confirm the morning habit checkin cron continues to deliver via `[whatsapp] Sending message` path after the fix.

**Schedule**: this subtask runs the morning AFTER deploy (typically at 7:10 AM ET, ~5 minutes after the 7:05 AM cron fires).

**Steps**:
```bash
# 1. Run at 7:10 AM ET the day after deploy
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$(date -u -d '15 minutes ago' +"%Y-%m-%d %H:%M:%S")' 2>/dev/null | grep -E '(habits-morning-checkin|\[whatsapp\] Sending message|Sent by felix-admin-habits)' | head -20"
```

**Expected**:
- One `habits-morning-checkin` cron tick fired
- One `Sent by felix-admin-habits:haiku` agent output
- One `[whatsapp] Sending message` event corresponding to the morning checkin
- One `[whatsapp] Sent message` ack
- Operator received the morning checkin DM on phone

If anything is missing OR delayed beyond reasonable cron tolerance: flag as SC-005 regression. May indicate the fix regressed the cron-announce path; surface to Kent.

Append outcome to `deploy-smoke-evidence.md`.

**Escalation-path special-case**: Still execute this subtask. The cron-announce path is independent of the DM-reply path and should continue to work. If it has regressed, that's a separate critical issue worth flagging.

## Authoritative deliverable: deploy-smoke-evidence.md

Create `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/deploy-smoke-evidence.md` with the full evidence trail. Template:

```markdown
# WP05 Deploy + Smoke Evidence

**Mission**: restore-whatsapp-dm-reply-delivery-01KTVVHH
**Executed at**: <ISO 8601 UTC>
**Path taken** (from terminal-disposition.md): <upgrade | edit-* | escalation>

## T022 Pre-flight
- Restic snapshot timestamp: <UTC>
- Operator attestation: confirmed via `--backup-confirmed`

## T023 Deploy execution
- Deploy log: see `/tmp/deploy-<TS>.log` (Mac-side, may be uploaded if needed)
- Exit code: <0 = success, non-zero = rollback executed>
- Key milestones:
  - <list each Stage's banner with timestamp>

## T024 5-DM smoke
- Smoke window: `<TS_START>` → `<TS_END>`
- Assertion output: `inbound=N send=N sent=N stall=N recovery=N resolve_fail_current=N trunc_main=N`
- Per the contract, expected post-fix: `inbound=5 send=5 sent=5 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0`
- Pass/Fail: <P|F>
- Operator-observed:
  - All 5 DMs received in WhatsApp: <Y|N>
  - Typing indicator fired: <Y|N>
  - Reply content quality: <good|poor with notes>

## T025 #557 Rebaseline
- Reset command: `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'`
- Completion timestamp: <ISO>
- Verification: <baseline count = 14, audit log clean>
- Merge trailer line for the mission's merge commit: `Rebaseline: completed at <ISO>`

## T026 Next-day cron regression check
- Run time: <next-day 7:10 AM ET>
- habits-morning-checkin fired: <Y|N>
- `[whatsapp] Sending message` event: <Y|N>
- Operator received morning checkin DM: <Y|N>
- Pass/Fail: <P|F>

## Final disposition
- WP05 status: <complete | failed | escalation-no-op>
- All SCs (SC-001 through SC-007) satisfied: <Y|N>
- Notes: <free text>
```

For **escalation-path**, the same file is created but with each section marked `(skipped: escalation-path; see ../terminal-disposition.md for issue link)`.

## Branch Strategy

- **Planning base branch**: `main`
- **Execution worktree**: assigned by `lanes.json`
- **Final merge target**: `main` (via spec-kitty merge gate)
- **Commit discipline**: per DIRECTIVE_033, stage ONLY `deploy-smoke-evidence.md`

## Definition of Done

Non-escalation paths:
- [ ] T022 pre-flight attestation recorded; Restic ≤24h confirmed
- [ ] T023 deploy script executed; output captured; exit code recorded
- [ ] T024 smoke window run; awk assertion matches expected post-fix pattern; operator confirmed receipt + typing indicator
- [ ] T025 rebaseline command executed; completion timestamp recorded for the merge trailer
- [ ] T026 next-day cron tick fired; `[whatsapp] Sending message` event observed; operator received morning checkin
- [ ] `deploy-smoke-evidence.md` filled with all sections + outcomes
- [ ] No vendored openclaw runtime files modified

Escalation path:
- [ ] T022, T023, T024, T025 marked `(skipped: escalation-path)` in evidence file
- [ ] T026 STILL executed (cron-announce path is independent of DM-reply path)
- [ ] `deploy-smoke-evidence.md` links to the internal tracking issue from `terminal-disposition.md`
- [ ] No vendored runtime modifications

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Deploy script regresses cron-announce path | High | T024 + T026 will detect; SC-005 is the canary; rollback via deploy script |
| Operator forgets rebaseline | High | T025 explicit subtask + merge gate enforcement per #557 |
| Operator forgets next-day check | Medium | T026 is a tracked subtask; mission accept may not pass until evidence file shows it complete |
| Smoke false-positives (wrong window, wrong DMs) | Medium | TS_SMOKE captured at the start of the 5-min window; operator confirms 5 DMs sent in that window |
| Upgrade path Stage 3 sudo step skipped or fails | High | Deploy script pauses; operator must explicitly press Enter only after sudo step succeeds |
| Next-day check runs against the wrong day's logs | Low | `--since '15 minutes ago'` is the safe pattern; verify the timestamp matches the cron schedule |

## Reviewer guidance

Check:

1. **deploy-smoke-evidence.md completeness**: all 5 subtask sections + final disposition; pass/fail explicitly marked
2. **Assertion verbatim match**: T024 awk output matches the expected pattern from `contracts/journal-event-assertions.md` byte-for-byte
3. **Rebaseline trailer ready**: T025 timestamp captured; reviewer/mission close-out adds the trailer to the merge commit
4. **Next-day check captured**: T026 is run AT THE SCHEDULED TIME (not skipped due to impatience)
5. **Escalation-path consistency**: if escalation, T022/T023/T024/T025 explicitly skipped with reason; T026 still executed
6. **DIRECTIVE_033**: only `deploy-smoke-evidence.md` in commit; nothing else
