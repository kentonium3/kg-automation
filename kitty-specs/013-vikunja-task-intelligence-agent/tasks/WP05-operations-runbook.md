---
work_package_id: WP05
title: Operations Runbook
dependencies: [WP03]
requirement_refs:
- FR-023
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T023, T024, T025, T026, T027]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/handbooks/
execution_mode: code_change
owned_files: [docs/handbooks/task-intelligence-ops.md]
---

# WP05: Operations Runbook

## Objective

Create `docs/handbooks/task-intelligence-ops.md` — a complete operations runbook covering how felix-admin-tasker operates, how to invoke it manually, how to manage retroactive enrichment, how to check enrichment status, and how to troubleshoot common issues.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent (FR-023)
- **Reference runbook**: Read `docs/handbooks/vikunja-ops.md` for the established handbook format
- **Agent standing orders**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (from WP03) — the runbook documents operational procedures for this agent
- **Cron schedule**: Incomplete task detection every 4 hours (`0 */4 * * *`)

### Implementation command

```bash
spec-kitty implement WP05 --base WP03
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP03 (must know agent behavior to document it)
- **Can run in parallel with**: WP04, WP06

---

## Subtask T023: Create Runbook Structure and Overview

**Purpose**: Establish the runbook file with proper YAML frontmatter, overview, and section structure.

**Steps**:
1. Create `docs/handbooks/task-intelligence-ops.md`
2. Add YAML frontmatter:
   ```yaml
   ---
   title: "Task Intelligence Operations"
   doc_type: handbook
   status: approved
   feature: F013
   last_validated: 2026-04-02
   ---
   ```
3. Add overview section explaining:
   - What felix-admin-tasker does (one paragraph)
   - How it fits in the system (receives from capture agent, writes to Vikunja)
   - Current operating mode (Assisted — Level 1)
   - Where it runs (office2, OpenClaw)

**Validation**:
- [ ] File created with correct frontmatter
- [ ] Overview is concise and accurate

---

## Subtask T024: Document Agent Operation and Manual Invocation

**Purpose**: Document how to manually invoke the agent for each action type.

**Steps**:
1. Add **Manual Invocation** section with commands for each action:

   **Enrich a specific task**:
   ```bash
   ssh office2-claude
   openclaw agent --agent felix-admin-tasker \
     --message '{"action": "enrich_task", "raw_text": "Your task description here", "source_reference": "manual", "inferred_identity": "personal"}' \
     --json --timeout 120
   ```

   **Run retroactive enrichment**:
   ```bash
   openclaw agent --agent felix-admin-tasker \
     --message '{"action": "retroactive_enrichment", "batch_size": 3}' \
     --json --timeout 300
   ```

   **Run incomplete task detection**:
   ```bash
   openclaw agent --agent felix-admin-tasker \
     --message '{"action": "detect_incomplete"}' \
     --json --timeout 300
   ```

2. Add **Scheduled Operations** section:
   - Incomplete task detection: `0 */4 * * *` (every 4 hours)
   - Cron managed by OpenClaw: `openclaw cron list`

3. Add **Checking Agent Status**:
   - View recent logs: `cat ~/second-brain/agents/logs/task-intelligence-$(date +%Y-%m-%d).md`
   - Check cron schedule: `openclaw cron list`

**Validation**:
- [ ] All three action types have manual invocation commands
- [ ] SSH connection uses correct host (office2-claude)
- [ ] Cron schedule documented
- [ ] Log viewing command provided

---

## Subtask T025: Document Retroactive Enrichment Procedures

**Purpose**: Document how to manage retroactive enrichment — triggering batches, checking progress, pausing/resuming.

**Steps**:
1. Add **Retroactive Enrichment** section:

   **Starting a batch**:
   - Invoke with `retroactive_enrichment` action (command from T024)
   - Agent will send batch of up to 5 tasks via WhatsApp
   - Respond per task: confirm, skip, or defer

   **Checking enrichment progress**:
   - Count remaining flat tasks in Inbox:
     ```bash
     curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
       "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%201&per_page=1" \
       | python3 -c "import sys,json; print(f'Flat tasks in Inbox: {len(json.load(sys.stdin))}')"
     ```

   **Pausing enrichment**:
   - Reply "later" to any batch to pause
   - Agent will not send more batches until manually triggered again

   **Resuming enrichment**:
   - Invoke `retroactive_enrichment` action again to resume

**Validation**:
- [ ] Start, check, pause, resume procedures documented
- [ ] Commands are copy-paste ready
- [ ] WhatsApp response options documented

---

## Subtask T026: Document Skip/Defer and Enrichment State

**Purpose**: Document how to skip tasks, defer enrichment, and query enrichment state.

**Steps**:
1. Add **Skip and Defer** section:

   **Skipping a task**:
   - Reply "skip N" during a batch (N = task number)
   - Agent adds `[Felix] enrichment | skipped` comment — task won't be proposed again

   **Declining detection offers**:
   - Reply "no" when agent asks about an incomplete task
   - Agent adds `[Felix] enrichment | declined` comment — task won't be proposed again

   **Checking enrichment state for a specific task**:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/{TASK_ID}/comments" \
     | python3 -c "import sys,json; [print(c['comment']) for c in json.load(sys.stdin) if '[Felix] enrichment' in c['comment']]"
   ```

   **Re-enabling a skipped task** (manual override):
   - Delete the `[Felix] enrichment | skipped` comment via Vikunja UI
   - Next detection poll will find the task and offer enrichment again

**Validation**:
- [ ] Skip and decline procedures documented
- [ ] State query command provided
- [ ] Re-enable procedure documented

---

## Subtask T027: Document Troubleshooting

**Purpose**: Document common issues and their resolution.

**Steps**:
1. Add **Troubleshooting** section:

   **Task not being enriched**:
   - Check if task has `[Felix] enrichment | skipped/declined` comment → delete to re-enable
   - Check if task is in a project other than Inbox → detection only checks Inbox
   - Check if task is marked done → enrichment skips completed tasks
   - Check agent logs for errors: `cat ~/second-brain/agents/logs/task-intelligence-*.md | grep -i error`

   **Duplicate enrichment proposals**:
   - Check task comments for multiple `[Felix] enrichment |` entries
   - Should not happen — agent checks before proposing
   - If occurring: check that the `GET /tasks/{id}/comments` endpoint is returning all comments

   **WhatsApp conversation not arriving**:
   - Check WhatsApp channel status
   - Check agent logs for send failures
   - Verify agent is running: `openclaw agent list`

   **Agent delegation failing (capture → tasker)**:
   - Check that felix-admin-tasker agent is deployed: `openclaw agent list`
   - Check for timeout issues in capture agent logs
   - Flat tasks should still appear in Inbox (fallback)

   **Vikunja API errors**:
   - Check Vikunja service: `curl -s https://office2.tail0f5f56.ts.net/api/v1/info`
   - Check API token validity
   - Review agent logs for specific error codes

**Validation**:
- [ ] Each issue has diagnostic steps
- [ ] Commands are copy-paste ready
- [ ] Resolution steps are actionable

---

## Definition of Done

- [ ] `docs/handbooks/task-intelligence-ops.md` exists with correct frontmatter
- [ ] All five sections complete: overview, manual invocation, retroactive enrichment, skip/defer, troubleshooting
- [ ] Commands are copy-paste ready and use correct hostnames/paths
- [ ] Follows format conventions of existing handbooks (vikunja-ops.md)
- [ ] Kent can operate, monitor, and troubleshoot the agent using this runbook alone

## Risks

- Low — documentation work following established patterns.

## Reviewer Guidance

- Verify all commands work (correct paths, hostnames, API endpoints)
- Check that the runbook is self-contained (Kent shouldn't need to read AGENTS.md to operate the agent)
- Compare format against `docs/handbooks/vikunja-ops.md`
- Ensure troubleshooting covers the most likely failure modes
