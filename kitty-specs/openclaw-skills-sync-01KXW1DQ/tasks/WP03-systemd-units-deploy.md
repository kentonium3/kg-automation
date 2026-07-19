---
work_package_id: WP03
title: Systemd units + deploy manifest + entrypoint (hard enable gate)
dependencies:
- WP01
requirement_refs:
- C-002
- FR-008
- FR-012
tracker_refs: []
planning_base_branch: feat/openclaw-skills-sync
merge_target_branch: feat/openclaw-skills-sync
branch_strategy: Planning artifacts for this mission were generated on feat/openclaw-skills-sync. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/openclaw-skills-sync unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
agent: "claude"
shell_pid: "89929"
shell_pid_created_at: "1784429842.402429"
history:
- '2026-07-19: authored by /spec-kitty.tasks'
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/deploy/agent-skill-sync.service
create_intent:
- scripts/openclaw/deploy/agent-skill-sync.service
- scripts/openclaw/deploy/agent-skill-sync.timer
- scripts/deploy/deploy-skills-sync.sh
- deploys/queued/skills-sync.yaml
execution_mode: code_change
owned_files:
- scripts/openclaw/deploy/agent-skill-sync.service
- scripts/openclaw/deploy/agent-skill-sync.timer
- scripts/deploy/deploy-skills-sync.sh
- deploys/queued/skills-sync.yaml
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load implementer-ivan
```

## Objective

Schedule the sync on office2 (systemd `--user` timer) and roll it out via a `deploys/queued/`
manifest whose entrypoint runs a **HARD verify-before-enable gate** — an installed-but-not-running
timer is exactly the stranded-edit failure this mission eliminates, so a failed smoke/enable must
fail the deploy loudly (Codex #1 HIGH-1).

**Read before coding**: `scripts/openclaw/deploy/agent-prompt-sync.{service,timer}` (mirror these);
`scripts/deploy/deploy-felix-canary.py` and `scripts/deploy/deploy-habits-weekly-driver.py` (the
verify-before-enable + `systemctl --user` + `XDG_RUNTIME_DIR` precedent); `deploys/schema/
manifest-v1.schema.json` and `deploys/applied/0012-prompt-sync-ff-race.yaml` (manifest shape);
`scripts/deploy/lib/README.md` (the deploy library API); this mission's `research.md` (D-5) +
`quickstart.md`.

### Subtask T010 — `agent-skill-sync.service`

Mirror `agent-prompt-sync.service`:
- `[Unit]` Description, Documentation (point at `agent-skill-sync-ops.md`), `After/Wants=network-online.target`.
- `[Service]` `Type=oneshot`, `WorkingDirectory=/home/claude/kg-automation`,
  `ExecStart=/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_skills` (the `-m` form — a
  script-path ExecStart fails ModuleNotFoundError, #668), journal stdout/stderr,
  `TimeoutStartSec=120s`, `EnvironmentFile=-/home/claude/.config/felix/alert-bus/env` (leading `-`
  keeps startup non-fatal if absent).
- Header comment block documenting the one-time operator enable (mirroring the reference).

### Subtask T011 — `agent-skill-sync.timer`

Mirror `agent-prompt-sync.timer`:
- `[Timer]` `OnUnitInactiveSec=300s` (non-overlapping ticks; matches prompt-sync cadence, NFR-001),
  `OnBootSec=120s` (settle network/Tailscale post-boot), `Persistent=true` (one catch-up tick —
  idempotent per NFR), `Unit=agent-skill-sync.service`.
- `[Install] WantedBy=timers.target`.
- Validate locally: `systemd-analyze verify scripts/openclaw/deploy/agent-skill-sync.timer` and the
  `.service` (note: full `--user` verify runs on office2; `bash`/analyze syntax check locally).

### Subtask T012 — `deploys/queued/skills-sync.yaml`

Author a v1 manifest validating against `deploys/schema/manifest-v1.schema.json`:
- `schema_version: v1`, `name: skills-sync`, `mission_slug: openclaw-skills-sync-01KXW1DQ`,
  **`tier: 3`**, `entrypoint: scripts/deploy/deploy-skills-sync.sh`, `audited_surface: true`.
- `verification.pre`: helper + units present in the checkout
  (`test -f scripts/openclaw/deploy/deploy_agent_skills.py`, `... agent-skill-sync.service`, `.timer`).
- `verification.post`: units placed in `~/.config/systemd/user/`, timer enabled
  (`systemctl --user is-enabled agent-skill-sync.timer`), freshness signal written
  (`test -f /data/services/openclaw/deploy/skills-last-tick.json`).
- Do NOT hand-set an applied record; felix-deployer owns application. Keep numbering rules in mind
  (the applied record is created by the pipeline).

### Subtask T013 — `scripts/deploy/deploy-skills-sync.sh` (HARD gate)

Safe-deploy order (DIR-005) with `set -euo pipefail` and `export XDG_RUNTIME_DIR=/run/user/$(id -u)`:
1. **Pre-flight**: assert the checkout has the helper + both unit files; assert the skills source dir
   exists.
2. **Place**: copy `agent-skill-sync.{service,timer}` → `~/.config/systemd/user/`.
3. `systemctl --user daemon-reload`.
4. **Smoke gate**: `systemctl --user start agent-skill-sync.service`; then assert
   `/data/services/openclaw/deploy/skills-last-tick.json` exists and is fresh (written this run).
   **If the smoke fails → exit non-zero (fail the deploy loudly).**
5. **Enable** (only after smoke passes): `systemctl --user enable --now agent-skill-sync.timer`.
6. **Assert**: `systemctl --user is-enabled agent-skill-sync.timer` == enabled AND the timer appears
   in `systemctl --user list-timers`. Any failure → exit non-zero.
- Print recovery instructions on failure (manual is fine; rollback = disable timer + rm units +
  daemon-reload). No sudo anywhere (Tier-0 discipline — hand any sudo step to the operator).
- Mirror the structure/logging of `deploy-felix-canary.py`'s verify-before-enable gate (F9 step).

## Branch Strategy

Planning on `feat/openclaw-skills-sync`; merge target `feat/openclaw-skills-sync`. Worktree per lane
from `lanes.json`. Depends on WP01 (the helper must exist for the smoke). Disjoint files from WP02 →
parallel-lane safe.

## Definition of Done

- [ ] `.service`/`.timer` authored, mirror prompt-sync, `-m` ExecStart, pass `systemd-analyze verify`
      (syntax) locally.
- [ ] Manifest validates against `manifest-v1.schema.json` (`tier: 3`, `audited_surface: true`, pre/post checks).
- [ ] `deploy-skills-sync.sh` is a HARD verify-before-enable gate (smoke before enable; loud failure);
      `bash -n` clean; `XDG_RUNTIME_DIR` exported.
- [ ] No best-effort enable; no sudo.

## Risks / reviewer guidance

- **The whole point**: reviewer must confirm the enable is a hard gate — a failed smoke/enable fails
  the deploy, it is NOT swallowed. An installed-but-idle timer would silently defeat the mission.
- Confirm the smoke runs the REAL unit once and checks the freshness signal BEFORE `enable --now`
  (order matters — mirror `deploy-felix-canary.py`).
- Confirm `XDG_RUNTIME_DIR` is exported for every `systemctl --user` call (non-login ssh is `degraded`).
- Manifest `entrypoint` regex is `^scripts/deploy/.+\.(sh|py)$` — the path matches.

## Activity Log

- 2026-07-19T02:54:52Z – claude – shell_pid=88924 – Assigned agent via action command
- 2026-07-19T02:57:37Z – claude – shell_pid=88924 – Units + manifest (schema-valid) + hard verify-before-enable gate; bash -n clean
- 2026-07-19T02:57:47Z – claude – shell_pid=89929 – Started review via action command
