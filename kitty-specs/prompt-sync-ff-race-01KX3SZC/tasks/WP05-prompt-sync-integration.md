---
work_package_id: WP05
title: prompt-sync integration — lock-wrap + advance_checkout + audit + ntfy
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
- T015
- T016
- T017
- T018
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/deploy/
create_intent: []
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- scripts/openclaw/deploy/deploy_agent_prompts.py
- scripts/openclaw/deploy/agent-prompt-sync.service
- tests/openclaw/test_deploy_agent_prompts.py
role: implementer
tags: []
shell_pid: "80886"
---

# WP05 — prompt-sync integration

## ⚡ Do This First: Load Agent Profile
Load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Objective
Route the prompt-sync tick through the new primitives while preserving its public
`GitPullResult` shape and the audit-log-jsonl contract, and give it ntfy health
alerting (it has none today).

## Context (read first)
- **Research D5 + D3**: [../research.md](../research.md) — preserve GitPullResult/audit; generic notifier + prompt-sync topic env.
- **Contract**: [../contracts/lib-api.md](../contracts/lib-api.md).
- **Code**: `scripts/openclaw/deploy/deploy_agent_prompts.py` — `git_pull()` ~line 214 (`git fetch origin main` then `git pull --ff-only origin main`; returns `GitPullResult(success, head_sha, stderr, stage)`); `run_tick` ~457; `audit_record`/`audit_append` ~262/269; per-agent copy loop in `sync_agent` ~317. Service unit: `scripts/openclaw/deploy/agent-prompt-sync.service`.
- Import primitives as in WP04. `from scripts.deploy.lib import health`.

## Subtasks

### T015 — wrap fetch/merge + copy critical section in `deploylock`
In `run_tick`, acquire `deploylock()` around the section that touches the checkout
(the `git_pull` + the per-agent prompt-copy loop). On `LockUnavailable`: append an
audit record `kind="git_pull_skipped", stage="lock", reason="lock_unavailable"`
and return the tick cleanly (defer). Do not copy prompts outside the lock.

### T016 — `git_pull` internals → `advance_checkout(assume_locked=True)`
Rewrite `git_pull()` to call `advance_checkout(repo_root, assume_locked=True)` and
adapt the result into the existing `GitPullResult(success, head_sha, stderr,
stage)`: `success = result.ok and (result.advanced or result.behind == 0)`;
`head_sha = result.post_head`; `stage = result.reason` on failure. Enrich the
existing `git_pull_failed` audit record with `local_head/origin_head/behind/ahead/reason`.
Keep `GitPullResult`'s public field names (other code/tests depend on them).

### T017 — wire health + ntfy topic
Call `health.record("agent-prompt-sync", result, state_path=<sync state dir>/git-health.json, notifier=lambda t,b: dispatch_health_notification("agent-prompt-sync", t, b, topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC"))`. Add `Environment=AGENT_PROMPT_SYNC_NTFY_TOPIC=` (documented, operator-filled) to `agent-prompt-sync.service` (or an EnvironmentFile line) so the topic is wired; note the fallback to `FELIX_DEPLOYER_NTFY_TOPIC`.

### T018 — tests (`tests/openclaw/test_deploy_agent_prompts.py`)
- `git_pull` maps `advance_checkout` results to `GitPullResult` correctly (success/no-op/diverged/fetch_failed).
- audit record for a failed advance carries the new ref-state fields; success/summary records unchanged.
- lock acquired around the tick; `LockUnavailable` → `git_pull_skipped` audit + clean defer, no prompt copy.
- health/notifier wiring (mocked).

## Definition of Done
- `git_pull` uses `advance_checkout`; `GitPullResult` shape preserved; audit contract intact + enriched.
- Lock wraps fetch/merge + copy; defer-on-lock is clean.
- ntfy topic wired in the service unit; health alerts on N confirmed failures.
- `python3 -m pytest tests/openclaw/test_deploy_agent_prompts.py` green.

## Reviewer guidance
Verify `GitPullResult` public fields are unchanged (downstream depends on them),
audit records stay contract-shaped (only additive fields), the lock covers the
copy loop too, and the ntfy topic env is actually wired (not just referenced).

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Activity Log

- 2026-07-09T17:15:09Z – claude – shell_pid=71988 – Assigned agent via action command
- 2026-07-09T17:30:05Z – claude – shell_pid=71988 – prompt-sync integration green (65 tests; openclaw+deploy 608; ruff/mypy clean); GitPullResult+audit preserved
- 2026-07-09T17:30:09Z – claude – shell_pid=80886 – Started review via action command
