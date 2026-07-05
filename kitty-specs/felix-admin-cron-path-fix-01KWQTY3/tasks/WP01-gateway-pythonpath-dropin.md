---
work_package_id: WP01
title: Gateway PYTHONPATH systemd drop-in + deploy (fleet-wide cwd guardrail)
dependencies: []
requirement_refs:
- FR-001
- FR-002
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
shell_pid: "52461"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/openclaw-gateway.service.d/
create_intent:
- scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf
- scripts/deploy/install-gateway-pythonpath-dropin.py
- deploys/queued/0006-gateway-pythonpath-dropin.yaml
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf
- scripts/deploy/install-gateway-pythonpath-dropin.py
- deploys/queued/0006-gateway-pythonpath-dropin.yaml
role: implementer
tags: []
---

# Work Package Prompt: WP01 – Gateway PYTHONPATH drop-in + deploy

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load implementer-ivan` (role: implementer). Adopt its identity,
boundaries, and initialization declaration, then continue.

## Branch Strategy

- **Planning/base branch at prompt creation**: `fix/felix-admin-cron-path-fix`
- **Final merge target**: `fix/felix-admin-cron-path-fix`
- Execution workspace/lane is resolved by `/spec-kitty.implement`; trust the path it prints.

## Objectives & Success Criteria

Deliver FR-001/FR-002: make `python3 -m scripts.*` resolve from **any** working
directory for **every** OpenClaw agent, by exporting `PYTHONPATH=/home/claude/kg-automation`
in the gateway's process environment via a **systemd drop-in** (not an edit to the
base unit — this avoids colliding with #653's in-flight `ExecStart` relocation).

Done when:
- The drop-in file exists and is syntactically valid.
- A deploy entrypoint + Tier-1 manifest install it, `daemon-reload`, restart the
  gateway, and **verify** the env reaches a real agent/cron subprocess (SC-10).

## Context & Constraints

- Read `kitty-specs/felix-admin-cron-path-fix-01KWQTY3/plan.md` (IC-01) +
  `research.md` (R1, R7-C1) + `contracts/path-resolution-and-migration.md` (C1).
- The base unit is `scripts/openclaw/openclaw-gateway.service`; it already sets
  `Environment=HOME=/home/claude`, `PATH=…`, etc. and uses `KillMode=control-group`.
  **Do NOT edit that file** — ship a drop-in.
- **Load-bearing (Codex #1 C1)**: env inheritance to agent tool subprocesses is
  *assumed* (Node `child_process` inherits `process.env`) but MUST be proven in a
  real agent/cron subprocess — an SSH login shell is NOT a valid proxy.
- Deploy is Tier-1 (gateway restart affects all agents briefly). Confirm the
  gateway returns healthy and agents reconnect after restart.
- This is an audited surface (systemd unit) → rebaseline obligation (recorded in WP06).

## Subtasks & Detailed Guidance

### Subtask T001 – Create the drop-in
- **File**: `scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf`
- **Content**:
  ```ini
  [Service]
  Environment=PYTHONPATH=/home/claude/kg-automation
  ```
- **Notes**: systemd merges `*.conf` drop-ins over the base unit; a bare
  `Environment=` in a drop-in is additive, not a replacement of the base unit's
  other `Environment=` lines.

### Subtask T002 – Deploy entrypoint
- **File**: `scripts/deploy/install-gateway-pythonpath-dropin.py`
- **Steps**:
  1. Follow `scripts/deploy/lib/` conventions (see `README.md`, `_cli.py`); accept `--dry-run`.
  2. Copy `pythonpath.conf` into the systemd **user** unit drop-in dir for
     `openclaw-gateway.service` (confirm the correct dir on office2 — the gateway
     is a `systemctl --user` unit; typically `~/.config/systemd/user/openclaw-gateway.service.d/`).
  3. `systemctl --user daemon-reload`; `systemctl --user restart openclaw-gateway.service`.
  4. **Verify** (SC-10): (a) `systemctl --user show openclaw-gateway.service -p Environment`
     contains `PYTHONPATH=/home/claude/kg-automation`; (b) exercise a real agent/cron
     payload that prints `os.environ.get("PYTHONPATH")` from a non-repo cwd and assert
     it equals `/home/claude/kg-automation`. If (b) fails, the guardrail is not
     effective — report and stop (do not claim success).
- **Notes**: idempotent; re-running is a no-op. The `claude` user has no sudo — use
  `--user` systemd only.

### Subtask T003 – Deploy manifest
- **File**: `deploys/queued/0006-gateway-pythonpath-dropin.yaml`
- **Steps**: schema `v1` (see `deploys/applied/0003-*.yaml`). `tier: 1`,
  `audited_surface: true`, `entrypoint: scripts/deploy/install-gateway-pythonpath-dropin.py`.
  `verification.pre`: gateway is active. `verification.post`: the two SC-10 checks above.
  `notes`: cite #656 FR-001/FR-002; note #653 ExecStart is untouched (drop-in).

## Test Strategy

- Unit-test the entrypoint's dry-run (prints planned actions, mutates nothing).
- The in-agent env verification is a deploy-time gate, encoded in the manifest `post`.

## Risks & Mitigations

- **Env not inherited** → guardrail ineffective. Mitigation: the SC-10 in-agent
  check is a hard gate; if it fails, fall back to the openclaw agent-env path
  (out-of-repo) — surface to the human.
- **Gateway restart** briefly drops agents. Mitigation: verify health post-restart;
  schedule at a quiet time if needed.

## Integration Verification (before for_review)

- [ ] Drop-in is valid; `systemctl --user show … -p Environment` shows the value.
- [ ] In-agent subprocess prints the expected `PYTHONPATH` from a non-repo cwd.
- [ ] Gateway healthy + agents reconnect after restart.

## Review Guidance

- Confirm the base unit was NOT edited (drop-in only).
- Confirm SC-10 is an actual in-agent check, not an SSH-shell check.

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T03:22:15Z – claude:sonnet:implementer-ivan:implementer – shell_pid=46408 – Assigned agent via action command
- 2026-07-05T03:29:45Z – claude:sonnet:implementer-ivan:implementer – shell_pid=46408 – Ready for review: drop-in + entrypoint + manifest + 15 unit tests (all pass); no linter available in env — py_compile syntax check exit 0
- 2026-07-05T03:30:54Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=52461 – Started review via action command
