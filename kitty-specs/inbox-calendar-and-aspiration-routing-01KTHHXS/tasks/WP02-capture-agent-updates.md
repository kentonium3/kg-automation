---
work_package_id: WP02
title: Capture agent — routing rows, completeness, clarification, audit
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
merge_target_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
base_commit: 0c324dff5deb5a5c8d8b3484d19681799131e757
created_at: '2026-06-08T09:55:24.675769+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
- T013
- T014
agent: "claude:opus-4-7:reviewer-renata:reviewer"
shell_pid: "21577"
history: []
agent_profile: generic-agent
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
role: implementer
tags: []
---

# WP02: Capture agent — routing rows, completeness, clarification, audit

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Apply the four new/changed classification rows to `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (the capture agent's standing orders), wire the completeness validation branch that invokes WP01's helper, add the pending-calendar-clarifications JSONL state-file write, format the WhatsApp clarification prompt, install the 24h timeout sweep, and extend the `log_action` allowlist with the new action types. This WP is the largest agent-prompt edit in the mission — eight subtasks across one file.

## Context

- **Authority docs**: `spec.md` FR-001 / FR-002 / FR-005 / FR-006 / FR-007 / FR-008 / FR-009 / FR-010 / FR-011 / FR-012; `contracts/validate_calendar_event.md` (helper invocation); `contracts/pending_clarification_record.md` (JSONL line shape); `contracts/capture_to_main_calendar_payload.md` (Felix main delegation contract).
- **Current AGENTS.md** at `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`. Key existing sections:
  - Step 3 (lines ~199–222): the routing table being modified.
  - Goal-handling block (lines ~376–438): the established model for "valid declaration vs aspiration" distinction — mirror this discipline for "active task vs aspiration vs Someday".
  - Action Types table (lines ~550–580): the `log_action` allowlist being extended.
  - GitHub issue creation section: unchanged but worth reading for prompt voice/conventions.
- **The classifier is Claude haiku** (per capture's identity label `felix-admin-capture:haiku`). Prompt budget is constrained. Keep new rows terse; reference contracts and helper paths rather than duplicating their contents inline.
- **Hard rules in capture's standing orders** (Output discipline section, lines ~28–84): these survive untouched. New work integrates into existing Step 1 and Step 3 + adds new Step 3 sub-sections; does NOT touch Output discipline.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent <name>` (depends on WP01; finalize-tasks computes the lane base)
- Depends on: WP01 (the validator helper must exist on disk for the branch base to include it).

---

## Subtask T007: Add Calendar event row to Step 3 routing table

**Purpose**: Replace the existing single "Task or action item" row with five rows — Calendar event being the first added. This is the primary user-visible change.

**Steps**:
1. Open `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`. Locate the Step 3 table at "### Step 3: Classify and route" (~ line 198).
2. Before the existing "Task or action item" row, add a new row:
   ```
   | Calendar event | Google Calendar (via Felix main delegation) | See "Calendar event completeness" sub-section below |
   ```
3. Update the classifier prompt body above the table (or whatever instruction text guides the LLM): explicitly list calendar-event signals. Suggested signal list (terse for prompt budget):
   - Has a date or relative time anchor ("Tuesday 2pm", "next Friday", "every Tuesday")
   - Has a duration or end time
   - Optionally has a location, attendees, or recurrence phrase
   - Verb shapes: "attend X", "meet with Y at Z", "lunch with N", "trivia night", "[recurring event name]"
   - NEGATIVE signal: imperative verb without a time anchor ("call dentist") is NOT a calendar event — it's a task.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] New row present in Step 3 table, positioned before "Task or action item"
- [ ] Classifier prompt body includes calendar-event signals + the negative-signal example
- [ ] T015 in WP03 will create the Felix-main side of the delegation; reference is not dangling

---

## Subtask T008: Add Aspiration / musing row

**Purpose**: Add the row that routes wishes / wonderings / self-observations to `08-Journal/`.

**Steps**:
1. In the Step 3 table, after the goal-related rows and before the "Task or action item" row, add:
   ```
   | Aspiration / musing | `08-Journal/Journal YYYY-MM-DD HHmm.md` | Append to today's dated journal entry (create if absent) |
   ```
2. Add to the classifier prompt body:
   - Aspiration signals: "I should...", "I wonder if...", "I need to start...", "maybe I should..."
   - These are framed as wishes or wonderings — NOT a concrete commitment with a completability test.
   - NEGATIVE signal: a valid Felix goal declaration (date + present-tense outcome + observable evidence) routes to `03-Constitution/Goals-MOC.md` via the existing goal-handling block. Aspiration row is the FALLBACK for goal-shaped content that fails the declaration validation.
3. After the table, add a brief Step 3 sub-section "Aspiration / musing handling":
   - Read existing `08-Journal/Journal YYYY-MM-DD HHmm.md` if present (HHmm = capture tick time).
   - If not present, create with full frontmatter following existing journal-entry conventions.
   - Append the cleaned content under a `## Inbox capture` heading.
   - Log `journal_entry_appended` via `log_action`.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] Aspiration row present in Step 3 table
- [ ] Classifier prompt distinguishes aspiration from valid goal declaration
- [ ] "Aspiration / musing handling" sub-section explicitly references `log_action: journal_entry_appended`

---

## Subtask T009: Add Someday item row + Vikunja Someday project resolution

**Purpose**: Add the row that routes concrete-but-parked items to Vikunja project "Someday" (id 4 per research R-004).

**Steps**:
1. In the Step 3 table, add (after the Aspiration row, before the active-task row):
   ```
   | Someday item | Vikunja project `Someday` (resolved by name) | Create task; identity inferred; NO due_date |
   ```
2. Add to the classifier prompt body:
   - Someday signals: concrete actionable item framed as not-now. Cue phrases: "eventually", "someday", "when I get around to it", "no rush", "future".
   - Example: "Get rid of the old lawn tractor when I get around to it." → Someday.
   - NEGATIVE signal: a concrete actionable item WITHOUT a parked-framing cue is an Active task (routes to Vikunja Inbox project), not Someday.
3. Add a brief Step 3 sub-section "Someday item handling":
   - Resolve Vikunja project "Someday" by name using the vikunja-api skill resolution pattern (do not hardcode id=4; the project resolution code path handles fallback).
   - Infer identity label per the existing rules (intentional / metalcasework / personal).
   - Create the task with NO `due_date` field.
   - Log `someday_task_created` via `log_action` with the resolved `vikunja_task_id`.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] Someday row present in Step 3 table
- [ ] Classifier prompt has Someday signals + the parked-framing rule
- [ ] "Someday item handling" sub-section explicitly says "no `due_date`" and references `log_action: someday_task_created`
- [ ] No hardcoded `project_id: 4` in the prompt text (resolution is by name)

---

## Subtask T010: Tighten "Task or action item" rule

**Purpose**: Update the existing active-task row so events ("attend X") and aspirations ("be Xer", "get Xer") no longer fall through into Vikunja.

**Steps**:
1. Update the active-task row in Step 3 table to clarify scope:
   ```
   | Active task | Vikunja Inbox project (via felix-admin-tasker delegation; fallback to flat task) | Requires concrete verb + clear completability test |
   ```
2. In the classifier prompt body, add an explicit rejection rule sub-section "Tightened task rule":
   - A block qualifies as an active task ONLY when:
     - It has a concrete verb (call, schedule, send, reschedule, write, draft, review, prepare, etc.)
     - AND a clear completability test (you can mark it done unambiguously)
   - These shapes are NEVER active tasks:
     - "Attend X meeting" / "Go to Y event" — that's a calendar event (route there)
     - "Be more X" / "Get to bed earlier" / "Become Y" — that's an aspiration (route there)
     - "Eventually do X" / "Someday Y" — that's a Someday item (route there)
3. Reference the negative-signal examples explicitly so the classifier sees them in the prompt:
   - GOOD: "Call dentist to reschedule cleaning" → active task
   - GOOD: "Draft Q3 marketing brief by Friday" → active task
   - BAD: "Attend trivia night Tuesday" → calendar event, NOT a task
   - BAD: "Get to bed earlier" → aspiration, NOT a task

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] Active-task row text updated to mention "concrete verb + completability test"
- [ ] "Tightened task rule" sub-section present with GOOD/BAD examples
- [ ] Classifier prompt no longer treats "attend X" as a task

---

## Subtask T011: Add completeness validation branch (invoke helper)

**Purpose**: When a block is classified as a calendar event, capture must invoke WP01's `validate_calendar_event.py` helper to determine complete-vs-incomplete and produce the delegation payload.

**Steps**:
1. Add a new sub-section to Step 3 titled "Calendar event completeness". Document the helper invocation:
   ```bash
   echo "<extracted block JSON>" | python3 /home/claude/kg-automation/scripts/calendar/validate_calendar_event.py
   ```
2. Document the input JSON shape (reference `contracts/validate_calendar_event.md` § Input schema; do not duplicate verbatim — agent prompt is read-only of the contract, not a re-statement).
3. Document the branching logic:
   - If `complete: true` → take the "Complete calendar event delegation" path (T015 in WP03).
     ```bash
     openclaw agent --agent main \
       --message "$(cat <<EOF
       <CalendarEventPayload JSON from helper output>
       EOF
       )" \
       --json --timeout 120
     ```
     Wait for Felix main's response; log `calendar_event_created` (or `calendar_event_failed` per response).
   - If `complete: false` → take the "Incomplete clarification" path (T012, T013).
4. Specify that capture passes `tick_iso` to the helper (the cron tick's reference time, captured at run start). This is required by the contract.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] "Calendar event completeness" sub-section exists and explicitly references the helper path and the contracts/validate_calendar_event.md doc
- [ ] Both `complete: true` and `complete: false` branches are documented with target sub-sections
- [ ] Felix main delegation command shape matches `contracts/capture_to_main_calendar_payload.md` (action="create_calendar_event")

---

## Subtask T012: Capture writes PendingClarificationRecord on incomplete

**Purpose**: When the helper returns `complete: false`, capture must append a JSONL line to the pending-calendar-clarifications state file per `contracts/pending_clarification_record.md`.

**Steps**:
1. Add a new sub-section "Incomplete calendar event: pending clarification". Document:
   - State file path: `~/second-brain/agents/state/pending-calendar-clarifications.jsonl`
   - Line shape (reference `contracts/pending_clarification_record.md` § Line schema; do not duplicate verbatim).
   - Generation rules: mint a fresh ULID for `clarification_id`; populate `fields_so_far` from the partial block; populate `missing_fields` from the helper's output; set `sent_at` to the cron tick's `tick_iso`.
2. Specify the atomic-write protocol:
   - Open file with `fcntl.flock(LOCK_EX)`
   - Append `<json>\n`
   - `fsync`
   - Release lock
3. Specify error handling: if the write fails (disk full, permission denied), log `calendar_event_failed` with `error_detail: "pending state write failed: <err>"`, leave source note at `status: needs-review`, surface in WhatsApp turn-summary.
4. Specify that the source inbox note's frontmatter is updated to `status: needs-review` (no `processed_at` yet). Use the existing atomic-write helper used elsewhere in capture (lines ~327–333 of current AGENTS.md).
5. Log `calendar_event_clarification_sent` via `log_action` with `clarification_id`, `missing_fields`, and `source_file`.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] "Incomplete calendar event: pending clarification" sub-section present
- [ ] State file path, line shape, and atomic-write protocol all documented
- [ ] Error handling for write failure is explicit
- [ ] Source note frontmatter update is explicit and references existing atomic-write conventions

---

## Subtask T013: WhatsApp clarification prompt format + 24h timeout sweep

**Purpose**: Format the clarification request that lands in Kent's WhatsApp turn-summary, and install the periodic timeout sweep that flips stale clarifications to `status: needs-review`.

**Steps**:
1. In Step 7 (Write the processing log) or directly above the existing turn-summary section, add a sub-section "Calendar clarifications turn-summary block". Specify the format:
   ```
   📅 Calendar items needing more info:
   - "<title>" — need <missing-field-1>, <missing-field-2>
   - "<title>" — need <missing-field>
   ```
   The bullet list is appended to the WhatsApp turn-summary AFTER existing routing summary content. Each open pending clarification (read from the state file at end-of-turn) produces one bullet.
2. Convert missing-field tokens to human-readable phrases:
   - `start_datetime` → "start time"
   - `end_or_duration` → "end time or duration"
   - `recurrence_pattern` → "recurrence pattern (you said it's recurring — how often?)"
   - `title` → "title"
3. Add a new sub-step to Step 1 (after prescan, before the routing loop): "24h timeout sweep". Document:
   - Read all entries in `~/second-brain/agents/state/pending-calendar-clarifications.jsonl`.
   - For each entry with `timed_out_at: null`, `resolved_at: null`, AND `sent_at` >24h before `tick_iso`:
     - Set `timed_out_at` to `tick_iso`.
     - Read the source inbox note; verify it's at `status: needs-review` (don't change if already different).
     - Log `calendar_event_clarification_timeout` with `clarification_id`, `sent_at`, `source_file`.
   - Atomic rewrite the state file with the updated entries.

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] "Calendar clarifications turn-summary block" sub-section present with the exact format spec
- [ ] Missing-field human-readable translation table present
- [ ] "24h timeout sweep" sub-step added to Step 1 (positioned to run after prescan but before routing)
- [ ] Atomic rewrite protocol referenced

---

## Subtask T014: Extend log_action allowlist

**Purpose**: Add the new action types to capture's allowlist documentation so the agent emits structured events that `summarize.py` can aggregate.

**Steps**:
1. Locate the Action Types table (lines ~550–580 of current AGENTS.md).
2. Add these new rows to the table:
   ```
   | calendar_event_created | A Google Calendar event was created via Felix main delegation | routine |
   | calendar_event_failed | A calendar create attempt failed (capture's view of Felix main's error) | error |
   | calendar_event_clarification_sent | A pending-calendar-clarifications record was written | routine |
   | calendar_event_clarification_timeout | A pending clarification was timed out at 24h | flagged |
   | journal_entry_appended | An aspiration was appended to today's journal | routine |
   | someday_task_created | A Someday Vikunja task was created | routine |
   ```
3. Update the Context Fields table (lines ~578–589 of current AGENTS.md) to add:
   ```
   | clarification_id | string | When a calendar clarification is sent or timed out |
   | gcal_event_id | string | When a calendar event is created |
   ```

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Validation**:
- [ ] All 6 new action types in the Action Types table
- [ ] `clarification_id` and `gcal_event_id` in the Context Fields table
- [ ] Existing rows preserved unchanged

---

## Definition of Done

- [ ] All 8 subtasks complete with their per-subtask validation items checked.
- [ ] Step 3 routing table has 5 distinct rows (Calendar event, Aspiration/musing, Someday item, Active task, plus the existing GitHub issue / Goal etc.) with no overlap.
- [ ] Helper invocation path is hardcoded to `/home/claude/kg-automation/scripts/calendar/validate_calendar_event.py` (matches existing pattern for other inbox helpers).
- [ ] WhatsApp turn-summary format is documented and matches the spec FR-006 contract.
- [ ] No uncommitted changes outside this WP's `owned_files`.
- [ ] AGENTS.md `wc -l` is within ~150% of pre-WP02 line count — substantial growth is expected but full doubling would be a red flag (consider extracting some content to a sibling skill file if exceeded).

## Risks

1. **Prompt budget overflow**: Haiku has a constrained prompt; if AGENTS.md grows too large the classifier degrades. Mitigation: keep new content terse; reference contract docs rather than restating; verify final file size with `wc -l`. If oversized, the fallback is to extract the calendar-routing detail into a sibling skill file and reference it from AGENTS.md (out of scope for this WP — escalate to operator).
2. **Voice-drift in agent prompt edits**: capture's existing prompt has a particular voice and structure. New sections must match it (terse, instruction-first, no narrative). Reviewer specifically checks voice consistency.
3. **Conflict with existing goal-handling block**: aspiration row must defer to the existing valid-declaration validation. Reviewer checks that the aspiration sub-section explicitly cross-references the goal-handling block.
4. **24h timeout sweep doesn't fire if capture cron is paused**: documented but unavoidable in this WP. Quickstart Test 6 verifies the sweep manually.

## Reviewer guidance

- Read the diff with the full AGENTS.md context — many edits are insertions into existing tables.
- Verify Step 3 table maintains its existing structure (column headers, ordering of pre-existing rows).
- Run `wc -l scripts/openclaw/agents/felix-admin-capture/AGENTS.md` before and after; flag if growth >50% (consider whether to split the file).
- Smoke-test by mentally walking through the quickstart Test 1, 3, 4, 5, 7, 8 against the new prompt content — does each classification land in the right row?
- Confirm references to WP01 (helper invocation path) and WP03 (Felix main delegation) are accurate and not dangling.

## Activity Log

- 2026-06-08T09:55:27Z – claude:opus-4-7:generic-agent:implementer – shell_pid=18905 – Assigned agent via action command
- 2026-06-08T10:04:27Z – claude:opus-4-7:generic-agent:implementer – shell_pid=18905 – Implementation complete on lane-b commit a5385161; all 8 subtasks T007-T014 done; AGENTS.md +265 lines (28% growth, within 50% soft signal). Ready for review.
- 2026-06-08T10:04:43Z – claude:opus-4-7:reviewer-renata:reviewer – shell_pid=21577 – Started review via action command
- 2026-06-08T10:07:52Z – user – shell_pid=21577 – Review passed: T007-T014 verified; 5 routing rows + signal cues preamble + completeness sub-section + JSONL atomic write + Step 1a 24h sweep + turn-summary block + 6 new log_action types + 2 context fields; Output discipline frozen surface preserved; helper path correct; Vikunja Someday by name; stylistic deviation (signal cues above table vs per-row) judged sound for haiku prompt budget
