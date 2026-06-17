---
work_package_id: WP03
title: Tick integration + stamping + ntfy
dependencies:
- WP02
requirement_refs:
- FR-003
- FR-006
- FR-009
- NFR-002
- NFR-004
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
subtasks:
- T009
- T010
- T011
- T012
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/_tick.py
create_intent:
- tests/deploy/test_tick_rebaseline.py
execution_mode: code_change
owned_files:
- scripts/deploy/felix-deployer/_tick.py
- scripts/deploy/felix-deployer/notify.py
- tests/deploy/test_tick_rebaseline.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity and
boundaries before reading further.

## Objective

Wire the WP02 engine into `run_tick()`, record outcomes for observability, and
dispatch ntfy alerts on the off-happy-path events — all preserving the tick's
absolute no-crash discipline.

Read first: `scripts/deploy/felix-deployer/_tick.py` (existing tick lifecycle),
`scripts/deploy/felix-deployer/notify.py` (existing ntfy dispatch),
`../contracts/rebaseline-lifecycle-v1.md` (C1/C2/C5), `../spec.md` (FR-003/006/009).

## Context

`run_tick()` already: `git pull --ff-only` → resolves `head_sha` → scans queue →
applies manifests → logs JSON lines. It wraps notification dispatch so it never
crashes the tick. I must capture the **pre-pull** HEAD (the engine needs the
pulled range), call `observe()` after the pull, and call `reconcile()` each tick.

## Subtasks

### T009 — Tick wiring
In `run_tick()`: resolve `pre_pull_head = _resolve_head_sha(repo_root)` **before**
`git pull`, and `post_pull_head` after. After the queue loop (so manifest
application isn't delayed), call `rebaseline.observe(pre_pull_head, post_pull_head)`
then `rebaseline.reconcile(...)`. Wrap both in broad try/except that logs a
`rebaseline_error` tick entry and returns 0 — the tick must never crash on
rebaseline logic (mirror the existing notify-dispatch wrapping).

### T010 — Observability stamping
Emit tick-log entries for each engine outcome (`not_required`, `pending_set`,
`completed` with rebaselined_at_utc+baseline_count, `cleared_clean`,
`unexpected_drift`, `failed`, `stale`) per data-model.md. Where a deploy was
applied this tick, also surface the rebaseline outcome on/near the applied
record so the deploy record carries rebaseline status (FR-003).

### T011 — ntfy dispatch for off-happy-path events
Add a sibling dispatch in `notify.py` (model on `dispatch_failure_notification`):
`dispatch_rebaseline_alert(event_key, token, detail, head_sha)` for
`rebaseline_failed` / `unexpected_drift` / `stale`. Dedupe — append `event_key`
to the token's `alerts_emitted` and skip if already present (exactly one alert
per event per token, FR-006/FR-009). Body includes `surface_ids`, drifted
baselines, and the manual `rebaseline_command` from the registry. Dispatch errors
are caught and logged, never raised.

### T012 — Tests `tests/deploy/test_tick_rebaseline.py`
Mock git/audit/notify. Assert: observe+reconcile are invoked with the correct
pulled range; the happy path (`pending_set` → later `completed`) needs zero
human interaction (NFR-004); a raised exception inside the engine is swallowed
(tick returns 0); each alert fires exactly once (dedupe); and the observe+
reconcile path stays within the tick-window budget (NFR-002 — assert the wrapped
work is bounded / not blocking, e.g. no unbounded retries).

## Branch Strategy
Planning base `main`; merge target `main`; lane worktree at implement time.
WP03 depends on WP02 — its lane includes WP02's `rebaseline.py`.

## Definition of Done
- `run_tick()` invokes the engine with the real pulled range; never crashes on
  rebaseline logic.
- Outcomes recorded; deploy record carries rebaseline status (FR-003).
- ntfy alerts fire once per event (FR-006/FR-009).
- `pytest tests/deploy/test_tick_rebaseline.py` passes, incl. the NFR-002 budget assertion.

## Risks / Reviewer guidance
- No-crash discipline is paramount — review that every engine call is wrapped and
  the tick still returns 0 on any failure.
- Don't delay manifest application; rebaseline runs after the queue loop.
- Verify dedupe actually prevents an alert storm while a token stays pending across many ticks.
