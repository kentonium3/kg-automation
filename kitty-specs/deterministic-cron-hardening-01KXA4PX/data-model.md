# Data Model: Deterministic escalation + weekly-report crons

Phase 1. Entities and value objects the mission introduces or touches. No new persistent store — Vikunja + JSONL state (existing) + a JSON freshness pointer.

## VikunjaScopeConfig (NEW — value object, IC-01)

The single source for Vikunja selectors, decoupling logic from the concrete taxonomy (#714).

| Field | Type | Today | Notes |
|-------|------|-------|-------|
| `escalation_excluded_project_ids` | list[int] | `[11, 13]` | Goals + Habits; escalation skips these. |
| `habit_selector` | object | `{"kind": "project_id", "value": 13}` | Habit identity. `kind ∈ {project_id, label}` so the #714 label move (`{"kind": "label", "value": "t:habit"}`) is a config edit. |

- **Invariant**: consumers read via accessors (`get_escalation_excluded_project_ids()`, `get_habit_selector()`) — never hardcode IDs.
- **Consumers**: `enumerate_candidates.py` (excluded ids); `query_active_habits_weekly.py` (habit selector); optionally the morning helper later.
- **Home**: `scripts/common/vikunja_scope.py` (Python constants + accessors). A Python module (not JSON) keeps it importable and unit-testable; a taxonomy swap is a one-line edit.

## EscalationCandidate (NEW — value object, IC-02)

One qualifying task, emitted by `enumerate_candidates.py` for the agent to act on.

| Field | Type | Source |
|-------|------|--------|
| `task_id` | int | Vikunja `id` |
| `project_id` | int | Vikunja `project_id` |
| `title` | str | Vikunja `title` |
| `due_date` | str (ISO) | Vikunja `due_date` |
| `priority` | int | Vikunja `priority` |
| `reason` | str | `"overdue"` or `"due_today_high_priority"` (which §1 branch qualified it) |

- **Emitted as**: a JSON array on stdout (see contracts/enumerate_candidates.md).
- **Qualification** (pure, tested): `done == false` AND `priority >= 2` AND `project_id NOT IN excluded` AND (`due < today` OR (`due == today` AND `priority >= 3`)); null-due sentinel excluded.

## WeeklyReportRun (NEW — process outcome, IC-03)

| Field | Type | Notes |
|-------|------|-------|
| `report_body` | str | Verbatim stdout of `query_active_habits_weekly --output text` |
| `attribution` | str (fixed) | Identity line prefixed to the delivered message (observed-mode attribution) |
| `delivery_confirmed` | bool | True only when `openclaw message send --json` confirms delivery (FR-006) |
| `tick` | TickSignal | Written after the run |

- **Invariant (FR-006)**: `delivery_confirmed` is stamped from the send result, never assumed. A generation or delivery failure surfaces (non-zero exit + OnFailure ntfy) and does **not** claim delivery.
- **Invariant (FR-005)**: delivered body = `attribution + "\n\n" + report_body`, byte-identical report portion.

## TickSignal (freshness pointer, IC-03/IC-04)

The driver's health pointer, consumed by the #722 canary `tick-signal-file` probe.

| Field | Type | Notes |
|-------|------|-------|
| `completed_at_utc` | str (ISO) | Freshness anchor |
| `exit_code` | int | 0 on success |
| `status` | str | `success` / `failure` |

- **Home**: `/data/services/felix-habits-weekly/state/last-tick.json` (atomic write).
- **max_age_seconds**: ≈ `691200` (8 days) — weekly period + slack.

## MonitoredServiceDefinition (MODIFIED — IC-04)

`docs/design/architecture/data/service-inventory.json`:
- **ADD** `felix-habits-weekly` (type `systemd_user_timer`, `health_check.method = tick-signal-file`, `endpoint` = the pointer path, `max_age_seconds ≈ 691200`).
- **MODIFY** `habit-checkin` — remove `habits-weekly-report` from the `openclaw-cron-state` `crons` list (leaving `habits-morning-checkin`).
- **UNCHANGED** `escalation-daily` (stays an `openclaw-cron-state` service).
