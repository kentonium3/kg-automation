---
work_package_id: WP04
title: audit.sh migration + enforcement co-emit
dependencies:
- WP01
requirement_refs:
- FR-006
- FR-009
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
agent: claude
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/enforcement/
create_intent:
- tests/office2/security_monitor/__init__.py
- tests/office2/security_monitor/test_audit_emit.py
execution_mode: code_change
owned_files:
- scripts/office2/security-monitor/audit.sh
- scripts/openclaw/enforcement/notification.py
- tests/openclaw/enforcement/test_notification.py
- tests/office2/security_monitor/__init__.py
- tests/office2/security_monitor/test_audit_emit.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load python-pedro` before anything else.

## Objective

Point security-monitor `audit.sh` at the bus **shim**, and add a `felix-alert` **co-emit** to the
enforcement notifier for agent-drift (keeping its existing WhatsApp + GitHub records).

Read first: `../research.md` (audit curl standardization note; D10 shim best-effort), `../contracts/alert-bus-api.md`
§3 and §5, `../plan.md` IC-06. Depends on WP01 (shim + `emit()`).

## Context

- `scripts/office2/security-monitor/audit.sh` currently hardcodes `NTFY_TOPIC="felix-office2-k9x4m2"`
  (~line 34) and posts with raw `curl -s --max-time 10 -X POST -d …` (~lines 246–251) — no
  `--fail`/`--show-error`/`--data-binary`. It runs via cron as `claude` (03:00 UTC), and notification
  failure must never fail the audit.
- `scripts/openclaw/enforcement/notification.py` alerts via WhatsApp (`send_whatsapp`) + GitHub
  (`create_drift_issue`); it does **not** use ntfy today.

## Subtasks

### T016 — Migrate `audit.sh` → `alert_bus.sh`
- Remove the hardcoded topic and the raw curl block. Replace with a call to
  `/home/claude/kg-automation/scripts/common/alert_bus.sh emit --source "security-monitor/audit"
  --severity <warn|error by alert count> --title "Felix Security Alert — office2"
  --description "<N> alert(s) on <DATE>" --detail summary="<first lines>"` (the shim is best-effort and
  sources the topic env-file — no hardcoded topic remains). Keep the audit's own control flow intact; the
  emit call must not be able to fail the cron (shim exits 0, but also guard with `|| true`).

### T017 — Enforcement co-emit
- In `notification.py`, at the drift-alert path, **add** an `emit()` call
  (`Alert(source="openclaw-enforcement/drift", severity=Severity.WARN|ERROR, title=…, description=…,
  details={... issue_url, agent ...})`) alongside the existing WhatsApp + GitHub calls. Do not remove or
  alter the WhatsApp/GitHub behavior. The co-emit is best-effort (never let it break enforcement).

### T018 — Tests
- Update `tests/openclaw/enforcement/test_notification.py`: assert the co-emit calls the bus (mock it)
  AND that WhatsApp + GitHub paths still fire (co-emit is additive, SC-007).
- Add `tests/office2/security_monitor/test_audit_emit.py` (a light test of the audit→shim invocation
  shape, or a bash-level assertion that audit calls `alert_bus.sh` and stays non-fatal on emit failure).

## Branch Strategy

Base/merge = `feat/unified-alert-bus`; worktree per `lanes.json`. Depends on **WP01**.

## Definition of Done

- [ ] `audit.sh` no longer hardcodes a topic or runs raw curl; it emits via `alert_bus.sh` and stays non-fatal.
- [ ] Enforcement emits a `felix-alert` for drift **in addition to** its WhatsApp + GitHub records (SC-007).
- [ ] `pytest tests/openclaw/enforcement/test_notification.py tests/office2/security_monitor` green.

## Reviewer guidance

Confirm the co-emit is strictly additive (WhatsApp + GitHub untouched); confirm audit's non-fatal
guarantee (emit failure cannot fail the cron); confirm no hardcoded topic remains anywhere in audit.sh.
