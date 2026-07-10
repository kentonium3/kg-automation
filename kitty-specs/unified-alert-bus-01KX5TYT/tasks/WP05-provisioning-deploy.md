---
work_package_id: WP05
title: Provisioning, runtime env wiring, deploy manifest
dependencies:
- WP02
- WP03
- WP04
requirement_refs:
- FR-001
- FR-007
- FR-008
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
- T021
- T022
agent: "claude:sonnet:implementer-ivan:implementer"
shell_pid: "30307"
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: deploys/queued/
create_intent:
- deploys/queued/unified-alert-bus.yaml
- scripts/deploy/deploy-unified-alert-bus.py
- scripts/common/alert_bus.env.sample
execution_mode: code_change
owned_files:
- deploys/queued/unified-alert-bus.yaml
- scripts/deploy/deploy-unified-alert-bus.py
- scripts/common/alert_bus.env.sample
- docs/design/architecture/data/credential-manifest.json
- scripts/deploy/felix-deployer/felix-deployer.service
- scripts/office2/felix-health-check.service
- scripts/openclaw/deploy/agent-prompt-sync.service
- scripts/office2/deploy/felix-health-check.sh
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load implementer-ivan` before anything else.

## Objective

Make the bus actually **deliver in production**: mint/record the new dedicated topic as a credential,
wire `FELIX_ALERT_NTFY_TOPIC` into every emitting runtime, ship the code via the manifest pipeline, and
add a preflight + per-runtime self-test. Without this WP the bus is built but silently gets
`NTFY_MISSING_TOPIC` (the CRITICAL gap the post-plan review caught).

Read first: `../research.md` D5 + D9, `../plan.md` IC-07, `docs/runbooks/deploy/discipline.md`, and an
existing applied manifest (e.g. `deploys/applied/0013-felix-calendar-helper.yaml`) as the schema model.
Depends on WP02–WP04 (the migrated code must exist).

## Context

- Committed units that need env wiring: `scripts/deploy/felix-deployer/felix-deployer.service`,
  `scripts/office2/felix-health-check.service`, `scripts/openclaw/deploy/agent-prompt-sync.service`.
- `scripts/office2/security-monitor/audit.sh` runs via **cron** (no systemd EnvironmentFile) — the shim
  sources the env-file itself (built in WP01), so audit needs no unit edit, only the env-file present.
- Credential pattern to mirror: `felix-deployer-ntfy-topic` in
  `docs/design/architecture/data/credential-manifest.json` (env-file at
  `/home/claude/.config/...`, provisioned out-of-band, never committed).

## Subtasks

### T019 — Deploy manifest + entrypoint (two-file shape, per deploy discipline)
- Create the manifest `deploys/queued/unified-alert-bus.yaml` (unnumbered — felix-deployer assigns the
  applied number) modeling an existing applied manifest. Tier 3; declares `expected_baselines` for the
  audited surfaces it drifts (systemd user units it edits + security-monitor); `entrypoint` points at the
  script below.
- Create the required companion **entrypoint** `scripts/deploy/deploy-unified-alert-bus.py` (the deploy
  discipline mandates every manifest ship with a `scripts/deploy/*.{sh,py}` entrypoint supporting
  `--dry-run`/`--apply`; felix-deployer runs `<entrypoint> --dry-run` then `--apply` each tick). This is a
  **thin verify-only** entrypoint (the migrated code reaches office2 via felix-deployer's `git pull`, like
  `deploys/applied/0009`/`0013` — no rsync): `--dry-run` checks the topic env-file is present (the
  preflight) and reports; `--apply` runs the preflight presence check then `alert_bus.sh self-test` to
  prove delivery. Make it `chmod +x` and importable/runnable per repo `scripts/deploy/` conventions
  (mirror an existing entrypoint's `--dry-run/--apply` interface). Ensure `alert_bus.sh` is delivered
  with its executable bit.
- **Ownership note (orchestrator amendment):** the entrypoint was added to this WP's `owned_files` after
  the initial decomposition, which had missed the deploy discipline's two-file requirement. It is a new
  file no other WP touches (no overlap).

### T020 — Credential + env template
- Add a `felix-alert-ntfy-topic` entry to `credential-manifest.json` (type env-file, path
  `/home/claude/.config/felix/alert-bus/env`, template `scripts/common/alert_bus.env.sample`, status
  active, provisioning out-of-band, never committed). Create `scripts/common/alert_bus.env.sample` with
  `FELIX_ALERT_NTFY_TOPIC=` (placeholder only — no real topic value ever committed).

### T021 — Wire EnvironmentFile into units + deploy script
- Add `EnvironmentFile=/home/claude/.config/felix/alert-bus/env` to the three `.service` units above.
  Keep their existing `EnvironmentFile`/`Environment` lines. Update `scripts/office2/deploy/felix-health-check.sh`
  to provision the alert-bus env-file (create the dir/file skeleton with 0600 if absent, mirroring how it
  handles `ntfy.env`) — but never write a real topic value.

### T022 — Preflight + per-runtime self-test (documented)
- The manifest's file-presence check is the deploy **preflight** (reports a missing env-file rather than
  deploying a silently-broken bus). Document the **per-runtime self-test** the operator/CI runs after
  deploy: `alert_bus.sh self-test` from the cron context, and a systemd-context self-test (a transient
  `systemd-run --user` honoring the unit EnvironmentFile) — proving delivery from both contexts. Put these
  steps in the manifest notes and reference them from `../quickstart.md`.

## Branch Strategy

Base/merge = `feat/unified-alert-bus`; worktree per `lanes.json`. Depends on **WP02, WP03, WP04**.

## Definition of Done

- [ ] `deploys/queued/unified-alert-bus.yaml` present, Tier 3, `expected_baselines` set, presence-check preflight, ships executable shim.
- [ ] `credential-manifest.json` has the `felix-alert-ntfy-topic` env-file entry; `alert_bus.env.sample` present (placeholder only).
- [ ] All three `.service` units load the alert-bus env-file; `felix-health-check.sh` provisions it (no real topic committed).
- [ ] Preflight + per-runtime self-test documented in the manifest + quickstart.
- [ ] No topic secret anywhere in the repo.

## Reviewer guidance

Confirm NO real topic value is committed anywhere; confirm each emitting runtime resolves the env
(systemd EnvironmentFile for the three services, shim-sourced env-file for cron audit); confirm the
manifest declares the right `expected_baselines` so auto-rebaseline covers the audited-surface drift.
**Rebaseline**: this WP touches audited surfaces → the merge commit must record the rebaseline outcome.

## Activity Log

- 2026-07-10T12:46:15Z – claude:sonnet:implementer-ivan:implementer – shell_pid=30307 – Assigned agent via action command
