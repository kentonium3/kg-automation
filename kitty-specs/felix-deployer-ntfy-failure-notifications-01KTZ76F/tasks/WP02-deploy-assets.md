---
work_package_id: WP02
title: Deploy assets — bootstrap, systemd unit, env.sample
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
- FR-007
- FR-012
- SC-007
- SC-008
tracker_refs:
- "kentonium3/kg-automation#595"
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on the coordination branch (per #1716 split-authority workaround). During /spec-kitty.implement this WP runs in a per-lane worktree under .worktrees/. Completed changes merge into main via /spec-kitty.merge.
subtasks:
- T006
- T007
- T008
- T009
agent_profile: implementer-ivan
role: implementer
agent: "claude"
authoritative_surface: scripts/deploy/
execution_mode: code_change
mission_slug: felix-deployer-ntfy-failure-notifications-01KTZ76F
owned_files:
- scripts/deploy/felix-deployer/felix-deployer.service
- scripts/deploy/felix-deployer/env.sample
- scripts/deploy/deploy-felix-deployer-bootstrap.sh
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` before reading anything else. The profile sets your identity, governance scope, boundaries, and initialization declaration.

## Objective

Strip the broken openclaw cron registration from the bootstrap script. Add the systemd `EnvironmentFile=` directive so `FELIX_DEPLOYER_NTFY_TOPIC` reaches the applier's process environment. Ship a `env.sample` template so the operator has a known-good starting point. Update the bootstrap script's applied-entry write to produce `0002-bootstrap-felix-deployer-v2.yaml` superseding the existing `0001` (which stays as historical record per spec C-008).

## Context

The existing bootstrap script (`scripts/deploy/deploy-felix-deployer-bootstrap.sh`) shipped with the parent mission has 7 steps. Step 5 attempts `openclaw cron edit felix-deployer-alert --payload-template ... --kind whatsapp-dm-outbound --schedule manual` — every flag here is invented; the live `openclaw 2026.6.5` CLI has no such surface. The bootstrap currently fails at step 5 on a real `--apply`, leaving the applier deployed but the alert path unregistered.

WP01 already retired the openclaw-cron approach in the code. THIS WP retires it in the deploy plumbing — and adds the env-file injection path that the new ntfy-based dispatcher needs to read `FELIX_DEPLOYER_NTFY_TOPIC`.

The new 6-step layout:
1. Pre-flight (unchanged; openclaw cron list still validates that openclaw is healthy on office2 — used as a generic health check, NOT for registering the felix-deployer-alert cron)
2. rsync repo (unchanged)
3. Install systemd user units, including the updated `.service` with `EnvironmentFile=` (T006)
4. `systemctl --user daemon-reload` (unchanged)
5. `systemctl --user enable --now felix-deployer.timer` (was step 5b in old layout; now standalone)
6. Post-flight verify + write `0002-bootstrap-felix-deployer-v2.yaml`

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per computed lane. After WP01 lands on coord branch, this WP's lane base will include WP01's changes (per #1684 single-lane sequencing chosen in tasks.md — WP01→WP02→WP03 on the same lane avoids the lane-base-derivation bug).

## Subtask guidance

### T006 — Add `EnvironmentFile=` to `felix-deployer.service`

Read the current file: `scripts/deploy/felix-deployer/felix-deployer.service`.

Add to the `[Service]` section (preserving existing directives):

```ini
EnvironmentFile=-/home/claude/.config/felix-deployer/env
```

The leading `-` makes the directive non-fatal if the file is missing (per systemd man page systemd.exec(5)). This guarantees:
- The unit starts even if the operator hasn't created the env file yet (graceful onboarding).
- When the file is present, `FELIX_DEPLOYER_NTFY_TOPIC` is exported into the process environment and is visible to `notify.py`'s `os.environ.get(NTFY_TOPIC_ENV)` lookup.

Verify by reading the resulting unit content and confirming the line is present exactly once.

### T007 — Strip step 5 (openclaw cron registration)

Open `scripts/deploy/deploy-felix-deployer-bootstrap.sh`.

Find the existing step 5 block. Looking at the current script, it includes:
- A `log "Step 5/7: registering openclaw cron '${OPENCLAW_CRON_NAME}'..."` line
- A `ssh -n "${SSH_OPTS[@]}" "$SSH_HOST" "openclaw cron edit ${OPENCLAW_CRON_NAME} --payload-template ${ALERT_TEMPLATE_REMOTE} --kind whatsapp-dm-outbound --schedule manual"` line
- A `log "[OK]   openclaw cron '${OPENCLAW_CRON_NAME}' registered."` line
- Likely a NOTE/comment block above it about openclaw cron CLI drift

Delete the entire step-5 block (including its NOTE comment).

In `usage()` and the file header comment, remove or update any reference to "openclaw cron registration" or the 7-step phrasing. The new layout is 6 steps; update step numbers in:
- The `usage()` heredoc's bulleted summary
- The script header comment (top of file, before `set -euo pipefail`)
- Each remaining step's log line: change `Step 6/7` → `Step 5/6`, `Step 7/7` → `Step 6/6`. (Or pick another numbering scheme — the constraint is that the log lines tell a coherent story in `--dry-run` output.)

Remove the now-unused module-level constants:
- `OPENCLAW_CRON_NAME` (set near the top)
- `ALERT_TEMPLATE_REMOTE` (set near the top)
- Any remote-side template-copy logic (look for `ALERT_TEMPLATE_LOCAL` or similar; remove the rsync line and the constant)

Update the `--dry-run` mode's preview text (around the `log "  ssh ${SSH_HOST} 'openclaw cron edit ..."` line) so it does NOT mention openclaw cron edit. Replace with a 6-step preview matching the new --apply path.

Verify after edits:

```bash
grep -nE 'felix-deployer-alert|payload-template|OPENCLAW_CRON_NAME|ALERT_TEMPLATE' scripts/deploy/deploy-felix-deployer-bootstrap.sh
# Expected: zero matches.
```

### T008 — Update applied-entry write to produce `0002-bootstrap-felix-deployer-v2.yaml`

In the remaining "step 6" (applied-entry write — was step 7 in the old layout), update:

- The `APPLIED_NAME` constant near the top:
  ```bash
  APPLIED_NAME="0002-bootstrap-felix-deployer-v2"
  ```
- The inline-manifest heredoc that writes `${REMOTE_REPO}/deploys/applied/${APPLIED_NAME}.yaml`:
  - Update `name:` field: `bootstrap-felix-deployer-v2`
  - Update `notes:` block to reference 0001 as superseded:
    ```yaml
    notes: |
      Bootstrap re-apply of felix-deployer with the ntfy.sh substrate fix
      (kentonium3/kg-automation#595). Supersedes deploys/applied/0001-bootstrap-felix-deployer.yaml,
      which records the original partial-applied state when step 5 (openclaw
      cron registration with non-existent flags) failed. The original 0001
      entry is preserved verbatim as the historical record of the broken-bootstrap
      event.

      This v2 bootstrap is the first successful clean apply of felix-deployer
      with the ntfy.sh failure-notification substrate. ntfy topic provisioning
      (FELIX_DEPLOYER_NTFY_TOPIC env var via /home/claude/.config/felix-deployer/env)
      is operator-driven, NOT part of this bootstrap.
    ```
- The `verification.post` block should drop any reference to `openclaw cron list` (or other cron checks) and retain only the timer-active + .service-file-present checks.

### T009 — Create `scripts/deploy/felix-deployer/env.sample`

Create the new file at `scripts/deploy/felix-deployer/env.sample`. File mode 0644. Content:

```sh
# Felix-deployer notification topic
#
# This file is the TEMPLATE. The real env file lives on office2 at
# /home/claude/.config/felix-deployer/env and is loaded by the
# felix-deployer.service systemd unit via EnvironmentFile=-/home/claude/.config/felix-deployer/env.
#
# Setup procedure (run ONCE on office2 during initial install / first redeploy):
#
#   ssh office2-claude 'mkdir -p ~/.config/felix-deployer && cat > ~/.config/felix-deployer/env <<EOF
#   FELIX_DEPLOYER_NTFY_TOPIC=felix-deployer-'$(openssl rand -hex 6)'
#   EOF
#   chmod 0640 ~/.config/felix-deployer/env'
#
# Then subscribe your ntfy phone app to the topic (https://ntfy.sh/<topic>).
#
# The topic is private but not a high-value secret: knowing it lets a
# passive listener read failure notifications, not impersonate any service.
# Do NOT commit the real file.

FELIX_DEPLOYER_NTFY_TOPIC=
```

The trailing `=` with empty value makes the systemd unit treat it as set-to-empty, which `notify.py`'s `_topic_or_missing()` check (env unset OR empty → `NTFY_MISSING_TOPIC`) catches uniformly.

## Test strategy

- `bash -n scripts/deploy/deploy-felix-deployer-bootstrap.sh` — syntax check passes.
- `./scripts/deploy/deploy-felix-deployer-bootstrap.sh --dry-run` — runs end-to-end on the local Mac (the `--dry-run` mode does NOT ssh-mutate office2, just prints the intended actions). The output must NOT contain any of: `openclaw cron edit`, `openclaw cron run`, `--payload-template`, `--payload-file`, `felix-deployer-alert`. Capture the dry-run output for the reviewer to inspect.
- `bash -n scripts/deploy/felix-deployer/env.sample` — bash treats the env.sample as a script syntactically; the syntax check should pass (it's a valid no-op assignment).
- Grep guard: `grep -nE 'felix-deployer-alert|payload-template|payload-file|OPENCLAW_CRON_NAME' scripts/deploy/deploy-felix-deployer-bootstrap.sh scripts/deploy/felix-deployer/felix-deployer.service` — zero matches.
- `make test` — no regressions in the broader test suite (this WP touches no Python code).

## Definition of Done

- `felix-deployer.service` contains the `EnvironmentFile=-/home/claude/.config/felix-deployer/env` line exactly once.
- `deploy-felix-deployer-bootstrap.sh`:
  - Contains zero references to `openclaw cron edit`, `--payload-template`, `--kind`, `--schedule manual`, `OPENCLAW_CRON_NAME`, `ALERT_TEMPLATE_REMOTE`, or `felix-deployer-alert`.
  - Steps are numbered 1/6 through 6/6 in log lines.
  - `--dry-run` preview text reflects the 6-step layout.
  - `APPLIED_NAME` is `0002-bootstrap-felix-deployer-v2`.
  - `name:` in the inline-manifest is `bootstrap-felix-deployer-v2`.
  - `notes:` block references `0001` as superseded with the substrate-swap rationale.
- `env.sample` exists at the declared path with the documented content and mode 0644.
- `bash -n` syntax check passes on both shell files.
- `--dry-run` mode runs to completion without errors.
- No file outside `owned_files` is modified.

## Risks

- **Heredoc quoting in the inline-manifest write**: the existing script uses `cat <<EOF` and bash variable interpolation. Be careful with the `${REMOTE_REPO}`, `${APPLIED_NAME}`, `${CREATED_AT}`, `${HEAD_SHA}` substitutions — quoting bugs here are easy to introduce and surface only on a real `--apply`. Recommendation: keep the existing heredoc style; only change the literal values and the `notes` block content.
- **Step renumbering inconsistency**: the log lines, `usage()`, header comments, and `--dry-run` preview text all carry step numbers. Mismatch produces operator confusion. Pick the new numbering scheme once and grep-verify it's consistent across the file.
- **systemd unit syntax**: `EnvironmentFile=` must be in `[Service]`, not `[Unit]` or `[Install]`. Confirm by reading the existing structure before inserting.
- **Empty topic in env.sample**: the trailing `=` with nothing after it must be a literal empty string, not a missing value. `FELIX_DEPLOYER_NTFY_TOPIC=` is correct; `FELIX_DEPLOYER_NTFY_TOPIC` (no equals) is an unset variable in some env-file parsers.

## Reviewer guidance

- Run the grep guard yourself before accepting (the WP can't be accepted if any forbidden term remains).
- Confirm the systemd `EnvironmentFile=-` directive's leading dash; without the dash, missing-file = unit-fail, which breaks graceful onboarding.
- Confirm step renumbering is consistent across `usage()`, the file header, log lines, and `--dry-run` preview text.
- Confirm `0002-bootstrap-felix-deployer-v2.yaml`'s `name:` field matches the file name minus the `0002-` prefix and the `.yaml` suffix.
- Confirm `env.sample` has a meaningful operator-facing comment (the procedure to mint and install the real file) — the file is the only documentation of that procedure at the time WP02 ships (quickstart.md ships in this same mission but is a planning artifact, not visible to the deployed system).
