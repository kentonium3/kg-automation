---
work_package_id: WP03
title: Tighten main/AGENTS.md below 12K bootstrap context cap
dependencies:
- WP02
requirement_refs:
- FR-001
- FR-007
- FR-012
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
- T017
phase: Phase 3 - Main Tightening
shell_pid: "47012"
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/main/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
tags: []
agent_profile: implementer-ivan
role: implementer
agent: "claude::reviewer-renata:reviewer"
---

# Work Package Prompt: WP03 – Tighten main/AGENTS.md below 12K bootstrap context cap

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree and records the lane branch in `base_branch`.

## Objectives & Success Criteria

This WP delivers the structural fix for kentonium3/kg-automation#579. After this WP:

- `scripts/openclaw/agents/main/AGENTS.md` < 12,000 chars (NFR-001).
- Calendar handler content (current lines 259–440) is REMOVED — its new home is `felix-admin-calendar/AGENTS.md` (delivered by WP02).
- A new "Calendar event creation delegation" section is added that mirrors the habit/inbox delegation patterns and points the main agent at `felix-admin-calendar` for calendar work.
- All other delegation sections (capture, habits, tasker, escalation) and standard preambles (Memory, Red Lines, Verbatim Pass-Through, etc.) are PRESERVED with no semantic regression.
- `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_main_agents_md_under_12k` transitions from FAIL to PASS.

**Requirements covered**: FR-001, FR-007, FR-012, NFR-001.

## Context & Constraints

- Current file: `scripts/openclaw/agents/main/AGENTS.md` (25,982 chars; 440 lines).
- Current calendar content: lines 259–440 (event creation handler + clarification reply handler) — ~10–11K chars.
- Current other delegations: capture (~197–216), habits (~217–235). These MUST stay in context after this WP.
- Per F-01 in research.md: subagent AGENTS.md files run at 12K–15K and don't show fatal truncation because their tails aren't load-bearing. main is the load-bearing case because its delegation routing lives in the tail.
- Per spec discovery Q3=A: target is < 12K HARD cap (not just under the ~14-15K effective source budget). Headroom matters; inbox-router extraction is a follow-on only if margin disappears.
- After T013 (remove calendar lines) the file is approximately 14-15K chars. Compression to <12K requires either (a) compressing other sections OR (b) accepting the delegation-pointer section adds back a small amount AND compressing the rest.

## Subtasks & Detailed Guidance

### Subtask T013 – Excise calendar handler content

- **Purpose**: Remove the calendar event creation handler + clarification reply handler from main.
- **Steps**:
  1. **First**: VERIFY line range. Run `grep -n "^## Calendar" scripts/openclaw/agents/main/AGENTS.md` — confirm the section starts at the expected line (~259 per plan-phase snapshot). If lines have shifted, update mental model before excising.
  2. Remove from "## Calendar event creation (delegated from capture)" header through end of "Calendar clarification reply handler" section.
  3. Confirm the next section after the calendar block is the original neighbor (whatever lived at line 441+).
- **Files**: `scripts/openclaw/agents/main/AGENTS.md`
- **Parallel?**: No — blocks T014.
- **Notes**: This is a straight excision. No rewording.

### Subtask T014 – Add calendar delegation pointer

- **Purpose**: Tell main where to route calendar work without inlining handler logic.
- **Steps**:
  1. **Read the canonical delegation pattern** from main's existing habits delegation section (lines ~217–235 of the pre-mission file) or inbox delegation section (~197–216).
  2. Locate the insertion point — after the inbox-processing delegation section, before the cron-driven sub-agent output rule.
  3. Insert a new section roughly 15–25 lines:
     ```markdown
     ## Calendar event creation delegation

     The `felix-admin-capture` agent (inbox processor) delegates Google Calendar event
     creation to `felix-admin-calendar`. When you receive a request to create a calendar
     event — or when capture's inbox-routing emits a payload with `action: "create_calendar_event"` —
     route the work to felix-admin-calendar via openclaw-agent dispatch. The payload contract
     is canonicalized in `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/capture_to_main_calendar_payload.md`
     (unchanged after the extraction).

     ## Calendar clarification reply delegation

     When Kent's inbox produced an incomplete calendar event, capture prompts him on WhatsApp
     and records the open prompt at `~/second-brain/agents/state/pending-calendar-clarifications.jsonl`.
     felix-admin-calendar owns the clarification round-trip: on every inbound WhatsApp DM,
     it checks the pending state file BEFORE other classifiers and resolves the round-trip when
     the reply matches.
     ```
  4. Final wording should match the project's voice; the above is structure, not prose-final.
- **Files**: `scripts/openclaw/agents/main/AGENTS.md`
- **Parallel?**: No — depends on T013.

### Subtask T015 – Whole-file compression review (conditional)

- **Purpose**: Land under 12K if T013+T014 didn't already.
- **Steps**:
  1. Measure: `wc -c scripts/openclaw/agents/main/AGENTS.md`.
  2. If `< 12000`: skip the rest of this subtask. Note in Activity Log: "Compression not required — file landed at <N> chars after T013+T014."
  3. If `>= 12000`: review every section for compression opportunities. Order of priorities:
     - Tighten verbose explanations / multi-paragraph rationales that have moved to data-flows.md or other docs
     - Remove dead references (sections about features that have shipped and now have their own substrate)
     - Compress example blocks (keep one per pattern, not three variants)
     - DO NOT remove or compress: delegation sections (capture, habits, tasker, escalation, the new calendar delegation), verbatim pass-through rules, output discipline rules, calendar delegation pointer just added.
- **Files**: `scripts/openclaw/agents/main/AGENTS.md`
- **Parallel?**: No.
- **Notes**: A semantic-preserving compression pass is the goal. If you can't get under 12K without removing load-bearing instructions, STOP and report — that's a planning-failure signal not a coding problem.

### Subtask T016 – Diff review for semantics

- **Purpose**: Confirm no delegation pattern, no rule-of-thumb, no escalation hook was inadvertently dropped.
- **Steps**:
  1. Side-by-side diff: pre-mission main/AGENTS.md vs post-WP03 main/AGENTS.md.
  2. Run through this checklist:
     - [ ] All 4 OpenClaw subagent delegation patterns intact (capture, habits, tasker, escalation)
     - [ ] New calendar delegation pointer present and well-formed
     - [ ] Memory / Red Lines / Verbatim Pass-Through preamble intact
     - [ ] Output Discipline block (if present in main) intact
     - [ ] Heartbeat / scheduled flow rules intact
     - [ ] Filing issues guidance intact
     - [ ] Tools section intact
- **Files**: none (review step)
- **Parallel?**: No.

### Subtask T017 – Verify pytest gate

- **Purpose**: Test-first gate passes.
- **Steps**:
  1. From repo root: `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_main_agents_md_under_12k -v`
  2. Expected: PASS.
- **Files**: none.
- **Parallel?**: No — runs last.

## Test Strategy

WP01's `test_main_agents_md_under_12k` assertion gates this WP. The compression work continues until the assertion passes.

Reviewer should also verify the structural diff (T016 checklist) — passing the size assertion is necessary but not sufficient for FR-007 (no regression in other delegations).

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Inadvertently drop a load-bearing delegation rule during T015 compression | T016 checklist; reviewer does side-by-side diff |
| Calendar delegation pointer text is wrong shape (doesn't match habit/inbox patterns) | T014 step 1 anchors to existing pattern; reviewer compares pointer prose to habit pointer |
| Can't get under 12K without semantic loss | STOP and report — escalate as planning failure; consider inbox-router extraction follow-on (was deferred per spec Q3=A) |
| `--agent` references to `main` for calendar work surface in the delegation pointer prose | OK — delegation pointer can reference main's role; the BUG was log_action `--agent main` for actions felix-admin-calendar performs, not narrative references |

## Review Guidance

- `wc -c scripts/openclaw/agents/main/AGENTS.md` < 12000?
- Diff vs pre-mission state shows: -lines (calendar handlers) +lines (delegation pointer) [+/- compression]?
- T016 checklist all checked?
- `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_main_agents_md_under_12k` PASSES?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
- 2026-06-11T04:23:03Z – claude::implementer-ivan:implementer – shell_pid=43094 – Assigned agent via action command
- 2026-06-11T04:30:33Z – claude::implementer-ivan:implementer – shell_pid=43094 – Ready for review: main/AGENTS.md tightened to 11934 chars (NFR-001 PASS, was 25982), calendar handler block excised, calendar event creation + clarification reply delegation pointers added to felix-admin-calendar, all other delegations preserved per T016 checklist (capture/habits/Memory/Red Lines/Verbatim Pass-Through/Output Discipline/Heartbeat/Filing issues/Tools)
- 2026-06-11T04:31:03Z – claude::reviewer-renata:reviewer – shell_pid=47012 – Started review via action command
