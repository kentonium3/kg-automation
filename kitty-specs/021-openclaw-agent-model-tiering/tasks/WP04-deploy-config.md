---
work_package_id: WP04
title: Deploy Tiered Configuration
dependencies: [WP02, WP03]
requirement_refs:
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T013, T014, T015, T016]
history:
- date: '2026-04-09T17:18:21Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/021-openclaw-agent-model-tiering/artifacts/
execution_mode: planning_artifact
owned_files:
- kitty-specs/021-openclaw-agent-model-tiering/artifacts/deploy-report.md
---

# WP04: Deploy Tiered Configuration

## Objective

Apply the validated model tier assignments to the production `openclaw.json` on office2. Change the global default to Haiku, update each agent's model field, restart OpenClaw, and verify all agents function correctly on their assigned models.

## Context

- Config file: `/home/claude/.openclaw/openclaw.json` on office2
- Backup created in WP01: `/home/claude/.openclaw/openclaw.json.backup.2026-04-09`
- Validation results from WP02 (inbox) and WP03 (habits, escalation) drive which agents move to Haiku
- `felix-admin-tasker` and `main` are pre-classified as Sonnet (pinned) — no validation needed
- Access via `ssh office2-claude`
- This is Tier 2 — backup confirmed in WP01

**CRITICAL**: Read the validation report from WP03 (T012) before making any changes. The model assignments depend entirely on validation results.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP04 --base WP03`

---

## Subtask T013: Set Global Default to Haiku

**Purpose**: Change the global default model so new agents default to the cheapest viable model.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Edit `/home/claude/.openclaw/openclaw.json`
3. Change `agents.defaults.model.primary` from `anthropic/claude-sonnet-4-6` to `anthropic/claude-haiku-4-5`
4. Also update `agents.defaults.models` to include Haiku:
   ```json
   "models": {
     "anthropic/claude-haiku-4-5": {},
     "anthropic/claude-sonnet-4-6": {}
   }
   ```
5. Do NOT change individual agent model fields yet (that's T014)

**Validation**:
- [ ] Global default changed to Haiku
- [ ] Models list includes both Haiku and Sonnet

---

## Subtask T014: Update Per-Agent Model Fields

**Purpose**: Apply validated model assignments to each agent.

**Steps**:
1. Read the validation report from WP03 (T012) for final model assignments
2. For each agent in `agents.list`, set the `model` field:

   **Pre-classified (no validation needed):**
   - `main`: Keep `anthropic/claude-sonnet-4-6` (orchestrator, pinned)
   - `felix-admin-tasker`: Keep `anthropic/claude-sonnet-4-6` (complex reasoning, pinned)

   **Based on validation results:**
   - `felix-admin-capture`: Set to Haiku if WP02 passed, keep Sonnet if failed
   - `felix-admin-habits`: Set to Haiku if WP03 passed for BOTH daily and weekly, keep Sonnet if either failed
   - `felix-admin-escalation`: Set to Haiku if WP03 passed, keep Sonnet if failed or uncertain

3. If an agent doesn't have a `model` field (like `main` which only has `"id": "main"`), add one explicitly
4. Verify the complete JSON is valid after editing (no syntax errors)

**Important**: The `main` agent currently has no `model` field — it inherits the global default. After T013 changes the default to Haiku, `main` would also default to Haiku. You MUST add an explicit `"model": "anthropic/claude-sonnet-4-6"` to the `main` agent entry to keep it on Sonnet.

**Validation**:
- [ ] Each agent has an explicit `model` field (no reliance on global default for Sonnet agents)
- [ ] Assignments match validation results
- [ ] JSON is syntactically valid
- [ ] `main` agent explicitly set to Sonnet (not inheriting Haiku default)

---

## Subtask T015: Restart OpenClaw and Verify

**Purpose**: Apply the config changes and verify each agent picks up its new model.

**Steps**:
1. Determine how to restart or reload OpenClaw on office2:
   - Check if there's a systemd service: `systemctl --user status openclaw` or `systemctl status openclaw`
   - Check if OpenClaw has a reload command
   - If running in Docker, check `docker ps` for OpenClaw container
2. Restart the service
3. After restart, verify:
   - OpenClaw is running and healthy
   - Check logs for model initialization messages (if available)
   - If possible, trigger a lightweight run of one agent and confirm the model used in the session
4. Verify the config file was not overwritten by the restart (re-read and confirm)

**Validation**:
- [ ] OpenClaw restarted successfully
- [ ] Service is healthy post-restart
- [ ] Config file preserved after restart
- [ ] At least one agent verified to be using its assigned model

---

## Subtask T016: Monitor First Scheduled Execution

**Purpose**: Verify that the first real scheduled execution of each agent uses the correct model and produces expected output.

**Steps**:
1. Wait for the next scheduled agent run (or manually trigger one per agent)
2. Check session logs after each run:
   - Verify the model field in the session metadata matches the assigned model
   - Verify the agent completed its task successfully
   - Compare output quality to the validation baseline
3. For agents moved to Haiku: confirm output quality is consistent with validation results
4. For agents remaining on Sonnet: confirm they're still using Sonnet (not accidentally on Haiku)
5. If any agent fails or produces degraded output:
   - Revert that agent's model to Sonnet in `openclaw.json`
   - Document the failure
   - The other agents can remain on their assigned models

**Validation**:
- [ ] Each agent's first post-change run verified
- [ ] Model used matches assignment
- [ ] Output quality consistent with validation
- [ ] No unexpected failures
- [ ] Any rollbacks documented

---

## Definition of Done

- [ ] Global default changed to Haiku
- [ ] All agents have explicit model assignments based on validation results
- [ ] `main` agent explicitly pinned to Sonnet
- [ ] OpenClaw restarted and healthy
- [ ] First scheduled execution of each agent verified
- [ ] No quality regressions observed

## Risks

- **Config syntax error breaks OpenClaw**: Backup exists from WP01; restore if needed
- **`main` agent inherits Haiku default**: MUST add explicit Sonnet model field to `main` entry
- **OpenClaw ignores per-agent model field**: If this happens, the native support assumption is wrong — escalate to Kent
- **Agent fails on first real run**: Revert individual agent to Sonnet; document failure

## Rollback Plan

If anything goes wrong:
1. Restore backup: `cp /home/claude/.openclaw/openclaw.json.backup.2026-04-09 /home/claude/.openclaw/openclaw.json`
2. Restart OpenClaw
3. Verify all agents running on Sonnet (pre-change state)

## Reviewer Guidance

- Verify `main` has an explicit Sonnet model field (most likely source of bugs)
- Check that the JSON is valid — a syntax error could take down all agents
- Confirm validation results were actually consulted (not just assumed)
- Verify first-run monitoring actually happened (not just "assumed working")
