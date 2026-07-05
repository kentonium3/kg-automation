---
work_package_id: WP05
title: One-time office2 migration entrypoint + Tier-2 manifest (atomic + quarantine)
dependencies:
- WP02
- WP03
requirement_refs:
- FR-005
- FR-008
- FR-012
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
shell_pid: "78208"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: python-pedro
authoritative_surface: scripts/deploy/
create_intent:
- scripts/deploy/migrate-inbox-state-and-logs.py
- deploys/queued/0007-migrate-inbox-state-and-logs.yaml
- tests/deploy/test_migrate_inbox_state.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/deploy/migrate-inbox-state-and-logs.py
- deploys/queued/0007-migrate-inbox-state-and-logs.yaml
- tests/deploy/test_migrate_inbox_state.py
role: implementer
tags: []
---

# Work Package Prompt: WP05 – Migration entrypoint + manifest

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Branch Strategy

- Planning/base + merge target: `fix/felix-admin-cron-path-fix`. Depends on WP02, WP03.

## Objectives & Success Criteria

A one-time, idempotent, **safe** office2 migration: move the inbox state file(s) to
`/data/services/openclaw/state/` (correct ownership/modes), preserve historical
forensic logs into the vault, and decommission the stray `/home/claude/second-brain`
**without data loss**. Delivered as a Tier-2 deploy manifest + entrypoint on the
`scripts/deploy/lib/` primitives. Done when `--dry-run` shows the plan and mutates
nothing, the entrypoint is idempotent, and it refuses to delete if anything is unclassified.

## Context & Constraints

- Plan IC-05; `research.md` R5/R7 (H1, H2, H3); `data-model.md` migration transition;
  `contracts` C5.
- **Tier-2** (state mutation on a service data dir, C-003): the entrypoint MUST
  confirm a Restic snapshot ≤24h (or trigger one) via `scripts/deploy/lib/snapshot`
  before mutating.
- **Live state (probe 2026-07-04)**: `/home/claude/second-brain/agents/state/` holds
  only `inbox-routing.jsonl`; `agents/logs/` has per-agent subdirs (enrichment,
  felix-admin-*, …) **plus** top-level `inbox-prescan-*.md`. `pending-calendar-clarifications.*`
  is not on disk now (created on demand).
- **Cutover (H1)**: readers (WP02/WP03) target `/data/...`; copy state there **before**
  they rely on it. The manifest ordering + `pre` presence check guarantee this.
- Target dir convention: `claude:secondbrain`, dir `0750`, files `0640`.

## Subtasks & Detailed Guidance

### Subtask T016 – migration entrypoint
- **File**: `scripts/deploy/migrate-inbox-state-and-logs.py`
- **Steps** (idempotent; support `--dry-run`):
  1. **Snapshot gate**: refuse unless a Restic snapshot ≤24h exists (or trigger one)
     via `scripts/deploy/lib/snapshot`.
  2. **Ensure target dir**: `/data/services/openclaw/state/` exists as `claude:secondbrain`, `0750`.
  3. **Copy state**: for each present file under `/home/claude/second-brain/agents/state/`
     (currently `inbox-routing.jsonl`; also any `pending-calendar-clarifications.*` if
     present), copy to the target preserving content; set `claude:secondbrain 0640`.
     Skip if an identical file already exists at target (idempotent).
  4. **Preserve logs**: **recursively** copy `/home/claude/second-brain/agents/logs/`
     (incl. per-agent subdirs) into `/home/kgale/second-brain/agents/logs/` without
     overwriting a same-named canonical log (skip-if-exists or suffix).
  5. **Inventory + classify**: walk the entire `/home/claude/second-brain` tree; every
     path must be classified as copied/handled. If any path is unclassified, **refuse**
     to remove and report it.
  6. **Quarantine**: rename `/home/claude/second-brain` → `/home/claude/second-brain.quarantine-<ts>`
     (ts passed in / derived deterministically — do not call `Date.now()` style in a
     way that breaks idempotency; accept a `--stamp` arg). Final delete only after the
     manifest `post` checks pass (or leave quarantined for a later verified window).
- **Notes**: `claude` has no sudo; all paths are claude-owned. Use `shutil`/`os` with
  explicit modes; chgrp to `secondbrain` (claude is in that group).

### Subtask T017 – manifest
- **File**: `deploys/queued/0007-migrate-inbox-state-and-logs.yaml`
- **Steps**: schema `v1`; `tier: 2`; `entrypoint: scripts/deploy/migrate-inbox-state-and-logs.py`.
  `verification.pre`: Restic snapshot ≤24h present. `verification.post`: state file(s)
  present + non-empty at `/data/...` with `claude:secondbrain 0640`; historical logs
  present in the vault; `/home/claude/second-brain` gone or quarantined; parity check
  (nothing unclassified dropped). `notes`: cite #656 FR-005/008/012; depends on the
  WP02/WP03 code being deployed (repointed readers).

### Subtask T018 – tests
- **File**: `tests/deploy/test_migrate_inbox_state.py`
- **Steps**: build a fake stray tree in a tmp dir; assert `--dry-run` prints the plan
  and mutates nothing; a real run copies + sets modes + quarantines; a second run is a
  no-op (idempotent); an unclassified extra file causes a refusal-to-delete.

## Test Strategy

- `python3 -m pytest tests/deploy/test_migrate_inbox_state.py -q` against tmp fixtures
  (no office2 dependency).

## Risks & Mitigations

- **Data loss on decommission (H2)** → inventory+quarantine+refuse-on-unclassified.
- **Cutover window (H1)** → copy-before-readers-rely + `pre` presence check; note the
  frontmatter-only-dedup case (WP03 T010) is the residual risk this ordering closes.
- **Snapshot missing** → gate refuses; trigger one first.

## Integration Verification (before for_review)

- [ ] `--dry-run` mutates nothing; real run idempotent.
- [ ] Refuses to delete when an unclassified path remains.
- [ ] Target files carry `claude:secondbrain 0640`; logs preserved recursively.

## Review Guidance

- Scrutinize the decommission path: is deletion truly gated on full classification +
  parity? Is the copy recursive over per-agent log subdirs?

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T03:51:20Z – claude:sonnet:python-pedro:implementer – shell_pid=65970 – Assigned agent via action command
- 2026-07-05T04:04:47Z – claude:sonnet:python-pedro:implementer – shell_pid=65970 – Ready for review: dry-run safe (mutates nothing, tested), idempotent (second run no-op, tested), H2 refuse-on-unclassified tested, atomic copy-before-cutover, recursive log preservation, quarantine-rename with stamp. Lint: ruff not installed on host; py_compile syntax OK. All 5 pytest cases pass.
- 2026-07-05T04:05:32Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=72525 – Started review via action command
- 2026-07-05T04:08:01Z – user – shell_pid=72525 – Moved to planned
- 2026-07-05T04:09:15Z – claude:sonnet:python-pedro:implementer – shell_pid=74738 – Started implementation via action command
- 2026-07-05T04:17:57Z – claude:sonnet:python-pedro:implementer – shell_pid=74738 – Cycle 2: perms repaired on existing targets, strict chown (hard fail, test override), manifest post verifies owner/group/mode/logs/quarantine/parity
- 2026-07-05T04:18:34Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=78208 – Started review via action command
- 2026-07-05T04:20:42Z – user – shell_pid=78208 – Moved to planned
