---
work_package_id: WP04
title: Observability + deploy
dependencies:
- WP02
- WP03
requirement_refs:
- FR-009
- FR-010
tracker_refs: []
planning_base_branch: fix/deterministic-cron-hardening
merge_target_branch: fix/deterministic-cron-hardening
branch_strategy: Planning artifacts for this mission were generated on fix/deterministic-cron-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deterministic-cron-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
agent: claude
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/deploy-habits-weekly-driver.py
create_intent:
- scripts/deploy/deploy-habits-weekly-driver.py
- deploys/queued/habits-weekly-driver.yaml
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- scripts/deploy/deploy-habits-weekly-driver.py
- deploys/queued/habits-weekly-driver.yaml
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile first: `/ad-hoc-profile-load implementer-ivan` (role: implementer). Adopt identity + boundaries, then proceed.

## Objective

Keep both jobs observable to the #722 canary and deploy the weekly driver safely: register the weekly-driver freshness service, strip the retired cron from `habit-checkin`, and create the deploy entrypoint (transactional cutover, exactly-one-producer postcheck) + a `deploys/queued` manifest with `expected_baselines`. (FR-009/010, C-003/004.)

**Note**: this WP CREATES the deploy artifacts. The actual office2 deploy runs post-merge (felix-deployer applies the manifest); the operator handles the careful live cutover verification. Do NOT run the deploy or edit office2 in this WP.

## Context

- **Depends on WP02 + WP03** (deploys their outputs).
- Authoritative contract: `contracts/post-plan-review-resolutions.md` (C2/C3/H4/M11/M12).
- Templates to mirror: `deploys/applied/0017-felix-canary-registry.yaml` (manifest + verify-before-enable pattern) and `scripts/deploy/deploy-felix-canary.py` (entrypoint). Rebaseline mechanics: CLAUDE.md "Rebaseline Obligation"; `docs/design/architecture/data/audited-surfaces.json`.
- #722 canary probes: `openclaw-cron-state` (crons) + `tick-signal-file` freshness (`scripts/canary/probes.py`).

### Subtask T012 — `service-inventory.json` (M12 — full cleanup)

**Purpose**: register the new freshness service + retire the old cron references.

**Changes**:
- **ADD** a `felix-habits-weekly` service entry: `type: systemd_user_timer`, `status: active`, `health_check`: `{method: "tick-signal-file", endpoint: "/data/services/felix-habits-weekly/state/last-tick.json", max_age_seconds: 691200, timeout_seconds: 5, expected: "status=success, exit_code=0, fresh within ~8 days"}`. Follow the exact shape of an existing freshness service (e.g. `felix-deployer`).
- **MODIFY** `habit-checkin`: remove `habits-weekly-report` from the `health_check.crons` list (leaving `habits-morning-checkin`); ALSO remove the `habits-weekly-report` entry from that service's `schedules[]` and fix any note/purpose text that references it (M12 — not only the crons list).
- Run `python3 tooling/scripts/validate_architecture_data.py` — must be OK (blocking Docs-CI gate). `max_age_seconds` must be a positive int.

### Subtask T013 — `scripts/deploy/deploy-habits-weekly-driver.py` (C2/C3)

**Purpose**: the deploy entrypoint felix-deployer runs on office2.

**Steps (transactional cutover, C3)**:
1. Install `felix-habits-weekly.{service,timer,onfailure}` into `~/.config/systemd/user/`; `systemctl --user daemon-reload`.
2. **`--self-test` gate (C2)**: run `python3 -m scripts.habits.weekly_report_driver --self-test`; assert exit 0, a fresh `last-tick.json`, and (from the dry-run send) that the delivery path was reached — WITHOUT a real send. Abort the deploy if the gate fails (no cutover on a bad build; #711/#703 lesson).
3. **Retire the old producer**: `openclaw cron rm` the `habits-weekly-report` cron (resolve its id via `openclaw cron list --json`); assert it is absent afterward.
4. **Enable the new producer**: `systemctl --user enable --now felix-habits-weekly.timer`; assert `next elapse` is scheduled (`systemctl --user list-timers`).
5. **Exactly-one-producer postcheck (C3)**: assert the openclaw cron is absent AND the timer enabled. FAIL (and alert) if both producers exist or neither does — never leave a half state.
6. Report outcome via the #701 alert bus (mirror felix-canary).
Make the entrypoint executable (`chmod +x`) — felix-deployer runs it directly (deploy gotcha). Use absolute `/usr/bin/openclaw`, `/usr/bin/python3`.

### Subtask T014 — `deploys/queued/habits-weekly-driver.yaml` (C4)

Mirror `deploys/applied/0017-felix-canary-registry.yaml`. Key fields:
- `schema_version: v1`, `name: habits-weekly-driver`, `mission_slug: deterministic-cron-hardening-01KXA4PX`, `tier: 3`, `entrypoint: scripts/deploy/deploy-habits-weekly-driver.py`, `audited_surface: true`, `apply_mode: manifest`.
- **`expected_baselines`**: name the openclaw-config baseline the `openclaw cron rm` drifts (the cron removal has **no repo-file signal**, so the auto-rebaseline needs it declared — CLAUDE.md). The systemd-unit + AGENTS.md changes have repo-file signals and auto-rebaseline without declaration.
- `notes`: describe the transactional cutover + the exactly-one-producer postcheck.
- **Do NOT pre-number** the queued manifest (`0018-…`) — felix-deployer assigns the applied number from `max(applied)+1`; a hardcoded number causes a collision (known gotcha). Filename stays `habits-weekly-driver.yaml`.

## Branch Strategy

Planning base + merge target: **`fix/deterministic-cron-hardening`**. Run in this WP's lane worktree; merge back to the mission branch. Deploy execution is post-mission-merge (operator-run), not part of this WP.

## Test strategy

- `python3 tooling/scripts/validate_architecture_data.py` OK.
- If practical, a light unit test of the entrypoint's pure helpers (cron-id resolution parsing, postcheck logic) with fake subprocess output — no office2 access in tests.
- `make test` green (the service-inventory change must not break the canary registry tests).

## Definition of Done

- [ ] `service-inventory.json`: new `felix-habits-weekly` freshness service; `habit-checkin` fully stripped of `habits-weekly-report` (crons + schedules + notes); validator OK.
- [ ] Deploy entrypoint implements the transactional cutover + `--self-test` gate + exactly-one-producer postcheck; executable; absolute binaries.
- [ ] Manifest created with `expected_baselines` for the cron-removal drift; not pre-numbered.
- [ ] `make test` + architecture-data validator green.

## Risks / reviewer guidance

- Reviewer verifies the cutover ORDER (self-test → retire cron → enable timer → postcheck) and that a failure at any step aborts without leaving both/zero producers (C3).
- Verify `expected_baselines` covers the cron-removal drift (else felix-deployer will alert unexpected drift post-deploy).
- Verify the manifest is NOT pre-numbered and the entrypoint is chmod +x.
- Verify the freshness `max_age_seconds` (~8 days) suits the weekly cadence and the `expected` text encodes status=success + exit_code=0 (H4 — a fresh failure tick must read unhealthy).
- Do NOT deploy or touch office2 in this WP.
