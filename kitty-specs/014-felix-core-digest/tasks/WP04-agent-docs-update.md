---
work_package_id: WP04
title: Agent AGENTS.md Updates
dependencies: [WP02]
requirement_refs:
- FR-16
- FR-17
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 014-felix-core-digest-WP02
base_commit: 0cd529e780b8fd84a3aad9a96bef737d873b0b21
created_at: '2026-04-04T15:38:48.993549+00:00'
subtasks: [T018, T019, T020, T021]
shell_pid: "95751"
agent: "claude"
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
---

# WP04: Agent AGENTS.md Updates

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP02 (log_action.py must exist so AGENTS.md can reference it)
- **Implementation command**: `spec-kitty implement WP04 --base WP02`

## Objective

Update all three deployed agents' Action Logging sections to reference
`log_action.py` via the OpenClaw `exec` tool. Each agent gets per-agent
action types and categories documented. No fields are silently dropped —
every currently-recorded field maps to a `log_action.py` argument.

## Context

### How Agents Will Call log_action.py

Via OpenClaw's `exec` tool during a run:
```bash
python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-capture \
  --category routine \
  --action file_processed \
  --target "Inbox 2026-04-04 0715.md" \
  --outcome completed \
  --context '{"vikunja_task_id": 42}'
```

The agent determines WHAT to log (the action, target, outcome, category).
`log_action.py` handles HOW (timestamp, run_id, schema, file path, verbosity).

### Field Mapping Reference

See `kitty-specs/014-felix-core-digest/research.md` section R4 for the
complete field mapping from old Markdown format to new log_action.py arguments.

---

## Subtask T018: Update felix-admin-capture AGENTS.md

**Purpose**: Replace the Processing Log section with log_action.py instructions.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
2. Find the Processing Log / Action Logging section (around line 276)
3. Replace it with a new Action Logging section:

**New section content**:
```markdown
## Action Logging

Log every significant action using the `exec` tool to call `log_action.py`:

```bash
python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-capture \
  --category <category> \
  --action <action> \
  --target <target> \
  --outcome <outcome> \
  --context '<json>'
```

### Action Types

| Action | When | Category |
|---|---|---|
| `scan_inbox` | Start of inbox scan | routine |
| `file_processed` | File successfully classified and routed | routine |
| `note_created` | New note created in vault | routine |
| `note_updated` | Existing note updated | routine |
| `task_created` | Vikunja task created | routine |
| `task_delegated` | Task delegated to felix-admin-tasker | routine |
| `goal_routed` | Goal content routed to appropriate location | routine |
| `item_flagged` | Content flagged for human review | flagged |
| `delegation_failed` | Task delegation to tasker failed | error |
| `file_locked` | File operation blocked by lock | error |
| `privacy_boundary` | Content references private path — halted | security |

### Context Fields

| Field | Type | When Used |
|---|---|---|
| `source_file` | string | Always — inbox filename being processed |
| `vikunja_task_id` | int | When a Vikunja task is created |
| `project` | string | When routing to a specific project |
| `flagged_reason` | string | When category is "flagged" |
| `error_detail` | string | When category is "error" |

### What Changed (F014)

Previously, this agent wrote a free-form Markdown log to
`~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md` with
frontmatter, section headers, and summary counts. That format is
replaced by structured log_action.py calls. Summary counts are no
longer written by the agent — they are derived by `summarize.py`
from the JSONL action stream.
```

4. Preserve all other sections of AGENTS.md unchanged

**Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] New section references log_action.py
- [ ] All previously-logged data has a mapping (see research R4)
- [ ] Action types cover all operations the agent performs
- [ ] No other AGENTS.md sections modified

---

## Subtask T019: Update felix-admin-habits AGENTS.md

**Purpose**: Add an Action Logging section for operational activity logging.
Note: the Vikunja comment-based state tracking is UNCHANGED by F014.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
2. Add a new Action Logging section (this agent may not have one currently, or
   it may be minimal since it uses Vikunja comments for state)
3. Clarify the distinction:
   - **Vikunja comments** = habit state tracking (complete/rescheduled/will-not-do) — unchanged
   - **log_action.py calls** = operational activity logging (what the agent did during a run)

**New section content**:
```markdown
## Action Logging

Log every significant operational action using the `exec` tool:

```bash
python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-habits \
  --category <category> \
  --action <action> \
  --target <target> \
  --outcome <outcome> \
  --context '<json>'
```

**Note**: This is operational logging (what the agent did). Habit state
tracking via Vikunja comments (`[Felix] YYYY-MM-DD | state | note`) is
unchanged and remains the authoritative record of habit completion.

### Action Types

| Action | When | Category |
|---|---|---|
| `morning_checkin` | Morning habit check-in run started | routine |
| `habit_queried` | Habit status queried from Vikunja | routine |
| `habit_recorded` | Habit completion recorded via comment | routine |
| `report_generated` | Weekly pattern report generated | routine |
| `report_delivered` | Report sent via WhatsApp | routine |
| `declining_trend` | Habit shows declining completion trend | flagged |
| `api_error` | Vikunja API call failed | error |

### Context Fields

| Field | Type | When Used |
|---|---|---|
| `habit_count` | int | Number of habits checked |
| `habit_name` | string | When flagging a specific habit |
| `completion_rate` | string | In reports and trend flags |
| `channel` | string | Delivery channel (e.g., "whatsapp") |

### What Changed (F014)

Previously, this agent had no file-based action log — all state was
tracked via Vikunja comments. F014 adds operational activity logging
via log_action.py to support the observation intelligence layer.
Vikunja comment format is unchanged.
```

**Files**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`

**Validation**:
- [ ] Clear distinction between Vikunja comments and log_action.py
- [ ] Vikunja comment section unchanged
- [ ] Action types cover operational activities
- [ ] No other AGENTS.md sections modified

---

## Subtask T020: Update felix-admin-tasker AGENTS.md

**Purpose**: Replace the Action Logging section with log_action.py instructions.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
2. Find the Action Logging section (around line 402)
3. Replace with:

**New section content**:
```markdown
## Action Logging

Log every significant action using the `exec` tool:

```bash
python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
  --agent felix-admin-tasker \
  --category <category> \
  --action <action> \
  --target <target> \
  --outcome <outcome> \
  --context '<json>'
```

### Action Types

| Action | When | Category |
|---|---|---|
| `task_proposed` | Enrichment proposal sent to Kent | routine |
| `task_confirmed` | Task confirmed and created in Vikunja | routine |
| `task_skipped` | Proposal skipped by Kent | routine |
| `task_declined` | Proposal declined by Kent | routine |
| `batch_enrichment_started` | Retroactive enrichment batch initiated | routine |
| `batch_enrichment_completed` | Retroactive batch finished | routine |
| `detection_poll` | Detection polling run completed | routine |
| `incomplete_detected` | Incomplete task found and flagged | flagged |
| `api_error` | Vikunja API call failed | error |
| `enrichment_failed` | Task enrichment operation failed | error |

### Context Fields

| Field | Type | When Used |
|---|---|---|
| `vikunja_task_id` | int | When a task is created or enriched |
| `task_title` | string | Target task being operated on |
| `batch_count` | int | Number of tasks in enrichment batch |
| `per_task_outcomes` | string | Summary of batch results |
| `incomplete_count` | int | Tasks found in detection polling |
| `proposed_count` | int | Proposals generated from detection |
| `error_detail` | string | Error description when category is error |

### What Changed (F014)

Previously, this agent wrote a structured Markdown log to
`~/second-brain/agents/logs/task-intelligence-YYYY-MM-DD.md` with
per-entry sections containing Agent, Autonomy level, Action, Target,
Outcome, and Details fields. Those fields now map to log_action.py
arguments: Action→--action, Target→--target, Outcome→--outcome,
Details→--context. Autonomy level and timestamp are read from the
registry and generated by log_action.py respectively.
```

**Files**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`

**Validation**:
- [ ] All old fields mapped (see research R4 mapping table)
- [ ] Action types match existing operations
- [ ] "What Changed" section explains migration clearly

---

## Subtask T021: Cross-Verify Field Mappings

**Purpose**: Final verification that no data is silently dropped in the
transition from old formats to new.

**Steps**:
1. Read `kitty-specs/014-felix-core-digest/research.md` section R4
2. For each agent, verify every field in the "Current Field" column has a
   corresponding entry in the new Action Logging section:

   **felix-admin-tasker**: HH:MM→ts, action_type→action, Agent→agent,
   Autonomy level→autonomy_level (registry), Action→action, Target→target,
   Outcome→outcome, Details→context

   **felix-admin-capture**: timestamp→ts, Files processed→target per entry,
   Actions taken→action+target, Tasks created→action+context.vikunja_task_id,
   Items flagged→category:flagged, Summary counts→derived by summarize.py

   **felix-admin-habits**: Date→ts, State→not applicable (Vikunja comments unchanged),
   operational actions→new log_action.py calls

3. Document any field that cannot be mapped and explain why (e.g., summary
   counts are derived, not logged directly)

**Files**: No file changes — this is a verification step

**Validation**:
- [ ] Every field in research R4 "Current Field" column accounted for
- [ ] Any unmapped fields have documented rationale
- [ ] No data silently dropped

---

## Definition of Done

- [ ] All three AGENTS.md files updated with log_action.py references
- [ ] Per-agent action type and category tables documented
- [ ] Field mapping verified against research R4 — no data dropped
- [ ] Vikunja comment format in habits agent unchanged
- [ ] No other AGENTS.md sections modified beyond Action Logging

## Risks

- **Habits agent**: Must be clear that Vikunja comment-based state tracking
  is separate from operational logging. Don't confuse the two.
- **Tasker field mapping**: The old format had "Details" as a catch-all.
  Make sure it maps cleanly to --context JSON.

## Reviewer Guidance

1. For each agent, cross-reference the old Action Logging section against the new one
2. Verify every previously-logged field has a mapping
3. Check that the habits agent Vikunja comment section is untouched
4. Verify exec tool command syntax is correct for each agent

## Activity Log

- 2026-04-04T15:38:49Z – claude – shell_pid=93657 – Started implementation via workflow command
- 2026-04-04T15:53:03Z – claude – shell_pid=93657 – All 4 subtasks done. Three AGENTS.md files updated with log_action.py references.
- 2026-04-04T15:53:13Z – claude – shell_pid=95751 – Started review via workflow command
- 2026-04-04T15:53:15Z – claude – shell_pid=95751 – Review passed: all three agents updated, field mappings verified against R4, habits Vikunja comments unchanged, Directive 3 compliance preserved
- 2026-04-04T16:52:29Z – claude – shell_pid=95751 – Merged to main, 72/72 tests passing
