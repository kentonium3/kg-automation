---
work_package_id: WP03
title: Inbox rewire + felix-admin-calendar reshape (closes
dependencies:
- WP02
requirement_refs:
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: feat/felix-calendar-helper
merge_target_branch: feat/felix-calendar-helper
branch_strategy: Planning artifacts for this mission were generated on feat/felix-calendar-helper. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-calendar-helper unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
- T013
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/route_calendar_event.py
create_intent: []
execution_mode: code_change
mission_id: 01KX4H3C4CZ2W0DRSHZHSNAY53
mission_slug: felix-calendar-helper-01KX4H3C
owned_files:
- scripts/inbox/route_calendar_event.py
- scripts/calendar_routing/validate_calendar_event.py
- scripts/openclaw/agents/felix-admin-calendar/AGENTS.md
- scripts/openclaw/agents/felix-admin-calendar/TOOLS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- tests/inbox/test_route_calendar_event.py
- tests/calendar/test_validate_calendar_event.py
role: implementer
tags: []
shell_pid: "60370"
---

# WP03 — Inbox rewire + felix-admin-calendar reshape (closes #679)

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load python-pedro` (role: implementer) first.

## Branch Strategy
- **Planning/base**: `feat/felix-calendar-helper` · **Merge target**: `feat/felix-calendar-helper`.

## Objective

Remove `gog` from the calendar surface and close #679 by making inbox capture
reach the calendar via **one deterministic command** (no agent-to-agent hop), and
reshaping `felix-admin-calendar` to judgment-only (it calls WP02's helper, not
gog). Authoritative: **`../contracts/felix-admin-calendar-reshape.md`** and
`../research.md` D4/D5. Reuse the existing deterministic parsers verbatim — only
the terminal "create" path and the default account change.

**Read first**: `scripts/inbox/route_calendar_event.py`,
`scripts/calendar_routing/validate_calendar_event.py`, the two agent AGENTS.md
files, and `scripts/inbox/handle_clarification_state.py` (clarification store is a
JSON **array** at `/data/services/openclaw/state/pending-calendar-clarifications.json`).

## Subtasks

### T009 — `route_calendar_event.py`: add `--create` mode + default account
- Add a `--create` flag (with `--source-path`) that: validates → normalizes → builds the
  `create_calendar_event` envelope → invokes the helper
  (`python3 -m scripts.google.calendar_helper create --payload-file <tmp> --idempotency-key <source_inbox_path> --json`)
  → emits a single result `{status: created|error|needs_clarification, event_id?, html_link?, missing?}`.
  On invalid/missing fields, return `needs_clarification` with the missing list (do not call the helper).
- Keep the existing `--as-delegation-payload` behavior for backward compat.
- Flip `DEFAULT_ACCOUNT` from `kent@intentional.biz` → `personal`.
- The deterministic field mapping + helper invocation live here (NOT in the agent prompt).

### T010 — `validate_calendar_event.py`: default account
- Flip `DEFAULT_ACCOUNT` `kent@intentional.biz` → `personal`. Update any fixtures/expected payloads accordingly.
- No other behavior change (NL parsing stays).

### T011 — `felix-admin-calendar` prompt reshape (AGENTS.md + TOOLS.md)
- Rewrite the calendar-create prose: **judgment-only** — parse Kent's conversational/clarification input,
  then invoke the helper (`… calendar_helper create --payload-file <tmp> --json`) instead of `gog calendar create`.
- Remove all `gog` references on the calendar surface from AGENTS.md and TOOLS.md.
- Preserve the clarification-reply handler (match reply → fill fields → re-validate → helper), using the
  existing JSON-array store. Preserve `log_action` logging. On helper exit 3/1, surface the error verbatim —
  **never** fake a created event (#683) and never fall back to gog.

### T012 — `felix-admin-capture` prompt (AGENTS.md + AGENTS.md.tmpl)
- Replace the calendar step: instead of building the envelope then `openclaw agent --agent felix-admin-calendar …`,
  run the **single** command `python3 -m scripts.inbox.route_calendar_event --create --payload-file <tmp> --source-path <abs>`
  and branch on its `status` (created → mark note processed; needs_clarification → existing clarification flow;
  error → surface). No `openclaw agent`/`sessions_send` hop. Keep AGENTS.md and .tmpl in sync.

### T013 — Update tests
- `tests/inbox/test_route_calendar_event.py`: cover the new `--create` mode (created / needs_clarification / error)
  with the helper subprocess mocked; assert `DEFAULT_ACCOUNT == "personal"` in emitted envelopes.
- `tests/calendar/test_validate_calendar_event.py`: update expected `account` to `personal` in payload assertions.

## Definition of Done
- [ ] `route_calendar_event --create` produces created/needs_clarification/error via the helper; default account personal.
- [ ] No `gog` on the calendar surface in either agent prompt; capture runs one command (no agent hop).
- [ ] Clarification round-trip preserved (JSON-array store); helper errors surfaced, never faked.
- [ ] `pytest tests/inbox/test_route_calendar_event.py tests/calendar/test_validate_calendar_event.py` passes.

## Risks / reviewer guidance
- Prompt fidelity is the #679 crux — verify capture's calendar step is a single deterministic command and that the
  weakest-model (haiku) surface is minimized (detect intent + extract NL fields + run one command + read status).
- Grep both agent workspaces for residual `gog` on the calendar surface.
- Confirm the clarification store path/format (`.json` array) is referenced correctly.

## Activity Log

- 2026-07-09T23:53:42Z – claude:opus:python-pedro:implementer – shell_pid=56852 – Assigned agent via action command
- 2026-07-10T00:02:45Z – claude:opus:python-pedro:implementer – shell_pid=56852 – Ready for review — route_calendar_event --create + judgment-only agent, no gog on calendar surface, capture runs one command (no hop), default account personal; inbox+calendar tests green.
- 2026-07-10T00:03:52Z – claude:opus:reviewer-renata:reviewer – shell_pid=60370 – Started review via action command
