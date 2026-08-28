---
work_package_id: WP05
title: Registration, runbooks, and the trusted install
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- FR-007
- FR-008
- FR-010
planning_base_branch: feat/backup-integrity-observability
merge_target_branch: feat/backup-integrity-observability
branch_strategy: Planning artifacts for this mission were generated on feat/backup-integrity-observability. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/backup-integrity-observability unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T11:30:00Z'
subtasks:
- T017
- T018
- T019
- T020
- T021
- T022
phase: Phase 3 - Register and document
history:
- at: '2026-08-28T11:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/
create_intent:
- docs/runbooks/crontab-recovery.md
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/service-dependencies.view.md
- docs/design/felix-capability-roadmap.md
- docs/runbooks/restic-backup-ops.md
- docs/runbooks/crontab-recovery.md
- docs/runbooks/deploy/discipline.md
- docs/runbooks/deploy/office2-deploy-paths.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
- scripts/deploy/lib/README.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP05 — Registration, runbooks, and the trusted install

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

Register the comparator so its signal reaches the canary, correct the restic
`expected` prose which this mission makes false, and put the recovery and install
procedures where an operator will actually look for them during an incident.

**Maps to**: FR-007, FR-008, FR-010; SC-006, SC-008.

---

## Subtasks

### T017 — Register the comparator; correct the restic entry

**Steps**:

1. Add `backup-script-drift` to `service-inventory.json`: `type:
   systemd_user_timer`, `status: active`, daily schedule, `risk_tier: 3`,
   dependency on `restic-backup` of type `monitors`.
2. `health_check`: `method: state-file`, absolute
   `state_path: /data/services/backup/state/script-drift-last-tick.json`,
   `max_age_seconds: 108000` (daily + slack), `timeout_seconds: 5`.
3. **Declare `success_status_values: ["success"]`.** Without an allow-list,
   `probes.py` treats `status` as a *deny-list* — any word it does not recognise
   as a failure passes as healthy, so a future verdict word would silently read
   fine. This is the #891 affirmative-health rule.
4. `expected` prose must state that `inconclusive` is unhealthy — a comparator
   that cannot read the deployed copy knows nothing.
5. **Correct the existing `restic-backup` entry's `expected` prose**, which this
   mission makes false in two ways: it must now describe the `prune_exit_code`
   rule (good-set `{0}` only, `127` = never attempted) and must no longer imply
   the snapshot timestamp can be absent. Also record that a prune failure makes
   the component unhealthy but deliberately does **not** gate Tier-2 deploys.
6. Update `last_updated` and append to `updated_by`.

**Validation**:
- [ ] `success_status_values` present on the new check
- [ ] `python3 tooling/scripts/validate_architecture_data.py --strict` passes
- [ ] `python3 -m pytest tests/canary/test_inventory_health_checks.py -q` passes

### T018 — Narrative, view, and roadmap

**Steps**:

1. `service-inventory.md` — add the comparator to the scheduled-jobs table.
2. `service-dependencies.view.md` — add the node and its edge to `restic-backup`.
   Verify the mermaid block stays balanced and every edge names a node that
   exists; a phantom target renders a ghost node.
3. `felix-capability-roadmap.md` — a short note under the observability
   foundation: retention failure and repo/host divergence are now observable.
   State the limit plainly — the install remains manual by security decision.

**Validation**:
- [ ] Mermaid parses; no dangling edges
- [ ] The manual-install limit is stated, not implied

### T019 — New `crontab-recovery.md` runbook

**Steps**:

1. Create `docs/runbooks/crontab-recovery.md` with standard frontmatter matching
   sibling runbooks.
2. The recovery, using WP04's emitter:
   ```
   python3 scripts/office2/crontab_capture.py --emit-body | crontab -
   ```
3. The deeper path when `/data` is gone: restore from a snapshot first (needs
   sudo, `/etc/restic/password` is root-only), then emit and install.
4. State explicitly: **do not** use the `grep -v "^# captured-…"` form from the
   #895 quickstart. It predates the sentinel header, leaves two stray lines
   behind, and is the defect #906 fixed. An operator who finds the old form
   during an incident needs to be told it is wrong.
5. Note the scope limit: the `claude` crontab only; `kgale` and `root` are
   unreadable unprivileged and are not covered.

**Validation**:
- [ ] The command works verbatim against a real artifact
- [ ] The superseded form is named and warned against

### T020 — `restic-backup-ops.md`: prune signal and the install decision

**Steps**:

1. Document `prune_exit_code`: `0` applied, non-zero failed, `127` never
   attempted, and that only `0` is success — explicitly noting it differs from
   `restic_exit_code`'s `{0, 3}`, and why.
2. Document the deploy story for `restic-backup.sh` (FR-008): it is **hand
   installed by the operator, by decision, not omission**, because
   `/data/services/backup/scripts/` must stay non-claude-writable — it holds a
   `NOPASSWD` sudo target and a writable directory there is equivalent to
   `NOPASSWD: ALL` (#899).
3. Document the install procedure with its **source verification** (FR-010):
   confirm the source matches the reviewed commit and the working tree is clean
   *before* `sudo install`, and compare hashes after. Protecting the destination
   while sourcing from a claude-writable checkout leaves the same boundary weak
   one step upstream.
4. Search the file (and `docs/runbooks/governance/`) for `jq` snippets or checks
   that test only `restic_exit_code`, and update them — otherwise the docs keep
   conflating "backup trust" with "component health" after this mission
   separates them.

**Validation**:
- [ ] No remaining doc check inspects only `restic_exit_code`
- [ ] Source verification appears before the `sudo install`, not after

### T021 — Deploy-discipline doc surfaces

**Steps**:

The signal-to-doc map lists these for `deploy-manifest-added` and
`office2-service-deployment`:

- `docs/runbooks/deploy/discipline.md`
- `docs/runbooks/deploy/office2-deploy-paths.md`
- `scripts/deploy/lib/README.md`

Update each, or record an explicit no-change rationale in your completion notes.
`office2-deploy-paths.md` in particular should note that `restic-backup.sh` is
the documented exception to the pipeline, with the reason.

**Validation**:
- [ ] Each of the three updated or given a written no-change rationale

### T022 — Index and portal

**Steps**:

1. `docs/INDEX.md` — add `crontab-recovery.md` (runbook-added) and reflect the
   `restic-backup-ops.md` change (runbook-modified).
2. `docs/DEVELOPER_PORTAL.md` — add the new runbook (runbook-added).

**Validation**:
- [ ] Both updated; `validate_docs.py` passes

---

## Definition of Done

- [ ] Comparator registered with `success_status_values` and an absolute `state_path`
- [ ] `restic-backup` `expected` prose true again
- [ ] All doc surfaces from the map updated or given a no-change rationale
- [ ] `validate_architecture_data.py --strict`, `validate_docs.py`, and the canary data guard all pass
- [ ] `make test` at or above the 6216 floor
- [ ] No file outside `owned_files` modified

## Out of scope

- `audited-surfaces.json` — listed for `systemd-unit-added-or-modified`, but its
  `systemd-user-units` surface already matches `scripts/office2/*.{service,timer}`,
  so no change is needed. Record that as the no-change rationale; do **not** edit
  the file, whose `rebaseline_command` is parsed and fragile (#895 C-001).
- `kitty-specs/**` — workflow-owned.

## Reviewer guidance

The highest-value check is `success_status_values` on the new health check:
without it the component reports healthy for any unrecognised status word, which
is the #891 defect reappearing in a component built to detect problems. Then read
the corrected `restic-backup` `expected` prose against WP02's actual code and
confirm they now agree — the whole reason this subtask exists is that they had
drifted. Finally confirm T020's install procedure verifies the *source*, since
protecting only the destination was the gap the post-plan review caught.
