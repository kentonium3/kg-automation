---
work_package_id: WP04
title: Deployment, Verification, and Documentation
lane: "for_review"
dependencies: [WP02, WP03]
requirement_refs:
- FR-021
- FR-022
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 007-vikunja-api-skill-WP02
base_commit: af03d7e8eb1d51e02a4268da40507fd8d0a556de
created_at: '2026-03-30T23:31:31.907525+00:00'
subtasks: [T015, T016, T017, T018, T019, T020]
agent: claude-opus
shell_pid: '33890'
history:
- date: '2026-03-30T22:03:15Z'
  event: created
  actor: claude
---

# WP04: Deployment, Verification, and Documentation

## Implementation Command

```bash
spec-kitty implement WP04 --base WP03
```

(WP04 depends on both WP02 and WP03. Use --base WP03 if WP03 was the last
merged, or --base WP02 if WP02 was last. The merge will integrate both.)

## Objective

Deploy the completed SKILL.md to office2, verify it loads in OpenClaw,
run end-to-end tests against live Vikunja, and update operational documentation.

## Context

- **SKILL.md**: `scripts/openclaw/skills/vikunja-api/SKILL.md` (complete after WP02+WP03)
- **Deploy target**: `~/.openclaw/skills/vikunja-api/SKILL.md` on office2
- **SSH**: `ssh office2-claude` (agents must use claude user)
- **OpenClaw ops**: `docs/handbooks/openclaw-ops.md`
- **Vikunja ops**: `docs/handbooks/vikunja-ops.md`

## Subtask Guidance

### T015: Deploy Skill to office2

**Purpose**: Copy the SKILL.md to the OpenClaw skills directory on office2.

**Steps**:
1. Create the skill directory on office2:
   ```bash
   ssh office2-claude "mkdir -p ~/.openclaw/skills/vikunja-api"
   ```
2. Copy the SKILL.md:
   ```bash
   ssh office2-claude "cat > ~/.openclaw/skills/vikunja-api/SKILL.md" \
     < scripts/openclaw/skills/vikunja-api/SKILL.md
   ```
3. Verify the file was written:
   ```bash
   ssh office2-claude "head -5 ~/.openclaw/skills/vikunja-api/SKILL.md"
   ```

**Validation**:
- [ ] SKILL.md exists at `~/.openclaw/skills/vikunja-api/SKILL.md` on office2
- [ ] File contents match the repo version

### T016: Verify Skill Appears in OpenClaw

**Purpose**: Confirm OpenClaw recognizes the skill.

**Steps**:
1. Check if the skills watcher picks it up automatically (default: enabled):
   ```bash
   ssh office2-claude "openclaw skills list" | grep vikunja
   ```
2. If not visible, start a new session:
   ```bash
   ssh office2-claude "openclaw gateway restart"
   ```
3. Re-check:
   ```bash
   ssh office2-claude "openclaw skills list" | grep vikunja
   ```
4. Expected output: `✓ ready  │ vikunja_api` (or similar)

5. Get detailed info:
   ```bash
   ssh office2-claude "openclaw skills info vikunja_api"
   ```

**Validation**:
- [ ] Skill appears in `openclaw skills list` as ready
- [ ] `openclaw skills info` shows correct description and path

### T017: End-to-End CRUD Test

**Purpose**: Verify the full task lifecycle works through the skill.

**Steps**:
1. Test via `openclaw agent --message` or by running the curl commands directly.
   The curl approach is more reliable for verification:

   **Create a test task**:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"title\": \"F007 verification test task\", \"description\": \"Created by F007 deployment test\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/11/tasks'
   ```
   Save the returned task ID.

   **Add a label**:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"label_id\": 3}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/labels'
   ```

   **Read it back**:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID'
   ```
   Verify: title, description, labels include metalcasework.

   **Update it**:
   ```bash
   ssh office2-claude 'curl -s -X POST \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"description\": \"Updated by F007 test\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID'
   ```

   **Add a comment**:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"comment\": \"[Felix] End-to-end test comment from F007 deployment\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/comments'
   ```

   **Mark complete**:
   ```bash
   ssh office2-claude 'curl -s -X POST \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"done\": true}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID'
   ```

   **Delete** (clean up test data):
   ```bash
   ssh office2-claude 'curl -s -X DELETE \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID'
   ```

2. Verify each step returns expected status codes and response shapes.

**Validation**:
- [ ] Create returns task with ID
- [ ] Label assignment succeeds
- [ ] Read returns task with correct fields and label
- [ ] Update changes description
- [ ] Comment appears with [Felix] prefix
- [ ] Complete sets done=true
- [ ] Delete removes the task

### T018: Verify Goals Filter

**Purpose**: Confirm the Goals filter returns active goal declarations.

**Steps**:
1. Query active goals:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%2011&sort_by=due_date&order_by=asc"'
   ```
2. If goal declarations from F006 exist, verify they appear in the response
3. If no goals exist yet, create a test goal, verify it appears, then clean up

**Validation**:
- [ ] Goals filter query executes without error
- [ ] Response includes task metadata needed for briefings (title, due_date, labels)

### T019: Update Ops Runbook

**Purpose**: Add Vikunja API skill documentation to the ops runbook.

**Steps**:
1. Update `docs/handbooks/vikunja-ops.md` with:
   - New section: "Vikunja API Skill (F007)"
   - Skill location on office2: `~/.openclaw/skills/vikunja-api/SKILL.md`
   - Skill source in repo: `scripts/openclaw/skills/vikunja-api/SKILL.md`
   - How to update the skill: copy from repo to office2
   - How to verify: `openclaw skills list | grep vikunja`
   - Troubleshooting: skill not loading, auth errors, API errors

2. Update `docs/handbooks/openclaw-ops.md`:
   - Update the Skill Directory section to list vikunja-api as an installed skill
   - Update the note that says "No custom skills are installed in F002"

**Validation**:
- [ ] vikunja-ops.md has skill documentation
- [ ] openclaw-ops.md skill directory section updated
- [ ] Update procedure documented
- [ ] Troubleshooting section included

### T020: Update Architecture Docs (if needed)

**Purpose**: Update architecture documentation if any JSON data files need changes.

**Steps**:
1. Check if `docs/design/architecture/data/data-flows.json` needs a new flow
   entry for OpenClaw → Vikunja API. Currently the only Vikunja flow is
   browser → Vikunja UI. The skill adds: OpenClaw agent → Vikunja API.

2. If adding a new data flow:
   - Add to `data-flows.json`: new flow entry for openclaw-vikunja-api
   - Update `data-flows.md` narrative
   - Update `data-flows.view.md` Mermaid diagram

3. Check `credential-manifest.json` — the vikunja-api token is already
   documented there. Verify F007 is noted as a consumer.

4. Update `last_updated` and `updated_by` fields on any changed JSON files.

**Validation**:
- [ ] Data flow for OpenClaw → Vikunja API documented (if applicable)
- [ ] Credential manifest notes F007 as consumer
- [ ] All changed architecture files have updated timestamps

## Definition of Done

- [ ] Skill deployed to office2 at `~/.openclaw/skills/vikunja-api/SKILL.md`
- [ ] `openclaw skills list` shows vikunja_api as ready
- [ ] Full CRUD round-trip verified against live Vikunja
- [ ] Goals filter returns expected results
- [ ] vikunja-ops.md updated with skill documentation
- [ ] openclaw-ops.md skill directory updated
- [ ] Architecture docs updated if applicable

## Risks

- **Gateway restart may be needed**: If the skills watcher doesn't pick up
  the new skill automatically, a gateway restart is required. This is a
  `systemctl --user restart openclaw-gateway` — no sudo needed.
- **Test data cleanup**: Ensure all test tasks are deleted after verification.
  Don't leave test data in Vikunja.
- **openclaw agent --message may not work as expected**: If the agent doesn't
  invoke the skill on a natural language message, fall back to direct curl
  verification. The skill is still valid even if agent routing needs tuning.

## Activity Log

- 2026-03-30T23:31:32Z – claude-opus – shell_pid=33890 – lane=doing – Assigned agent via workflow command
- 2026-03-30T23:37:57Z – claude-opus – shell_pid=33890 – lane=for_review – Ready for review: Skill deployed to office2, E2E CRUD verified, Goals filter returns 3 goals, runbooks and architecture updated
