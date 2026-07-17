---
work_package_id: WP02
title: Inbox scan, Tier-1 classification, correlation record
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-008
- FR-011
- FR-014
- FR-016
tracker_refs: []
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
- T009
phase: Phase 2 - Engine
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "63112"
shell_pid_created_at: "1784328759.330247"
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/intake/scan_inbox.py
create_intent:
- scripts/intake/__init__.py
- scripts/intake/scan_inbox.py
- tests/intake/__init__.py
- tests/intake/test_scan_inbox.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/intake/__init__.py
- scripts/intake/scan_inbox.py
- tests/intake/__init__.py
- tests/intake/test_scan_inbox.py
role: implementer
tags: []
---

# Work Package Prompt: WP02 — Inbox scan, Tier-1 classification, correlation record

## ⚡ Do This First: Load Agent Profile

Use `/ad-hoc-profile-load` to load the profile and behave per its guidance first.

- **Profile**: `python-pedro` · **Role**: `implementer` · **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch / merge target: `feat/task-intake-validation-loop`. Worktree per `lanes.json`.

## Objective

Build the deterministic intake scan: enumerate not-done Vikunja **Inbox** tasks,
classify Tier-1 completeness, write a **collision-safe** correlation record and a
per-tick observability artifact, and render the numbered digest text. **No LLM.**

Read first: `contracts/helpers.contract.md` (`scan_inbox` section), `data-model.md`
(Inbox task, Intake digest/correlation record, observability artifact), spec FR-001/002/
003/008/011/014/016 + SC-001/003/009/011, `scripts/vikunja/migrate_tasks.py` (paginated
done-inclusive `GET /tasks/all`, felix-bot default `VikunjaClient`), and the habits state
dir pattern (`scripts/habits/` writes `morning-checkin-<date>.json` / `sweeper-tick-<date>.json`).

## Subtasks

### T005 — Enumerate Inbox tasks (read path)
`scripts/intake/scan_inbox.py`: resolve the Inbox project id via
`vikunja_refs.project_id("inbox")`; read tasks with the **felix-bot** token (default
`VikunjaClient`); paginate `GET /tasks/all` done-inclusive; filter to
`project_id == inbox && done == false`. Reuse migrate_tasks' pagination approach.

### T006 — Tier-1 classification (FR-002, deterministic)
For each task compute `missing_fields ⊆ {project, friction, quadrant}`: a task is
Tier-1-complete iff project ≠ Inbox AND has a schedulable `f:` (`f:1-flow`/`f:2-growth`/
`f:3-edge`) AND exactly one `q:`. `f:4-overload` does **not** satisfy friction. A task
already carrying `f:4-overload` (decomposition-pending) is **excluded from the incomplete
set** (FR-009 — do not re-prompt it). Being in Inbox ⇒ project is missing.

### T007 — Correlation record (FR-016, collision-safe)
Write an **immutable** record per `digest_id` to
`/data/services/openclaw/state/intake/digests/intake-<digest_id>.json` + update a
`latest.json` pointer. `digest_id` = `<utc-compact>-<source_cron?>`. Never overwrite a
prior same-day file. Expire digests older than the window (default 48h). Schema per
data-model (entries: `{n, task_id, title, missing_fields}`). Render `digest_text`:
numbered lines with title + missing fields (Output Discipline — one message body).

### T008 — Tick artifact + CLI
Write `intake-tick-<ET-date>.json` (`started_at_utc`, `exit_status`, `{scanned, incomplete,
prompted}`, `errors[]`). CLI flags: `--state-dir` (default the office2 path), `--now-utc`
(injectable clock — do NOT call wall-clock directly; determinism), `--dry-run` (classify +
render, no writes), `--json`. `incomplete == 0` → empty `digest_text`, no record write beyond
the tick artifact, exit 0 (SC-009). Exit non-zero only on infra failure.

### T009 — Unit tests
`tests/intake/test_scan_inbox.py` (mock Vikunja): classification incl. f:4 exclusion and
already-complete tasks; correlation-record immutability (two ticks → two files + updated
pointer, no overwrite); 48h expiry; injectable-clock determinism; SC-009 zero-incomplete →
no message; digest_text numbering.

## Definition of Done
- `python3 -m scripts.intake.scan_inbox --dry-run --json --now-utc <iso>` renders a correct digest against a mocked Inbox.
- Correlation records are immutable per `digest_id`; `latest.json` points to newest.
- `pytest tests/intake/test_scan_inbox.py -q` green; no LLM on the path; no wall-clock calls.

## Risks / reviewer guidance
- **Reviewer:** confirm the record is per-`digest_id` immutable (NOT overwrite-per-day — Codex #1); f:4 tasks are excluded from the incomplete count (Codex #4); the clock is injectable; felix-bot (read) is used, never a write.

## Implementation command
`spec-kitty agent action implement WP02 --agent claude`

## Activity Log

- 2026-07-17T22:40:45Z – claude:sonnet:python-pedro:implementer – shell_pid=58959 – Assigned agent via action command
- 2026-07-17T22:52:48Z – claude:sonnet:python-pedro:implementer – shell_pid=58959 – WP02 Inbox scan + Tier-1 classify + immutable correlation record; 29 tests green
- 2026-07-17T22:52:57Z – claude:opus:reviewer-renata:reviewer – shell_pid=63112 – Started review via action command
