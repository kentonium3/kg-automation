---
work_package_id: WP01
title: Rebaseline destructive-step warning
dependencies: []
requirement_refs:
- FR-007
planning_base_branch: feat/crontab-backup-coverage
merge_target_branch: feat/crontab-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on feat/crontab-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/crontab-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crontab-backup-coverage-01M12V87
base_commit: 0adee2012657e7df3407661a927df0a199aeea23
created_at: '2026-08-28T02:37:36.005537+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 0 - Guard the destructive step
history:
- at: '2026-08-28T00:37:21Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks/
create_intent: []
execution_mode: code_change
owned_files:
- docs/runbooks/security-baseline-ops.md
- docs/runbooks/governance/post-change-verification.md
- docs/INDEX.md
- CLAUDE.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP01 — Rebaseline destructive-step warning

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

The documented rebaseline procedure begins by deleting every security-monitor
baseline:

```
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

On 2026-08-27 that directory held `crontabs.txt` — the **only** surviving copy of
the `claude` crontab after `/home/claude` was destroyed. An operator following
the runbook before transcribing it would have destroyed the last copy. This work
package puts a warning in front of the destructive step at every place a human
is told to run it.

**Done when**: every operator-facing prose copy carries the warning above the
`rm`, the stale baseline count is corrected, and
`docs/design/architecture/data/audited-surfaces.json` is **byte-identical** to
what it was before you started.

**Maps to**: FR-007, C-001, C-005, SC-006.

---

## ⛔ The one thing that must not happen

`docs/design/architecture/data/audited-surfaces.json` contains a
`rebaseline_command` field holding that same command string. **Do not edit it.**
It is not documentation — it is parsed:

```python
# scripts/deploy/felix-deployer/rebaseline.py:585-586
rm_tokens = rm_part.split()
if len(rm_tokens) < 2 or rm_tokens[0] != "rm":
```

On parse failure `_build_readonly_audit_cmd` returns `["true"]`, documented
in-code as producing no output and therefore an **inconclusive** audit. Rewriting
the command to archive-instead-of-delete — which issue #895 suggests as the
"better" option — would silently disable the deferred-confirm rebaseline audit
for every future deploy. The mission spec forbids it (C-001) and research R-02
explains why. Prose only.

Verify before you finish:

```bash
git diff --stat docs/design/architecture/data/audited-surfaces.json
```

Must print nothing.

---

## Subtasks

### T001 — Warn above the manual reset in `security-baseline-ops.md`

**Purpose**: This is the primary operator-facing copy — the "Manual reset
procedure (fallback)" section, around line 165-175.

**Steps**:

1. Open `docs/runbooks/security-baseline-ops.md` and find the
   `## Manual reset procedure (fallback)` heading.
2. Insert a warning block **between the prose paragraph and the fenced command**,
   so it cannot be missed by someone scrolling to the code block. Content must
   convey, in your own words:
   - the baselines directory is written for *drift detection*, not as a backup;
   - some baselines may nonetheless be the only surviving copy of host state —
     `crontabs.txt` was exactly that on 2026-08-27;
   - archive or transcribe anything you might need **before** running the `rm`,
     e.g. `cp -a baselines/ /tmp/baselines-$(date +%s)/`;
   - reference #895 so the reader can find the history.
3. Do not restructure the section or reword the surrounding prose beyond what the
   insertion requires.

**Files**: `docs/runbooks/security-baseline-ops.md`

**Validation**:
- [ ] The warning appears *above* the fenced `rm` command, not after it
- [ ] The command inside the fence is unchanged

### T002 — Warn above the rebaseline command in `post-change-verification.md`

**Purpose**: `docs/runbooks/governance/post-change-verification.md:93` carries the
same command in a governance checklist an operator follows after a change.

**Steps**:

1. Locate the fenced command at approximately line 93.
2. Add a **short** pointer — one or two sentences — warning that the `rm` is
   destructive and linking to the fuller warning in
   `docs/runbooks/security-baseline-ops.md`. Do not duplicate the full block; a
   governance checklist should stay scannable, and one canonical explanation is
   easier to keep true than three.

**Files**: `docs/runbooks/governance/post-change-verification.md`

**Validation**:
- [ ] Warning present above the command
- [ ] Links to the canonical explanation rather than restating it

### T003 — Warn above the rebaseline command in `CLAUDE.md`

**Purpose**: `CLAUDE.md:368` documents the out-of-band manual reset. This file is
read by every agent session, so the warning belongs here too.

**Steps**:

1. Find the fenced command under the "Out-of-band exception (manual reset still
   required)" paragraph.
2. Add the same short pointer as T002, pointing at
   `docs/runbooks/security-baseline-ops.md`.
3. Keep it tight — `CLAUDE.md` is loaded into every session's context and prose
   added here has a recurring cost.

**Files**: `CLAUDE.md`

**Validation**:
- [ ] Warning present above the command
- [ ] Added text is 2 sentences or fewer

### T004 — Correct the stale baseline count

**Purpose**: `docs/runbooks/security-baseline-ops.md:176` says the reset writes
"14 baseline files". The registry (`expected_baseline_count`) and the live host
both say **15** — verified by `ls /data/services/security-monitor/baselines/ | wc -l`.
The count went to 15 in #818 and this prose was not updated.

**Steps**:

1. Change `14` to `15` in the "Expected output on success" sentence.
2. Scan the rest of the file for any other hard-coded baseline count and correct
   it the same way.

**Files**: `docs/runbooks/security-baseline-ops.md`

**Validation**:
- [ ] No occurrence of a stale count remains: `grep -n "14 baseline" docs/runbooks/security-baseline-ops.md` returns nothing

**Why this is in scope**: the boy-scout directive is active in this project's
charter, the error is in a section this WP already edits, and an operator
verifying a reset against a wrong expected count either ignores the doc or wastes
time investigating a non-problem.

### T005 — Record the runbook-modified signal in `docs/INDEX.md`

**Purpose**: `docs/design/architecture/data/signal-to-doc-map.json` maps the
`runbook-modified` change class to `docs/INDEX.md`. This is the surface routinely
missed — see #492, the precedent that motivated formalizing the map.

**Steps**:

1. Read the entries for `docs/runbooks/security-baseline-ops.md` and
   `docs/runbooks/governance/post-change-verification.md` in `docs/INDEX.md`.
2. If either description is now inaccurate given the added warning, update it.
   If both remain accurate, **make no edit** and say so in your completion notes —
   a no-change rationale is a valid outcome here and is better than a cosmetic
   diff.

**Files**: `docs/INDEX.md`

**Validation**:
- [ ] Either the index reflects the change, or the WP notes record why no change was needed

---

## Definition of Done

- [ ] Warning present above the destructive step in all three operator-facing files
- [ ] `git diff --stat docs/design/architecture/data/audited-surfaces.json` is empty
- [ ] Stale baseline count corrected
- [ ] `docs/INDEX.md` updated or a no-change rationale recorded
- [ ] `python3 tooling/scripts/validate_docs.py` passes
- [ ] `python3 tooling/scripts/validate_architecture_data.py --strict` passes
- [ ] No file under `docs/diagnostics/**` or `kitty-specs/**` was touched

## Out of scope

- Changing the rebaseline command anywhere, including to an archive form (C-001;
  if still wanted, that is a separate issue with a parser change attached).
- The historical copies under `docs/diagnostics/**` and `kitty-specs/**`. These
  are frozen records of past missions. `kitty-specs/` is additionally
  write-prohibited for anything but spec-kitty itself.

## Reviewer guidance

The single highest-value check is `git diff` on
`docs/design/architecture/data/audited-surfaces.json` — it must be empty. After
that, confirm the warning is positioned *above* each command rather than below,
since a warning under the thing it warns about is decoration. Finally, confirm no
diagnostics or kitty-specs file was swept in by an over-broad find-and-replace.
