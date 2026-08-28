---
work_package_id: WP03
title: Schedule and deploy the capture
dependencies:
- WP02
requirement_refs:
- FR-002
planning_base_branch: feat/crontab-backup-coverage
merge_target_branch: feat/crontab-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on feat/crontab-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/crontab-backup-coverage unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T00:37:21Z'
subtasks:
- T012
- T013
- T014
- T015
- T016
phase: Phase 1 - Make the crontab recoverable
history:
- at: '2026-08-28T00:37:21Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/office2/crontab-capture
create_intent:
- scripts/office2/crontab-capture.service
- scripts/office2/crontab-capture.timer
- scripts/deploy/deploy-crontab-capture.py
- deploys/queued/crontab-capture.yaml
execution_mode: code_change
owned_files:
- scripts/office2/crontab-capture.service
- scripts/office2/crontab-capture.timer
- scripts/deploy/deploy-crontab-capture.py
- deploys/queued/crontab-capture.yaml
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP03 — Schedule and deploy the capture

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

Install WP02's helper on office2 as a **systemd user timer**, through the
`deploys/queued/` manifest pipeline.

A timer, not a sixth cron entry. `Linger=yes` is set for `claude` and 15 user
timers already run there; the crontab holds only the five legacy jobs that #890
exists to retire, and adding to it would enlarge exactly that problem. A timer is
also repo-tracked, manifest-deployable, and supports `Persistent=true` so a run
missed while the host was down executes on the next boot — cron silently skips.

**Done when**: units and entrypoint exist, the manifest validates locally against
the schema, and `--dry-run` reports the intended actions while changing nothing.

**Maps to**: FR-002, NFR-001, NFR-002, C-004.

---

## Required reading

- `scripts/deploy/deploy-habits-weekly-driver.py` — the precedent. It copies
  units to `~/.config/systemd/user/`, runs `daemon-reload`, `enable --now`, and
  verifies via `list-timers` + `is-enabled`. Mirror its structure.
- `deploys/applied/0018-habits-weekly-driver.yaml` — a Tier 3 user-timer manifest.
- `deploys/schema/manifest-v1.schema.json` — authoritative; `additionalProperties:
  false`, so any unknown key is rejected.
- `docs/runbooks/deploy/discipline.md`.

---

## Subtasks

### T012 — `crontab-capture.service`

**Steps**:

1. Create `scripts/office2/crontab-capture.service`, `Type=oneshot`.
2. `WorkingDirectory=/home/claude/kg-automation`.
3. `ExecStart=/usr/bin/python3 /home/claude/kg-automation/scripts/office2/crontab_capture.py`
   — office2 is **python3-only**; a bare `python` exits 127 and has previously
   produced false cron-failure alerts.
4. Set an explicit `Environment=PATH=...` matching `felix-deployer.service`.
5. Header comment: what it captures, why, and the issue reference.

**Validation**:
- [ ] `systemd-analyze verify` reports no errors (or the unit parses cleanly)
- [ ] Absolute interpreter path, no bare `python`

### T013 — `crontab-capture.timer`

**Steps**:

1. Create `scripts/office2/crontab-capture.timer`.
2. `OnCalendar=hourly`.
3. `Persistent=true` — this is the point of choosing a timer; do not omit it.
4. `RandomizedDelaySec` of a minute or two so the capture does not contend with
   the top-of-hour cluster.
5. `[Install] WantedBy=timers.target`.

**Interval rationale (FR-002)**: the snapshot copy refreshes only once per daily
backup regardless of capture cadence, so hourly does not improve
restore-from-backup freshness. It improves the *primary* recovery path — the live
artifact under `/data/`, on a different tree from `/home/claude`, which would
have survived the 2026-08-27 deletion. Hourly is free because WP02 rewrites the
artifact only when the content changed.

**Validation**:
- [ ] Interval is strictly shorter than the backup interval, so a capture always
      precedes any given backup run (this is the FR-002 assertion)
- [ ] `Persistent=true` present

### T014 — Deploy entrypoint

**Steps**:

1. Create `scripts/deploy/deploy-crontab-capture.py`, executable, supporting
   `--dry-run` and `--apply`. felix-deployer invokes entrypoints **by file path**
   (`subprocess.run([path, "--dry-run"])`), not via `python3 -m`.
2. Actions on `--apply`:
   - create `/data/services/host-state/crontabs/` (mode 0755, owned by `claude`);
   - `shutil.copy2` both units into `~/.config/systemd/user/`;
   - `systemctl --user daemon-reload`;
   - `systemctl --user enable --now crontab-capture.timer`;
   - verify via `systemctl --user is-enabled` and `list-timers`.
3. `--dry-run` must report every one of those without performing any of them.
4. Idempotent: re-running on an already-installed host is a no-op that still
   exits 0.
5. Emit structured progress lines like the precedent does, and a non-zero exit on
   any failed step.

⚠ **Do not wrap any command in `ssh office2-claude '...'`.** The entrypoint
already runs *on* office2 as the `claude` user; that host alias is defined in the
Mac's SSH config and loopback SSH from office2 to itself fails.

**Validation**:
- [ ] `--dry-run` changes nothing (verify with `systemctl --user list-unit-files`)
- [ ] Re-running `--apply` is a clean no-op

### T015 — The manifest

**Steps**:

Create `deploys/queued/crontab-capture.yaml`:

```yaml
schema_version: v1
name: crontab-capture
mission_slug: crontab-backup-coverage-01M12V87
tier: 3
entrypoint: scripts/deploy/deploy-crontab-capture.py
audited_surface: true
verification:
  pre:
  - python3 -m scripts.deploy.lib.snapshot verify_restic_recent 24
  - test -f scripts/office2/crontab_capture.py
  post:
  - systemctl --user is-enabled crontab-capture.timer
  - python3 /home/claude/kg-automation/scripts/office2/crontab_capture.py --dry-run
created_at: '2026-08-28T00:37:21Z'
created_by: crontab-backup-coverage-01M12V87
notes: |
  <your notes here — see constraints below>
```

Constraints, each of which will bite if ignored:

- **`notes` has `maxLength: 2000`.** Exceeding it is *not* caught before apply:
  felix-deployer runs the entrypoint's side effects and then refuses to write the
  applied record, leaving the manifest queued and re-applying every five minutes
  with no alert. That is #891; the underlying ordering defect is #901. Count your
  characters.
- **Tier 3**, not 2. This installs a user timer and a helper; it changes no
  backup configuration. Precedent: `0018`. The restic pre-check is included
  voluntarily, not because the tier demands it.
- **Do not set `expected_baselines`.** It exists for deploys that mutate host
  state through a runtime CLI with no repo-file signal (the canonical case being
  `openclaw cron rm`). Enabling this timer drifts `systemd-user-units.txt` and
  `systemd-user-unit-contents.txt`, but `audited-surfaces.json` already matches
  `scripts/office2/*.service` and `*.timer` — verified — so the observe-range
  auto-rebaseline covers it. Precedent: `0020`.
- `name` must match `^[a-z][a-z0-9-]+[a-z0-9]$`, 3–80 chars.
- No `NNNN-` prefix on the filename; the applier assigns it.

**Validation**:
- [ ] `notes` under 2000 characters — measure it, do not estimate

### T016 — Validate the manifest locally

**Purpose**: CI does **not** schema-validate queued manifests. The
`deploy-manifest-validate` workflow only runs schema unit tests over fixtures, so
a malformed manifest passes CI and fails on office2 after its side effects have
landed. This subtask is the real gate.

**Steps**:

```bash
python3 -m scripts.deploy.lib.manifest validate_manifest_file deploys/queued/crontab-capture.yaml
```

```bash
python3 -c "import yaml; print(len(yaml.safe_load(open('deploys/queued/crontab-capture.yaml'))['notes']))"
```

**Validation**:
- [ ] Validator reports ok
- [ ] Printed notes length < 2000

---

## Definition of Done

- [ ] Units, entrypoint, and manifest created
- [ ] Manifest passes local schema validation; `notes` under the limit
- [ ] `--dry-run` verified inert
- [ ] `make test` still at or above the 6177 floor
- [ ] No file outside `owned_files` modified

## Out of scope

- The helper itself — **WP02**.
- `service-inventory.json` registration — **WP05**.
- Any edit to `scripts/office2/restic-backup.sh`. It is `root:root`,
  hand-deployed, and outside the manifest pipeline (#903). The whole design
  avoids touching it.
- Adding a restic source path. `restic forget` runs without `--group-by`, so a
  fifth path would split the snapshot group and permanently strand the existing
  17 snapshots from pruning (C-002).

## Reviewer guidance

Check the `notes` length first — it is the failure that costs a re-applying loop
on the host. Then confirm `expected_baselines` is **absent** and that the reviewer
agrees the repo-file signal exists (grep `audited-surfaces.json` for
`scripts/office2/*.timer`). Then confirm no verification command is wrapped in
`ssh`. Finally, confirm the timer interval is genuinely shorter than the daily
backup interval — that is the only thing making FR-002 true.
