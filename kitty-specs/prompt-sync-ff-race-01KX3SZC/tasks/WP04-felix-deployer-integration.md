---
work_package_id: WP04
title: felix-deployer integration — lock-wrap tick + advance_checkout + health
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- FR-001
- FR-002
- FR-004
- FR-005
tracker_refs: []
planning_base_branch: fix/prompt-sync-ff-race
merge_target_branch: fix/prompt-sync-ff-race
branch_strategy: Planning artifacts for this mission were generated on fix/prompt-sync-ff-race. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/prompt-sync-ff-race unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/
create_intent:
- tests/deploy/test_tick_ffrace.py
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- scripts/deploy/felix-deployer/_tick.py
- tests/deploy/test_tick_rebaseline.py
- tests/deploy/test_tick_ffrace.py
role: implementer
tags: []
shell_pid: "81996"
---

# WP04 — felix-deployer integration

## ⚡ Do This First: Load Agent Profile
Load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Objective
Route felix-deployer's tick through the new primitives WITHOUT regressing the
#685/#688 rebaseline subsystem. Two things: (1) wrap the **whole** tick critical
section in `deploylock` (Codex CRITICAL — felix mutates the checkout long after
the pull: `git rm/add/commit`, `git push`, rebaseline stamp commits, watermark
writes); (2) replace the bare `git pull --ff-only` with `advance_checkout(assume_locked=True)`.

## Context (read first)
- **Research D2 + D5**: [../research.md](../research.md) — actor-level lock scope; preserve `pre_pull_head`/`post_pull_head`.
- **Contract**: [../contracts/lib-api.md](../contracts/lib-api.md) — `advance_checkout(assume_locked=True)`, `deploylock`.
- **Code**: `scripts/deploy/felix-deployer/_tick.py` — bare pull at ~line 341 (`pull = _git(["pull","--ff-only"], cwd=repo_root)`); `pre_pull_head` captured ~339; `post_pull_head` ~354 feeds the rebaseline observe range. Post-pull the tick applies manifests, commits applied records + `deploy(rebaseline)` stamps, pushes, and writes the watermark (lines ~356–740).
- Import primitives: `from scripts.deploy.lib.gitsync import advance_checkout`, `from scripts.deploy.lib.deploylock import deploylock, LockUnavailable`, `from scripts.deploy.lib import health`. Keep the `_git` seam for everything else.

## Subtasks

### T011 — wrap the whole tick body in `deploylock`
Acquire `deploylock()` at the top of the tick's checkout-touching section (from
`pre_pull_head` capture) and hold it through the watermark write. On
`LockUnavailable`: log `{"event":"tick_skip","reason":"lock_unavailable"}` and
`return 0` (benign defer — the other actor holds it; try next tick). Do NOT let the lock wrap unrelated pure-read setup that doesn't touch the checkout, but DO cover every git-mutating step.

### T012 — bare pull → `advance_checkout(assume_locked=True)`
Replace line ~341 with `result = advance_checkout(repo_root, assume_locked=True)`.
Map `result.pre_head → pre_pull_head` and `result.post_head → post_pull_head`
(the rebaseline observe range MUST be identical to today). On `not result.ok`:
- `reason == "diverged"` or `"merge_failed"` or `"fetch_failed"` → log `tick_skip`
  enriched with `local_head/origin_head/behind/ahead/reason` and `return 0`.
Keep the existing `git_pull_failed`-shaped record but add the new ref-state fields.

### T013 — wire health + fail-loud logging
Call `health.record("felix-deployer", result, state_path=<felix state dir>/git-health.json, notifier=<felix ntfy sender>)`. Ensure the failure log line carries `local_head/origin_head/behind/ahead/reason` (FR-005 fail-loud).

### T014 — tests
- Update `tests/deploy/test_tick_rebaseline.py`: prove the rebaseline observe
  range (pre/post head) is unchanged by routing through `advance_checkout` (mock
  it to return known pre/post heads).
- New `tests/deploy/test_tick_ffrace.py`: lock is acquired around the tick;
  `LockUnavailable` → `tick_skip reason=lock_unavailable`, return 0, no mutation;
  `diverged`/`fetch_failed` → enriched `tick_skip` + health increment; clean
  advance → normal flow + health reset.
- Mock git via the existing `_git`/`advance_checkout` seams.

## Definition of Done
- felix-deployer holds `deploylock` across its ENTIRE checkout-mutating section.
- `advance_checkout(assume_locked=True)` replaces the bare pull; `pre_pull_head`/`post_pull_head` semantics preserved (rebaseline range identical).
- Health wired; failures log ref state.
- `python3 -m pytest tests/deploy/test_tick_rebaseline.py tests/deploy/test_tick_ffrace.py` green; full `tests/deploy/` green.

## Reviewer guidance
The load-bearing check: the lock spans the WHOLE tick (not just the pull), and the
rebaseline range is provably unchanged. Verify defer-on-lock returns 0 without
mutating, and diverged/fetch/merge failures are logged with ref state + counted by health.

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Activity Log

- 2026-07-09T17:14:43Z – claude – shell_pid=71988 – Assigned agent via action command
- 2026-07-09T17:31:51Z – claude – shell_pid=71988 – felix-deployer integration green (53 tests; full deploy suite 434); rebaseline range preserved; lock spans whole tick
- 2026-07-09T17:31:55Z – claude – shell_pid=81996 – Started review via action command
