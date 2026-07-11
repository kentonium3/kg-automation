---
work_package_id: WP01
title: health_check max_age_seconds schema + validator support
dependencies: []
requirement_refs:
- FR-002
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
agent: "claude"
shell_pid: "38968"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
role: implementer
execution_mode: code_change
authoritative_surface: tooling/scripts/
owned_files:
- tooling/scripts/validate_architecture_data.py
- tests/tooling/test_validate_architecture_data_max_age.py
create_intent:
- tests/tooling/test_validate_architecture_data_max_age.py
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Add the **single inventory schema change** this mission needs: an optional `max_age_seconds` integer on
`health_check`, and teach the architecture-data validator to validate it. This field is the machine-readable
freshness bound that every freshness/log-scan probe reads (operator decision DM-01KX8TY3N10EQT1V81Z8DJCMRZ:
machine-readable field, **not** prose parsing). This WP is the foundation for WP02/WP03/WP05.

**You do NOT edit `service-inventory.json` data in this WP** — you only teach the validator to accept and
sanity-check the new field. The actual `max_age_seconds` values on entries are added by WP05.

Read first: `../data-model.md` (the "health_check (schema delta)" section — `max_age_seconds` is the ONLY
inventory schema change), `../contracts/canary-contracts.md` §1, `../research.md` R2.

## Context

- **File**: `tooling/scripts/validate_architecture_data.py` — a **blocking Docs-CI gate** (warn-only by
  default; `--strict` exits non-zero). Follow its existing conventions exactly.
- **Existing shape**: pure rule functions take one inventory `entry` dict + `file` and yield `Finding(file,
  entity, rule, detail)` objects. See `check_health()` (the health_check-presence rule) as your structural
  template — add a sibling rule, do not fold logic into `check_health`.
- **Canonical sets already defined at module top** (reuse them, do not redefine):
  - `SERVICE_TYPES` (cron, docker, docker-compose, host-binary, native, npm-global, openclaw-cron,
    scheduled, systemd-timer, systemd_user_timer)
  - `STATUS_ENUM` and `LIVE_STATUS_VALUES = {"active","running"}` — alert-eligibility uses the latter.
- **warn→strict pattern**: this mirrors the existing `STATUS_ENUM`/health-check posture — the omit-warning
  is a *warning* (reported, non-blocking under warn-only), NOT a hard error. Only a genuinely malformed
  `max_age_seconds` (present but not a positive int) is a real validity problem.

## Subtasks

### T001 — Validate `max_age_seconds` type when present
- Add a rule (e.g. `check_max_age_seconds(entry, file)`) that inspects `entry.get("health_check")`.
- If `health_check` is a dict **and** contains `max_age_seconds`, require it to be an `int` (reject `bool` —
  in Python `bool` is an `int` subclass, so guard with `type(v) is int` or `isinstance(v,int) and not
  isinstance(v,bool)`) and `> 0`. Otherwise yield a `Finding(rule="max-age-type", detail=...)` naming the
  bad value.
- Do NOT require the field — absence is legal (liveness-only checks omit it).

### T002 — Warn when an alert-eligible freshness/log-scan check omits `max_age_seconds`
- For an entry whose `type ∈ SERVICE_TYPES` and `status ∈ LIVE_STATUS_VALUES` and whose
  `health_check.method` is a **freshness or log-scan** method
  (`tick-signal-file`/`signal-file`/`state-file`/`log-tail`/`journal`), if `max_age_seconds` is absent,
  yield a `Finding(rule="max-age-missing", detail="alert-eligible freshness/log-scan health_check omits
  max_age_seconds; freshness cannot be evaluated")`.
- This is a **warning** (surfaces under warn-only; only fails under `--strict`), matching the existing
  posture. Define the freshness/log-scan method set as a small module constant near `SERVICE_TYPES`
  (e.g. `FRESHNESS_METHODS`) so WP02/WP03 can conceptually align (they duplicate their own copy — do not
  create a shared import dependency from `scripts/` into `tooling/`).
- Wire both new rules into whatever aggregator drives per-entry checks (find where `check_health` is
  invoked in `validate_document`/the deep traversal and add the new rule calls alongside it).

### T003 — Unit tests
- New file `tests/tooling/test_validate_architecture_data_max_age.py`.
- Cover: (a) valid positive int passes; (b) `0`, negative, `"100800"` string, `true` bool each yield a
  `max-age-type` finding; (c) an alert-eligible `tick-signal-file` entry without `max_age_seconds` yields a
  `max-age-missing` warning; (d) a `suspended` freshness entry without the field yields **no** warning
  (not alert-eligible); (e) an `http` (liveness) entry without the field yields no warning.
- Match the existing test style in `tests/tooling/` (import the rule functions directly; assert on the
  `Finding.rule` values). Do not lower the repo coverage gate.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] `max_age_seconds` present-but-invalid (non-int, ≤0, bool) yields a `max-age-type` finding.
- [ ] Alert-eligible freshness/log-scan check omitting `max_age_seconds` yields a `max-age-missing` warning;
      suspended or liveness-only entries do not.
- [ ] `python tooling/scripts/validate_architecture_data.py` still exits 0 (warn-only) on the current tree
      (the field is absent everywhere until WP05 — so only warnings, no strict failures introduced here).
- [ ] `pytest tests/tooling/` green; new tests cover accept/reject/warn/suppress paths.
- [ ] No new dependency; rule functions stay pure (no I/O).

## Reviewer guidance

Verify: the `bool`-is-not-a-valid-int guard is present (a common miss); the omit-warning is gated on
`LIVE_STATUS_VALUES` (a suspended stale-freshness entry must NOT warn); the new rules are actually wired
into the traversal (not just defined); running the validator on the real tree stays exit-0 under warn-only.

## Activity Log
- 2026-07-11T16:51:56Z – claude – shell_pid=38968 – Assigned agent via action command
