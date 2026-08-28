---
work_package_id: WP01
title: Record the prune outcome
dependencies: []
requirement_refs:
- FR-001
- FR-002
planning_base_branch: feat/backup-integrity-observability
merge_target_branch: feat/backup-integrity-observability
branch_strategy: Planning artifacts for this mission were generated on feat/backup-integrity-observability. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/backup-integrity-observability unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T11:30:00Z'
subtasks:
- T001
- T002
- T003
- T004
phase: Phase 0 - Make the prune outcome exist
history:
- at: '2026-08-28T11:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/office2/restic-backup.sh
create_intent: []
execution_mode: code_change
owned_files:
- scripts/office2/restic-backup.sh
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP01 — Record the prune outcome

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

On 2026-08-27 a stale lock blocked `restic forget --prune` for ten hours. Every
health surface read healthy the whole time — correctly, because the *backup* was
healthy. The prune had failed, and `backup.sh` throws that result away:

```bash
PRUNE_RC=$?
if [ $PRUNE_RC -ne 0 ]; then
    log "WARNING: Prune failed with exit code $PRUNE_RC"
```

It logs it, and `write_state_pointer` records only `restic_exit_code`. Make the
prune outcome exist in the pointer.

**Done when**: every run records `prune_exit_code`, and a run that never reached
the prune step records `127` rather than `0` or nothing.

**Maps to**: FR-001, FR-002.

---

## ⚠ Read before editing

**This file is `root:root` on office2 and hand-installed.** You change the repo
copy only. Do **not** attempt to install it, and do not add any deploy step for
it — `/data/services/backup/scripts/` must stay non-claude-writable because it
holds a `NOPASSWD` sudo target, and making it writable recreates the #899
privilege escalation. The operator installs it manually; the repo legitimately
leads the host until then.

---

## Subtasks

### T001 — Initialise `PRUNE_RC` to the `127` not-run sentinel

**Purpose**: Distinguish "never attempted" from "succeeded". This is the whole of
FR-002 and it is easy to get wrong.

**Steps**:

1. Beside the existing block near line 24:
   ```bash
   BACKUP_RC=127      # "not run" sentinel; overwritten by `restic backup`
   ```
   add `PRUNE_RC=127` with a matching comment. Follow the existing convention
   rather than inventing a second one.
2. Do **not** use `null` or leave it unset. The canary's explicit-error scan
   guards with `isinstance(code, int)`, so a non-integer is *skipped* — a run
   killed between a successful backup and the prune would then write
   `restic_exit_code: 0` with a non-integer prune value and read **healthy**.
   That is exactly the silent-success path this mission closes.

**Validation**:
- [ ] `PRUNE_RC` is initialised before any early `exit` can be reached

### T002 — Record `prune_exit_code` in the state pointer

**Steps**:

1. In the `write_state_pointer` heredoc, add `"prune_exit_code": $PRUNE_RC,`
   beside `"restic_exit_code": $BACKUP_RC,`.
2. Keep every existing field's name, type, and meaning unchanged — a pointer
   written before this change must stay interpretable (NFR-002), and both
   consumers (`scripts/canary/probes.py`, `scripts/deploy/lib/snapshot.py`) read
   by key.
3. `write_state_pointer` runs from the `EXIT` trap, so the field is recorded on
   failure paths too. Do not move the trap or add a second writer.

**Validation**:
- [ ] Valid JSON on every path (`python3 -m json.tool` the emitted file)
- [ ] No existing field renamed, retyped, or reordered out of the schema

### T003 — Confirm every pre-prune exit path reports `127`

**Purpose**: The sentinel is only worth anything if it survives the paths that
skip the prune.

**Steps**:

Walk each early exit and confirm what the pointer will say:

| Path | `restic_exit_code` | `prune_exit_code` | Correct? |
|---|---|---|---|
| `/mnt/backups` not mounted → `exit 1` | 127 | 127 | unhealthy — right, nothing ran |
| repo inaccessible → `exit 1` | 127 | 127 | unhealthy — right |
| backup fails (not 0/3) → `exit 1` | actual | 127 | unhealthy — right, retention also did not run |
| backup exits 3, prune succeeds | 3 | 0 | healthy — right, consistent with existing backup semantics |
| backup 0, prune fails | 0 | non-zero | unhealthy — the case this mission exists for |

Record any path where the table does not hold.

**Validation**:
- [ ] Each row confirmed by reading the script, not assumed

### T004 — Update the script's own header comment

**Steps**:

Extend the `#511` comment block at the top to say the pointer now also carries
the prune outcome and what `127` means. Someone reading this file during an
incident should not have to infer the sentinel.

**Validation**:
- [ ] The `127` sentinel is explained in-file

---

## Definition of Done

- [ ] `PRUNE_RC` initialised to `127`; `prune_exit_code` recorded on every path
- [ ] Emitted JSON valid; no existing field changed
- [ ] The T003 table confirmed by reading the code
- [ ] `make test` at or above the 6216 floor
- [ ] **No install attempted**; no deploy manifest added for this file

## Out of scope

- Teaching the canary to read the field — **WP02**.
- Installing the script on office2 — the operator's privileged step.
- Changing the prune command, retention policy, schedule, or source set.

## Reviewer guidance

Check T001 first: a `null` or unset sentinel silently reintroduces the defect,
and it looks harmless. Then confirm the emitted JSON is valid on the *early-exit*
paths, not just the happy path — that is where a shell-variable mistake shows up.
Finally confirm nothing here tries to install the file or add a manifest for it.
