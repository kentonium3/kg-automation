---
work_package_id: WP02
title: Canary registry loader (registry.py)
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- FR-006
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
- T008
- T009
agent: "claude"
shell_pid: "54709"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
role: implementer
execution_mode: code_change
authoritative_surface: scripts/canary/
owned_files:
- scripts/canary/__init__.py
- scripts/canary/registry.py
- tests/canary/__init__.py
- tests/canary/test_registry.py
create_intent:
- scripts/canary/__init__.py
- scripts/canary/registry.py
- tests/canary/__init__.py
- tests/canary/test_registry.py
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Build `scripts/canary/registry.py` — the loader that turns `service-inventory.json` into the runner's work
list. It yields one `CanaryTarget` per **service-type** entry, marks each alert-eligible or not by its
declared `status` (ADR-0006), resolves the freshness pointer path, and returns a **coverage-gap set** for
live entries that declare no usable `health_check` (FR-006). This is the first module in the new
`scripts/canary/` package — you also create its `__init__.py`.

The registry is **pure and offline**: it takes the inventory as a parsed dict (or a path it reads once),
never probes anything, never calls an LLM. Probing is WP03; orchestration is WP04.

Read first: `../data-model.md` (CanaryTarget), `../contracts/canary-contracts.md` §2 (method vocabulary),
`../research.md` R3 (real vocabulary) + R9 (coverage-gap set), `../plan.md` IC-02.

## Context

- **Inventory**: `docs/design/architecture/data/service-inventory.json` — top-level `{"schema_version",
  "last_updated","updated_by","services":[...]}`. Iterate `doc["services"]`. Each entry has `name`/`id`,
  `type`, `status`, and (for service types) `health_check`.
- **Canonical type sets** — the validator (`tooling/scripts/validate_architecture_data.py`) already defines
  `SERVICE_TYPES` and `NON_SERVICE_TYPES`. **Duplicate these sets as module constants in `registry.py`**
  (with a comment pointing at the validator as the source of truth) — do NOT import from `tooling/` into
  `scripts/` (keeps the runtime package free of the tooling dependency). Only `SERVICE_TYPES` entries become
  targets; `python-module`/`library`/`cli-integration` are exempt.
- **Status vocabulary (ADR-0006)**: alert-eligible ⟺ `status ∈ {active, running}`. `suspended`,
  `deprecated`, `planned`, `retired` are **not** alert-eligible (WP03 will gate-before-probe on this flag).
- **Real method heterogeneity you must tolerate** (do NOT rewrite the inventory): methods present today are
  `http`, `shell`, `systemd-status`, `tick-signal-file`/`signal-file`/`state-file`, `log-tail`/`journal`,
  `self-check-command`/`self-test`, and `none`. You classify; WP03 dispatches.

## Subtasks

### T004 — `CanaryTarget` dataclass + type-set constants
- `@dataclass(frozen=True)` `CanaryTarget` with fields from data-model.md: `component_id: str`,
  `type: str`, `status: str`, `alert_eligible: bool`, `health_check: dict | None`, `pointer_path: str | None`.
- Module constants `SERVICE_TYPES`, `NON_SERVICE_TYPES` duplicated from the validator (comment the source).
- `component_id` = `entry["name"]` if present else `entry["id"]` (stable identity; becomes the alert
  `source` and dedup key downstream).

### T005 — Load inventory → targets
- `load_targets(inventory: dict) -> tuple[list[CanaryTarget], list[CoverageGap]]` (signature your call; keep
  it pure — accept the parsed dict). Provide a thin `load_inventory(path=DEFAULT_INVENTORY_PATH) -> dict`
  helper that reads + `json.load`s the file (module constant
  `DEFAULT_INVENTORY_PATH = Path("docs/design/architecture/data/service-inventory.json")`, injectable).
- Yield a `CanaryTarget` for **every** entry whose `type ∈ SERVICE_TYPES`. Skip `NON_SERVICE_TYPES` silently
  (they are code records, not services — exempt by design, not a gap).

### T006 — Alert-eligibility gate
- `alert_eligible = status in {"active", "running"}`. Carry it on the target. (This is the ADR-0006
  status-gates-health flag; WP03's `evaluate()` returns `suppressed` without probing when it is false.)

### T007 — Pointer-path resolution (F4)
- For a target whose `health_check.method` is a freshness-pointer method
  (`tick-signal-file`/`signal-file`/`state-file`), set `pointer_path = health_check.get("state_path") or
  health_check.get("endpoint")` — **`state_path` first, then `endpoint`** (restic sets `state_path`;
  agent-prompt-sync puts the path in `endpoint`). For non-freshness methods `pointer_path = None`.

### T008 — Coverage-gap set (FR-006)
- `@dataclass(frozen=True)` `CoverageGap` with `component_id`, `type`, `reason` (e.g. `"method-none"`,
  `"no-health-check"`, `"unhandled-method:<m>"`).
- An entry is a coverage gap **only if it is alert-eligible** (active/running) AND its `health_check` is
  missing/empty, or `method == "none"`, or `method` is not in the handled vocabulary. Suspended-class
  entries are never gaps (they're intentionally off). Return gaps as a separate list; do NOT emit here
  (WP04 emits them as WARN).
- Define the handled-method set as a module constant so "unhandled" is precise; keep it aligned with WP03's
  dispatch table (comment the cross-reference).

### T009 — Unit tests
- `tests/canary/__init__.py` (package marker) + `tests/canary/test_registry.py`.
- Build small **fixture inventories inline** (dicts) — never read the live `service-inventory.json`.
- Cover: a service-type entry becomes a target; a `python-module` entry does not; `active`/`running` →
  alert-eligible, `suspended` → not; pointer-path resolves `state_path` first then falls back to `endpoint`;
  an `active` entry with `method: none` → a gap; a `suspended` entry with `method: none` → **not** a gap;
  an unhandled method string on an active entry → a gap.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] `load_targets` yields exactly one target per service-type entry; code records are skipped.
- [ ] `alert_eligible` matches ADR-0006 (`active`/`running` only).
- [ ] Pointer path resolves `state_path`-then-`endpoint` for freshness methods; `None` otherwise.
- [ ] Coverage gaps are produced only for alert-eligible entries with no usable health_check; suspended
      entries are never gaps.
- [ ] `scripts/canary/__init__.py` exists (package importable as `scripts.canary.registry`).
- [ ] `pytest tests/canary/test_registry.py` green; tests use inline fixtures, not the live file.

## Reviewer guidance

Verify: the `SERVICE_TYPES` set matches the validator's exactly (drift here silently drops components);
gaps are gated on alert-eligibility (a suspended `method: none` must not be a gap); pointer-path order is
`state_path` **then** `endpoint` (reversing it breaks restic vs agent-prompt-sync); no probing, no network,
no LLM in the loader; the handled-method constant is consistent with WP03's dispatch.

## Activity Log
- 2026-07-11T17:45:10Z – claude – shell_pid=54709 – Assigned agent via action command
- 2026-07-11T17:53:18Z – claude – shell_pid=54709 – WP02: registry loader; 20 tests; SERVICE_TYPES matches validator.
- 2026-07-11T17:53:25Z – user – shell_pid=54709 – APPROVE (reviewer-renata): all 7 DoD pass; pointer order + gap gating + SERVICE_TYPES match verified; 20 tests.
