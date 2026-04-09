---
work_package_id: WP03
title: Repo Sync and Validation
dependencies:
- WP02
requirement_refs:
- NFR-001
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Depends on WP02
subtasks:
- T010
- T011
- T012
history:
- date: '2026-04-09T20:07:16Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/design/architecture/service-inventory.md
tags: []
---

# WP03: Repo Sync and Validation

## Objective

Sync the updated agent files from office2 to the repo-side copies, update the service inventory documentation, and test the feature end-to-end with a real inbox note.

## Context

- WP01 and WP02 modified AGENTS.md and TOOLS.md on office2 at `/data/services/openclaw/inbox-agent/`
- Repo-side copies at `scripts/openclaw/agents/felix-admin-capture/` must be kept in sync
- Service inventory at `docs/design/architecture/service-inventory.md` describes the inbox agent
- Testing requires creating an inbox note with a GitHub issue trigger and running the agent

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP03 --agent claude`

---

## Subtask T010: Update Repo-Side Copies

**Purpose**: Keep the repo-side agent file copies in sync with what's deployed on office2.

**Steps**:
1. SSH to office2 and read the current versions:
   - `/data/services/openclaw/inbox-agent/AGENTS.md`
   - `/data/services/openclaw/inbox-agent/TOOLS.md`
2. Compare with repo-side copies at:
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
3. Update the repo-side copies to match the office2 versions
4. The office2 versions are authoritative — the repo copies are for version control and reference

**Validation**:
- [ ] Repo AGENTS.md matches office2 AGENTS.md
- [ ] Repo TOOLS.md matches office2 TOOLS.md
- [ ] Diff shows only the WP01/WP02 additions (no unrelated changes)

---

## Subtask T011: Update service-inventory.md

**Purpose**: Document the GitHub issue routing capability in the inbox agent's service inventory entry.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`
2. Find the "Felix Admin Capture Agent (F008)" section
3. Update the Purpose line to mention GitHub issue routing:
   - Before: "Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, writes processing logs"
   - After: "Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, routes GitHub issue requests to kentonium3/kg-automation, writes processing logs"
4. Keep the change minimal — one phrase addition

**Validation**:
- [ ] Service inventory entry updated with GitHub routing mention
- [ ] Change is minimal and consistent with existing style

---

## Subtask T012: Test Feature with a Real Inbox Note

**Purpose**: Verify the complete flow works end-to-end: trigger detection → issue creation → processing summary.

**Steps**:
1. Create a test inbox note on office2:
   ```bash
   ssh office2-claude
   cat > "/home/kgale/second-brain/notes/00-Inbox/Inbox $(date +%Y-%m-%d\ %H%M)-test.md" << 'EOF'
   ---
   date: $(date +%Y-%m-%d)
   time: $(date +%H:%M)
   type: inbox
   status: unprocessed
   ---

   File a github issue for adding a visual indicator in the inbox processing summary that shows which model each agent used during its run. This would help with monitoring the model tiering from issue 135.
   EOF
   ```
2. Trigger an inbox processing run:
   ```bash
   openclaw cron run <inbox-7am-cron-id>
   ```
3. Wait for the run to complete (check session files)
4. Verify:
   - [ ] The agent detected the GitHub issue trigger
   - [ ] An issue was created on kentonium3/kg-automation
   - [ ] The issue has a clean title (not raw transcription)
   - [ ] Labels are reasonable (likely P2-feature, area/felix-core or area/ea)
   - [ ] `spec: brief` label applied
   - [ ] The processing summary mentions the created issue
5. If the issue was created, check its body on GitHub:
   - [ ] Summary section present
   - [ ] Source/original text preserved
6. Clean up: if the test issue is not a real issue Kent wants, close it

**Important**: This test uses real infrastructure (creates a real GitHub issue). The test content should be something plausible that Kent might actually want, so it's useful even if kept.

**Validation**:
- [ ] End-to-end flow completed successfully
- [ ] Issue visible on GitHub with correct metadata
- [ ] Processing summary includes the issue
- [ ] If agent failed, failure mode documented for debugging

---

## Definition of Done

- [ ] Repo-side AGENTS.md and TOOLS.md match office2 versions
- [ ] Service inventory updated
- [ ] End-to-end test completed (pass or documented failure)
- [ ] All changes committed to repo

## Risks

- **Haiku can't execute gh CLI**: The agent runs on Haiku which struggled with multi-step tool workflows (mission 021). The gh call is a single command, but if it fails, document the failure mode — it may indicate that this feature needs Sonnet or simpler instructions.
- **Test creates a real issue**: Use plausible content so the issue is useful even if kept.

## Reviewer Guidance

- Verify repo copies exactly match office2 (diff should show zero differences)
- Check that the test was actually run (not just planned)
- If the test failed, review the failure mode — is it a Haiku capability issue or an instruction clarity issue?
