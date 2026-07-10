---
work_package_id: WP03
title: felix-health-check migration + AlertResult adapter
dependencies:
- WP01
requirement_refs:
- FR-006
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
agent: claude
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/office2/felix_health_check/
create_intent:
- tests/office2/__init__.py
- tests/office2/felix_health_check/__init__.py
- tests/office2/felix_health_check/test_run.py
execution_mode: code_change
owned_files:
- scripts/office2/felix_health_check/run.py
- tests/office2/__init__.py
- tests/office2/felix_health_check/__init__.py
- tests/office2/felix_health_check/test_run.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load python-pedro` before anything else.

## Objective

Migrate `scripts/office2/felix_health_check/run.py` onto the `felix-alert` bus while **preserving its
`{attempted, sent, detail}` signal shape** (written to `last-run.json`) via an explicit adapter.

Read first: `../contracts/alert-bus-api.md` §5 (adapters), `../plan.md` IC-05. Depends on WP01.

## Context

- `run.py` currently POSTs via curl (`_send_ntfy` ~lines 163–219), resolves `NTFY_TOPIC` from env, and
  returns `{"attempted": bool, "sent": bool, "detail": str}`; the caller persists this to a signal file.
- The bus resolves the single `FELIX_ALERT_NTFY_TOPIC`; the old `NTFY_TOPIC` var becomes vestigial
  (runtime env wiring is WP05).

## Subtasks

### T013 — Migrate the send path → `emit()`
- Replace the curl block with an `Alert(source="felix-health-check/run", severity=Severity.ERROR,
  title=…, description=…, details=…)` + `emit()`. Keep the existing title and the truncated bash-output
  body content (fold the output into `description`/`details` — the bus renderer truncates/redacts).

### T014 — `AlertResult → {attempted, sent, detail}` adapter
- Add a small adapter: `attempted = result.topic_configured`, `sent = result.ok`,
  `detail = result.reason or "delivered"`. Keep `last-run.json` byte-compatible with today's shape so no
  downstream consumer breaks (NFR-004).

### T015 — Unit tests
- New `tests/office2/felix_health_check/test_run.py` (mock the bus). Cover the adapter for three cases:
  missing topic (`attempted=False, sent=False`), curl failure (`attempted=True, sent=False`), success
  (`attempted=True, sent=True`). Add the `__init__.py` files so the test package imports.

## Branch Strategy

Base/merge = `feat/unified-alert-bus`; worktree per `lanes.json`. Depends on **WP01**.

## Definition of Done

- [ ] `run.py` has no curl/ntfy code; delivery via `emit()` (SC-006).
- [ ] `last-run.json` `{attempted,sent,detail}` shape unchanged across missing-topic/failure/success.
- [ ] `pytest tests/office2/felix_health_check` green.

## Reviewer guidance

Verify the adapter mapping matches the contract exactly and that the signal-file shape is byte-compatible
with the pre-migration output; confirm no live ntfy in tests.
