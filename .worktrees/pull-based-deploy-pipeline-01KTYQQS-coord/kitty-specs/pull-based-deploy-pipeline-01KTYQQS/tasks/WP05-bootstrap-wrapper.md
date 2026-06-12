---
work_package_id: WP05
title: Bootstrap wrapper and retroactive applied entry
dependencies:
- WP02
- WP03
- WP04
requirement_refs:
- FR-015
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
agent: "claude:sonnet:implementer-ivan:reviewer"
shell_pid: "37340"
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- scripts/deploy/deploy-felix-deployer-bootstrap.sh
- tests/deploy/test_bootstrap_record.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Ship the one-shot bootstrap that deploys the applier itself to office2. After this lands and runs once, every subsequent deploy goes through the manifest discipline.

## Context

The bootstrap is conceptually the first deploy — but the manifest discipline doesn't exist on office2 yet at bootstrap time. So we use the existing canonical one-shot pattern: `deploy-149.sh` is the reference shape (per `kitty-specs/<slug>/plan.md` and the original Felix charter). After `--apply`, the script writes `deploys/applied/0001-bootstrap-felix-deployer.yaml` as the canonical first entry, so future agents reading the discipline runbook see a concrete worked example of an `applied/` manifest.

Per `kitty-specs/<slug>/research.md` R-04, this is the resolved Decision Moment `01KTYT0M1P91042MJ0G5WXCYN2` (`bootstrap_retroactive_applied_entry: yes_canonical_example`).

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T022 — `deploy-felix-deployer-bootstrap.sh` core

Read `scripts/deploy/deploy-149.sh` as the reference shape. Mirror its conventions:
- `set -euo pipefail`
- `--dry-run` and `--apply` modes
- Pre-flight checks
- Strict order-of-operations
- Halt on any failure
- Manual rollback in script header
- No system crontab (use openclaw cron for registering `felix-deployer-alert`)

Script outline:

```bash
#!/usr/bin/env bash
# deploy-felix-deployer-bootstrap.sh
# Bootstrap deploy for the felix-deployer applier.
# This is a one-shot wrapper following the deploy-149.sh canonical shape.
# After this runs successfully on office2, all subsequent deploys go through
# the manifest discipline (deploys/queued/).
#
# Rollback:
#   ssh office2-claude 'systemctl --user disable --now felix-deployer.timer felix-deployer.service'
#   ssh office2-claude 'rm /home/claude/.config/systemd/user/felix-deployer.{service,timer}'
#   ssh office2-claude 'systemctl --user daemon-reload'

set -euo pipefail

MODE="${1:-}"
case "$MODE" in --dry-run|--apply|--rollback) ;;
  *) echo "usage: $0 --dry-run|--apply|--rollback" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SSH_HOST="office2-claude"

# Pre-flight (all modes)
echo "Pre-flight: confirming source files present locally..."
python3 -m scripts.deploy.lib.verify verify_file_present "${REPO_ROOT}/scripts/deploy/felix-deployer/deployer.py"
python3 -m scripts.deploy.lib.verify verify_file_present "${REPO_ROOT}/scripts/deploy/felix-deployer/felix-deployer.service"
python3 -m scripts.deploy.lib.verify verify_file_present "${REPO_ROOT}/scripts/deploy/felix-deployer/felix-deployer.timer"
python3 -m scripts.deploy.lib.verify verify_file_present "${REPO_ROOT}/scripts/deploy/lib/__init__.py"

echo "Pre-flight: confirming openclaw cron is healthy on office2..."
ssh "$SSH_HOST" 'openclaw cron list --json' >/dev/null

if [ "$MODE" = "--rollback" ]; then
  echo "Rollback mode..."
  ssh "$SSH_HOST" 'systemctl --user disable --now felix-deployer.timer felix-deployer.service || true'
  ssh "$SSH_HOST" 'rm -f /home/claude/.config/systemd/user/felix-deployer.service /home/claude/.config/systemd/user/felix-deployer.timer'
  ssh "$SSH_HOST" 'systemctl --user daemon-reload'
  echo "Rollback complete."
  exit 0
fi

if [ "$MODE" = "--dry-run" ]; then
  echo "DRY RUN — would do:"
  echo "  rsync scripts/deploy/felix-deployer/ → office2:/home/claude/kg-automation/scripts/deploy/felix-deployer/"
  echo "  rsync scripts/deploy/lib/             → office2:/home/claude/kg-automation/scripts/deploy/lib/"
  echo "  install felix-deployer.service + .timer → ~/.config/systemd/user/"
  echo "  systemctl --user daemon-reload"
  echo "  systemctl --user enable --now felix-deployer.timer"
  echo "  openclaw cron edit felix-deployer-alert (register payload template)"
  echo "  python3 -m scripts.deploy.lib.applied write_applied --name 0001-bootstrap-felix-deployer --apply-mode bootstrap"
  exit 0
fi

# --apply
echo "Applying..."

# Source artifacts
rsync -av --delete "${REPO_ROOT}/scripts/deploy/felix-deployer/" "${SSH_HOST}:/home/claude/kg-automation/scripts/deploy/felix-deployer/"
rsync -av --delete "${REPO_ROOT}/scripts/deploy/lib/" "${SSH_HOST}:/home/claude/kg-automation/scripts/deploy/lib/"

# Systemd units
ssh "$SSH_HOST" 'mkdir -p ~/.config/systemd/user'
scp "${REPO_ROOT}/scripts/deploy/felix-deployer/felix-deployer.service" "${SSH_HOST}:~/.config/systemd/user/"
scp "${REPO_ROOT}/scripts/deploy/felix-deployer/felix-deployer.timer" "${SSH_HOST}:~/.config/systemd/user/"
ssh "$SSH_HOST" 'systemctl --user daemon-reload'
ssh "$SSH_HOST" 'systemctl --user enable --now felix-deployer.timer'

# Register openclaw cron for DM dispatch
# (The exact `openclaw cron edit` invocation depends on openclaw's current surface;
#  consult `openclaw cron --help` on office2 if needed. The cron MUST be named
#  `felix-deployer-alert` and use the template at templates/felix-deployer-alert.txt.)
ssh "$SSH_HOST" 'openclaw cron edit felix-deployer-alert --payload-template /home/claude/kg-automation/scripts/deploy/felix-deployer/templates/felix-deployer-alert.txt --kind whatsapp-dm-outbound --schedule manual'

# Post-flight: confirm timer is running
ssh "$SSH_HOST" 'systemctl --user status felix-deployer.timer | grep -q "active (waiting)\|active (running)"'

echo "Bootstrap complete. felix-deployer is live on office2."
```

### T023 — Bootstrap writes retroactive applied entry

At the end of `--apply` (after the post-flight check passes), invoke:

```bash
ssh "$SSH_HOST" "cd /home/claude/kg-automation && python3 -m scripts.deploy.lib.applied write_applied --name 0001-bootstrap-felix-deployer --apply-mode bootstrap --tier 1 --audited-surface true --entrypoint scripts/deploy/deploy-felix-deployer-bootstrap.sh --issue 'kentonium3/kg-automation#136' --created-by 'operator-bootstrap' --notes 'Bootstrap deploy of felix-deployer itself. First-ever applied manifest under the discipline.'"
```

Then commit + push the new file from office2.

### T024 — `--rollback` mode + header

Already drafted in T022 above. Confirm the rollback steps in the script header match the implementation precisely (both must be in sync).

### T025 — `tests/deploy/test_bootstrap_record.py`

Subprocess-mock test:
1. `test_bootstrap_dry_run_lists_expected_actions` — run `bash deploy-felix-deployer-bootstrap.sh --dry-run` (in a sandbox where ssh is mocked); assert stdout contains each expected "would do" line
2. `test_bootstrap_apply_constructs_correct_applied_yaml` — mock the write_applied invocation; verify the resulting YAML structure validates against the manifest schema with `apply_mode: bootstrap`
3. `test_bootstrap_rollback_disables_timer` — run `--rollback` with ssh mocked; assert correct systemctl commands are dispatched

Use `subprocess.run` against the actual script with `PATH` mocked to a stub ssh + a stub `python3 -m` that records calls.

## Test strategy

- `pytest tests/deploy/test_bootstrap_record.py -v` — green
- Bash syntax check: `bash -n scripts/deploy/deploy-felix-deployer-bootstrap.sh` — no errors
- Manual smoke on office2 (post-merge, by operator) — `./scripts/deploy/deploy-felix-deployer-bootstrap.sh --dry-run` shows expected output; `--apply` succeeds end-to-end; timer is active

## Definition of Done

- All 2 owned files exist
- Bash script passes `bash -n` (syntax) and `shellcheck` (style; warnings OK)
- All 3 test scenarios pass
- The `--rollback` instructions in the script header match the implementation
- The retroactive applied entry written by `--apply` validates against the manifest schema

## Risks

- **openclaw cron edit surface drift**: the exact CLI for registering a cron has shifted across openclaw versions (memory `reference_openclaw_upgrade_gotchas`). Confirm against `openclaw cron edit --help` on office2 BEFORE running `--apply`. The dry-run mode should print the intended invocation so the operator can verify.
- **systemd user services without lingering**: `systemctl --user enable` requires loginctl lingering to run after logout. The `claude` user already has lingering enabled per `felix-doc-auditor` precedent — verify with `loginctl show-user claude | grep Linger`.
- **rsync --delete on first run**: target directories don't exist yet on office2. Add `mkdir -p` before rsync if needed.
- **Concurrent bootstrap runs**: not handled; operator's responsibility to run once.

## Reviewer guidance

1. Diff against `scripts/deploy/deploy-149.sh` — confirm same conventions (modes, header, no crontab).
2. Verify the rollback instructions in the script header match what `--rollback` does.
3. Confirm the retroactive applied YAML has `apply_mode: bootstrap` (NOT `manifest`).
4. Run the dry-run subprocess test manually to confirm output matches the expected actions list.
5. Confirm no `crontab` literal anywhere in the script (use openclaw cron only).

## Activity Log

- 2026-06-12T22:55:12Z – claude:sonnet:implementer-ivan:implementer – shell_pid=34976 – Assigned agent via action command
- 2026-06-12T23:02:35Z – claude:sonnet:implementer-ivan:implementer – shell_pid=34976 – Bootstrap + retroactive applied entry. All 3 test scenarios green.
- 2026-06-12T23:03:14Z – claude:sonnet:implementer-ivan:reviewer – shell_pid=37340 – Started review via action command
- 2026-06-12T23:05:11Z – user – shell_pid=37340 – Review passed: bash -n clean; 3/3 tests green; no crontab literal; rollback header matches --rollback; constructed bootstrap manifest validates against manifest-v1 schema with apply_mode: bootstrap and issue ref (no mission_slug); --apply rsyncs felix-deployer/+lib/, scps units, daemon-reload, enables timer, registers openclaw cron, post-flight active check, writes retroactive applied entry via lib.applied write_applied --manifest <path>.
