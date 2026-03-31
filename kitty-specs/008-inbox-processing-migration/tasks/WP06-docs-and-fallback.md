---
work_package_id: WP06
title: Documentation and Fallback Verification
lane: "doing"
dependencies: [WP04]
requirement_refs:
- C-006
- FR-024
- FR-026
- FR-027
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 008-inbox-processing-migration-WP04
base_commit: aa93b5727523d7098b41cae718db38ab3f9fdc6c
created_at: '2026-03-31T04:01:10.109376+00:00'
subtasks: [T026, T027, T028]
shell_pid: "78903"
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
---

# WP06: Documentation and Fallback Verification

## Implementation Command

```bash
spec-kitty implement WP06 --base WP04
```

(WP06 depends on WP04 only. It can run in parallel with WP05.)

## Objective

Create the inbox processing ops runbook, update architecture docs with the
new agent and cron jobs, and verify the original Cowork skills are unchanged.

## Context

- **Runbook location**: `docs/handbooks/inbox-ops.md` (new file)
- **Architecture data**: `docs/design/architecture/data/service-inventory.json`
- **Architecture narrative**: `docs/design/architecture/service-inventory.md`
- **Cowork skills location**: `~/second-brain/.claude/skills/` (local Mac path)
- **Existing runbook pattern**: `docs/handbooks/vikunja-ops.md`, `docs/handbooks/openclaw-ops.md`

## Subtask Guidance

### T026: Create Inbox Operations Runbook

**Purpose**: Document how to operate, monitor, and troubleshoot inbox processing.

**Steps**:
1. Create `docs/handbooks/inbox-ops.md` with standard frontmatter:
   ```yaml
   ---
   title: Inbox Processing Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```
2. Include these sections:

   **Overview**: What the felix-admin-capture agent does, where it runs, how
   often.

   **Agent Management**:
   - Agent name: `felix-admin-capture`
   - Workspace: `/data/services/openclaw/inbox-agent/`
   - Source in repo: `scripts/openclaw/agents/felix-admin-capture/`
   - How to update workspace files (copy from repo to office2)
   - How to verify: `openclaw agents list`

   **Schedule**:
   - 3 cron jobs: inbox-morning (7 AM ET), inbox-midday (12 PM ET), inbox-evening (6 PM ET)
   - View jobs: `openclaw cron list`
   - Manual trigger: `openclaw cron run inbox-morning`
   - View run history: `openclaw cron runs inbox-morning`

   **Processing Log**:
   - Location: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
   - How to check: `ls -lt /home/kgale/second-brain/agents/logs/ | head`
   - What to look for: tasks created, items flagged, errors

   **WhatsApp Trigger**:
   - Send "process my inbox" via WhatsApp
   - Agent responds with processing summary
   - (Note: include any limitations discovered in WP05)

   **Cowork Fallback**:
   - When: office2 agent down or misconfigured
   - How: Open Claude session on Mac, invoke inbox-processor skill manually
   - Skills location: `~/second-brain/.claude/skills/`
   - Warning: do not run both simultaneously on the same inbox files

   **Troubleshooting**:
   | Symptom | Check | Fix |
   | --- | --- | --- |
   | No processing logs | `openclaw cron list`, `openclaw cron runs` | Verify cron jobs exist and are enabled |
   | Vault not accessible | `ls /home/kgale/second-brain/vault/00-Inbox/` | Check Obsidian Sync: `systemctl status obsidian-sync` |
   | Vikunja tasks not created | Processing log error section | Check vikunja_api skill and API token |
   | Agent not responding | `openclaw agents list` | Restart gateway: `systemctl --user restart openclaw-gateway` |
   | Privacy violation | Should never happen | Check AGENTS.md standing orders |

   **Privacy Boundary**:
   - Absolute rule: `02-Growth/_private/` is never touched
   - Enforced in SOUL.md, AGENTS.md, and TOOLS.md

**Validation**:
- [ ] Runbook covers all sections listed above
- [ ] Frontmatter is valid
- [ ] Follows the pattern of existing runbooks (vikunja-ops.md, openclaw-ops.md)

### T027: Update Architecture Docs

**Purpose**: Record the new agent and cron jobs in the service inventory.

**Steps**:
1. Update `docs/design/architecture/data/service-inventory.json`:
   - Add felix-admin-capture agent entry under the OpenClaw Gateway service
     (as a sub-component, similar to how the WhatsApp channel was added)
   - Add inbox-processing cron job entry under Scheduled Jobs
   - Update `last_updated` and `updated_by: "F008"`

2. Update `docs/design/architecture/service-inventory.md`:
   - Add felix-admin-capture to the OpenClaw section
   - Add inbox-processing cron to the Scheduled Jobs table
   - Include workspace path, cron schedule, and purpose

**Validation**:
- [ ] service-inventory.json updated with agent and cron entries
- [ ] service-inventory.md narrative matches JSON
- [ ] `updated_by: "F008"`

### T028: Verify Cowork Skills Unchanged

**Purpose**: Confirm the original skills are intact for fallback use.

**Steps**:
1. Verify all three skill files exist (read locally):
   ```bash
   ls -la ~/second-brain/.claude/skills/inbox-processor/SKILL.md
   ls -la ~/second-brain/.claude/skills/kent-voice/SKILL.md
   ls -la ~/second-brain/.claude/skills/vault-writer/SKILL.md
   ```
2. Verify they have not been modified during F008 implementation:
   - Check git status of the second-brain repo if available
   - Or compare file modification dates against F008 start date
3. Note in the runbook that these skills are the fallback path

**Validation**:
- [ ] All 3 Cowork skills exist and are unchanged
- [ ] Fallback documented in inbox-ops.md (T026)

## Definition of Done

- [ ] `docs/handbooks/inbox-ops.md` exists with all required sections
- [ ] `docs/design/architecture/data/service-inventory.json` updated
- [ ] `docs/design/architecture/service-inventory.md` updated
- [ ] Cowork skills verified unchanged
- [ ] All docs pass validation (frontmatter, formatting)

## Risks

- **Architecture doc conflicts**: If other features have updated
  service-inventory.json since the worktree was created, the merge may
  conflict. Resolve by taking the latest version and adding F008 entries.
