---
work_package_id: WP06
title: Architecture docs + alerting runbook
dependencies:
- WP05
requirement_refs:
- FR-001
- FR-005
- FR-007
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T023
- T024
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "41648"
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks/alerting.md
create_intent:
- docs/runbooks/alerting.md
execution_mode: code_change
owned_files:
- docs/runbooks/alerting.md
- docs/design/architecture/data/service-inventory.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load curator-carla` before anything else.

## Objective

Document the `felix-alert` bus so it is discoverable and reusable, and record it in the authoritative
architecture data. Satisfies the architecture-doc standing requirement (Directive 5).

Read first: `../spec.md`, `../contracts/alert-bus-api.md`, `../data-model.md`, `../plan.md` IC-08. Depends
on WP05 (final wiring known).

## Subtasks

### T023 — `service-inventory.json`
- Add the alert-bus shared library + the unified operator-alerts topic to
  `docs/design/architecture/data/service-inventory.json` (set `updated_by` to `701`). Note that the three
  migrated emitters now deliver via the bus and their old per-component topics are retired. Keep JSON
  authoritative; if a markdown view mirrors this JSON, sync it (a small out-of-map edit with a one-line
  rationale is acceptable) and ensure the architecture-data validator passes.

### T024 — `docs/runbooks/alerting.md`
- New runbook: what the bus is, the `Alert` schema, the severity→priority/tag map, and **how to emit**
  from Python (`from scripts.common.alert_bus import emit, Alert, Severity`), the CLI
  (`python3 -m scripts.common.alert_bus emit …`), and bash (`scripts/common/alert_bus.sh emit …`). Cover
  the topic-secret provisioning model, the fail-safe contract, and the self-test. Link it from the
  observability/coherence docs that already reference `felix-alert` (do not restructure those docs).

## Branch Strategy

Base/merge = `feat/unified-alert-bus`; worktree per `lanes.json`. Depends on **WP05**.

## Definition of Done

- [ ] `service-inventory.json` records the bus + unified topic (`updated_by: 701`); validator green.
- [ ] `docs/runbooks/alerting.md` documents Python/CLI/bash emit + schema + severity map + self-test.
- [ ] Any mirrored markdown view is consistent with the JSON.

## Reviewer guidance

Verify the JSON is authoritative and the validator passes; confirm the runbook's emit examples match the
actual public API + CLI contract (no drift from `contracts/alert-bus-api.md`).

## Activity Log

- 2026-07-10T13:11:55Z – claude:sonnet:curator-carla:implementer – shell_pid=38611 – Assigned agent via action command
- 2026-07-10T13:18:58Z – claude:sonnet:curator-carla:implementer – shell_pid=38611 – Ready: T023 service-inventory.json (alert-bus library + unified felix-alert topic + 3 migrated emitters + enforcement co-emit; updated_by #701) — arch-data validator 0 findings incl --strict. T024 docs/runbooks/alerting.md (Python/CLI/bash emit, Alert schema, severity->priority/tag map, topic-secret provisioning, fail-safe contract, per-runtime self-test) — emit examples verified against real scripts.common.alert_bus API/CLI, zero drift from contracts. validate_docs OK (regenerated DEVELOPER_PORTAL runbook-filter block — mechanical #492-class sync; INDEX.md flagged for follow-up, not CI-gated). Pre-commit hooks green.
- 2026-07-10T13:19:36Z – claude:opus:reviewer-renata:reviewer – shell_pid=41648 – Started review via action command
- 2026-07-10T13:22:29Z – user – shell_pid=41648 – Review passed: service-inventory.json records alert-bus library + unified felix-alert topic + 3 migrated emitters (felix-deployer/security-monitor/felix-health-check) + enforcement co-emit; updated_by credits 701; JSON valid; arch-data validator OK 0 findings incl --strict. alerting.md covers bus purpose, Alert schema, full severity->priority/tag map (info->low/information_source, warn->default/warning, error->high/rotating_light, critical->max/rotating_light,sos), Python/CLI/bash emit, topic-secret provisioning, fail-safe contract, self-test; front-matter matches repo runbook shape. Emit examples verified zero-drift vs real scripts.common.alert_bus API (import OK) + CLI --help + contracts/alert-bus-api.md. Out-of-map DEVELOPER_PORTAL.md edit is minimal (single generated runbook-filter line, build_runbook_filter.py --check exits 0, tree clean) and #492-justified. validate_docs OK. INDEX.md correctly flagged as follow-up. Anti-patterns N/A (docs-only WP); no frozen-surface violation; commit touches only 3 declared files.
