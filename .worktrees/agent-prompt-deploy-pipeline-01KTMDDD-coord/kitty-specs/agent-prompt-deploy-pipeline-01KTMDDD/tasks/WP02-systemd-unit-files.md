---
work_package_id: WP02
title: Systemd unit files
dependencies:
- WP01
requirement_refs:
- FR-011
- FR-012
- FR-013
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
agent: claude
history:
- timestamp: '2026-06-08T20:25:00Z'
  actor: claude
  event: Created via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/deploy/
execution_mode: code_change
mission_id: 01KTMDDDGGY00S3S3VFGK0Z6P9
mission_slug: agent-prompt-deploy-pipeline-01KTMDDD
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/deploy/agent-prompt-sync.service
- scripts/openclaw/deploy/agent-prompt-sync.timer
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load implementer-ivan
```

This sets up the implementer posture: small, focused changes; high attention to operational detail.

## Objective

Author the user-level systemd service and timer unit files that the office2 operator copies once to `~/.config/systemd/user/`. The timer fires every 5 minutes after the previous tick exits; the service invokes the WP01 helper as a oneshot Python process.

Both unit files model directly on `scripts/sync/systemd/felix-vikunja-sync.{service,timer}`, which is the working precedent currently driving the Felix-Vikunja sync timer on office2.

## Context — read these first

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-011, FR-012, FR-013 | Required unit-file shape |
| [../plan.md](../plan.md) § IC-06 | Concern map for this WP |
| [../research.md](../research.md) § D-008 | Cadence decision (OnUnitInactiveSec=300s, NOT OnCalendar) |
| `scripts/sync/systemd/felix-vikunja-sync.service` | Structural precedent (5-min cadence, oneshot, claude user) |
| `scripts/sync/systemd/felix-vikunja-sync.timer` | Structural precedent (same shape we want) |
| [../quickstart.md](../quickstart.md) | The operator install procedure these files plug into |

## Branch Strategy

- **Planning base / merge target**: `main`
- **Coordination branch**: `kitty/mission-agent-prompt-deploy-pipeline-01KTMDDD`
- **Execution worktree**: `spec-kitty implement WP02 --agent claude` creates a lane worktree off the coordination branch.
- WP02 depends on WP01 being merged to coordination first; spec-kitty's lane sequencing enforces this.

## Subtask Guidance

### T008 — Author `agent-prompt-sync.service`

**Purpose**: User-level systemd oneshot unit that invokes the WP01 helper for one tick.

**Steps**:

1. Create file `scripts/openclaw/deploy/agent-prompt-sync.service` with the following structure (modeled on `scripts/sync/systemd/felix-vikunja-sync.service`):
   - Header comment block explaining: what the unit does, the operator deploy steps, the `systemd-analyze --user verify` validation command, where the helper lives in repo, what the audit log path is
   - `[Unit]` section: `Description=` (one-line), `Documentation=` pointing at the runbook (file URI under `/home/claude/kg-automation/docs/runbooks/agent-prompt-sync-ops.md`), `After=network-online.target` (allow git pull), `Wants=network-online.target`
   - `[Service]` section: `Type=oneshot`, `WorkingDirectory=/home/claude/kg-automation`, `ExecStart=/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_prompts`, `StandardOutput=journal`, `StandardError=journal`, `TimeoutStartSec=120s`
   - `[Install]` section: `WantedBy=default.target`
2. Use the EXACT `-m` invocation form per NFR-005 — script-path form (`/usr/bin/python3 /home/claude/kg-automation/scripts/...py`) will fail with `ModuleNotFoundError` per `[[feedback_helper_m_invocation_form]]`.
3. Do NOT include any `Environment=` directives; the helper reads no environment variables (per spec.md design).

**Files**:
- `scripts/openclaw/deploy/agent-prompt-sync.service` (new)

**Validation**: `systemd-analyze --user verify scripts/openclaw/deploy/agent-prompt-sync.service` from a Linux box with systemd available returns 0. (On Mac, this command isn't available; document it in the unit header for the operator to run on office2.)

### T009 — Author `agent-prompt-sync.timer`

**Purpose**: User-level systemd timer that activates the service unit every 5 minutes after the previous tick exits.

**Steps**:

1. Create file `scripts/openclaw/deploy/agent-prompt-sync.timer` with the following structure (modeled on `scripts/sync/systemd/felix-vikunja-sync.timer`):
   - Header comment block explaining: timer semantics (`OnUnitInactiveSec` vs `OnCalendar`), boot delay rationale (`OnBootSec=120s`), missed-tick behavior (`Persistent=true`), operator enable command
   - `[Unit]` section: `Description=` (mirror the service description, e.g., "Agent Prompt Deploy Pipeline (5-min cadence)"), `Documentation=` (same runbook path)
   - `[Timer]` section: `OnUnitInactiveSec=300s`, `OnBootSec=120s`, `Unit=agent-prompt-sync.service`, `Persistent=true`
   - `[Install]` section: `WantedBy=timers.target`
2. Header comment must explicitly explain WHY `OnUnitInactiveSec=300s` was chosen over `OnCalendar=*/5` (overlap-prevention) — this is the design decision from D-008 in research.md.

**Files**:
- `scripts/openclaw/deploy/agent-prompt-sync.timer` (new)

**Validation**: `systemd-analyze --user verify scripts/openclaw/deploy/agent-prompt-sync.timer` returns 0.

### T010 — Document unit verification

**Purpose**: Make the unit-file verification command discoverable to operators directly inside the unit headers (no need to consult a separate runbook for the basic sanity check).

**Steps**:

1. In the header comment of BOTH unit files, include a clearly-labeled "Operator validation" section with:
   ```
   # Operator validation (run on office2 from /home/claude/kg-automation):
   #   systemd-analyze --user verify scripts/openclaw/deploy/agent-prompt-sync.service
   #   systemd-analyze --user verify scripts/openclaw/deploy/agent-prompt-sync.timer
   ```
2. Cross-reference the WP03 runbook for the full install + verify + troubleshooting flow.

**Files**:
- `scripts/openclaw/deploy/agent-prompt-sync.service` (header comment block)
- `scripts/openclaw/deploy/agent-prompt-sync.timer` (header comment block)

**Validation**: Both header comments contain the validation command and the runbook cross-reference.

## Definition of Done

- [ ] `scripts/openclaw/deploy/agent-prompt-sync.service` exists with the structure above
- [ ] `scripts/openclaw/deploy/agent-prompt-sync.timer` exists with the structure above
- [ ] Both unit files have an "Operator validation" comment block at the top
- [ ] ExecStart uses the `-m scripts.openclaw.deploy.deploy_agent_prompts` form (NOT script-path form)
- [ ] Timer uses `OnUnitInactiveSec=300s` (NOT `OnCalendar=*/5`)
- [ ] Timer has `Persistent=true`
- [ ] Service has `Type=oneshot` and `WorkingDirectory=/home/claude/kg-automation`
- [ ] (Optional, operator-runnable) `systemd-analyze --user verify` on office2 returns 0
- [ ] Lane committed; WP frontmatter `lane` updated to `for_review`

## Risks

- Operator forgets to `systemctl --user daemon-reload` after copying the units → timer doesn't activate. Mitigation: the install procedure in the WP03 runbook explicitly includes this step. Comment in the unit headers as well.
- `network-online.target` doesn't activate cleanly on office2's boot (it occasionally hangs in Linux). Mitigation: `OnBootSec=120s` gives a 2-minute boot delay that almost always resolves the timing race; the existing felix-vikunja-sync precedent uses the same combination and is stable.

## Reviewer Guidance

- Compare each unit file line-by-line against the `felix-vikunja-sync.{service,timer}` precedent. Differences should be ONLY: unit name, Description, Documentation path, ExecStart command. Everything else should match the precedent.
- Verify `ExecStart` uses the `-m` invocation form (this has bitten us TWICE per `[[feedback_helper_m_invocation_form]]`).
- Verify NO `--full-auto` or any agent-specific flags appear (this is a Python helper, not an LLM agent).
- Verify the timer references the service by exact unit name (`Unit=agent-prompt-sync.service`, not `Unit=agent_prompt_sync.service`).

## Next Step

After this WP merges to coordination branch:
- `spec-kitty agent action implement WP03 --agent claude` (the architecture-doc-sync WP)
