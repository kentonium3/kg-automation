---
work_package_id: WP03
title: Backup script drift comparator
dependencies: []
requirement_refs:
- FR-004
- FR-005
planning_base_branch: feat/backup-integrity-observability
merge_target_branch: feat/backup-integrity-observability
branch_strategy: Planning artifacts for this mission were generated on feat/backup-integrity-observability. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/backup-integrity-observability unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T11:30:00Z'
subtasks:
- T008
- T009
- T010
- T011
- T012
- T013
phase: Phase 2 - Detect divergence, fix recovery
history:
- at: '2026-08-28T11:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/office2/backup_script_drift.py
create_intent:
- scripts/office2/backup_script_drift.py
- scripts/office2/backup-script-drift.service
- scripts/office2/backup-script-drift.timer
- scripts/deploy/deploy-backup-script-drift.py
- deploys/queued/backup-script-drift.yaml
- tests/office2/backup_script_drift/__init__.py
- tests/office2/backup_script_drift/test_backup_script_drift.py
execution_mode: code_change
owned_files:
- scripts/office2/backup_script_drift.py
- scripts/office2/backup-script-drift.service
- scripts/office2/backup-script-drift.timer
- scripts/deploy/deploy-backup-script-drift.py
- deploys/queued/backup-script-drift.yaml
- tests/office2/backup_script_drift/**
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP03 — Backup script drift comparator

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/backup-integrity-observability`
- **Final merge target**: `feat/backup-integrity-observability`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch`.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

`scripts/office2/restic-backup.sh` is the repo source of truth for the deployed
`/data/services/backup/scripts/backup.sh`, but nothing compares them. #889
changed the repo copy with no manifest and the live file was installed by hand.
They currently match — which is luck, not enforcement, on the one script the
Tier-2 change-control guarantee depends on.

**Done when**: divergence is detected and reported, an unreadable deployed copy
reports inconclusive rather than match, and the component is registered-ready.

**Maps to**: FR-004, FR-005; NFR-004; C-001, C-002.

---

## ⛔ The boundary this must not cross

`/data/services/backup/scripts/` is `root:root` **deliberately**. It holds the
`NOPASSWD` sudo target `backup.sh`, and a claude-writable directory on that path
makes the grant equivalent to `NOPASSWD: ALL` — that was #899, a real privilege
escalation fixed on 2026-08-27.

This component **reads** those paths and never writes them. Do not add
remediation, do not "helpfully" copy the repo file into place, and do not add a
deploy step for `backup.sh`. Reading does not weaken the boundary; writing
destroys it.

---

## Subtasks

### T008 — Comparator module

**Steps**:

1. Create `scripts/office2/backup_script_drift.py` following
   `docs/design/helper-script-conventions.md` — argparse CLI, exit codes
   `0`/`1`/`2`, `SUMMARY:` final line, `INFO:`/`WARN:` on stdout, `ERROR:` to
   stderr, atomic state writes.
2. Expose a pure `compare(repo_path, deployed_path) -> verdict` that the tests
   can drive directly, plus a CLI wrapper.
3. Verdicts, exactly three:

   | verdict | condition |
   |---|---|
   | `match` | both readable, contents identical |
   | `drift` | both readable, contents differ |
   | `inconclusive` | deployed copy missing, unreadable, or unstattable |

4. Compare content hashes (MD5 is sufficient — this is drift detection, not a
   security control) and report both hashes in the output.
5. Flags: `--repo-path`, `--deployed-path` (defaults to the real pair), plus the
   state path.

**Validation**:
- [ ] `compare()` is importable and side-effect free
- [ ] Nothing in the module can write to the deployed path

### T009 — Freshness pointer with affirmative health

**Steps**:

1. Write `/data/services/backup/state/script-drift-last-tick.json` atomically on
   every run, per `data-model.md`:
   `status`, `exit_code`, `completed_at_utc`, `verdict`, `repo_md5`,
   `deployed_md5`.
2. Health mapping — `verdict` is diagnostic, `status`/`exit_code` carry health:

   | verdict | status | exit_code |
   |---|---|---|
   | `match` | `success` | 0 |
   | `drift` | `error` | 1 |
   | `inconclusive` | `error` | 2 |

3. **`inconclusive` is never healthy.** A comparator that cannot see the deployed
   copy knows nothing, and reporting nothing-known as agreement is the exact
   failure it exists to prevent.
4. Name diagnostic fields to avoid the canary's explicit-error keys
   (`error`, `errors`, `exit_status`, `cycle_error`) — hence `verdict`.
5. Pointer-write failure must not crash the run.

**Validation**:
- [ ] Pointer written on all three verdicts
- [ ] No diagnostic field collides with the explicit-error scan

### T010 — Unit and timer

**Steps**:

1. `backup-script-drift.service` — `Type=oneshot`,
   `WorkingDirectory=/home/claude/kg-automation`, absolute
   `/usr/bin/python3` (office2 is python3-only; a bare `python` exits 127).
2. `backup-script-drift.timer` — `OnCalendar=daily`, `Persistent=true`,
   `RandomizedDelaySec`, `WantedBy=timers.target`.
3. Header comments explaining what it compares and why the install stays manual.

**Validation**:
- [ ] Absolute interpreter path; `Persistent=true` present

### T011 — Deploy entrypoint

**Steps**:

Model on `scripts/deploy/deploy-crontab-capture.py` (same repo, recent, reviewed):
`--dry-run` / `--apply`; a deploy-user preflight asserting the euid passwd name
is `claude` **and** `Path.home() == /home/claude` before any mutation; copy units
to `~/.config/systemd/user/`; `daemon-reload`; gate on the helper's own
`--dry-run` succeeding **before** `enable --now`; then assert `is-enabled` and a
concrete `NextElapseUSecRealtime`.

⚠ Never wrap a command in `ssh office2-claude '...'` — this runs *on* office2 and
loopback SSH fails.

**Validation**:
- [ ] `--dry-run` inert; re-running `--apply` is a clean no-op
- [ ] Helper gate runs before the timer is enabled

### T012 — Manifest, with verification

**Steps**:

1. `deploys/queued/backup-script-drift.yaml`: `tier: 3`, `audited_surface: true`,
   entrypoint path, `mission_slug`.
2. **Declare `verification.post` even though Tier 3 does not require it.** The
   schema only mandates it for Tiers 1–2, which makes a deploy that installs
   nothing too easy to pass. Assert: timer `is-enabled`, a concrete next elapse,
   and the pointer exists.
3. **Do not** declare `expected_baselines` — the unit files are tracked, so
   `audited-surfaces.json`'s `systemd-user-units` surface gives a repo-file
   signal and the observe-range auto-rebaseline covers it (precedent:
   `applied/0020`, confirmed empirically by the #895 deploy).
4. `notes` must stay under **2000** characters. Exceeding it lets the entrypoint's
   side effects land and then blocks the applied record, re-applying every tick
   with no alert (#891/#901). Measure it.

**Validation**:
- [ ] `python3 -m scripts.deploy.lib.manifest validate_manifest_file <path>` passes
- [ ] Printed `notes` length < 2000

### T013 — Tests

**Steps**:

`tests/office2/backup_script_drift/`, using `tmp_path`, never the real paths:

1. Identical files → `match`, `status: success`, `exit_code: 0`.
2. Differing files → `drift`, unhealthy.
3. Missing deployed file → `inconclusive`, unhealthy.
4. Unreadable deployed file (chmod 000, skip if running as root) →
   `inconclusive`, **never** `match`.
5. Missing *repo* file → `inconclusive`.
6. The pointer is judged correctly by the **real** `scripts.canary.probes.run_probe`
   for all three verdicts.
7. Atomicity: a simulated write failure leaves no partial pointer and no `.tmp`.

**Validation**:
- [ ] Case 4 explicitly asserts `!= "match"` — fail-closed is the point
- [ ] Case 6 uses the real probe, not a reimplementation

---

## Definition of Done

- [ ] All three verdicts reachable and correctly mapped to health
- [ ] Manifest validates locally; `notes` under the limit
- [ ] `--dry-run` verified inert
- [ ] `make test` at or above the 6216 floor
- [ ] Nothing writes under `/data/services/backup/scripts/`
- [ ] No file outside `owned_files` modified

## Out of scope

- Registering the component in `service-inventory.json` — **WP05** (and note it
  must declare `success_status_values: ["success"]` there).
- Installing `backup.sh`, or any deploy path for it (C-001, C-002).
- Remediating drift. This component observes; the operator installs.

## Reviewer guidance

Hunt for fail-open. For every path where the deployed copy cannot be read —
missing, permission denied, a race with an in-progress install — confirm the
verdict is `inconclusive` and the health is unhealthy. A comparator that reports
`match` when it does not know is worse than none, because it converts an unknown
into a false assurance. Then confirm the module cannot write to the deployed
directory under any flag.
