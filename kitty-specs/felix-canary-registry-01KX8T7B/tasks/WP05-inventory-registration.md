---
work_package_id: WP05
title: Inventory - restic freshness normalization + runner registration
dependencies:
- WP01
requirement_refs:
- FR-007
- FR-010
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
agent: "claude"
shell_pid: "55097"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: curator-carla
role: implementer
execution_mode: code_change
authoritative_surface: docs/design/architecture/data/
owned_files:
- docs/design/architecture/data/service-inventory.json
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load curator-carla`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Make the **only** `service-inventory.json` edits this mission requires (this WP is the sole owner of that
file, so all inventory changes route here):
1. Normalize the **restic backup** onto the registry's uniform freshness path by adding
   `max_age_seconds: 100800` to its `health_check` — it becomes the first real end-to-end canary (FR-007,
   SC-005, the #511 dogfood).
2. **Register the `felix-canary` runner** itself as a Felix component (FR-010) so a stalled runner is
   detectable and so it appears in the inventory the runner reads.

No new scripts, no new pointer writer — the restic `last-backup.json` writer already exists (#511, Codex
F10). This WP is a careful data edit + semantic confirmation.

Read first: `../data-model.md` (health_check schema delta), `../contracts/canary-contracts.md` §1 + §7,
`../research.md` R11 (restic scope correction), `../plan.md` IC-05. Also read the restic entry currently in
`service-inventory.json` and `docs/runbooks/restic-backup-ops.md`.

## Context

- `docs/design/architecture/data/service-inventory.json` is the **authoritative** operational record and a
  blocking Docs-CI gate via `tooling/scripts/validate_architecture_data.py`. Edit surgically; keep the file
  valid JSON; run the validator after.
- The restic entry today: `name: restic-backup`, `type: cron`, `status: active`, `health_check.method:
  shell` with a jq one-liner that reads `/data/services/backup/state/last-backup.json` and already enforces
  a 100800-second (28 h) staleness bound. Pointer fields: `snapshot_timestamp_utc` (authoritative),
  `restic_exit_code` (good iff in {0,3}), `state_path` points at the pointer file.
- WP04 defines the runner's own tick-signal at `/data/services/felix-canary/state/last-tick.json` with a
  `completed_at_utc` timestamp field.

## ⚠️ Design callout — restic method vs the freshness probe (resolve in T022)

R11 says "add `max_age_seconds: 100800` so the **new freshness probe** (not the embedded jq) drives it
uniformly." But restic's `health_check.method` is `shell` — and the freshness probe (WP03) dispatches on the
**freshness-pointer methods** (`tick-signal-file`/`signal-file`/`state-file`), not on `shell`. Adding
`max_age_seconds` to a `shell` check is inert (the shell probe ignores it). To actually let the shared
freshness probe drive restic, its method must become a freshness-pointer method.

**Required resolution**: change the restic `health_check.method` from `shell` to **`state-file`** and add
`max_age_seconds: 100800`, keeping `state_path` (already the pointer path). Update the `expected` prose to
describe the freshness-probe semantics (pointer `snapshot_timestamp_utc` within `max_age_seconds` AND
`restic_exit_code ∈ {0,3}`) instead of the jq contract. Verify WP03's freshness probe honors those fields:
its candidate-timestamp-key list must include `snapshot_timestamp_utc`, and its explicit-error rule must
treat a `restic_exit_code` not in {0,3} as `failed`. **Coordinate with WP03** — if WP03's probe does not yet
handle the `restic_exit_code` good-set, flag it in your review handoff so WP03 covers it (they share the
freshness-probe contract; do not encode restic-specific field names anywhere except WP03's generic
candidate-key/explicit-error logic). If, on inspection, the operator/reviewer prefers to **keep** restic as
`shell` (its jq already works and this mission's value is the runner, not re-plumbing a working check), the
fallback is: leave method `shell`, still add `max_age_seconds: 100800` as documentation of the intended
bound, and note that restic remains driven by its own jq for now. **State which option you took and why in
the DoD checkbox + review handoff.** Recommended: the `state-file` conversion (it is the point of FR-007 —
uniform freshness — and removes the duplicate embedded staleness logic).

## Subtasks

### T022 — Restic freshness normalization
- Apply the design-callout resolution to the `restic-backup` entry: add `max_age_seconds: 100800`; convert
  method to `state-file` (recommended) with updated `expected` prose, keeping `state_path` and `note`.
- Do NOT touch `/data/services/backup/scripts/backup.sh` (the writer already exists — F10).

### T023 — Register the `felix-canary` runner (FR-010)
- Add a new `services[]` entry:
  - `name: felix-canary` (or the id form matching sibling entries), `type: systemd_user_timer`,
    `status: active`.
  - `health_check`: `method: tick-signal-file`, `state_path:
    /data/services/felix-canary/state/last-tick.json`, `expected`: prose describing "tick-signal written
    each pass; `status: success` and `completed_at_utc` within `max_age_seconds`; a stale/missing file
    beyond ~35 min means the timer stopped", `timeout_seconds: 5`, `max_age_seconds: 2100` (15-min cadence
    + slack).
  - A `note` pointing at `docs/runbooks/canary-registry-ops.md` (created by WP07) and describing the
    tick-signal schema (from WP04 data-model).
- Match the field ordering/style of the sibling `felix-trust-scan` entry so the diff reads cleanly.

### T024 — Confirm semantics + narrative
- Confirm `last-backup.json`'s `snapshot_timestamp_utc` is the authoritative freshness anchor the probe will
  read (cross-check `docs/runbooks/restic-backup-ops.md`); note it in the entry `note` if not already clear.
- Update the file's top-level `updated_by` to append this mission (`felix-canary-registry-01KX8T7B (#327)`)
  and `last_updated` to today; keep the existing accumulation style.
- Run `python tooling/scripts/validate_architecture_data.py` — it must exit 0 (warn-only); the two edited
  entries validate (WP01's `max-age-type` rule accepts `100800`/`2100`; no `max-age-missing` warning for
  either, since both now declare it).

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] Restic `health_check` carries `max_age_seconds: 100800`; the shell-vs-state-file decision is made and
      recorded (recommended: converted to `state-file`) — WP03 coordination noted if the probe needs the
      `restic_exit_code`/`snapshot_timestamp_utc` handling.
- [ ] `felix-canary` runner registered (`systemd_user_timer`, `active`, `tick-signal-file` health_check on
      `last-tick.json`, `max_age_seconds: 2100`).
- [ ] `updated_by`/`last_updated` refreshed; file is valid JSON (`python3 -m json.tool` clean).
- [ ] `python tooling/scripts/validate_architecture_data.py` exits 0; no new warnings on the two entries.

## Reviewer guidance

Verify: the file is still valid JSON and the diff is surgical (only the restic entry + the new canary entry
+ the header fields changed); the restic method decision is explicitly recorded and consistent with WP03's
probe (if `state-file`, WP03 must read `snapshot_timestamp_utc` + treat `restic_exit_code ∉ {0,3}` as
failed); the canary entry's `max_age_seconds` (2100) matches the 15-min cadence; no code files touched
(inventory data only).

## Activity Log
- 2026-07-11T17:45:52Z – claude – shell_pid=55097 – Assigned agent via action command
- 2026-07-11T17:52:02Z – claude – shell_pid=55097 – WP05: restic→state-file freshness + felix-canary registration; strict validator exit 0.
- 2026-07-11T17:52:08Z – user – shell_pid=55097 – APPROVE (reviewer-renata): all 5 DoD pass; FR-007+FR-010; strict exit 0; surgical diff.
