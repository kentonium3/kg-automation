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
shell_pid: "82197"
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

**SCOPE NARROWED (see spec FR-008/SC-5 + fast-follow #659).** A one-time, idempotent,
**safe, non-destructive** office2 migration of the **inbox** content only: move the inbox
state file(s) to `/data/services/openclaw/state/` (correct ownership/modes) and copy the
**inbox** historical forensic logs (`inbox-prescan-*.md`) into the vault. **Do NOT remove
or quarantine the `/home/claude/second-brain` tree** — it still hosts the active
observation-digest subsystem (`scripts/openclaw/observation/config.py`, felix-core-digest)
which is out of scope and handled by the fast-follow **#659**. Delivered as a Tier-2 deploy
manifest + entrypoint on `scripts/deploy/lib/`. Done when `--dry-run` shows the plan and
mutates nothing, the entrypoint is idempotent, and no ledger entry can be lost.

## Context & Constraints

- Plan IC-05; `research.md` R5/R7 (H1); `data-model.md`; `contracts` C5. Where those
  describe full-tree decommission/quarantine, treat that as **superseded** by this
  narrowed scope (#659 owns the full decommission).
- **Tier-2** (state mutation on a service data dir, C-003): confirm a Restic snapshot
  ≤24h (or trigger one) via `scripts/deploy/lib/snapshot` before mutating.
- **Live state (probe 2026-07-04)**: `/home/claude/second-brain/agents/state/` holds
  only `inbox-routing.jsonl`; `agents/logs/` has **top-level `inbox-prescan-*.md` (ours)**
  PLUS per-agent subdirs (enrichment, felix-admin-*, …) that belong to the observation
  subsystem — **do NOT touch those subdirs**. `pending-calendar-clarifications.*` not on disk now.
- **Cutover (H1)**: readers (WP02/WP03) target `/data/...`; copy state there **before**
  they rely on it. The manifest ordering + `pre` presence check guarantee this.
- Target dir convention: `claude:secondbrain`, dir `0750`, files `0640`.

## Subtasks & Detailed Guidance

### Subtask T016 – migration entrypoint (inbox-only, non-destructive)
- **File**: `scripts/deploy/migrate-inbox-state-and-logs.py`
- **Steps** (idempotent; support `--dry-run`; parameterize roots so tests use tmp dirs):
  1. **Snapshot gate**: refuse unless a Restic snapshot ≤24h exists (or trigger one) via `scripts/deploy/lib/snapshot`.
  2. **Ensure target dir**: `/data/services/openclaw/state/` exists as `claude:secondbrain`, `0750`. Always ENFORCE (repair) owner/group/mode even if it pre-exists.
  3. **Migrate state (non-destructive)**: for each present state file under `agents/state/` (`inbox-routing.jsonl`; also `pending-calendar-clarifications.*` if present), copy to the target and enforce `claude:secondbrain 0640`. If the target already exists: identical → skip copy (still enforce perms); **divergent `.jsonl` ledger → UNION-MERGE** (preserve every entry from both sides, no loss); divergent non-mergeable → **CONFLICT abort** (exit 1). [Keep the accepted cycle-2/3 logic.]
  4. **Copy INBOX logs only**: copy the **top-level** `agents/logs/inbox-prescan-*.md` files into `/home/kgale/second-brain/agents/logs/` (skip-if-exists). **Do NOT** recurse into the per-agent subdirs (enrichment, felix-admin-*, …) — those are the observation subsystem's, owned by #659.
  5. **NO decommission**: do NOT inventory/quarantine/remove `/home/claude/second-brain`. Leave the tree in place. (Removing it is #659, after its writers are repointed.)
- **Notes**: `claude` has no sudo; strict ownership enforcement is a hard error in production (`--skip-chown` for dev tests). Keep the snapshot gate + strict perms from the accepted cycles.

### Subtask T017 – manifest
- **File**: `deploys/queued/0007-migrate-inbox-state-and-logs.yaml`
- **Steps**: schema `v1`; `tier: 2`; `entrypoint: scripts/deploy/migrate-inbox-state-and-logs.py`.
  `verification.pre`: Restic snapshot ≤24h present. `verification.post`: state file(s) present + non-empty at `/data/...` with owner=claude group=secondbrain mode=0640; state dir mode 0750; at least the migrated `inbox-prescan-*.md` present in the vault. **Do NOT** assert `/home/claude/second-brain` is gone (it intentionally remains — #659). `notes`: cite #656 FR-005/008/012 (narrowed) + the #659 fast-follow for full decommission; depends on WP02/WP03 repointed readers.

### Subtask T018 – tests
- **File**: `tests/deploy/test_migrate_inbox_state.py`
- **Steps** (tmp fixtures, no office2 dep): `--dry-run` mutates nothing; a real run migrates state + copies inbox-prescan logs + enforces modes (incl. on a pre-existing target); second run idempotent no-op; **divergent-ledger union-merge preserves all entries** (target {A,B}+source {B,C} → {A,B,C}); divergent non-mergeable → conflict abort; and **the `/home/claude/second-brain` tree + its per-agent log subdirs are LEFT INTACT** (assert they still exist and the observation subdirs were not copied/removed).

## Test Strategy

- `python3 -m pytest tests/deploy/test_migrate_inbox_state.py -q` against tmp fixtures.

## Risks & Mitigations

- **Ledger data loss** → union-merge on divergent target / conflict-abort non-mergeable (keep accepted logic).
- **Cutover window (H1)** → copy-before-readers-rely + `pre` presence check.
- **Accidentally touching the observation subsystem** → copy only top-level `inbox-prescan-*.md`; never recurse per-agent subdirs; never remove the tree (that's #659).
- **Snapshot missing** → gate refuses; trigger one first.

## Integration Verification (before for_review)

- [ ] `--dry-run` mutates nothing; real run idempotent; strict perms enforced (incl. pre-existing target).
- [ ] Divergent-ledger union-merge loses no entry; non-mergeable divergence aborts.
- [ ] Only top-level `inbox-prescan-*.md` copied to vault; observation per-agent subdirs untouched.
- [ ] `/home/claude/second-brain` tree is LEFT IN PLACE (no quarantine/remove); manifest post does not assert it gone.

## Review Guidance

- Confirm the tree is NOT removed and observation subdirs are untouched (that's #659).
- Confirm the union-merge no-data-loss path and strict perms are intact from prior cycles.

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
- 2026-07-05T04:22:40Z – claude:sonnet:python-pedro:implementer – shell_pid=80086 – Started implementation via action command
- 2026-07-05T04:27:17Z – claude:sonnet:python-pedro:implementer – shell_pid=80086 – Cycle 3: divergent-target data-loss fixed — union-merge ledger, conflict-abort otherwise; no dropped entries; all tests green
- 2026-07-05T04:27:55Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=82197 – Started review via action command
- 2026-07-05T04:30:08Z – user – shell_pid=82197 – Review passed: union-merge preserves JSONL ledger entries, non-mergeable divergent state aborts before quarantine, snapshot/dry-run/idempotency/classification gates verified; focused migration and dependency path tests pass
