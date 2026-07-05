---
work_package_id: WP04
title: Convert felix-admin-tasker + felix-admin-calendar; audit main
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-008
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
agent: "claude"
shell_pid: "7663"
history:
- 2026-07-05 authored from plan IC-04/IC-05 (tasker, calendar, main audit)
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/felix-admin-tasker/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-calendar/AGENTS.md
- scripts/openclaw/agents/main/AGENTS.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile
Run `/ad-hoc-profile-load implementer-ivan` (role: implementer). Then read this WP.

## Objective
Convert tasker (2 `-m scripts.` + abs-path + `.tmpl`) and calendar (abs-path only) to the
canonical form; audit `main` and convert any abs-path or confirm clean. Canonical form per
`../research.md` R-02. Covers BOTH `python` and `python3` abs-path (Codex MED-1 — calendar/
tasker use bare `python`).

## Subtasks
- **T015 — tasker.** Convert the 2 `python3 -m scripts.enrichment.…` (lines ~130, 142) to the
  cd form; convert tasker's abs-path `python /home/claude/kg-automation/scripts/openclaw/observation/log_action.py`
  (line ~283) and any in `AGENTS.md.tmpl` (e.g. `.tmpl:423`, `:513`) to
  `cd "${PYTHONPATH:?…}" && python3 scripts/openclaw/observation/log_action.py`. Keep `.tmpl`↔
  `AGENTS.md` lockstep.
- **T016 — calendar.** Convert the abs-path invocations: `python /home/claude/kg-automation/scripts/openclaw/observation/log_action.py`
  (lines ~58, 64, 155) and `python3 /home/claude/kg-automation/scripts/calendar_routing/validate_calendar_event.py`
  (line ~111, note the `echo … | python3 …` pipe — the recognizer treats the pipeline as one
  logical command) to the cd form. Preserve the stdin-pipe shape.
- **T017 — main audit.** Scan `main/AGENTS.md` for the class; convert any `-m scripts.` or
  abs-path invocation, or confirm clean (0 in-scope invocations). Record the finding.
- **T018 — self-verify.** WP01 checker over all four files → 0 findings; args absolute.

## Branch Strategy
Base/merge: `feat/agent-runtime-env-guardrails`. Lane worktree from `lanes.json`.

## Definition of Done
- tasker (+`.tmpl`) + calendar scan clean; main audited (converted or confirmed clean).
- `python` and `python3` abs-path both handled. calendar stdin-pipe preserved.
- `.tmpl`↔rendered parity for tasker.

## Reviewer guidance
- Confirm calendar's `echo … | python3 validate_calendar_event.py` still pipes correctly after
  the `cd "${PYTHONPATH:?}" && …` prefix.
- Confirm `python` (not just `python3`) abs-path lines were caught.
- Run WP01 checker over all four → 0 findings; verify main's audit disposition is recorded.

## Activity Log

- 2026-07-05T22:33:52Z – claude – shell_pid=7663 – Assigned agent via action command
