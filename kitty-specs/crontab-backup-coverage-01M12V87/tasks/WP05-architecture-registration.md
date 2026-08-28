---
work_package_id: WP05
title: Architecture registration and doc surfaces
dependencies:
- WP02
- WP04
requirement_refs:
- FR-005
- FR-006
planning_base_branch: feat/crontab-backup-coverage
merge_target_branch: feat/crontab-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on feat/crontab-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/crontab-backup-coverage unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T00:37:21Z'
subtasks:
- T020
- T021
- T022
- T023
- T024
phase: Phase 3 - Register and document
history:
- at: '2026-08-28T00:37:21Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/service-dependencies.view.md
- docs/design/felix-capability-roadmap.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP05 — Architecture registration and doc surfaces

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/crontab-backup-coverage`
- **Final merge target**: `feat/crontab-backup-coverage`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch` when
  the worktree is created.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

Register both components for health monitoring, and update every architecture
surface the signal-to-doc map names for this change class. Registration is what
turns WP02's and WP04's pointers into actual alerting; without it they are files
nobody reads.

**Done when**: both components are registered with health checks that can fail,
the blocking validators pass, and the doc surfaces named by
`signal-to-doc-map.json` are updated.

**Maps to**: FR-005, FR-006, NFR-004, SC-005.

---

## Required reading

Run this to get the authoritative target list — note `change_class` is nested
under `match`, not top-level, which is easy to get wrong:

```bash
python3 - <<'PY'
import json
m=json.load(open('docs/design/architecture/data/signal-to-doc-map.json'))
for e in m['mappings']:
    mt=e.get('match') or {}
    if mt.get('source')=='mission-architecture-impact':
        print(mt.get('change_class'), '->', e.get('doc_targets'))
PY
```

The relevant classes are `service-added-or-modified`,
`systemd-unit-added-or-modified`, `data-flow-added-or-modified`.

Also read, before writing any JSON:
- `tooling/scripts/validate_architecture_data.py` — the blocking CI validator.
  There is no JSON Schema; this file *is* the schema.
- `tests/canary/test_inventory_health_checks.py` — a second, stricter gate.
- The `security-monitor` entry in `service-inventory.json` — the best `state-file`
  health-check model in the file.

---

## Subtasks

### T020 — Register `crontab-capture`

**Steps**:

1. Add an entry to the `services` array of
   `docs/design/architecture/data/service-inventory.json`:
   - `type`: `systemd_user_timer` (a valid `SERVICE_TYPES` member — verified)
   - `status`: `active`
   - `host`: `office2`
   - `schedule` / `schedule_note` reflecting the hourly timer
   - `script`, `exec_start`, `purpose`, `risk_tier: 3`
   - `deployed_by`: the issue reference
2. `health_check`:
   - `method`: `state-file`
   - `state_path`: `/data/services/host-state/last-tick.json` — **absolute**, and
     declared as `state_path`, not smuggled into `endpoint`
   - `max_age_seconds`: `7200` — an `int`, never a bool or string; twice the
     hourly interval, per the sub-hourly convention
   - `expected`: prose stating that `status=success` with a recent
     `completed_at_utc` means the capture ran; note that a refusal writes
     `status=error` and is *not* healthy
   - `timeout_seconds`: `5`
3. Add a `dependencies` entry expressing that this component's output is consumed
   by `restic-backup`.
4. Update the file's `last_updated` and append to `updated_by`, matching the
   existing style.

**Validation**:
- [ ] `max_age_seconds` is a positive integer literal
- [ ] `state_path` is absolute and not under `/tmp`

### T021 — Register `agent-drift-check`

**Steps**:

1. Add an entry for `scripts/openclaw/enforcement/drift_check.py`:
   - `type`: `cron` (it runs from the `claude` crontab at `0 6 * * *` — do **not**
     change that crontab)
   - `schedule`: `0 6 * * *`, `cron_user`: `claude`
   - `exec_start` matching the existing crontab line
   - `purpose` naming agent workspace drift enforcement (mission 028)
2. `health_check`:
   - `method`: `state-file`
   - `state_path`: `/data/services/openclaw/state/enforcement/last-tick.json`
   - `max_age_seconds`: `108000` (24h cycle + 6h slack, mirroring
     `security-monitor`)
   - `expected`: prose that makes the distinction explicit — `status=success`
     with `exit_code=0` means the check **ran**; `has_drift: true` is a finding,
     **not** a health failure, and is reported through the drift check's own
     alerting path
3. Do not reference `/tmp/drift-check.log` as a health signal anywhere.

**Validation**:
- [ ] Nothing in the entry probes `/tmp`
- [ ] The `expected` prose states that drift-found is still healthy

### T022 — Data-flow surfaces

**Steps**:

1. Add the new flow to `docs/design/architecture/data/data-flows.json`:
   producer `crontab-capture` → storage `/data/services/host-state/crontabs/` →
   consumer `restic-backup`, and the recovery path where a human is the consumer.
2. Reflect it in the narrative `docs/design/architecture/data-flows.md`.
3. Reflect it in the Mermaid view `docs/design/architecture/data-flows.view.md`,
   matching the existing diagram conventions.

**Validation**:
- [ ] The Mermaid block parses
- [ ] JSON and narrative agree with each other

### T023 — Service inventory narrative and dependency view

**Steps**:

1. Update `docs/design/architecture/service-inventory.md` with both components,
   matching the surrounding format.
2. Update `docs/design/architecture/service-dependencies.view.md` so
   `crontab-capture` appears with its edge to `restic-backup`.

**Validation**:
- [ ] Narrative matches the JSON — the JSON is authoritative on conflict

### T024 — Capability roadmap note

**Steps**:

1. Add a brief note to `docs/design/felix-capability-roadmap.md` recording that
   host-state capture now exists, scoped to the `claude` crontab, and that the
   `kgale`/`root` crontabs remain uncovered because reading them needs privilege.
2. Keep it short and factual. State the limit explicitly — an over-broad claim
   here is worse than no note, because the next incident will be planned against
   it.

**Validation**:
- [ ] The `claude`-only scope is stated, not implied

---

## Definition of Done

- [ ] Both components registered with pointer-method health checks
- [ ] `python3 tooling/scripts/validate_architecture_data.py --strict` passes
- [ ] `python3 -m pytest tests/canary/test_inventory_health_checks.py -v` passes
- [ ] `python3 tooling/scripts/validate_docs.py` passes
- [ ] `make test` at or above the 6177 floor
- [ ] All doc surfaces from the signal-to-doc-map query updated, or a written
      no-change rationale for any skipped one
- [ ] No file outside `owned_files` modified

## Out of scope

- `docs/INDEX.md` — owned by **WP01**.
- `docs/design/architecture/data/audited-surfaces.json`. The signal-to-doc map
  lists it for `systemd-unit-added-or-modified`, but its `systemd-user-units`
  surface **already** matches `scripts/office2/*.service` and `*.timer`
  (verified), so no pattern change is needed. Record that as the no-change
  rationale. Do **not** edit the file — its `rebaseline_command` is parsed by
  `rebaseline.py:585-586` and any change there silently degrades every
  deferred-confirm audit (C-001).
- Writing the pointers themselves — WP02 and WP04.

## Reviewer guidance

The failure mode to hunt is a health check that cannot fail — the #891 class. For
each entry ask: what concrete condition makes this report unhealthy, and is that
condition reachable? A `state-file` check with an absolute path and an integer
`max_age_seconds` is reachable; a missing bound degrades to liveness-only and
passes forever. Then check the inverse for `agent-drift-check`: a drift-finding
run must **not** read as unhealthy. Finally, confirm `audited-surfaces.json` is
untouched.
