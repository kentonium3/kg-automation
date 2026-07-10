---
work_package_id: WP02
title: felix-deployer subsystem migration (+ real stderr)
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-006
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
- T011
- T012
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "22532"
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/deploy/felix-deployer/notify.py
- scripts/deploy/felix-deployer/_tick.py
- scripts/deploy/lib/health.py
- scripts/openclaw/deploy/deploy_agent_prompts.py
- tests/deploy/test_notify.py
- tests/deploy/test_tick_ffrace.py
- tests/deploy/test_tick_rebaseline.py
- tests/deploy/test_health.py
- tests/openclaw/test_deploy_agent_prompts.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load python-pedro` before anything else.

## Objective

Migrate the **felix-deployer notification subsystem** onto the `felix-alert` bus (`emit()` from WP01),
delete its own curl code, and — critically — thread the **real captured error/stderr** into failure
alerts so an operator can diagnose without logging into office2 (SC-002 / the #699 opacity class).

Read first: `../research.md` D8 (stderr threading is a HARD requirement) + D3, `../contracts/alert-bus-api.md`
§1 and §5, `../plan.md` IC-05. Depends on WP01's public API being merged/available.

## Context (current code)

- `scripts/deploy/felix-deployer/notify.py` has three emit paths: `dispatch_failure_notification`,
  `dispatch_rebaseline_alert`, and a health path; each builds a title/body and runs curl.
- `scripts/deploy/lib/health.py::dispatch_health_notification` is a generic notifier returning **bool**
  (True iff POST rc==0); `health.record()` uses that bool to stamp `last_alert_ts`.
- `scripts/deploy/felix-deployer/_tick.py` calls the notify functions (failure at ~:622, rebaseline at
  ~:985) and the health notifier (~:148). **`_tick.py` currently passes only `result.summary`** to the
  failure notification — `scripts/deploy/lib/apply.py` already captures `stderr_excerpt`, so the real
  error exists upstream but is dropped at the call site. That is exactly the #699 gap.
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (agent-prompt-sync) loads `notify.py` via importlib
  and calls `dispatch_health_notification` for its git-advance behind-N health signal.

## Subtasks

### T008 — Migrate `notify.py` emit paths → `emit()`
- Replace the curl blocks in `dispatch_failure_notification` and `dispatch_rebaseline_alert` with an
  `Alert(...)` + `emit()` call. Choose severity: failures → `Severity.ERROR`; a rebaseline anomaly that
  needs immediate action → `Severity.ERROR` (or `CRITICAL` if the existing semantics were urgent — match
  today's intent). Keep each function's existing signature/return contract used by `_tick.py`.
- Remove the module's curl constants/helpers once no path uses them.

### T009 — Thread real stderr into failure alerts (SC-002)
- At the `_tick.py` failure call site (~:622), pass the apply result's `details` — `stderr_excerpt`,
  `stdout_excerpt`, `argv`/`failed_command`, `returncode`, `phase`, `manifest_path` — into the Alert
  `details` (via `notify.dispatch_failure_notification`'s parameters; extend them if needed). The rendered
  alert body must name the failing cause (e.g. a non-executable deploy script), not just "dry-run failed".

### T010 — Migrate `health.py` `dispatch_health_notification` → `emit()`
- Replace its curl block with `emit()`. **Preserve the bool return** (`return result.ok`) so
  `health.record()` still stamps `last_alert_ts` correctly. Map the caller's topic-env fallback logic to
  the bus (the bus now resolves the single `FELIX_ALERT_NTFY_TOPIC`; the old per-actor topic-env params
  become vestigial — remove or make them no-ops, and note it in the migration).

### T011 — Update the agent-prompt-sync consumer
- In `deploy_agent_prompts.py`, keep calling the (now bus-backed) health notifier; ensure its
  `health.record()` path still receives a bool and stamps `last_alert_ts`. No behavior change beyond the
  delivery backend. (Runtime env wiring for this service is WP05.)

### T012 — Update tests (+ #699 regression)
- Update `tests/deploy/test_notify.py`, `test_tick_ffrace.py`, `test_tick_rebaseline.py`,
  `tests/deploy/test_health.py`, `tests/openclaw/test_deploy_agent_prompts.py` to assert on `emit()`
  (mock the bus) instead of curl. Add a **#699 regression test**: a failure whose apply result carries a
  distinctive stderr string produces an alert whose body contains that string.

## Branch Strategy

Base/merge = `feat/unified-alert-bus`; execution worktree per `lanes.json`. This WP depends on **WP01**
— branch from the base that includes WP01's merged bus API.

## Definition of Done

- [ ] `notify.py`, `health.py` contain **no curl/ntfy code** — delivery is via `emit()` only (SC-006).
- [ ] felix-deployer failure alerts carry the real stderr (`stderr_excerpt` etc.) in Alert.details (SC-002).
- [ ] `health.py` still returns bool; `last_alert_ts` stamping preserved for both felix-deployer and agent-prompt-sync.
- [ ] `pytest tests/deploy tests/openclaw/test_deploy_agent_prompts.py` green, incl. the #699 regression test.

## Reviewer guidance

Confirm the stderr actually reaches `Alert.details` (trace `_tick.py` → notify → emit); verify the bool
return contract is intact (grep `last_alert_ts`); ensure no curl remnants; check that removing the old
topic-env params didn't break `health.record()` callers.

## Activity Log

- 2026-07-10T12:22:35Z – claude:sonnet:python-pedro:implementer – shell_pid=4043 – Assigned agent via action command
- 2026-07-10T12:38:29Z – claude:sonnet:python-pedro:implementer – shell_pid=4043 – Ready: felix-deployer notify/health/rebaseline migrated to felix-alert emit() (SC-006, no curl/subprocess code in notify.py or health.py); #699 fix threads apply result stderr_excerpt/argv/returncode/manifest_path into Alert.details (regression test asserts cause reaches rendered body); bool contract for last_alert_ts preserved. 514/514 owned tests pass; diff-scoped ruff exit 0.
- 2026-07-10T12:39:16Z – claude:opus:reviewer-renata:reviewer – shell_pid=22532 – Started review via action command
- 2026-07-10T12:44:35Z – user – shell_pid=22532 – Review passed: notify.py + health.py contain zero curl/ntfy/subprocess code — delivery via emit() only (SC-006 verified by grep + test_notify_has_no_curl_or_subprocess). SC-002 core fix confirmed: _tick.py:~622 threads apply result's real error context (stderr_excerpt/stdout_excerpt/argv/failed_command/returncode/manifest_path/error_code) into Alert.details; #699 regression test asserts the distinctive stderr string reaches BOTH alert.details AND the real render_body() output — proved NON-synthetic (breaking the threading makes it fail). Signatures/return contracts preserved: failure/rebaseline paths return LibResult, health path returns bool (result.ok) so health.record() stamps last_alert_ts for both felix-deployer and agent-prompt-sync (verified end-to-end). Redaction judgment: _TOKEN_RE can redact very long unbroken path runs to [REDACTED], but realistic deploy-failure stderr (Permission denied, not executable, No such file, exit 126, No module named X) always preserves the diagnostic CAUSE plus the manifest name (title) and returncode — over-redaction degrades the path, never the cause, so SC-002 intent holds; consistent with the documented better-to-over-redact-than-leak invariant. Scope clean (7 owned files only). 514/514 tests pass. Anti-pattern checklist 1-8 all PASS/N-A.
