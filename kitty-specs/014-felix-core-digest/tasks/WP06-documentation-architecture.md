---
work_package_id: WP06
title: Documentation and Architecture
dependencies: [WP05]
requirement_refs:
- FR-22
- FR-24
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 014-felix-core-digest-WP05
base_commit: 861d1f1401a2975ed369677125eac0ea60285256
created_at: '2026-04-04T16:19:37.192830+00:00'
subtasks: [T026, T027, T028, T029, T030, T031, T032]
shell_pid: "99713"
agent: "claude"
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- docs/handbooks/observation-ops.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
---

# WP06: Documentation and Architecture

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP05 (infrastructure deployed — docs describe deployed state)
- **Implementation command**: `spec-kitty implement WP06 --base WP05`

## Objective

Create the operations runbook and update all architecture documentation to
accurately reflect the deployed system. JSON files are the authoritative
record; Markdown files are narrative views that must match.

**Standing directive**: Architecture docs must reflect the actual deployed
state. This WP is the final step — it documents what was built.

## Context

### Architecture Documentation Structure

```
docs/design/architecture/
├── data/
│   ├── service-inventory.json    ← authoritative JSON
│   └── data-flows.json           ← authoritative JSON
├── service-inventory.md          ← narrative view
├── data-flows.md                 ← narrative view
└── change-control.md             ← update protocol
```

### Existing Service Types in service-inventory.json

Read the file first to understand the current schema. Entries include:
- Docker services (Vikunja)
- systemd units (obsidian-sync, second-brain-sync, openclaw-gateway)
- OpenClaw cron jobs (inbox-processing, habit-checkin, task-detection)
- System cron jobs (restic-backup, security-monitor)

felix-core-digest goes in as a **systemd timer** (type "cron" or similar —
match the pattern used by existing scheduled entries).

### Constraint C-04 Reminder

felix-core-digest is registered in `service-inventory.json`, NOT in
`AGENT-REGISTRY.md`. The agent registry is for Claude agents with governance
concerns. summarize.py is deterministic Python with no autonomy, no
stochastic behavior, and no constitutional compliance needs.

---

## Subtask T026: Create Operations Runbook

**Purpose**: Enable Kent to monitor, troubleshoot, and adjust the observation
layer without reading code.

**Steps**:
1. Create `docs/handbooks/observation-ops.md`
2. Include all required sections:

**Reading Digests in Obsidian**:
- Path: `Agent-Logs/` in the vault
- `overview.md` — consolidated daily summary
- `{agent-name}/YYYY-MM-DD-log.md` — per-agent detail
- Digests refresh within 15 minutes of agent activity
- Retention: last 5 days visible; older files auto-deleted

**Accessing Raw JSONL on office2**:
- Path: `~/second-brain/agents/logs/{agent-name}/YYYY-MM-DD.jsonl`
- Read with: `cat` / `jq` / `python -m json.tool`
- One JSON object per line; each line is one agent action
- Useful for debugging or auditing individual entries

**Changing Verbosity**:
- Edit `docs/constitution/agent-registry.json`
- Set `log_verbosity` to `brief`, `standard`, or `verbose`
- Deploy updated registry: `scp docs/constitution/agent-registry.json office2-claude:~/repos/kg-automation/docs/constitution/`
- Effects: brief (required fields only), standard (+ context), verbose (+ trace debugging)
- Recommendation: Use `verbose` only during active debugging; return to `standard` after

**Verifying the Timer**:
- `ssh office2-claude 'systemctl --user list-timers'`
- `ssh office2-claude 'systemctl --user status felix-core-digest.timer'`
- `ssh office2-claude 'journalctl --user -u felix-core-digest.service --since today'`

**Running Manually**:
- Dry run: `ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --dry-run'`
- Live run: `ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py'`
- Specific date: `ssh office2-claude 'python3 ~/repos/.../summarize.py --date 2026-04-03'`

**Troubleshooting**:
- **No digests appearing**: Check timer is running, check JSONL files exist, check Obsidian Sync status
- **Parse errors in journal**: Malformed JSONL line — check raw log file, correct the agent instruction
- **Stale output**: Idempotency check may be skipping — check JSONL mtime vs digest mtime
- **Missing agent**: Verify agent is in registry and has log_verbosity field

**Architecture Note**:
- `log_action.py` is a utility script, not a service — no monitoring needed
- Agents call it via OpenClaw exec tool during runs
- If an agent fails to call log_action.py, the action is simply not logged (no cascading failure)

**Files**: `docs/handbooks/observation-ops.md` (new)

**Validation**:
- [ ] All FR-22 topics covered
- [ ] Commands are copy-pasteable
- [ ] No code reading required to use the runbook

---

## Subtask T027: Update service-inventory.json

**Purpose**: Add felix-core-digest as a scheduled service.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Add a new entry for felix-core-digest matching the existing schema
3. Key fields:
   - Service name: `felix-core-digest`
   - Type: Match existing scheduled entry pattern (check how restic-backup or security-monitor are typed)
   - Description: `Agent activity log summarization — reads JSONL, generates Markdown digests`
   - Schedule: `Every 15 minutes (systemd user timer)`
   - User: `claude`
   - ExecStart: `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/observation/summarize.py`
   - Deployed by: `F014`
   - `updated_by`: `"F014"`
4. Update root-level metadata (`updated`, `updated_by`)

**Files**: `docs/design/architecture/data/service-inventory.json`

**Validation**:
- [ ] Entry matches existing schema pattern
- [ ] `updated_by: "F014"` set
- [ ] JSON is valid

---

## Subtask T028: Update data-flows.json

**Purpose**: Add the observation intelligence layer data flow.

**Steps**:
1. Read `docs/design/architecture/data/data-flows.json`
2. Add a new flow entry:
   - Flow name: `observation-digest` or `agent-log-digest`
   - Source: Agent (via log_action.py) → JSONL files
   - Processing: summarize.py (15-min cron)
   - Destination: Obsidian vault (Agent-Logs/ Markdown)
   - Direction: One-way (agent → digest)
   - Deployed by: `F014`
3. Update root-level metadata

**Files**: `docs/design/architecture/data/data-flows.json`

**Validation**:
- [ ] Flow entry matches existing schema
- [ ] Complete chain documented: agent → JSONL → summarize.py → Markdown → Obsidian
- [ ] JSON is valid

---

## Subtask T029: Update service-inventory.md

**Purpose**: Narrative view must match JSON source.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`
2. Add felix-core-digest under the appropriate section (Scheduled Services or similar)
3. Include: description, schedule, user, path, deployed by
4. Match the level of detail of existing entries

**Files**: `docs/design/architecture/service-inventory.md`

**Validation**:
- [ ] Entry matches JSON source content
- [ ] Placed in correct section

---

## Subtask T030: Update data-flows.md

**Purpose**: Narrative view must match JSON source.

**Steps**:
1. Read `docs/design/architecture/data-flows.md`
2. Add the observation digest flow
3. Include a description of the full chain: agent action → log_action.py → JSONL → summarize.py → Markdown digest → Obsidian Sync → Kent's devices
4. Match the level of detail of existing flow descriptions

**Files**: `docs/design/architecture/data-flows.md`

**Validation**:
- [ ] Flow description matches JSON source
- [ ] Full chain documented

---

## Subtask T031: Verify JSON-Markdown Consistency

**Purpose**: Cross-verify that narrative Markdown accurately reflects
authoritative JSON.

**Steps**:
1. Compare `service-inventory.json` felix-core-digest entry against
   `service-inventory.md` section
2. Compare `data-flows.json` observation-digest entry against
   `data-flows.md` section
3. Verify all fields present in JSON are reflected in Markdown
4. Flag any discrepancies

**Files**: No changes — verification only

**Validation**:
- [ ] service-inventory JSON ↔ MD consistent
- [ ] data-flows JSON ↔ MD consistent

---

## Subtask T032: Cross-Verify Deployed State

**Purpose**: Final check that architecture docs reflect what's actually deployed.

**Steps**:
1. Verify felix-core-digest in service-inventory matches the actual
   timer/service files created in WP05
2. Verify data flow description matches the actual code paths in
   log_action.py (WP02) and summarize.py (WP03)
3. Verify no stale references to old output paths (`00-System/agent-activity/`)
   remain in architecture docs
4. Verify AGENT-REGISTRY.md does NOT contain a felix-core-digest entry
   (constraint C-04)

**Files**: No changes — verification only

**Validation**:
- [ ] Timer/service matches docs
- [ ] Data flow matches code
- [ ] No stale path references
- [ ] AGENT-REGISTRY.md unchanged (no felix-core-digest entry)

---

## Definition of Done

- [ ] `observation-ops.md` created with all FR-22 required topics
- [ ] `service-inventory.json` updated with `updated_by: "F014"`
- [ ] `data-flows.json` updated with observation flow
- [ ] `service-inventory.md` matches JSON source
- [ ] `data-flows.md` matches JSON source
- [ ] JSON ↔ Markdown consistency verified
- [ ] Deployed state matches documentation
- [ ] AGENT-REGISTRY.md NOT modified (C-04)

## Risks

- **Schema mismatch**: service-inventory.json and data-flows.json may have evolved
  since the plan was written. Read current files before writing.
- **Stale references**: Old output path may appear in existing docs. Grep for
  `00-System/agent-activity` and remove if found in architecture docs.

## Reviewer Guidance

1. Verify ops runbook is usable without code knowledge
2. Verify JSON files are valid after edits
3. Verify Markdown matches JSON content exactly
4. Confirm AGENT-REGISTRY.md was NOT modified
5. Grep for `00-System/agent-activity` — should not appear in updated docs

## Activity Log

- 2026-04-04T16:19:37Z – claude – shell_pid=99713 – Started implementation via workflow command
- 2026-04-04T16:48:10Z – claude – shell_pid=99713 – All 7 subtasks done. Runbook, JSON, and Markdown architecture docs updated.
