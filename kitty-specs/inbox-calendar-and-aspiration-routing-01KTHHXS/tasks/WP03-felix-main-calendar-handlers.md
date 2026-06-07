---
work_package_id: WP03
title: Felix main — calendar create + clarification reply handler
dependencies:
- WP01
- WP02
requirement_refs:
- FR-005
- FR-007
- FR-011
tracker_refs: []
planning_base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
merge_target_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
- T019
history: []
authoritative_surface: scripts/openclaw/agents/main/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
tags: []
---

# WP03: Felix main — calendar create + clarification reply handler

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Extend `scripts/openclaw/agents/main/AGENTS.md` (Felix main's tracked standing orders) with two new sections: (1) a calendar-create handler that accepts delegation payloads from capture (matching the contract WP02 writes), and (2) a clarification-reply handler that on inbound WhatsApp reads the pending-calendar-clarifications JSONL state file, matches the reply to an open record, re-runs the validator with merged fields, and dispatches the completed event.

## Context

- **Authority docs**: `spec.md` FR-005 / FR-007 / FR-011; `contracts/capture_to_main_calendar_payload.md` (delegation payload + response shape + standing-orders deltas); `contracts/pending_clarification_record.md` (state file line shape); `data-model.md` (CalendarEventPayload + PendingClarificationRecord entities).
- **Current Felix main standing orders**: `scripts/openclaw/agents/main/AGENTS.md` (257 lines as of plan-phase verification). The current file is the generic openclaw workspace AGENTS.md template plus Kent's customizations.
- **gog skill is system-installed**: `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md` (per research R-001). Felix main already has gog available — this WP teaches Felix what gog calls to make when capture delegates calendar work.
- **gog command shape** (per the gog skill SKILL.md): `gog calendar create <calendarId> --account <email> --summary <title> --from <iso> --to <iso> [--rrule <rrule>] [--location <loc>] [--description <desc>] [--start-timezone <tz>] [--attendees <comma>] -j`.
- **Default account + calendar**: `--account kent@intentional.biz --calendar primary` (per R-006). The delegation payload may override; Felix main uses payload values verbatim.
- **`openclaw doctor` warning**: Felix main's `message` tool is missing from its allowlist, so channel-action calls (`thread-reply`, `sendAttachment`) can fail. This WP's flow does NOT use channel actions — replies happen via standard openclaw end-of-turn outbound. If the warning surfaces as an actual failure during smoke testing, that's a pre-existing config gap to escalate separately (do not try to fix it inside this WP).

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP03 --agent <name>` (depends on WP01 and WP02; finalize-tasks computes the lane base to include both)
- Depends on: WP01 (validator helper for the reply-handler's re-validation step), WP02 (the delegation payload shape capture sends; the state file shape capture writes).

---

## Subtask T015: Add "Calendar event creation (delegated from capture)" section

**Purpose**: Document how Felix main responds when capture delegates a complete calendar event creation via `openclaw agent --agent main --message <CalendarEventPayload>`.

**Steps**:
1. Read `scripts/openclaw/agents/main/AGENTS.md`. Identify the appropriate insertion point — after existing sections that handle other delegation patterns (look for any "When you receive an openclaw agent message" sections; if absent, add as a new top-level section under "Tools" or before "Group Chats").
2. Add the section header `## Calendar event creation (delegated from capture)`.
3. Document the trigger:
   - "When you receive an openclaw-agent message with `action: 'create_calendar_event'`, do not respond in chat. Instead, perform the calendar write workflow below."
4. Document the input payload schema. Reference `contracts/capture_to_main_calendar_payload.md`; do not duplicate fields verbatim — just call out the required fields and link to the contract.
5. Document the gog command synthesis rules:
   ```
   gog calendar create <calendar_id> \
     --account <account> \
     --summary "<summary>" \
     --from <start_rfc3339> --to <end_rfc3339> \
     [--start-timezone <start_timezone>] \
     [--location "<location>"] \
     [--description "<description>"] \
     [--rrule "<rrule>"] \
     [--attendees "<comma-joined attendees>"] \
     -j
   ```
   Square-bracketed flags are conditional on the payload field being non-null.
6. Specify the response envelope (return to the openclaw-agent caller as JSON):
   - Success: `{"status": "created", "gcal_event_id": <gog's eventId>, "html_link": <gog's htmlLink>, "summary": <summary>, "start_rfc3339": <start>, "rrule": <rrule or null>}`
   - Failure: `{"status": "error", "error": <gog stderr verbatim>, "exit_code": <gog exit code>}`

**Files**:
- `scripts/openclaw/agents/main/AGENTS.md`

**Validation**:
- [ ] Section header present and positioned reasonably in the file
- [ ] Action trigger explicitly named (`action: 'create_calendar_event'`)
- [ ] gog command shape documented with all conditional flags
- [ ] Response envelope spec covers both success and error
- [ ] References `contracts/capture_to_main_calendar_payload.md` for the full contract

---

## Subtask T016: Felix main parses gog response + logs via log_action

**Purpose**: Wire the observability path so every calendar-create attempt produces a structured `log_action` event, matching the existing convention.

**Steps**:
1. In the same Calendar event creation section, add a "Logging" sub-section.
2. Document the log_action invocations:
   - On success:
     ```bash
     python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
       --agent main \
       --category routine \
       --action calendar_event_created \
       --target "<gcal_event_id>" \
       --outcome success \
       --context '{"source_inbox_path": "<from payload>", "account": "<from payload>", "calendar_id": "<from payload>", "rrule": "<from payload or null>", "clarification_id": "<from payload or null>"}'
     ```
   - On failure:
     ```bash
     python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \
       --agent main \
       --category error \
       --action calendar_event_failed \
       --target "<source_inbox_path>" \
       --outcome error \
       --context '{"error_detail": "<gog stderr>", "exit_code": <gog exit code>, "clarification_id": "<from payload or null>"}'
     ```
3. Note that on office2 the log_action path is `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py` (deploy artifact path, matching the existing pattern in capture's AGENTS.md).
4. The response envelope to the openclaw-agent caller is logged AFTER the log_action call; if log_action itself fails, log to stderr and continue (do not block the response).

**Files**:
- `scripts/openclaw/agents/main/AGENTS.md`

**Validation**:
- [ ] Logging sub-section under Calendar event creation
- [ ] Both success and failure log_action calls documented
- [ ] Path to log_action.py is the deploy artifact path
- [ ] Context fields include all relevant entries (source_inbox_path, account, calendar_id, rrule, clarification_id, error_detail)

---

## Subtask T017: Add "Calendar clarification reply handler" section

**Purpose**: Document Felix main's behavior on every inbound WhatsApp message — check the pending-calendar-clarifications state file and, if non-empty, attempt to match the inbound reply.

**Steps**:
1. Add a new section `## Calendar clarification reply handler` near the Calendar event creation section (sibling).
2. Document the trigger:
   - "On every inbound WhatsApp message: BEFORE any other intent classification of the message, check `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` (the pending-calendar-clarifications state file)."
   - "If the file does not exist or is empty, skip this handler entirely."
3. Document the matching rules:
   - Read all lines; deserialize to JSON; filter to records where `timed_out_at` is null AND `resolved_at` is null.
   - If zero open records, skip.
   - If exactly one open record, attempt to match it against the inbound message body (handle even ambiguous matches — the operator's reply is naturally aligned to the most recent prompt).
   - If multiple open records: try to identify which by signal extraction (does the reply mention a title or date that matches one record's `fields_so_far.title`?). If unambiguous match found, proceed. If ambiguous, send a turn-summary asking Kent to specify which event ("Got it. Was that for: 'lunch with John next Tuesday' or 'meeting with Y'?") and STOP without writing.
4. Document the extraction step:
   - Parse the inbound message for time references ("Tuesday at 1pm", "1pm to 2pm"), duration ("for an hour"), location ("at Cafe X"), recurrence ("every week"), attendees ("with Jane, Bob").
   - Merge extracted values into a candidate block: `{...fields_so_far, <newly extracted fields>}`.
5. Document the re-validation step:
   - Pipe the merged candidate block JSON to `python3 /home/claude/kg-automation/scripts/calendar/validate_calendar_event.py`.
   - If output is `complete: true`, proceed to dispatch (T018+T019).
   - If output is `complete: false` AND the same set of missing fields as before, send a turn-summary noting that the reply was insufficient and the record stays open ("Still need: <missing>"); do NOT increment the timeout clock.
   - If `complete: false` AND a different set of missing fields (i.e., made some progress but still incomplete), send a turn-summary noting partial progress, update `last_reprompt_at` in the state file, and the record stays open.

**Files**:
- `scripts/openclaw/agents/main/AGENTS.md`

**Validation**:
- [ ] Section header present
- [ ] Trigger explicitly says "BEFORE other intent classification"
- [ ] Matching rules cover zero-open, one-open, multi-open scenarios
- [ ] Ambiguous-match disambiguation flow documented (ask Kent which one)
- [ ] Re-validation step references WP01 helper path
- [ ] Partial-progress vs no-progress branches documented

---

## Subtask T018: Felix main match + merge + re-run validator

**Purpose**: The procedural detail of how Felix main produces the merged candidate block. Codified separately from T017 (which is high-level matching logic) because the merge mechanics are subtle.

**Steps**:
1. Under the Calendar clarification reply handler section, add a sub-section "Field merge and re-validation".
2. Document field extraction patterns (regex-style guidance for the agent prompt — not literal regex; the agent applies these):
   - Time-of-day: "<n>am", "<n>pm", "<n>:<m>am", "<n>:<m>pm", "noon", "midnight", "<n>:<m>" (24h).
   - Duration: "for <n> (hour|minute|hr|min)(s)?", "<n>h<m>m".
   - End time: "to <n>am|pm" / "until <n>am|pm".
   - Date: "Tuesday", "next Tuesday", "tomorrow", "<n>/<m>", "<Month> <day>", "<Month> <day>, <year>".
   - Location: "at <words>", "@<words>".
   - Recurrence: "every <weekday>", "weekly", "biweekly", "monthly", "first|second|third|fourth|last <weekday>".
   - Attendees: "with <name>(, <name>)*".
3. Specify the merge rule:
   - Each extracted field replaces or fills the corresponding field in `fields_so_far`.
   - If a field is already non-null in `fields_so_far` AND the reply extracts a different value, the reply WINS (treat the reply as the operator's correction).
4. Document the re-validation invocation:
   ```bash
   echo "<merged candidate block JSON>" | python3 /home/claude/kg-automation/scripts/calendar/validate_calendar_event.py
   ```
5. Pass through `tick_iso` set to the inbound message receipt time, NOT the original `sent_at` (so "next Tuesday" in the reply resolves correctly).

**Files**:
- `scripts/openclaw/agents/main/AGENTS.md`

**Validation**:
- [ ] "Field merge and re-validation" sub-section present
- [ ] Field extraction patterns documented for all 6 field types
- [ ] Merge rule explicitly states "reply wins on conflict"
- [ ] Re-validation invocation references helper path correctly
- [ ] `tick_iso` source is documented (inbound message receipt, not original sent_at)

---

## Subtask T019: Felix main: dispatch + remove resolved record + flip source note

**Purpose**: The closing leg of the reply handler — once re-validation returns `complete: true`, Felix main creates the event, removes the record from the state file, and flips the source inbox note's frontmatter from `needs-review` to `processed`.

**Steps**:
1. Under the Calendar clarification reply handler section, add a sub-section "Resolve and create".
2. Document the dispatch step:
   - Re-enter the "Calendar event creation (delegated from capture)" handler with the synthesized `CalendarEventPayload`. Set `clarification_id` in the payload to the resolved record's id (so the Logging sub-section can include it in the log_action context).
   - Felix main IS the same agent both sending and receiving this delegation; the dispatch is conceptual, not a real openclaw-agent round-trip. Document it as: "Apply the gog command from the Calendar event creation section, with the synthesized payload."
3. Document the state-file rewrite:
   - Open `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` with `fcntl.flock(LOCK_EX)`.
   - Read all lines; deserialize.
   - Filter out the record whose `clarification_id` matches the resolved one.
   - Atomic rewrite: write to `<state-file>.tmp`, `fsync`, `rename` over the original.
   - Release lock.
4. Document the source note frontmatter flip:
   - Read `<source_inbox_path>`. Locate the YAML frontmatter.
   - Set `status: processed`; set `processed_at: "<tick_iso>"`.
   - Atomic write (same convention as capture's Step 5c — write to .tmp, rename).
5. Document the log_action calls:
   - `calendar_event_clarification_resolved` with `clarification_id`, `source_file`, `gcal_event_id` (from the gog response).
   - The Calendar event creation section's `calendar_event_created` log_action also fires (covering both events with one resolution flow).
6. Document the failure mode:
   - If the gog calendar create call fails in this resolution flow, log `calendar_event_failed` (per the Logging sub-section), DO NOT remove the state-file record (let it persist; Kent can re-try by sending another reply), DO NOT flip source note status (stays at needs-review).
   - Surface the failure to Kent in WhatsApp turn-summary with the gog error text.

**Files**:
- `scripts/openclaw/agents/main/AGENTS.md`

**Validation**:
- [ ] "Resolve and create" sub-section present
- [ ] State-file rewrite protocol with file lock + atomic rename documented
- [ ] Source note frontmatter flip atomic write documented
- [ ] log_action calls (calendar_event_clarification_resolved + calendar_event_created) both listed
- [ ] Failure mode (gog fails during resolution) explicitly documented — state file NOT modified, source note NOT flipped, failure surfaced in WhatsApp

---

## Definition of Done

- [ ] All 5 subtasks complete with their per-subtask validation items checked.
- [ ] Felix main AGENTS.md has two new top-level sections: "Calendar event creation (delegated from capture)" and "Calendar clarification reply handler".
- [ ] Both sections cross-reference the contracts in `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/`.
- [ ] log_action calls match the new action types added in WP02's allowlist (T014).
- [ ] State-file path is `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` consistently across sections.
- [ ] No uncommitted changes outside this WP's `owned_files`.

## Risks

1. **Multi-handler precedence**: the clarification reply handler must run BEFORE Felix main's existing intent-classification logic on inbound WhatsApp. If Felix main's existing flow has a "default scheduling intent" handler that fires first, the calendar-clarification reply could be mis-routed there. Reviewer specifically checks that the precedence is correct.
2. **State-file write-write race**: capture writes new records via T012; Felix main removes resolved records here. The file lock (LOCK_EX) is shared by both writers. Reviewer verifies the lock pattern is identical on both sides.
3. **`openclaw doctor` warning about main's `message` tool**: pre-existing config gap. Out of scope; document as a known caveat in the section.

## Reviewer guidance

- Read Felix main AGENTS.md end-to-end with the diff applied. Mentally walk through:
  - Calendar event creation: capture's delegation arrives → does Felix main correctly synthesize the gog command?
  - Clarification reply: inbound WhatsApp arrives → does Felix main read the state file before classifying intent?
- Verify the conceptual "self-dispatch" in T019 (re-enter calendar-create handler) is unambiguous in the prompt — the agent should understand this as "apply the same workflow with the synthesized payload" rather than literally invoking openclaw agent on itself.
- Confirm log_action paths are deploy-artifact paths (`/home/claude/...`), not repo-relative paths.
