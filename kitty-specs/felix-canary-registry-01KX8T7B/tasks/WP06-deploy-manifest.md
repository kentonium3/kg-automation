---
work_package_id: WP06
title: Deploy - systemd timer + manifest + verify-before-enable
dependencies:
- WP04
- WP05
requirement_refs:
- FR-010
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T025
- T026
- T027
- T028
- T029
agent: "claude"
shell_pid: "69736"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
role: implementer
execution_mode: code_change
authoritative_surface: scripts/deploy/
owned_files:
- scripts/deploy/deploy-felix-canary.py
- scripts/office2/felix-canary.service
- scripts/office2/felix-canary.timer
- scripts/office2/felix-canary-onfailure.service
- deploys/queued/0017-felix-canary-registry.yaml
- tests/deploy/test_deploy_felix_canary.py
create_intent:
- scripts/deploy/deploy-felix-canary.py
- scripts/office2/felix-canary.service
- scripts/office2/felix-canary.timer
- scripts/office2/felix-canary-onfailure.service
- deploys/queued/0017-felix-canary-registry.yaml
- tests/deploy/test_deploy_felix_canary.py
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Ship the runner to office2 as a `systemd --user` timer through the **manifest discipline**: author the
systemd units (service + 15-min timer + an `OnFailure=` alert shim), the `deploy-felix-canary.py`
entrypoint, and the `deploys/queued/0017-felix-canary-registry.yaml` manifest that `felix-deployer` applies.
The deploy **verifies before enabling** by running the real unit once and asserting a tick-signal + ledger
line landed (F9, the #703 lesson), and it rebaselines the audited systemd surface.

Read first: `../contracts/canary-contracts.md` §5 (CLI) + §6 (deploy contract, F9) + §7 (registration),
`../quickstart.md` (Deploy section), `../plan.md` IC-06. **Study the sibling deploy exactly**:
`scripts/deploy/deploy-truthful-reporting.py`, `scripts/office2/felix-trust-scan.{service,timer}`, and
`deploys/applied/0015-truthful-reporting-detector.yaml`. Also read `docs/runbooks/deploy/discipline.md` and
the deploy gotchas in your review of prior missions (chmod +x; bare `python3` in ExecStart; venv absolute
python — not relevant here since this uses system `python3` -m).

## Context

- **office2 runtime**: `HOME=/home/claude`, checkout at `/home/claude/kg-automation`, `python3` only (no
  `python`). Units run as the `claude` user. Alert-bus topic env-file at
  `/home/claude/.config/felix/alert-bus/env`.
- **ExecStart form** (mirror trust-scan exactly): `/usr/bin/python3 -m scripts.canary.run --once` with
  `Environment=HOME=/home/claude`, `Environment=PYTHONPATH=/home/claude/kg-automation`,
  `WorkingDirectory=/home/claude/kg-automation`, `EnvironmentFile=-/home/claude/.config/felix/alert-bus/env`.
- **Manifest numbering**: `deploys/applied/` currently ends at `0016`; `deploys/queued/` is empty → this
  manifest is `0017`.
- **Tier**: 3 (installs a user timer + runs a self-test; no Tier 0/1/2 action). `audited_surface: true`
  (systemd units are an audited surface → rebaseline).
- **`felix-trust-scan.service` has NO `OnFailure=`** — you must ADD an `OnFailure=` shim for the canary
  (SC-006 crash detection). Do not copy trust-scan's omission.

## Subtasks

### T025 — systemd units
- `scripts/office2/felix-canary.service`: `Type=oneshot`, the ExecStart form above,
  `OnFailure=felix-canary-onfailure.service`. `Description` names the canary.
- `scripts/office2/felix-canary.timer`: `OnBootSec=5min`, `OnUnitActiveSec=15min`, `Persistent=true`,
  `WantedBy=timers.target` (copy trust-scan's timer).
- `scripts/office2/felix-canary-onfailure.service`: `Type=oneshot` that emits an out-of-band ERROR via the
  bus shim — e.g. `ExecStart=/home/claude/kg-automation/scripts/common/alert_bus.sh emit --source
  felix-canary/onfailure --severity error --title "felix-canary run failed" --description "The
  felix-canary.service run exited non-zero; the health canary did not complete a pass."` with the same
  `EnvironmentFile=-`. (This fires independent of runner logic when the main unit fails — SC-006.)

### T026 — `deploy-felix-canary.py` entrypoint
- Mirror `deploy-truthful-reporting.py`'s structure and `--apply` flag. Steps:
  1. Install the three unit files into `~/.config/systemd/user/`.
  2. `systemctl --user daemon-reload`.
  3. Run the verify-before-enable gate (T027).
  4. Only on gate success: `systemctl --user enable --now felix-canary.timer`.
  5. Report the outcome via the #701 bus (no parallel channel).
- **Byte-identical ExecStart guard (#703)**: the deploy script must derive/verify the exact `ExecStart`
  string from the installed `.service` file, not a hand-typed variant — the self-test runs the SAME command
  the timer runs. Add an explicit assertion comparing them.
- The script file must be `chmod +x` (felix-deployer runs the entrypoint directly — a live deploy lesson).

### T027 — Verify-before-enable (F9)
- (a) `python3 -m scripts.canary.run --self-check` → must print `status=ok`.
- (b) **Run the real unit once**: `systemctl --user start felix-canary.service` (the actual ExecStart, under
  the unit user + EnvironmentFile), then **assert** `/data/services/felix-canary/state/last-tick.json` was
  written with a fresh `completed_at_utc` AND a ledger line landed under
  `/data/services/felix-canary/ledger/<today>.jsonl`. This proves the deployed command can write state +
  ledger under systemd — which `--dry-run` alone cannot (dry-run writes nothing). Fail the deploy (no enable)
  if either assertion fails.
- (c) Only then enable the timer.

### T028 — Manifest
- `deploys/queued/0017-felix-canary-registry.yaml`: `schema_version: v1`, `name: felix-canary-registry`,
  `mission_slug: felix-canary-registry-01KX8T7B`, `tier: 3`, `entrypoint:
  scripts/deploy/deploy-felix-canary.py`, `audited_surface: true`, `created_by`, `apply_mode: manifest`,
  a `notes` block describing install + the F9 verify-before-enable + the `OnFailure` shim, and the
  rebaseline expectation (systemd unit audited surface → felix-deployer auto-rebaselines on the happy path;
  if any CLI-mutation drift has no repo-file signal, declare `expected_baselines`). Model the YAML on
  `deploys/applied/0015-truthful-reporting-detector.yaml`.

### T029 — Deploy-script unit tests
- `tests/deploy/test_deploy_felix_canary.py` (match the style of existing `tests/deploy/` tests — mock
  `subprocess`/systemctl; no real systemd). Cover: the byte-identical-ExecStart assertion (service file vs
  the string the script verifies); the gate fails the deploy when the tick-signal/ledger assertion fails;
  units are installed before `daemon-reload`; enable happens only after a passing gate.
- Also assert (static test) that the `.service` `ExecStart` uses `/usr/bin/python3 -m scripts.canary.run`
  (never bare `python`) and declares `OnFailure=felix-canary-onfailure.service`.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`. **Deploy happens post-merge** (feat→main→felix-deployer) — this WP only
authors the manifest + units + script + tests; it does not run the deploy.

## Definition of Done

- [ ] Three unit files authored; `.service` has `OnFailure=felix-canary-onfailure.service` and the exact
      ExecStart form (`/usr/bin/python3 -m scripts.canary.run --once`, HOME/PYTHONPATH/WorkingDir/env-file).
- [ ] `deploy-felix-canary.py` installs → daemon-reload → verify (self-check + real-unit-run asserting
      tick+ledger, F9) → enable; is `chmod +x`; asserts byte-identical ExecStart (#703); reports via the bus.
- [ ] `deploys/queued/0017-felix-canary-registry.yaml` present, tier 3, `audited_surface: true`, entrypoint
      wired, rebaseline noted.
- [ ] `pytest tests/deploy/test_deploy_felix_canary.py` green; ExecStart-equality + gate-fail + ordering
      covered; no real systemd in tests.

## Reviewer guidance

Verify: the `OnFailure=` shim exists and is wired (trust-scan lacked one — a copy-paste would miss SC-006);
ExecStart is byte-identical between the `.service` file and the deploy self-test path (#703 — the whole
point); the F9 gate runs the **real unit** and asserts tick+ledger (not just `--self-check`/`--dry-run`,
which cannot catch a state-write failure under systemd); the deploy script is executable; manifest tier +
audited_surface + numbering (0017) are correct; no Tier 0/1/2 action smuggled in.

## Activity Log
- 2026-07-11T18:28:00Z – claude – shell_pid=69736 – Assigned agent via action command
- 2026-07-11T18:38:23Z – claude – shell_pid=69736 – WP06: deploy units+script+manifest; 23 tests; verify-before-enable.
- 2026-07-11T18:38:30Z – user – shell_pid=69736 – APPROVE (reviewer-renata): all 6 DoD pass; ExecStart guard + OnFailure + enable-last F9 gate all test-proven; fixes #711 hazard.
