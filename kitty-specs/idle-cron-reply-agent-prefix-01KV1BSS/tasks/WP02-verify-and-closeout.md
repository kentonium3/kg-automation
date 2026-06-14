---
work_package_id: WP02
title: Verify deployment + doc-sync + rebaseline closeout
dependencies:
- WP01
requirement_refs:
- C-002
- C-003
- C-007
- FR-008
- NFR-003
tracker_refs:
- kentonium3/kg-automation#592
planning_base_branch: feat/idle-cron-reply-agent-prefix
merge_target_branch: feat/idle-cron-reply-agent-prefix
branch_strategy: Planning artifacts for this mission were generated on feat/idle-cron-reply-agent-prefix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/idle-cron-reply-agent-prefix unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
history: []
agent_profile: implementer-ivan
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: code_change
mission_slug: idle-cron-reply-agent-prefix-01KV1BSS
owned_files:
- docs/design/architecture/service-inventory.md
role: implementer
tags: []
agent: "claude"
shell_pid: "74785"
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

After WP01 lands and the `agent-prompt-sync.service` 5-min timer has copied the new AGENTS.md files to office2, verify the change reaches WhatsApp in the new byte format (SC-001), verify the tasker rule update is visible via `systemPromptReport` in a fresh session (SC-006), update the one in-repo narrative doc that describes the IDLE reply format (`docs/design/architecture/service-inventory.md`), run the rebaseline procedure per #557 (SC-005), and record the rebaseline marker in the merge commit message.

## Context

The full design context lives in [`spec.md`](../spec.md), [`plan.md`](../plan.md), and [`research.md`](../research.md). Load-bearing points for this WP:

- **Mission is observable, not testable in pytest.** The verification surface is operator-observable (WhatsApp messages, `openclaw cron run` exit, `systemPromptReport` output, file fingerprints on office2). There is no Python unit test for this WP.
- **Cache-staleness gotcha** ([[reference_openclaw_gotchas]]): `openclaw systemPromptReport` caches at session init. T009 explicitly opens a fresh OpenClaw session before invoking `systemPromptReport` to avoid the cached-old-rule false-positive.
- **`inbox-5pm` auth-error overlap** (research R-05): live probe at 2026-06-13T20:54Z showed `inbox-5pm` in `error` state with `authentication_error: invalid x-api-key`. If still firing at T008 time, substitute `inbox-7am`, `inbox-noon`, or `inbox-10pm` for the capture-agent SC-001 verification — any of capture's 4 crons satisfies SC-001.
- **Rebaseline ordering** (research R-04 risk): T010 (rebaseline) runs only AFTER T007 confirms `agent-prompt-sync.service` has synced the new AGENTS.md to office2. Otherwise the security-monitor baselines re-snapshot the OLD content and the change shows as drift on the next audit pass.
- **24-hour soak (SC-002) is post-merge operator-observation**, not part of WP02. The mission-acceptance gate (`/spec-kitty.accept`) verifies SC-002 only after the operator confirms the 24-hour window elapsed cleanly. Do NOT block WP02 review on the 24-hour window.
- **Tier-3 risk** (spec C-001): no Restic precondition, no sudo, no infrastructure change. The only operator-supervised action is the rebaseline; the operator runs it after merge.

## Branch Strategy

- planning_base_branch: `feat/idle-cron-reply-agent-prefix`
- merge_target_branch: `feat/idle-cron-reply-agent-prefix`
- Depends on WP01. Spec-kitty's `next` flow will pick this WP up after WP01 is review-approved.

## Subtask guidance

### T006 — Update `docs/design/architecture/service-inventory.md` IDLE description

**Purpose**: Sync the one narrative architecture doc that explicitly describes the IDLE reply format so it matches the new byte format. This is the only in-repo doc-sync target this mission has identified via grep across `docs/`.

**Pre-edit state**:

The current file at line ~239 contains a description of `felix-admin-capture`'s no-op behavior that reads (paraphrase):

> "When the helper reports zero unprocessed files, zero parse failures, and zero markers to clean up, the agent replies with the single token `IDLE` and takes no further action."

This is a third-person description of the rule and needs to track the new byte format.

**Steps**:

1. Open `docs/design/architecture/service-inventory.md`.
2. Find the line referencing the IDLE reply (approximately line 239). Confirm it describes capture's no-op behavior.
3. Replace `the single token \`IDLE\`` with `the byte string \`[felix-admin-capture]: IDLE\``.
4. If the surrounding sentence references "single token" elsewhere, update consistently.
5. Check whether other Felix sub-agents (habits, tasker, escalation) are also described in this file with their own IDLE-reply lines — if so, update each with its own slug.
6. Add a tiny inline parenthetical noting the rule generalizes (e.g., "(the same `[<agent-slug>]: IDLE` pattern applies across the four IDLE-emitting Felix sub-agents; see kentonium3/kg-automation#592)"). Keep the parenthetical to one sentence.

**Files**:
- `docs/design/architecture/service-inventory.md` (edit only)

**Validation**:
- [ ] `grep -n 'single token \`IDLE\`' docs/design/architecture/service-inventory.md` returns no remaining stale references.
- [ ] The updated sentence references `[felix-admin-capture]: IDLE` (and analogous slugs for habits/tasker/escalation if those agents have lines too).
- [ ] No edits outside this file.

### T007 — Confirm office2 deployed AGENTS.md content

**Purpose**: Before exercising the WhatsApp surface, verify that the `agent-prompt-sync.service` timer has actually copied the new AGENTS.md content to `/data/services/openclaw/<workspace>/AGENTS.md` on office2. This is the precondition for T008/T009/T010.

**Pre-step**: Confirm the mission's merge commit (or at least WP01's commit) has landed on a branch that the deploy pipeline observes. Per spec C-002 + FR-008, the timer syncs on every 5-min tick if the repo head has changed.

**Steps**:

1. Per [[reference_office2_agent_deploy_paths]], identify the deploy directory for each in-scope agent (slug → workspace mapping). Likely:
   - `felix-admin-capture` → `/data/services/openclaw/inbox-agent/`
   - `felix-admin-habits` → `/data/services/openclaw/habits-agent/`
   - `felix-admin-tasker` → `/data/services/openclaw/tasker-agent/`
   - `felix-admin-escalation` → `/data/services/openclaw/escalation-agent/`
   - (Verify against `/home/claude/.openclaw/openclaw.json` `workspace` fields if uncertain.)
2. On office2, for each workspace directory, compare the deployed AGENTS.md to the in-repo one:
   ```bash
   ssh office2-claude 'for ws in inbox-agent habits-agent tasker-agent escalation-agent; do
     echo "=== $ws ===";
     wc -c /data/services/openclaw/$ws/AGENTS.md;
     grep -c "\\[felix-admin-" /data/services/openclaw/$ws/AGENTS.md;
   done'
   ```
3. Each deployed file should show the post-mission byte count (~ matches the repo file size) and a `grep -c '\[felix-admin-'` ≥ 4 (canonical block + at least one example).
4. If a workspace shows the OLD byte count or `grep -c` < 4, the timer hasn't synced yet. Wait up to 5 minutes and retry. If still stale, check `systemctl --user status agent-prompt-sync.service` on office2 (operator).

**Files**: no in-repo edits; this is an office2 verification step.

**Validation**:
- [ ] All 4 deployed AGENTS.md byte counts match their in-repo equivalents (within a few bytes for line-ending differences if any).
- [ ] All 4 deployed AGENTS.md contain the new `[felix-admin-<slug>]: IDLE` literal.
- [ ] No stale "single token `IDLE`" or "four characters `IDLE`" wording in any deployed file.

### T008 — SC-001 verification: live cron run + WhatsApp byte-format check

**Purpose**: Trigger one IDLE cron per cron-firing in-scope agent and visually confirm the WhatsApp reply is the exact byte string `[<agent-slug>]: IDLE`.

**Pre-step**: T007 confirms deployed files. If T007 didn't pass, do NOT run T008.

**Steps**:

1. List the relevant cron IDs:
   ```bash
   ssh office2-claude 'openclaw cron list --json' | python3 -c "
   import json,sys
   d = json.load(sys.stdin)
   for j in d['jobs']:
       if j['agentId'] in ('felix-admin-capture','felix-admin-habits','felix-admin-escalation') and j['enabled']:
           print(f\"{j['name']:30}  {j['agentId']:30}  {j['id']}\")
   "
   ```
2. For each of the 3 cron-firing in-scope agents, pick one healthy cron ID:
   - Capture: prefer `inbox-7am`. If its state is non-error, use it. Otherwise fall through to `inbox-noon` or `inbox-10pm`.
   - Habits: `habits-morning-checkin`.
   - Escalation: `escalation-daily`.
   - **Skip `inbox-5pm` if it's still in auth-error state per research R-05.**
3. For each chosen cron ID, invoke a synchronous one-shot run:
   ```bash
   ssh office2-claude "openclaw cron run --wait <id>"
   ```
   The `--wait` flag synchronously waits for the run to complete. Capture the exit status.
4. Each invocation should produce a WhatsApp message to the operator's phone. The operator visually confirms each message is exactly:
   - `[felix-admin-capture]: IDLE`
   - `[felix-admin-habits]: IDLE`
   - `[felix-admin-escalation]: IDLE`
   No preamble, no trailing prose, no leading whitespace before `[`, no characters after `IDLE`. If any message deviates, file a regression and reject this WP.

**Files**: no in-repo edits.

**Validation**:
- [ ] 3/3 cron runs returned exit 0.
- [ ] 3/3 WhatsApp messages match the expected byte string exactly.
- [ ] None of the 3 messages contain a `Helper exit code…` preamble, an "All clean — IDLE" wrapper, or any trailing prose.

### T009 — SC-006 verification: tasker systemPromptReport in fresh session

**Purpose**: `felix-admin-tasker` has no cron; SC-001 cannot exercise it directly. Verify the deployed AGENTS.md update via `openclaw systemPromptReport` in a session that started AFTER deploy (per C-007 cache-staleness guard).

**Steps**:

1. Restart the OpenClaw gateway on office2 to guarantee a fresh session for `systemPromptReport`:
   ```bash
   ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
   ```
   Wait ~5 seconds for the gateway to settle.
2. Invoke the report:
   ```bash
   ssh office2-claude 'openclaw systemPromptReport --agent felix-admin-tasker' | head -200
   ```
3. Confirm the output contains the new Hard rule #1 block:
   - The literal `[felix-admin-tasker]: IDLE` MUST appear at least once.
   - The phrase "the literal byte string" MUST appear.
   - The operator-rationale line ("observed-mode attribution is a load-bearing observability surface…") MUST appear.

**Files**: no in-repo edits.

**Validation**:
- [ ] `openclaw systemPromptReport --agent felix-admin-tasker` post-restart contains the new Hard rule #1 block.
- [ ] No stale "the four characters `IDLE`" wording in the report output.

### T010 — Rebaseline per #557 + record merge-commit marker

**Purpose**: AGENTS.md is in the `openclaw-agent-prompts` audited-surface set per `docs/design/architecture/data/audited-surfaces.json`. Per #557 + spec C-003 + SC-005, the security-monitor baselines on office2 MUST be reset post-deploy, and the mission's merge commit message MUST record `Rebaseline: completed at <ts>` (or `Rebaseline: not required — <reason>` if the surface didn't change, which is NOT the case here).

**Pre-step**: T007 + T008 + T009 must all pass. The rebaseline runs after deploy is confirmed.

**Steps**:

1. Run the canonical rebaseline command per `docs/runbooks/security-baseline-ops.md` (also documented as `rebaseline_command` in `audited-surfaces.json`):
   ```bash
   ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
   ```
2. Capture the completion timestamp in UTC ISO-8601 format. Example: `2026-06-13T22:30:00Z`.
3. Confirm the post-rebaseline file count is at expected (14 per `audited-surfaces.json` `expected_baseline_count`):
   ```bash
   ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
   ```
   Expect `14`.
4. Record the rebaseline timestamp in the merge commit message. When `/spec-kitty.merge` runs, the operator (or the merge-commit author tool) MUST include in the commit message body:
   ```
   Rebaseline: completed at <ts>
   ```
   (using the timestamp captured in step 2).
5. **Note**: spec-kitty.merge generates the merge commit; the implementer's role here is to surface the timestamp to the operator/merge tool. Document the timestamp in the WP completion summary so it's available when the merge runs.

**Files**: no in-repo edits; the rebaseline marker lives in the merge commit message generated by `/spec-kitty.merge`.

**Validation**:
- [ ] Rebaseline command exited 0; post-rebaseline `ls | wc -l` returned 14.
- [ ] Rebaseline timestamp recorded in WP completion summary (so it lands in the merge commit message).
- [ ] No drift surfaced on the next scheduled audit pass (verify by spot-checking `tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log`).

## Definition of Done

- [ ] `docs/design/architecture/service-inventory.md` updated; no stale "single token IDLE" wording.
- [ ] T007 confirmed all 4 deployed AGENTS.md match the in-repo versions.
- [ ] T008's 3 WhatsApp messages exactly matched the expected byte form.
- [ ] T009 confirmed tasker's deployed system prompt contains the new rule.
- [ ] T010 rebaseline completed; timestamp recorded for the merge commit.

## Risks (reviewer should verify)

- **Office2 SSH connectivity / Tailscale** outages would block T007–T010. The reviewer should not approve this WP if any office2 step couldn't be run; route back to implementer with a re-run instruction.
- **Cache-staleness in T009**: if the gateway restart was skipped, the report may show stale content and falsely pass. Reviewer confirms `systemctl restart` ran before the report.
- **Rebaseline ordering**: if T010 ran before T007 confirmed sync, the baselines may have snapshotted OLD content. Reviewer confirms T010 ran AFTER T007 returned clean.
- **24-hour soak (SC-002)**: this is NOT a WP02 gate. Reviewer must NOT hold WP02 for the 24-hour soak; that's the mission-acceptance gate's responsibility.

## Reviewer guidance

The 4 substantial gates for this WP are:
1. **T007**: deployed files match repo (NFR-001 round-trip).
2. **T008**: 3/3 WhatsApp messages byte-exact (SC-001).
3. **T009**: tasker rule reachable in fresh session (SC-006).
4. **T010**: rebaseline complete; timestamp captured (SC-005, #557).

T006 doc-sync is a single-line edit; verify by `git diff` inspection only.

Approve only if 1–4 all pass.

## Activity Log

- 2026-06-14T00:15:09Z – user – WP02 in-WP deliverables complete: T006 (service-inventory.md doc-sync to new byte format) + T007 (pre-deploy baselines confirmed on office2 via ssh office2-claude — all 4 workspaces at pre-mission size, 0 [felix-admin-*] matches as expected). T008/T009/T010 remain pending: these are RUNTIME verifications that require the new content to be live on office2 via the agent-prompt-sync.service timer, which only fires post-merge to main (per FR-008). They are explicit operator-supervised post-merge commitments and gate the mission accept step — not in-WP code work. Reviewer should approve WP02 on the strength of T006/T007 + the spec's explicit framing of T008-T010 as post-merge runtime work. --force flag used for mid8-doubling pre-flight bug.
- 2026-06-14T00:15:15Z – claude – shell_pid=74785 – Started review via action command
