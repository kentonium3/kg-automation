---
work_package_id: WP03
title: Weekly-report deterministic driver + systemd units
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
- FR-006
- FR-007
tracker_refs: []
planning_base_branch: fix/deterministic-cron-hardening
merge_target_branch: fix/deterministic-cron-hardening
branch_strategy: Planning artifacts for this mission were generated on fix/deterministic-cron-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deterministic-cron-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "2196"
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/habits/weekly_report_driver.py
create_intent:
- scripts/habits/weekly_report_driver.py
- scripts/office2/felix-habits-weekly.service
- scripts/office2/felix-habits-weekly.timer
- scripts/office2/felix-habits-weekly-onfailure.service
- tests/habits/test_weekly_report_driver.py
execution_mode: code_change
owned_files:
- scripts/habits/weekly_report_driver.py
- scripts/office2/felix-habits-weekly.service
- scripts/office2/felix-habits-weekly.timer
- scripts/office2/felix-habits-weekly-onfailure.service
- tests/habits/test_weekly_report_driver.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile first: `/ad-hoc-profile-load python-pedro` (role: implementer). Adopt identity + boundaries, then proceed.

## Objective

Produce and deliver the weekly habit report with **no LLM turn**: a deterministic driver that runs the existing report helper, delivers via `openclaw message send`, confirms delivery truthfully, and writes a freshness tick — plus contracted systemd units. (FR-004/005/006/007.)

## Context

- **Depends on WP01** (the weekly helper it wraps now reads the scope config).
- Authoritative contracts: `contracts/weekly_report_driver.md` + `contracts/post-plan-review-resolutions.md` (C1/C2/H4/M11).
- The report helper (unchanged here) is `python3 -m scripts.habits.query_active_habits_weekly --output text` → prints the rendered report body on stdout, exit 0 on success.
- **Delivery interface (verified live)**: `openclaw message send --channel whatsapp --target +16179300916 --message "<body>" --json`. Use the absolute `/usr/bin/openclaw`.
- **Delivery-confirmation predicate (C1, verified)**: success = exit 0 AND non-empty `payload.result.messageId` (or top-level `messageId`) AND `dryRun == false`. Anything else = not delivered.
- Freshness tick pattern: mirror the canary/#720 `last-tick.json` (atomic write). Home: `/data/services/felix-habits-weekly/state/last-tick.json`.

### Subtask T009 — `scripts/habits/weekly_report_driver.py`

**Purpose**: the non-LLM producer+deliverer.

**Behavior**:
1. Run the report helper (in-process import preferred, or subprocess `python3 -m scripts.habits.query_active_habits_weekly --output text`). Capture the report body.
2. On helper failure (non-zero / exception): write a **`failure`** tick (`status="failure"`, `exit_code!=0`, `failure_reason`), exit non-zero. Do NOT deliver a partial/fabricated report.
3. Compose the message: `"<attribution>\n\n" + report_body` where `attribution` is a fixed identity line, e.g. `Sent by felix-habits-weekly-driver`. The report portion MUST be byte-identical to the helper output (FR-005).
4. Deliver via `openclaw message send ... --json`; parse the JSON.
5. **Confirm (FR-006/C1)**: stamp `delivery_confirmed=true` ONLY when the predicate holds. Otherwise `delivery_confirmed=false`, write a `failure` tick, exit non-zero.
6. Write `last-tick.json` atomically: `{completed_at_utc, exit_code, status, delivery_confirmed, failure_reason}`. `status="success"` only when delivered.

**Modes (C2)**:
- `--self-test`: run the helper + compose, call `openclaw message send --dry-run` (NO real send), AND write the tick. This is the deploy gate — it exercises the full path and produces a fresh tick without messaging Kent.
- `--dry-run`: preview only — print the composed message, no send, **no state written** (local preview).
- default (no flag): the real scheduled run (real send + tick).

Keep effects injected (a `run_helper` callable, a `send` callable, a `now`, a state path) so tests are offline.

### Subtask T010 — Systemd units (`scripts/office2/felix-habits-weekly.*`)  ⚠️ AUDITED SURFACE

Mirror the felix-canary units (`scripts/office2/felix-canary.*`). Contracted fields (M11):
- **`felix-habits-weekly.service`** (Type=oneshot): `Environment=HOME=/home/claude`; `Environment=PYTHONPATH=/home/claude/kg-automation`; `WorkingDirectory=/home/claude/kg-automation`; `ExecStart=/usr/bin/python3 -m scripts.habits.weekly_report_driver`; `TimeoutStartSec=120`; `OnFailure=felix-habits-weekly-onfailure.service`. Include any `EnvironmentFile=-` needed for the OpenClaw gateway token if the canary uses one (check `felix-canary.service`).
- **`felix-habits-weekly.timer`**: `OnCalendar=Mon *-*-* 06:00:00 America/New_York` (or the systemd equivalent — match the retired cron's Monday 06:00 ET slot); `Persistent=true`.
- **`felix-habits-weekly-onfailure.service`**: ntfy shim via `scripts/common/alert_bus.sh` (mirror `felix-canary-onfailure.service`).

### Subtask T011 — `tests/habits/test_weekly_report_driver.py`

Offline (fake helper + fake send + injected now/state path). Cover:
- Happy path: helper body delivered verbatim after the attribution line; tick `status=success`, `delivery_confirmed=true`.
- Helper failure → no send; tick `status=failure`; non-zero exit.
- Send returns a shape WITHOUT `messageId` (queued/failed) → `delivery_confirmed=false`; tick `status=failure`; non-zero exit (FR-006 — never claim delivery).
- Malformed JSON from send → not confirmed → failure.
- `--self-test`: writes a fresh tick, calls send with `--dry-run` (assert the dry-run flag), no real send.
- `--dry-run`: no state written, no send.

## Branch Strategy

Planning base + merge target: **`fix/deterministic-cron-hardening`**. Run in this WP's lane worktree; merge back to the mission branch. Unit installation/enabling happens later in deploy (WP04) — this WP only creates the unit files.

## Test strategy

`pytest tests/habits/test_weekly_report_driver.py -q`. Do not enable/start the units in this WP (that is WP04's deploy).

## Definition of Done

- [ ] Driver runs helper → composes (byte-identical body) → delivers → confirms via the messageId predicate → writes tick; `--self-test` and `--dry-run` modes behave as contracted.
- [ ] Never stamps `delivery_confirmed=true` without the predicate (tested).
- [ ] Systemd units created with the contracted fields (absolute python3 + openclaw, PYTHONPATH, WorkingDirectory, OnFailure).
- [ ] Tests green.

## Risks / reviewer guidance

- Reviewer verifies FR-006: the confirmation predicate is exactly C1, and every non-confirmed shape yields a failure tick + non-zero exit (no false "delivered").
- Verify the units use the **absolute** `/usr/bin/python3` and the driver uses **absolute** `/usr/bin/openclaw` (systemd has no PATH — the recurring deploy gotcha).
- Verify `--self-test` writes a tick (so WP04's deploy gate can assert freshness) while NOT sending a real message.
- Do NOT edit `query_active_habits_weekly.py` here (WP01 owns it); the driver only invokes it.

## Activity Log

- 2026-07-12T04:05:32Z – claude:sonnet:python-pedro:implementer – shell_pid=91777 – Assigned agent via action command
- 2026-07-12T04:14:15Z – claude:sonnet:python-pedro:implementer – shell_pid=91777 – WP03 impl complete: weekly_report_driver (C1 predicate, self-test) + systemd units; 30 tests/97% branch, ruff+mypy clean
- 2026-07-12T04:14:25Z – claude:opus:reviewer-renata:reviewer – shell_pid=2196 – Started review via action command
