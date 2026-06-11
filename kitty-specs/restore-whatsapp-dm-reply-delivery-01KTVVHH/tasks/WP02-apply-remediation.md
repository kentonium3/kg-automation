---
work_package_id: WP02
title: Apply Remediation
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
- T011
- T012
agent: claude
history:
- event: created
  timestamp: '2026-06-11T18:30:00Z'
  by: /spec-kitty.tasks
- event: h6-added
  timestamp: '2026-06-11T18:50:00Z'
  by: /spec-kitty.tasks (operator update — added upgrade-path branch)
agent_profile: implementer-ivan
authoritative_surface: scripts/
execution_mode: code_change
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
owned_files:
- scripts/openclaw/openclaw.json
- scripts/openclaw/agents/main/AGENTS.md
- scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh
- docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-disposition.md
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

Apply the remediation named by **WP01's Decision Record**. Three execution paths:

- **Upgrade path** (Decision Record says `Fix shape: H6 — upgrade openclaw <version>`): build a deploy script that performs the openclaw runtime upgrade per the `reference_openclaw_upgrade_gotchas` checklist, including pre-flight, doctor check, restart, and post-flight smoke
- **Edit path** (Decision Record says `Fix shape: H5/H4/H2/H3 — <change>`): edit the named repo source file; deploy script syncs the change to office2 via DIR-005 strict-order safe-deploy
- **Escalation path** (Decision Record says `Escalation: H1`): draft + file an internal tracking issue per FR-009 with all WP01 evidence; document the operational workaround in `terminal-disposition.md`; do NOT create a deploy script

You succeed when ONE of:
- (Upgrade path) `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh` exists and exercises the upgrade sequence with the gotchas checklist
- (Edit path) the named source-file edit is committed AND a deploy script exists that syncs it to office2 with post-flight smoke
- (Escalation path) internal tracking issue is filed (URL in `terminal-disposition.md`)

In all paths: `terminal-disposition.md` is created and committed.

## Context

Read these BEFORE starting:

1. [`research.md`](../research.md) — **especially the `## Discovery Findings (WP01 — ...)` block authored by WP01 + §9 H6 update**
2. [`spec.md`](../spec.md) — FR-001 through FR-009; C-001 unchanged (no vendored patching — upgrade is not patching); A3 relaxed per research §9
3. [`contracts/embedded-run-lifecycle.md`](../contracts/embedded-run-lifecycle.md) (read-only)
4. [`contracts/journal-event-assertions.md`](../contracts/journal-event-assertions.md) — awk one-liner for the post-flight smoke
5. [`quickstart.md`](../quickstart.md) §4 — canonical deploy + smoke sequence
6. Memory `reference_openclaw_upgrade_gotchas` — **critical for upgrade path**: prior-incident checklist
7. Existing kg-automation deploy scripts as conventions reference: `scripts/deploy/deploy-felix-admin-calendar.sh`, `docs/runbooks/deployment.md`

**Project memory rules to heed**:
- `feedback_upstream_issue_title_pre_approval` — escalation path: present title + body to Kent for approval BEFORE filing
- `feedback_helper_m_invocation_form` — any Python helper invoked uses `python3 -m scripts.X.Y` form
- `feedback_command_formatting` — readable output, helper sub-scripts for multi-step sequences
- `feedback_verify_cli_flag_shape` — any CLI flag MUST be verified against `<cli> --help` before deploying
- `feedback_no_workarounds_for_expediency` — for the upgrade, follow canonical npm/pipx install paths; no manual binaries

## Detailed guidance per subtask

### T008 — Apply named remediation per WP01 outcome

**Step 1 — Identify the path from WP01's Decision Record**:
- `Fix shape: H6` → upgrade path (most likely per Codex prior)
- `Fix shape: H5` → operational plugin reinstall path (small repo edit if any; mostly deploy-script work)
- `Fix shape: H4` → openclaw.json config edit path
- `Fix shape: H2` → openclaw.json config-field-addition path
- `Fix shape: H3` → main/AGENTS.md edit path
- `Escalation: H1` → no source-code edit (jump to T011)

**Step 2 — Apply the action**:

#### Upgrade path (H6) — most likely
- **DO NOT** run the upgrade in this subtask. The deploy script (T009) executes it. T008 is the *planning* and *repo-side preparation* of the upgrade.
- Determine the canonical install method: `ssh office2-claude 'which openclaw && readlink -f $(which openclaw)'` — confirms npm-global vs pipx
- Record the target version (per WP01 plan, likely `2026.6.5`) in this WP's notes
- Verify the upgrade-gotchas checklist (per memory `reference_openclaw_upgrade_gotchas`):
  - `models.providers.<x>.models[]` present in deployed openclaw.json (already true per WP01 prior reads)
  - `@openclaw/whatsapp` external plugin enabled (already true)
  - systemd unit Description (cosmetic per memory; do NOT block on this)
- No repo file edit required for the upgrade itself. (Skip to T009 for the deploy script.)

#### Edit paths (H2 / H3 / H4 / H5)
- For H2 or H4 → edit `scripts/openclaw/openclaw.json` (repo-side template)
- For H3 → edit `scripts/openclaw/agents/main/AGENTS.md`; **wc -c MUST stay < 12000** post-edit (FR-006)
- For H5 → no repo edit; the fix is operational (plugin reinstall, executed in T009)

Apply edit using `jq` (for JSON) or precise text edits (for Markdown). NEVER edit JSON by hand-merging text.

#### Escalation path (H1)
- T008 is skipped. Move directly to T011.

### T009 — Create scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh

**Purpose**: Build the deploy script per DIR-004/005. Three variants depending on path.

**Shared structure** (mandatory):
```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh
# Mission: restore-whatsapp-dm-reply-delivery-01KTVVHH (GitHub #588)
# Path: <UPGRADE | EDIT-H2 | EDIT-H3 | EDIT-H4 | EDIT-H5>
# Tier: 2 (Application/State); requires Restic ≤24h pre-flight + #557 rebaseline

REQUIRE_BACKUP_FLAG="--backup-confirmed"
if [[ "${1:-}" != "$REQUIRE_BACKUP_FLAG" ]]; then
  echo "ERROR: this script requires the operator to attest the Tier 2 pre-flight."
  echo "Usage: $0 $REQUIRE_BACKUP_FLAG"
  echo "Before running, verify a Restic snapshot ≤24h via:"
  echo "  ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-\$(date +%Y-%m-%d).log'"
  exit 64
fi
TS=$(date -u +%Y%m%d-%H%M%S)
REPO_ROOT="$(git rev-parse --show-toplevel)"
```

**Upgrade-path variant** (H6):
```bash
echo "[deploy] === Stage 1: Pre-flight ==="
ssh -o ConnectTimeout=5 office2-claude 'echo ok' >/dev/null || { echo "FAIL: office2-claude unreachable"; exit 1; }
ssh office2-claude 'openclaw doctor --json > /tmp/openclaw-doctor.pre-upgrade.json 2>&1 || true; cat /tmp/openclaw-doctor.pre-upgrade.json | head -20'

echo "[deploy] === Stage 2: Backup current openclaw.json ==="
ssh office2-claude "cp /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS"

echo "[deploy] === Stage 3: openclaw upgrade ==="
echo "[deploy] NOTE: 'npm install -g' requires sudo. Operator MUST run this step manually via ssh office2-kgale:"
echo "  ssh office2-kgale 'sudo npm install -g openclaw@<TARGET-VERSION>'"
echo "[deploy] Pausing for operator confirmation. Press Enter when the upgrade is complete..."
read -r

echo "[deploy] === Stage 4: Post-upgrade verification (gotchas checklist) ==="
ssh office2-claude 'openclaw --version' | grep -q '<TARGET-VERSION>' || { echo "FAIL: version mismatch post-upgrade"; exit 1; }
ssh office2-claude 'openclaw doctor --json' | jq '.success' | grep -q 'true' || { echo "FAIL: doctor reports failure"; exit 1; }
# Verify models.providers.anthropic.models[] still present per reference_openclaw_upgrade_gotchas
ssh office2-claude 'jq ".models.providers.anthropic.models | length > 0" /home/claude/.openclaw/openclaw.json' | grep -q true || { echo "FAIL: models.providers required-field missing"; exit 1; }
# Verify whatsapp plugin still enabled
ssh office2-claude 'jq ".plugins.entries.whatsapp.enabled" /home/claude/.openclaw/openclaw.json' | grep -q true || { echo "FAIL: whatsapp plugin not enabled"; exit 1; }

echo "[deploy] === Stage 5: Restart gateway ==="
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
sleep 10
ssh office2-claude 'systemctl --user is-active openclaw-gateway.service' | grep -q '^active$' || { echo "FAIL: gateway not active post-restart"; exit 1; }

echo "[deploy] === Stage 6: Post-flight smoke (operator-driven) ==="
echo "[deploy] OPERATOR: send ONE DM to +16179300916 within the next 60 seconds."
SMOKE_TS=$(date -u +"%Y-%m-%d %H:%M:%S")
echo "[deploy] smoke window starts at: $SMOKE_TS"
sleep 60

RESULTS=$(ssh office2-claude "journalctl --user -u openclaw-gateway --since '$SMOKE_TS' 2>/dev/null | awk '/\\[whatsapp\\] Inbound message/{i++} /\\[whatsapp\\] Sending message ->/{s++} /\\[whatsapp\\] Sent message /{sent++} /\\[diagnostic\\] stalled session/{stall++} /\\[diagnostic\\] stuck session recovery/{rec++} /sessions\\.resolve.*INVALID_REQUEST.*current/{rf++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail=\"rf}'")
echo "[deploy] smoke results: $RESULTS"
echo "$RESULTS" | grep -q "inbound=1 send=1 sent=1 stall=0 recovery=0 resolve_fail=0" || {
  echo "FAIL: post-flight smoke did not match expected pattern"
  echo "[deploy] ROLLBACK INSTRUCTIONS:"
  echo "  ssh office2-kgale 'sudo npm install -g openclaw@2026.5.28'"
  echo "  ssh office2-claude 'cp /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS /home/claude/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway.service'"
  exit 1
}

echo "[deploy] === SUCCESS ==="
echo "[deploy] NEXT (operator): run #557 rebaseline per quickstart.md §4.7:"
echo "  ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'"
```

**Edit-path variant** (H2/H3/H4): replace Stage 3 with `scp` + atomic file replace; replace Stage 4 with sha256 verify. Keep Stages 5–6 the same.

**Plugin-reinstall variant** (H5): replace Stage 3 with `ssh office2-claude 'openclaw plugins install clawhub:@openclaw/whatsapp'` and Stage 4 with `openclaw plugins info @openclaw/whatsapp` version check.

### T010 — Add post-flight smoke assertion to deploy script

**Purpose**: Already embedded in T009 Stage 6. Verify byte-for-byte match with `contracts/journal-event-assertions.md`.

**Verify**:
- The awk regex patterns in Stage 6 match `contracts/journal-event-assertions.md` § "Event patterns (POSIX ERE)" exactly
- The expected counts are correct for a 1-DM smoke (`inbound=1 send=1 sent=1 stall=0 recovery=0 resolve_fail=0`)

### T011 — Alt-path: file internal tracking issue per FR-009 (escalation path only)

Same flow as the prior version. Title:
```
Vendored openclaw embedded_run lifecycle never completes for DM-initiated runs (root cause for #588) — not addressed by 2026.6.5
```

Body sections:
- Summary
- Diagnostic isolation: link to `research.md` §3, §4, §9
- 2026.6.5 release-notes review: cite the Codex summary in §9; note which fixes were tested + refuted by WP01
- Evidence: paste WP01 Discovery findings; runtime versions tested (pre + post-upgrade)
- Why this is in vendored code: per research §3.4 source-dive + WP01 H6 desk review + (if applicable) H6 active upgrade test
- Workaround: documented in `terminal-disposition.md`
- Cross-references: #588, this mission slug

Labels: `P1-bug`, `area/felix-core`, `area/tooling`, `upstream-pending-release`

**Present to Kent for approval** (per `feedback_upstream_issue_title_pre_approval`) BEFORE filing.

### T012 — Append terminal disposition to terminal-disposition.md

Create `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/terminal-disposition.md`:

```markdown
# WP02 Terminal Disposition

**Mission**: restore-whatsapp-dm-reply-delivery-01KTVVHH
**Authored at**: <ISO 8601 UTC>
**Path taken**: <upgrade-path | edit-path-H2 | edit-path-H3 | edit-path-H4 | edit-path-H5 | escalation-path>

## If upgrade path
- WP01 Decision Record verdict: H6
- Target version: <e.g., 2026.6.5>
- Deploy script: scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh (upgrade variant)
- Commit SHA: <git rev-parse HEAD>
- Next: WP05 executes the upgrade via the deploy script + operator-driven smoke

## If edit path
- WP01 Decision Record verdict: <H2|H3|H4|H5>
- Source file edited: <path>
- Deploy script: scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh (edit variant)
- Commit SHA: <git rev-parse HEAD>
- Next: WP05 executes the deploy script + operator-driven smoke

## If escalation path
- WP01 Decision Record verdict: H1 (vendored runtime; even 2026.6.5 didn't address)
- Internal tracking issue: kentonium3/kg-automation#<N> (filed at <ISO TS>; Kent approved title + body)
- Operational workaround documented: <details>
- Mission terminal state: per FR-009, mission concludes after this WP. WP05 runs as NO-OP per its escalation-path handling.
```

Commit the file with DIRECTIVE_033 discipline.

## Branch Strategy

- **Planning base branch**: `main`
- **Execution worktree**: assigned by `lanes.json`
- **Final merge target**: `main` (via spec-kitty merge gate)
- **Commit discipline**: per DIRECTIVE_033, stage ONLY the WP02 owned_files

## Definition of Done

Upgrade-path:
- [ ] T008 npm/pipx install method confirmed; target version recorded in notes; gotchas checklist verified
- [ ] T009 deploy script with upgrade variant created, shellcheck-clean
- [ ] T010 post-flight smoke assertion matches `contracts/journal-event-assertions.md`
- [ ] T012 `terminal-disposition.md` records upgrade path + target version + commit SHA
- [ ] No vendored openclaw runtime files modified (C-001 — upgrade is not modification)

Edit-path:
- [ ] T008 named source file edited; change minimal + idempotent
- [ ] T009 deploy script with edit variant created, shellcheck-clean
- [ ] T010 post-flight smoke assertion matches contracts
- [ ] T012 `terminal-disposition.md` records edit path + commit SHA
- [ ] If H3 edit: `wc -c scripts/openclaw/agents/main/AGENTS.md` < 12000 (FR-006)
- [ ] No vendored openclaw runtime files modified (C-001)

Escalation-path:
- [ ] T011 issue title + body presented to Kent for approval
- [ ] T011 issue filed via `gh issue create` only after Kent's approval
- [ ] T012 `terminal-disposition.md` records escalation + issue URL
- [ ] No source-code edits (T008/T009/T010 skipped)
- [ ] No vendored runtime modifications (C-001)

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Upgrade introduces unrelated breakage | Medium | Gotchas checklist in T008+T009; openclaw doctor verification; rollback path in deploy script |
| Upgrade requires sudo but agent has no sudo | Certain | Deploy script explicitly pauses for operator manual `sudo` step via `ssh office2-kgale` |
| Edit applied to office2 deployed file but NOT repo source | High | T008 edits the repo source; T009 deploy script syncs to office2 |
| AGENTS.md edit pushes file over 12K cap (regresses #579) | High | Mandatory `wc -c` check in DoD |
| Issue filed without Kent's approval | High | T011 explicit "wait for approval" gate |
| 2026.6.5 doesn't fix the bug but post-flight smoke false-positives | Low | Smoke uses operator-confirmed 1-DM cycle + journal assertion; both must pass |

## Reviewer guidance

Check (path-specific):

**Upgrade path**:
1. Gotchas checklist applied: models.providers, whatsapp plugin, systemd Description (cosmetic) all verified post-upgrade
2. Deploy script Stage 3 explicitly notes the sudo requirement + pauses for operator
3. Rollback instructions printed on failure (Stage 6) include `npm install -g openclaw@2026.5.28`
4. `openclaw doctor --json` verification in Stage 4

**Edit path**:
1. Edit matches WP01 Decision Record byte-for-byte
2. Deploy script Stage 4 sha256 atomicity (tmp + rename, never partial write)
3. AGENTS.md size invariant preserved

**Escalation path**:
1. Issue body references release-note review findings (cites which 2026.6.5 fixes were tested + refuted)
2. Kent's approval documented in conversation transcript

**All paths**:
- `terminal-disposition.md` committed
- DIRECTIVE_033 staging discipline followed
- C-001 honored (no vendored runtime modifications; upgrade is not modification)
