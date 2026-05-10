---
work_package_id: WP03
title: Governance + inventory updates
dependencies: []
requirement_refs:
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
- T013
agent: "claude:sonnet:implementer:implementer"
shell_pid: "41730"
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: docs/constitution/
execution_mode: code_change
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- docs/constitution/AGENT-REGISTRY.md
- docs/constitution/agent-registry.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/doc-domain-map.json
tags: []
---

# WP03 — Governance + inventory updates

## Objective

Register `felix-doc-auditor` in both governance (AGENT-REGISTRY.md + agent-registry.json) and operational inventories (service-inventory.json + service-inventory.md + doc-domain-map.json) per the templates in `contracts/agent-registry-entry.template.md`. Without this, the agent exists on paper in this repo but is not discoverable through canonical inventories.

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9`
- Spec: [../spec.md](../spec.md) — Architecture Impact section enumerates these files
- Plan: [../plan.md](../plan.md) — Project Structure section
- Research: [../research.md](../research.md) — R-003 (two-registration requirement), R-004 (registry entry format), R-005 (domain map structure)
- Contracts: [../contracts/agent-registry-entry.template.md](../contracts/agent-registry-entry.template.md) — authoritative entry format
- Existing patterns: `felix-admin-tasker` entry in service-inventory.json is the closest model (cron-driven OpenClaw agent); `felix-admin-capture` entry in AGENT-REGISTRY.md is the closest model for the markdown narrative section

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: per-WP worktree from `lanes.json`. Branch from `main`. Merge back via spec-kitty review/merge.

## Subtasks

### T009 — Add felix-doc-auditor entry to AGENT-REGISTRY.md

**Purpose**: Add the human-readable governance entry for the new agent. ~30 lines added to existing file.

**File**: `docs/constitution/AGENT-REGISTRY.md` (modify)

**Steps**:

1. Read the existing file to locate the insertion point. Convention: per-agent sections are grouped (e.g., all `felix-admin-*` together). Place `felix-doc-auditor` alphabetically after the felix-admin-* sections OR at the end of the agent list.

2. Use the markdown block in `contracts/agent-registry-entry.template.md` verbatim, substituting:
   - Date placeholders → 2026-05-09 (today / mission creation date)
   - Mission ID → `01KR7JK9QTHM5F4PD3YC43KDQW`
   - Mission slug → `felix-doc-auditor-agent-01KR7JK9`
   - Issue → `#105`

3. Confirm "Team" assignment. The template provisionally says "SuperAdmin (B)" — verify against existing AGENT-REGISTRY.md team taxonomy. If a different team is more appropriate, use that. Don't invent a new team.

**Validation**:
- [ ] New section appears in correct position
- [ ] All fields populated (Team, Scope, Current Autonomy Level, Model, Deployed, Registered)
- [ ] Transition History table has the registration row

---

### T010 — Add felix-doc-auditor entry to agent-registry.json

**Purpose**: Machine-readable governance entry. Mirrors T009. ~30 lines of JSON appended to the agents array.

**File**: `docs/constitution/agent-registry.json` (modify)

**Steps**:

1. Read the existing JSON to find the `agents` array (or whatever the canonical list field is — verify the schema before assuming).

2. Append the JSON block from `contracts/agent-registry-entry.template.md` (the second code block) with the same substitutions as T009.

3. Update the file's `last_updated` and `updated_by` fields to today and `#105` (or the mission identifier per existing convention).

4. Validate the JSON: `python3 -m json.tool docs/constitution/agent-registry.json > /dev/null && echo OK`

**Validation**:
- [ ] JSON parses cleanly
- [ ] New agent entry matches the markdown narrative from T009 field-for-field
- [ ] `last_updated` and `updated_by` bumped per change-control protocol

---

### T011 — Add felix-doc-auditor entry to service-inventory.json

**Purpose**: Operational inventory entry. The agent shows up here as a runtime service. ~30-40 lines of JSON appended.

**File**: `docs/design/architecture/data/service-inventory.json` (modify)

**Steps**:

1. Read the existing file. Find the `felix-admin-tasker` entry — that's the closest structural model (`type: "openclaw-cron"` with `schedules` array).

2. Append a new entry following that pattern:
   ```json
   {
     "name": "felix-doc-auditor",
     "type": "openclaw-cron",
     "host": "office2",
     "agent": "felix-doc-auditor",
     "schedules": [
       {"name": "doc-audit-poll", "cron": "0 * * * *", "local_time": "Every 60 minutes (top of each hour UTC)"}
     ],
     "timeout_seconds": 1800,
     "session_mode": "isolated",
     "deployed_by": "#105",
     "deployed_on": "2026-05-09",
     "status": "active",
     "purpose": "Documentation audit — processes Doc Audit and Weekly Doc Audit issues; classifies docs as high-confidence edit (commits directly) or judgment gap (files docs-debt issue); detects missing artifacts",
     "model": "anthropic/claude-sonnet-4-6",
     "model_policy": "pinned",
     "autonomy_level": "Assisted (Level 1)",
     "risk_tier": 3,
     "dependencies": [
       {"target": "openclaw-gateway:18789", "type": "requires", "description": "Dispatched by OpenClaw cron scheduler"},
       {"target": "doc-audit", "type": "requires", "description": "Reads ~/.openclaw/skills/doc-audit/SKILL.md at start of every audit"},
       {"target": "doc-domain-map.json", "type": "requires", "description": "Scope contract"},
       {"target": "gh-cli", "type": "requires", "description": "All GitHub interactions (issues, comments, labels)"}
     ],
     "health_check": {
       "method": "logs",
       "endpoint": "/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md",
       "expected": "regular activity entries during audit-issue presence",
       "timeout_seconds": 60
     },
     "config_files": [
       {"path": "/data/services/openclaw/felix-doc-auditor/AGENTS.md", "format": "markdown", "source_in_repo": "scripts/openclaw/agents/felix-doc-auditor/AGENTS.md"},
       {"path": "~/.openclaw/skills/doc-audit/SKILL.md", "format": "markdown", "source_in_repo": "scripts/openclaw/skills/doc-audit/SKILL.md"}
     ]
   }
   ```

3. Bump file-level `last_updated` to 2026-05-09 and `updated_by` to `issue-105-doc-auditor` (or per existing convention).

4. Validate JSON: `python3 -m json.tool docs/design/architecture/data/service-inventory.json > /dev/null`

**Validation**:
- [ ] Entry mirrors `felix-admin-tasker` structure where applicable
- [ ] Cron schedule matches NFR-001 (60-min interval)
- [ ] `dependencies` enumerates the doc-audit skill, domain map, gh CLI, openclaw-gateway
- [ ] JSON parses cleanly
- [ ] `last_updated` and `updated_by` bumped

---

### T012 — Add narrative section for felix-doc-auditor to service-inventory.md

**Purpose**: Markdown view counterpart to T011. ~15-25 lines added.

**File**: `docs/design/architecture/service-inventory.md` (modify)

**Steps**:

1. Read the existing file. Identify the section pattern (e.g., `### Felix Admin Capture Agent (F008)`) and add a new section after the existing felix-admin-* entries.

2. Compose the section:
   ```markdown
   ### Felix Doc Auditor (#105, 2026-05-09)
   - **Deployed by**: #105 / mission `felix-doc-auditor-agent-01KR7JK9`
   - **Type**: OpenClaw cron agent (sub-agent of the gateway)
   - **Agent name**: `felix-doc-auditor`
   - **Workspace**: `/data/services/openclaw/felix-doc-auditor/` (deployed from `scripts/openclaw/agents/felix-doc-auditor/`)
   - **Skill**: `~/.openclaw/skills/doc-audit/` (deployed from `scripts/openclaw/skills/doc-audit/`)
   - **Model**: `anthropic/claude-sonnet-4-6` (pinned — judgment-heavy work)
   - **Autonomy level**: Assisted (Level 1) — planned promotion to Supervised (Level 2) after ~1 week clean operation
   - **Schedule**: every 60 minutes (top of hour, UTC) via OpenClaw cron
   - **Purpose**: processes Doc Audit and Weekly Doc Audit issues automatically; commits high-confidence edits directly, files docs-debt issues for judgment items, detects missing artifacts
   - **Approval mechanism (Level 1)**: WhatsApp summary message + reply parsing (`approve`/`reject`/`skip`); 2-hour timeout = default deny
   - **Concurrency lock**: GitHub label `status:in-progress` on the in-flight audit issue
   - **Runbook**: `docs/runbooks/doc-auditor-ops.md`
   ```

**Validation**:
- [ ] Section placed appropriately in document structure
- [ ] Cross-references to runbook and skill paths are accurate
- [ ] Field-by-field consistent with T011 JSON entry

---

### T013 — Add doc-auditor-ops.md reference to doc-domain-map.json

**Purpose**: Add the new ops runbook to the domain map under `area/felix-core` so it becomes part of future audit scope. ~1 line added.

**File**: `docs/design/architecture/data/doc-domain-map.json` (modify)

**Steps**:

1. Read the existing file. Locate the `area/felix-core` array.

2. Add `"docs/runbooks/doc-auditor-ops.md"` to the array (alphabetical position).

3. Bump `last_updated` to 2026-05-09 and `updated_by` to `#105` (or per existing convention).

4. Validate JSON: `python3 -m json.tool docs/design/architecture/data/doc-domain-map.json > /dev/null`

**Validation**:
- [ ] New entry present in `area/felix-core` array
- [ ] JSON parses cleanly
- [ ] `last_updated` and `updated_by` bumped

## Definition of Done (WP03)

- [ ] All 5 files modified per their per-subtask validation
- [ ] Both JSON files (`agent-registry.json`, `service-inventory.json`, `doc-domain-map.json`) validate via `python3 -m json.tool`
- [ ] Markdown narratives (`AGENT-REGISTRY.md`, `service-inventory.md`) match the JSON entries field-for-field
- [ ] All file-level `last_updated`/`updated_by` fields bumped per change-control protocol

## Risks

- **JSON syntax errors** are easy to introduce. Always run `python3 -m json.tool <file> > /dev/null` after each edit.
- **Drift between markdown and JSON** — both are owned by this WP and must stay in sync. After all edits, re-read the markdown narrative against the JSON entry and reconcile any differences.
- **Team taxonomy** — the template uses "SuperAdmin (B)" as a placeholder. If the existing AGENT-REGISTRY.md uses a different team for similar agents, follow that convention.

## Reviewer guidance

A reviewer should check:
1. All five files modified, no others
2. JSON files validate
3. Field-for-field consistency between markdown and JSON for the same agent
4. New agent entry follows the structural patterns of existing felix-admin-* entries
5. `risk_tier` value (3) matches the change-risk taxonomy for "Logic/Workflow" tier
6. `model` field uses the latest available Sonnet revision (verify against memory: `anthropic/claude-sonnet-4-6` is current per memory; `4-7` may exist by execution time — use the latest pinnable revision)

## Implementation command

```bash
spec-kitty agent action implement WP03 --agent <agent-name>
```

## Activity Log

- 2026-05-10T16:58:11Z – claude:sonnet:implementer:implementer – shell_pid=41730 – Started implementation via action command
- 2026-05-10T17:02:22Z – claude:sonnet:implementer:implementer – shell_pid=41730 – Ready for review: 5 file modifications per contracts/agent-registry-entry.template.md and WP prompt JSON spec. Both JSON files validate cleanly. Markdown narratives match JSON authoritative.
