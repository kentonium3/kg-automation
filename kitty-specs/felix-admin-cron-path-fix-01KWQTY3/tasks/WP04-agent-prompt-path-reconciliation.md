---
work_package_id: WP04
title: Agent prompt path/ref reconciliation (logs, calendar .jsonl, stale refs)
dependencies: []
requirement_refs:
- FR-003
- FR-006
- FR-007
- FR-009
- FR-010
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
shell_pid: "61308"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md.tmpl
- scripts/openclaw/agents/felix-admin-calendar/AGENTS.md
- scripts/openclaw/agents/felix-admin-calendar/TOOLS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/TOOLS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/main/AGENTS.md
role: implementer
tags: []
---

# Work Package Prompt: WP04 – Agent prompt path/ref reconciliation

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load curator-carla` (role: implementer) before anything else.

## Branch Strategy

- Planning/base + merge target: `fix/felix-admin-cron-path-fix`.

## Objectives & Success Criteria

Reconcile path/reference drift across the felix-admin agent prompts (an **audited
surface**). Path strings must match the constants chosen in WP02/WP03
(`/data/services/openclaw/state/`, `/home/kgale/second-brain/agents/logs/`).
Done when the deployed prompts contain no `/home/claude/second-brain`, no
`~/second-brain` write/log target (outside `_private`), and no `~/repos/kg-automation`.

## Context & Constraints

- Plan IC-03/IC-04; `research.md` R3/R4/R7 (C3, M1); `contracts` C3/C4.
- **Scope discipline**: this WP fixes **paths/refs** and removes **false warning
  prose** only. It does **NOT** remove the functional `cd /home/claude/kg-automation &&`
  prefixes (kept as belt; their removal is #658, post SC-10 verification).
- **Absolute rule — never touch** the `~/second-brain/notes/04-Growth/_private/`
  boundary lines (they are read-prohibitions, not writers). Leave them verbatim.
- Keep `.md` and `.tmpl` copies in sync where both exist.

## Subtasks & Detailed Guidance

### Subtask T011 – Capture prompts: log path + prose (FR-006/007/003)
- **Files**: capture `AGENTS.md`, `AGENTS.md.tmpl`, `TOOLS.md`, `TOOLS.md.tmpl`
- **Steps**: repoint the forensic-log write target (the `~/second-brain/...` line
  ~565 in `AGENTS.md.tmpl`, and the corresponding `AGENTS.md`/`TOOLS.md` copies) to
  the absolute `/home/kgale/second-brain/agents/logs/`. Remove the now-false
  "Working dir: /home/claude/kg-automation" prose (line ~74 in `AGENTS.md`) — capture
  has no `cd &&` to keep, so just drop the misleading note. Reconcile `TOOLS.md` vs
  `AGENTS.md` so they agree.

### Subtask T012 – Calendar + main: clarification .jsonl path (FR-010)
- **Files**: `felix-admin-calendar/AGENTS.md` (lines ~82, ~134), `felix-admin-calendar/TOOLS.md` (~20), `main/AGENTS.md` (~198)
- **Steps**: repoint the inline `pending-calendar-clarifications.jsonl` path from
  `~/second-brain/agents/state/` (or `os.path.expanduser("~/...")`) to the absolute
  `/data/services/openclaw/state/pending-calendar-clarifications.jsonl`. **Path only** —
  do NOT change the `.jsonl` format or the inline handling logic (format unification
  is a #658 follow-up).

### Subtask T013 – Escalation: stale ref + prose (FR-009/003)
- **File**: `felix-admin-escalation/AGENTS.md` (~line 265)
- **Steps**: fix `~/repos/kg-automation/…/log_action.py` → the canonical
  `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py`. Remove any
  now-false "you must cd / ModuleNotFoundError" warning prose; keep functional cd if present.

### Subtask T014 – Tasker: refs (FR-009)
- **Files**: `felix-admin-tasker/AGENTS.md` (~283), `felix-admin-tasker/TOOLS.md` (~30)
- **Steps**: fix `~/repos/kg-automation/…/log_action.py` → `/home/claude/kg-automation/...`;
  fix `~/second-brain/agents/logs/` → `/home/kgale/second-brain/agents/logs/`. **Do NOT**
  touch the `_private` boundary lines (AGENTS.md ~101, TOOLS.md ~39).

### Subtask T015 – Habits: prose only (FR-003)
- **File**: `felix-admin-habits/AGENTS.md`
- **Steps**: remove the now-false "cwd matters / running from elsewhere produces
  ModuleNotFoundError" warning (line ~90). **KEEP** the `cd /home/claude/kg-automation &&`
  prefixes on the invocations (harmless belt; removal deferred to #658).

## Test Strategy

- Static grep gate (add to the WP's DoD, not necessarily a pytest): across all
  owned files, `grep -n "/home/claude/second-brain"` and
  `grep -n "~/second-brain" | grep -v _private` and `grep -n "~/repos/kg-automation"`
  must all be empty.

## Risks & Mitigations

- Audited surface — keep edits minimal and path-focused; note the #621 gap (AGENTS.md
  not baseline-hashed) is recorded in WP06.
- `.md`/`.tmpl` divergence — update both.

## Integration Verification (before for_review)

- [ ] Grep gate clean (no stray/stale write targets; `_private` untouched).
- [ ] Calendar `.jsonl` path is absolute `/data/...`; format unchanged.
- [ ] Functional `cd &&` prefixes in habits are still present.

## Review Guidance

- Verify no `_private` line was altered. Verify `cd &&` belts were NOT removed.

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T03:23:22Z – claude:sonnet:curator-carla:implementer – shell_pid=47053 – Assigned agent via action command
- 2026-07-05T03:29:29Z – claude:sonnet:curator-carla:implementer – shell_pid=47053 – Ready for review: grep gate clean, cd belts kept, _private lines untouched
- 2026-07-05T03:30:09Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=51712 – Started review via action command
- 2026-07-05T03:38:34Z – user – shell_pid=51712 – Moved to planned
- 2026-07-05T03:39:30Z – claude:sonnet:curator-carla:implementer – shell_pid=57941 – Started implementation via action command
- 2026-07-05T03:42:23Z – claude:sonnet:curator-carla:implementer – shell_pid=57941 – Cycle 2: fixed tasker AGENTS.md.tmpl; all 3 grep gates now clean across .md AND .tmpl
- 2026-07-05T03:43:01Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=61308 – Started review via action command
- 2026-07-05T03:46:47Z – user – shell_pid=61308 – Review passed: cycle-2 tasker AGENTS.md.tmpl sync verified; .md/.tmpl stale-path grep gates clean; contract path refs and cd/_private constraints satisfied
