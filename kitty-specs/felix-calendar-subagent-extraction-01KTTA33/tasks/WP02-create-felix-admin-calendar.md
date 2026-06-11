---
work_package_id: WP02
title: Create felix-admin-calendar OpenClaw subagent
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-006
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
- T012
phase: Phase 2 - New Agent
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-calendar/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-calendar/**
tags: []
---

# Work Package Prompt: WP02 – Create felix-admin-calendar OpenClaw subagent

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree and records the lane branch in `base_branch`.

## Objectives & Success Criteria

Stand up the new OpenClaw subagent's workspace files following the established Felix subagent pattern. After this WP:

- `scripts/openclaw/agents/felix-admin-calendar/{IDENTITY,SOUL,AGENTS,TOOLS,USER}.md` all exist with substantive content.
- `AGENTS.md` declares a broader calendar-substrate charter (per spec discovery Q2=A+C) and contains the calendar event creation handler + clarification reply handler moved 1:1 from main/AGENTS.md lines 259–440 (with `--agent` log_action values updated to `felix-admin-calendar`).
- `AGENTS.md` < 12,000 chars (NFR-004 — pytest WP01 assertion passes).
- IDENTITY / SOUL / TOOLS / USER follow the felix-admin-habits canonical pattern.

**Requirements covered**: FR-002, FR-003, FR-004, FR-006, NFR-004.

## Context & Constraints

- Reference pattern: `scripts/openclaw/agents/felix-admin-habits/{IDENTITY,SOUL,AGENTS,TOOLS,USER}.md` (and `felix-admin-tasker`, `felix-admin-capture` — all follow the same shape).
- Canonical setup runbook: `docs/runbooks/openclaw-agent-setup.md` — Required vs Optional files; size limits; standard sections.
- Output Discipline block: canonical source is `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` lines ~33–84. Per runbook, this block MUST appear on any agent whose standing orders surface to user-facing WhatsApp (calendar replies DO surface to Kent).
- Calendar handler content source: `scripts/openclaw/agents/main/AGENTS.md` lines 259–440 (current file).
- Payload contract: `contracts/calendar-event-payload.md` (unchanged except `--agent` value).
- Charter expression: declare calendar-substrate as the domain at the TOP of AGENTS.md, before handlers. See plan.md "Architecture" section for the topology framing.
- Size budget: < 12,000 chars total (NFR-004). Iterate until under cap.

## Subtasks & Detailed Guidance

### Subtask T006 – Create directory

- **Purpose**: Workspace dir for the new agent.
- **Steps**:
  1. `mkdir -p scripts/openclaw/agents/felix-admin-calendar`
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/`
- **Parallel?**: No — blocks T007–T011.

### Subtask T007 – IDENTITY.md

- **Purpose**: Short identity card per openclaw-agent-setup runbook.
- **Steps**:
  1. Create `scripts/openclaw/agents/felix-admin-calendar/IDENTITY.md` (~150 chars target).
  2. Follow the felix-admin-habits pattern:
     ```markdown
     # IDENTITY.md

     - **Name:** Felix (Calendar)
     - **Creature:** Calendar substrate agent
     - **Vibe:** Precise, deliberate, time-aware — every event lands cleanly
     - **Emoji:** 📅
     ```
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/IDENTITY.md`
- **Parallel?**: [P] after T006.

### Subtask T008 – SOUL.md

- **Purpose**: Voice, privacy boundary, Output Discipline block per pattern.
- **Steps**:
  1. Create `scripts/openclaw/agents/felix-admin-calendar/SOUL.md` (~3,000–4,000 chars).
  2. Mirror `scripts/openclaw/agents/felix-admin-habits/SOUL.md` structure: Purpose / Voice principles (same canonical block) / Privacy boundary / Output Discipline.
  3. Purpose: a sentence stating the calendar subagent's role — "felix-admin-calendar. Your purpose is calendar-substrate work: creating Google Calendar events from inbox-extracted payloads, handling clarification round-trips when capture's extraction was incomplete, and (future) calendar credential health, RRULE handling, and attendee management."
  4. Include the canonical Output Discipline Hard Rules block from `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` lines ~33–84 — copy verbatim.
  5. Privacy boundary: "NEVER read, process, route to, or reference `04-Growth/_private/`."
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/SOUL.md`
- **Parallel?**: [P] after T006.

### Subtask T009 – AGENTS.md (the longest subtask in this WP)

- **Purpose**: Charter + handler logic. The substantive content moved from main.
- **Steps**:
  1. Create `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md`. Structure:
     ```
     # AGENTS.md — felix-admin-calendar

     ## Charter
     <2-3 paragraphs declaring calendar-substrate as this agent's domain. Future scope: credential health, RRULE integration, attendee tracking. Current scope: event creation + clarification reply.>

     ## Memory / Red Lines / Verbatim Pass-Through
     <Match main agent's section structure for these standard preambles>

     ## Calendar event creation handler
     <COPY VERBATIM from main/AGENTS.md lines 259–331, with one change: in log_action invocations, replace --agent main with --agent felix-admin-calendar>

     ## Calendar clarification reply handler
     <COPY VERBATIM from main/AGENTS.md lines 333–440, same --agent value substitution>
     ```
  2. Update `--agent` value: every occurrence of `--agent main` in the log_action commands becomes `--agent felix-admin-calendar`. Search the moved content carefully. Two known instances in the calendar event creation handler (success + failure log_action). Possibly more in clarification reply.
  3. Update the cross-reference at line 387 of the original ("Self-dispatch into the Calendar event creation handler above") — confirm the relative reference still makes sense inside this new file (handlers are sibling sections).
  4. Verify size: `wc -c scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` should be < 12,000. If over, conduct prose compression on the charter section first (handlers stay verbatim).
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md`
- **Parallel?**: No — too central. Do this as a focused single-pass.
- **Notes**: Per `feedback_wp_prompts_grep_codebase`, verify the EXACT line range and current content before excerpting — main/AGENTS.md may have shifted since this prompt was generated.

### Subtask T010 – TOOLS.md

- **Purpose**: Agent-specific tool references (gog CLI invocation patterns, Google Calendar API notes).
- **Steps**:
  1. Create `scripts/openclaw/agents/felix-admin-calendar/TOOLS.md` (~500–1500 chars).
  2. Document gog: invocation template (from contracts/calendar-event-payload.md), OAuth note ("wired via openclaw-gateway-env systemd EnvironmentFile and GOG_KEYRING_PASSWORD; no per-call credential work").
  3. Reference `contracts/calendar-event-payload.md` as the authoritative payload contract.
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/TOOLS.md`
- **Parallel?**: [P] after T006.

### Subtask T011 – USER.md

- **Purpose**: Identity of the human served (Kent).
- **Steps**:
  1. Create `scripts/openclaw/agents/felix-admin-calendar/USER.md`. Mirror `scripts/openclaw/agents/felix-admin-habits/USER.md` shape.
  2. Include: Kent's name, timezone (America/New_York), default calendar account (kent@intentional.biz), preferences relevant to calendar work (event timing patterns, attendee defaults if any).
- **Files**: `scripts/openclaw/agents/felix-admin-calendar/USER.md`
- **Parallel?**: [P] after T006.

### Subtask T012 – Verify size gate

- **Purpose**: Confirm the test-first assertion passes.
- **Steps**:
  1. From repo root: `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_felix_admin_calendar_agents_md_under_12k -v`
  2. Expected: PASS (was failing before this WP).
  3. If FAIL: compress AGENTS.md charter prose; do NOT touch handler content (it's a verbatim move).
- **Files**: none (verification step)
- **Parallel?**: No — runs last.

## Test Strategy

WP01's pytest helpers ARE the test for this WP. The `test_felix_admin_calendar_agents_md_under_12k` assertion transitions from FAIL to PASS as a direct consequence of T009+T012.

`test_openclaw_config_schema.py` assertions stay RED until WP04 lands the openclaw.json mutation (and the fixture is updated).

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Calendar handler content drifts during the move (typos, broken cross-references) | T009 is a focused single-pass; reviewer does line-by-line diff between original main lines 259–440 and new felix-admin-calendar/AGENTS.md handler sections |
| `--agent main` → `--agent felix-admin-calendar` substitution missed | Reviewer greps the new file for `--agent main` → expect zero hits |
| Charter prose pushes file over 12K cap | T012's pytest assertion gates; compress charter before resorting to handler compression |
| Output Discipline block not present (per `reference_felix_output_discipline_pattern`) | Reviewer confirms block presence; canonical source is `felix-admin-capture/AGENTS.md` |
| Self-dispatch reference broken after move | T009 step 3; sibling-section reference within the same AGENTS.md remains valid (Calendar clarification reply → Calendar event creation, both in this file) |

## Review Guidance

- All 5 files present in `scripts/openclaw/agents/felix-admin-calendar/`?
- Diff `scripts/openclaw/agents/main/AGENTS.md` lines 259–440 (pre-mission state) against `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` handler sections — content match line-for-line modulo the `--agent` substitution?
- `grep -n "main" scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` reveals only intended references (charter wording, not log_action --agent values)?
- `wc -c scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` < 12000?
- `pytest scripts/openclaw/agents/tests/test_agents_md_size.py::test_felix_admin_calendar_agents_md_under_12k` PASSES?
- IDENTITY.md follows the 4-line shape (Name, Creature, Vibe, Emoji)?
- SOUL.md includes the canonical Output Discipline Hard Rules block?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
