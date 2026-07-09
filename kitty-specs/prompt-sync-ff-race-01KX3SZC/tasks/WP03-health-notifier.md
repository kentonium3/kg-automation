---
work_package_id: WP03
title: health signal watermark + generic ntfy notifier
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
- NFR-003
- NFR-004
tracker_refs: []
planning_base_branch: fix/prompt-sync-ff-race
merge_target_branch: fix/prompt-sync-ff-race
branch_strategy: Planning artifacts for this mission were generated on fix/prompt-sync-ff-race. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/prompt-sync-ff-race unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent:
- scripts/deploy/lib/health.py
- tests/deploy/test_health.py
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- scripts/deploy/lib/health.py
- scripts/deploy/felix-deployer/notify.py
- tests/deploy/test_health.py
role: implementer
tags: []
shell_pid: "70971"
---

# WP03 — health signal + generic notifier

## ⚡ Do This First: Load Agent Profile
Load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Objective
Make a silent multi-week deploy stall impossible: a per-actor health watermark
that alerts (via ntfy) after N consecutive **confirmed** failed advances, plus a
**generic** health-notification function (the existing `notify.py` is manifest-
failure-shaped, not reusable as-is). Consumes `AdvanceResult` from WP01.

## Context (read first)
- **Contract (authoritative)**: [../contracts/lib-api.md](../contracts/lib-api.md) — `health.record()` + `dispatch_health_notification()`.
- **Research D3 + D4**: [../research.md](../research.md) — confirmed-only counting, defer-benign, `failure_streak_started_ts` throttle, generic notifier.
- **Data model**: [../data-model.md](../data-model.md) — health watermark fields + alert rule.
- **Reuse**: `scripts/deploy/felix-deployer/notify.py` (`_redact_and_truncate`, `_topic_redact`, curl POST, `NTFY_TOPIC_ENV`).

## Subtasks

### T007 — health watermark schema + atomic IO (`scripts/deploy/lib/health.py`)
Per-actor JSON: `actor, consecutive_failures, failure_streak_started_ts,
last_success_head, last_success_ts, last_alert_ts, updated_ts`. Read (missing →
fresh zero-state) and write **atomically** (temp file + `os.replace`). Timestamps
are ISO-8601 UTC (accept an injected clock for tests — no bare `datetime.now()` in a way tests can't control).

### T008 — `record(actor, result, *, state_path, threshold=3, notifier=None) -> bool`
- `result.ok` (success or clean no-op) → reset `consecutive_failures=0`, clear
  `failure_streak_started_ts` and `last_alert_ts`, update `last_success_*`.
- `result.reason == "lock_unavailable"` → **no-op** for the streak (benign defer): do not increment, do not alert.
- `result.reason in {"diverged","fetch_failed","merge_failed"}` → increment; set `failure_streak_started_ts` if starting a streak.
- Alert once per streak when `consecutive_failures >= threshold` AND (`last_alert_ts is None` OR `last_alert_ts < failure_streak_started_ts`); stamp `last_alert_ts`; call `notifier`. Return True iff an alert fired.

### T009 — generic `dispatch_health_notification(actor, title, body, *, topic_env)` in notify.py
Add a generic sender that resolves the topic from `topic_env` (caller passes the
env var name; e.g. prompt-sync uses `AGENT_PROMPT_SYNC_NTFY_TOPIC`, falling back
to `FELIX_DEPLOYER_NTFY_TOPIC` if unset), reusing the existing redaction + curl
internals. Best-effort: log on failure, never raise into a tick. Do NOT break the
existing `dispatch_failure_notification`.

### T010 — tests (`tests/deploy/test_health.py`)
- streak increments only on confirmed failures; `lock_unavailable` leaves streak untouched.
- one alert per streak at threshold; no duplicate on the next failing tick.
- success resets streak + clears `last_alert_ts`; a later streak alerts again (re-alert after recovery).
- atomic write (state file valid after write); injected clock.
- `dispatch_health_notification` topic resolution + fallback + best-effort failure (notifier mocked).

## Definition of Done
- `health.py` + the new notify function match the contract; `python3 -m pytest tests/deploy/test_health.py` green.
- `lock_unavailable` never counts as a failure; throttle anchored on `failure_streak_started_ts`.
- Existing `dispatch_failure_notification` behavior unchanged (its tests still green).
- Full `tests/deploy/` suite green.

## Reviewer guidance
Verify: defer (`lock_unavailable`) is benign; exactly one alert per streak;
re-alert after recovery; atomic state write; the generic notifier reuses redaction
and does not raise. Confirm no regression to the manifest-failure notifier.

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Activity Log

- 2026-07-09T17:05:59Z – claude – shell_pid=67770 – Assigned agent via action command
- 2026-07-09T17:13:22Z – claude – shell_pid=67770 – health + generic notifier green (24 tests; full deploy suite 408)
- 2026-07-09T17:13:27Z – claude – shell_pid=70971 – Started review via action command
- 2026-07-09T17:13:55Z – user – shell_pid=70971 – Review passed: lock_unavailable benign, failure_streak_started_ts throttle, atomic write, existing notifier unbroken; 24 tests + full suite 408 green
