---
work_package_id: WP05
title: Office2 deployment
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
- T020
- T021
agent: "claude:sonnet:implementer:implementer"
shell_pid: "45945"
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: scripts/office2/deploy/
execution_mode: code_change
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- scripts/office2/deploy/felix-doc-auditor.sh
tags: []
---

# WP05 — Office2 deployment

## Objective

Deploy the agent and skill to office2, register the agent in the OpenClaw config, and create the `status:in-progress` GitHub label. Cron entry is initially **disabled** so the canary in WP06 can run first against a single issue under controlled conditions.

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9`
- Spec: [../spec.md](../spec.md) — Architecture Impact section
- Plan: [../plan.md](../plan.md) — Project Structure section, Technical Context
- Research: [../research.md](../research.md) — R-003 (two-registration), R-009 (label), R-010 (cron interval), R-011 (deploy mechanism)
- Quickstart: [../quickstart.md](../quickstart.md) — Step 1 (Confirm initial state)
- Office2 SSH conventions per CLAUDE.md: agents use `ssh office2-claude` (no sudo); Kent runs sudo via `ssh office2-kgale`

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: per-WP worktree from `lanes.json`. Branch from `main`. Merge back via spec-kitty review/merge.
- **Strict dependency**: WP01-WP04 must be merged to `main` before this WP runs (the deploy script will `git pull` on office2 to fetch the new files).

## Subtasks

### T017 — Create scripts/office2/deploy/felix-doc-auditor.sh

**Purpose**: Idempotent deploy helper that codifies the deployment procedure. Re-runnable for future updates. ~50-80 lines.

**File**: `scripts/office2/deploy/felix-doc-auditor.sh` (new)

**Steps**:

1. Check if `scripts/office2/deploy/` exists. If not, create the directory.

2. Compose the script:
   ```bash
   #!/usr/bin/env bash
   # felix-doc-auditor.sh — Deploy or refresh felix-doc-auditor agent on office2
   # Idempotent: safe to re-run after any in-repo source changes.
   #
   # Run from office2 (as claude or kgale; sudo required for some steps).
   # Usage: bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor.sh

   set -euo pipefail

   REPO_ROOT="/home/claude/kg-automation"
   AGENT_NAME="felix-doc-auditor"
   SKILL_NAME="doc-audit"
   AGENT_REPO_PATH="${REPO_ROOT}/scripts/openclaw/agents/${AGENT_NAME}"
   AGENT_DEPLOY_PATH="/data/services/openclaw/${AGENT_NAME}"
   SKILL_REPO_PATH="${REPO_ROOT}/scripts/openclaw/skills/${SKILL_NAME}"
   SKILL_DEPLOY_PATH="${HOME}/.openclaw/skills/${SKILL_NAME}"

   echo ">>> Pulling latest repo state"
   git -C "${REPO_ROOT}" pull origin main

   echo ">>> Verifying source paths exist"
   for p in "${AGENT_REPO_PATH}" "${SKILL_REPO_PATH}"; do
     if [ ! -d "${p}" ]; then
       echo "ERROR: source directory missing: ${p}" >&2
       exit 1
     fi
   done

   echo ">>> Deploying agent workspace -> ${AGENT_DEPLOY_PATH}"
   mkdir -p "${AGENT_DEPLOY_PATH}"
   rsync -av --delete "${AGENT_REPO_PATH}/" "${AGENT_DEPLOY_PATH}/"

   echo ">>> Deploying skill -> ${SKILL_DEPLOY_PATH}"
   mkdir -p "${SKILL_DEPLOY_PATH}"
   rsync -av --delete "${SKILL_REPO_PATH}/" "${SKILL_DEPLOY_PATH}/"

   echo ">>> Verifying OpenClaw recognizes the agent"
   if openclaw agents 2>/dev/null | grep -q "${AGENT_NAME}"; then
     echo "    OK: ${AGENT_NAME} is registered with OpenClaw"
   else
     echo "    WARNING: ${AGENT_NAME} not in 'openclaw agents' output"
     echo "    Manual step required: edit /home/claude/.openclaw/openclaw.json"
     echo "    See WP05 / T019 for the JSON snippet to add"
   fi

   echo ">>> Verifying skill is discoverable"
   if [ -f "${SKILL_DEPLOY_PATH}/SKILL.md" ]; then
     echo "    OK: ${SKILL_DEPLOY_PATH}/SKILL.md present"
   else
     echo "    ERROR: skill SKILL.md missing after deploy" >&2
     exit 1
   fi

   echo ">>> Done. Next: register cron entry in openclaw.json (see WP05 / T019),"
   echo "    create the GitHub label (see WP05 / T020),"
   echo "    then run the canary (WP06 / T022)."
   ```

3. `chmod +x scripts/office2/deploy/felix-doc-auditor.sh`

**Validation**:
- [ ] Script is executable
- [ ] `set -euo pipefail` present
- [ ] Idempotency: running twice produces no errors and no destructive changes
- [ ] Verification steps catch missing source files and unregistered agent

---

### T018 — Run the deploy helper on office2

**Purpose**: Execute the script from T017 to perform the actual deploy.

**Steps**:

1. SSH to office2 as claude:
   ```bash
   ssh office2-claude "bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor.sh"
   ```

2. Verify the output. Expected:
   - "Pulling latest repo state" succeeds
   - Source paths verified
   - Agent workspace deployed to `/data/services/openclaw/felix-doc-auditor/`
   - Skill deployed to `~/.openclaw/skills/doc-audit/`
   - Either "OK: felix-doc-auditor is registered" OR a warning that openclaw.json edit is needed (T019)

3. If permission errors occur (e.g., on `/data/services/openclaw/`), present them to Kent for `ssh office2-kgale` execution with sudo.

**Validation**:
- [ ] `ls /data/services/openclaw/felix-doc-auditor/` shows the 5 workspace files (IDENTITY, SOUL, TOOLS, USER, AGENTS.md)
- [ ] `ls ~/.openclaw/skills/doc-audit/` shows SKILL.md
- [ ] `ls -la /data/services/openclaw/felix-doc-auditor/` shows files owned by `claude:claude` (or per existing felix-admin-* convention)

---

### T019 — Register agent in /home/claude/.openclaw/openclaw.json

**Purpose**: Tell OpenClaw about the new agent. Manual edit since openclaw.json is sensitive config not in this repo.

**Steps**:

1. Back up the current openclaw.json:
   ```bash
   ssh office2-claude "cp /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"
   ```

2. Inspect the current file structure to find the `agents` array and the `crons` array:
   ```bash
   ssh office2-claude "jq '.agents[] | .id' /home/claude/.openclaw/openclaw.json"
   ssh office2-claude "jq '.crons[]' /home/claude/.openclaw/openclaw.json"
   ```

3. Add a new agents entry. Example shape (verify against existing entries):
   ```json
   {
     "id": "felix-doc-auditor",
     "model": "anthropic/claude-sonnet-4-6",
     "workspace_path": "/data/services/openclaw/felix-doc-auditor"
   }
   ```

4. Add a new crons entry — **enabled: false** initially:
   ```json
   {
     "agent": "felix-doc-auditor",
     "schedule": "0 * * * *",
     "task": "Process the next unprocessed Doc Audit or Weekly Doc Audit issue per the doc-audit skill workflow.",
     "enabled": false,
     "timeout_seconds": 1800
   }
   ```
   (Field names may differ — match the existing convention used for other felix-admin-* agents.)

5. Validate the JSON: `jq . /home/claude/.openclaw/openclaw.json > /dev/null` — must parse cleanly.

6. Reload OpenClaw config (per existing convention; might be `systemctl reload openclaw-cron` or similar).

**Validation**:
- [ ] Backup file created
- [ ] JSON parses cleanly after edit
- [ ] `openclaw agents | grep felix-doc-auditor` returns the new agent
- [ ] Cron entry exists but is `enabled: false` (or commented out)

---

### T020 — Create GitHub label `status:in-progress`

**Purpose**: One-time creation of the concurrency lock label. Can run before or after T018-T019.

**Steps**:

1. From any host with `gh` configured (Mac local or office2):
   ```bash
   gh label create "status:in-progress" \
     --color fbca04 \
     --description "Automated agent processing this issue. Manual cleanup if older than 30 min." \
     --repo kentonium3/kg-automation
   ```

2. If the label already exists (rerun safety), `gh` returns an error — that's fine, treat as success.

3. Verify:
   ```bash
   gh label list --repo kentonium3/kg-automation | grep status:in-progress
   ```

**Validation**:
- [ ] Label exists in the repo
- [ ] Color is `fbca04` (yellow — visually distinct from process labels)
- [ ] Description matches per the contract (R-009)

---

### T021 — Verify deployment

**Purpose**: End-to-end sanity check before declaring deployment complete. ~Validation only.

**Steps**:

1. Verify agent recognized by OpenClaw:
   ```bash
   ssh office2-claude "openclaw agents" | grep felix-doc-auditor
   # Expected: identity card line for the new agent
   ```

2. Verify skill discoverable:
   ```bash
   ssh office2-claude "ls ~/.openclaw/skills/doc-audit/SKILL.md"
   # Expected: file exists
   ```

3. Verify workspace deployed:
   ```bash
   ssh office2-claude "ls /data/services/openclaw/felix-doc-auditor/"
   # Expected: AGENTS.md IDENTITY.md SOUL.md TOOLS.md USER.md
   ```

4. Verify cron entry exists but disabled:
   ```bash
   ssh office2-claude "jq '.crons[] | select(.agent == \"felix-doc-auditor\")' /home/claude/.openclaw/openclaw.json"
   # Expected: entry with enabled: false (or commented out per convention)
   ```

5. Verify GitHub label:
   ```bash
   gh label list --repo kentonium3/kg-automation | grep status:in-progress
   ```

6. Confirm no stray label currently applied to any audit issues:
   ```bash
   gh issue list --repo kentonium3/kg-automation --label "status:in-progress" --state open
   # Expected: no results
   ```

**Validation**:
- [ ] All 6 verification steps pass
- [ ] Document any deviations in `kitty-specs/.../canary-log.md` (touched in WP06)

## Definition of Done (WP05)

- [ ] `scripts/office2/deploy/felix-doc-auditor.sh` exists, is executable, and runs cleanly from a fresh office2 SSH
- [ ] Agent workspace deployed to `/data/services/openclaw/felix-doc-auditor/`
- [ ] Skill deployed to `~/.openclaw/skills/doc-audit/`
- [ ] OpenClaw recognizes `felix-doc-auditor` (`openclaw agents` lists it)
- [ ] Cron entry registered in openclaw.json (initially disabled)
- [ ] `status:in-progress` GitHub label exists
- [ ] All T021 verification steps pass

## Risks

- **openclaw.json edit risk**: a corrupt JSON breaks ALL OpenClaw agents (not just this one). Always back up first; always validate with `jq` after edit.
- **Permission mismatch**: if the deploy script runs as kgale instead of claude (or vice versa), files end up with wrong ownership. Verify with `ls -la` after deploy. The existing felix-admin-* agents are owned by claude:claude — match that.
- **Sudo requirements unclear**: T018 might hit permission errors on `/data/services/openclaw/` depending on existing directory perms. If so, surface to Kent for `ssh office2-kgale` execution.
- **OpenClaw cron service name unknown**: T019 step 6 references `systemctl reload openclaw-cron` as a placeholder. Check the actual service name on office2 (`systemctl list-units | grep openclaw`).

## Reviewer guidance

A reviewer should check:
1. Deploy script is idempotent (running twice doesn't break anything)
2. openclaw.json edit follows the structural convention of existing entries (don't invent new fields)
3. Cron is initially disabled — verify before declaring WP05 done
4. Label color and description match the R-009 contract
5. T021 verification list is exhaustive — all 6 checks should pass

## Implementation command

```bash
spec-kitty agent action implement WP05 --agent <agent-name>
```

## Activity Log

- 2026-05-10T17:17:05Z – claude:sonnet:implementer:implementer – shell_pid=45945 – Started implementation via action command
