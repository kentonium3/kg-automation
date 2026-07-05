---
work_package_id: WP02
title: Inbox state helpers — relocate to /data + ownership/mode convention
dependencies: []
requirement_refs:
- FR-004
- FR-010
- FR-012
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
shell_pid: "55465"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
create_intent:
- tests/inbox/test_state_paths.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/routing_log.py
- scripts/inbox/handle_clarification_state.py
- tests/inbox/test_state_paths.py
role: implementer
tags: []
---

# Work Package Prompt: WP02 – Inbox state helpers relocation + ownership

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Branch Strategy

- Planning/base + merge target: `fix/felix-admin-cron-path-fix`. Trust the lane path `/spec-kitty.implement` prints.

## Objectives & Success Criteria

Relocate the two inbox state files off the stray `~/second-brain/agents/state/`
(which resolves to `/home/claude/...` — unsynced) to the canonical
`/data/services/openclaw/state/`, and enforce the ownership/mode convention.
Done when both path constants point at `/data/...`, parents are created with the
right mode, and tests prove path-independence from HOME/cwd.

## Context & Constraints

- Plan IC-02; `research.md` R2/R7; `data-model.md` E1/E2; `contracts` C2/C2c.
- Canonical target dir `/data/services/openclaw/state/` exists on office2 as
  `claude:secondbrain`, mode `0750`; state files should be `claude:secondbrain 0640`.
- Both modules resolve their default **at call time** (via
  `sys.modules[__name__].DEFAULT_…`) — preserve that so tests can monkeypatch.
- **Do not** migrate live data here (that's WP05) — only change where the code reads/writes.

## Subtasks & Detailed Guidance

### Subtask T004 – routing_log.py
- **File**: `scripts/inbox/routing_log.py`
- **Steps**:
  1. Change `DEFAULT_ROUTING_LOG_PATH` (currently
     `Path.home() / "second-brain" / "agents" / "state" / "inbox-routing.jsonl"`, ~line 22)
     to the absolute `Path("/data/services/openclaw/state/inbox-routing.jsonl")`.
  2. Update the module docstring (lines ~4-7) that says it lives at
     `~/second-brain/agents/state/inbox-routing.jsonl`.
  3. In the writer's parent-dir creation (currently `mkdir(..., mode=0o700)`, ~line 135):
     create with mode `0o750` and do not force `0o700`; leave group as inherited
     (`secondbrain` via the setgid parent). Don't chown in the helper (the deploy
     entrypoint/manifest owns ownership); just avoid a too-restrictive mode.
- **Notes**: keep the call-time default resolution intact.

### Subtask T005 – handle_clarification_state.py
- **File**: `scripts/inbox/handle_clarification_state.py`
- **Steps**:
  1. Change `STATE_PATH_DEFAULT` (currently
     `Path.home() / "second-brain" / "agents" / "state" / "pending-calendar-clarifications.json"`, ~line 47)
     to `Path("/data/services/openclaw/state/pending-calendar-clarifications.json")`.
  2. Update the docstring references (lines ~14, ~248) to the new path.
  3. Where it creates the parent dir (~line 79, currently default umask): use an
     explicit mode `0o750` consistent with T004.
- **Notes**: format/semantics of the `.json` file are unchanged. The calendar
  agent's separate `.jsonl` writer is repointed in WP04 (not here).

### Subtask T006 – tests
- **File**: `tests/inbox/test_state_paths.py`
- **Steps**:
  - Assert both defaults equal the `/data/services/openclaw/state/...` absolute paths.
  - Monkeypatch `HOME` to a temp dir and change cwd; assert the resolved defaults
    are **unchanged** (they are absolute, not `~`-derived).
  - Round-trip: write an entry via the writer to a tmp path, read it back via the
    reader; a missing file yields an empty result (fail-safe), not an exception.
  - If practical, assert the created parent dir mode is not more restrictive than `0750`.

## Test Strategy

- `python3 -m pytest tests/inbox/test_state_paths.py -q` (run with `PYTHONPATH` set
  or `-m` from repo root). Tests must not depend on office2.

## Risks & Mitigations

- Hidden readers of the old path → grep confirmed only these two modules + a prescan
  docstring (prescan handled in WP03). Re-grep before finishing.

## Integration Verification (before for_review)

- [ ] Both constants absolute → `/data/services/openclaw/state/`.
- [ ] Call-time resolution preserved (monkeypatch test passes).
- [ ] Parent-dir mode not more restrictive than `0750`.

## Review Guidance

- Confirm no `Path.home()`/`~` remains in either state-path constant.

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T03:22:48Z – claude:sonnet:python-pedro:implementer – shell_pid=47053 – Assigned agent via action command
- 2026-07-05T03:28:11Z – claude:sonnet:python-pedro:implementer – shell_pid=47053 – Ready for review: routing_log.py DEFAULT_ROUTING_LOG_PATH → /data/services/openclaw/state/inbox-routing.jsonl; handle_clarification_state.py STATE_PATH_DEFAULT → /data/services/openclaw/state/pending-calendar-clarifications.json; both mkdir modes updated to 0o750; docstrings updated; 13 tests all pass; no ruff/flake8 available (not installed), syntax validated via py_compile; no stale ~/second-brain path refs remain in scripts/inbox/
- 2026-07-05T03:28:46Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=50462 – Started review via action command
- 2026-07-05T03:31:09Z – user – shell_pid=50462 – Moved to planned
- 2026-07-05T03:32:09Z – claude:sonnet:python-pedro:implementer – shell_pid=53691 – Started implementation via action command
- 2026-07-05T03:34:03Z – claude:sonnet:python-pedro:implementer – shell_pid=53691 – Cycle 2: updated stale test_routing_log.py; full inbox suite green (290 passed, 35 skipped, 1 xfailed)
- 2026-07-05T03:35:25Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=55465 – Started review via action command
