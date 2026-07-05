---
work_package_id: WP03
title: Phase-2 decommission entrypoint (gated, _private-safe)
dependencies:
- WP02
requirement_refs:
- FR-003
- FR-004
- FR-005
tracker_refs: []
planning_base_branch: fix/observation-digest-repoint
merge_target_branch: fix/observation-digest-repoint
branch_strategy: Planning artifacts for this mission were generated on fix/observation-digest-repoint. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/observation-digest-repoint unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
- T011
agent: claude
history:
- created by /spec-kitty.tasks 2026-07-05
agent_profile: python-pedro
authoritative_surface: scripts/deploy/observation_decommission.py
create_intent:
- scripts/deploy/observation_decommission.py
- scripts/deploy/decommission-observation-stray-tree.py
- tests/deploy/test_observation_decommission.py
execution_mode: code_change
owned_files:
- scripts/deploy/observation_decommission.py
- scripts/deploy/decommission-observation-stray-tree.py
- tests/deploy/test_observation_decommission.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile: `/ad-hoc-profile-load python-pedro` (role: implementer). This WP performs an
**irreversible whole-tree deletion of a second-brain clone** — read the spec's FR-003/FR-004,
C-008/C-009/C-010, and research.md D3/D8/D9/D12 in full before writing a line. Absolute rule:
**never read, walk, copy, or log any `_private` path.**

## Objective

Build **Phase 2 (destructive, separate deploy)**: `scripts/deploy/observation_decommission.py`
(logic) + `scripts/deploy/decommission-observation-stray-tree.py` (executable wrapper) that, only
after a hard precondition gate, quiesces the digest timer, does a final log merge, and removes the
entire `/home/claude/second-brain` clone with a single root-level `rm -rf`.

## Context (why this is dangerous)

`/home/claude/second-brain` is a git clone of `kentonium3/second-brain` containing a March vault
snapshot, old digest/state, live observation logs, and a `_private` growth directory. Kent
authorized full deletion (`DM-01KWS4F986PVHTJRSHZPQACDM7`) for this tree only. The design guards
against data loss (snapshot + origin recoverability) and privacy leaks (never touch `_private`).
Reuse `union_merge_jsonl`/`migrate_logs` and the snapshot gate from WP02's
`observation_migration.py` and `scripts/deploy/lib/`.

### Subtask T008 — Precondition gate (module)

Implement `check_preconditions(source_root, ...)` returning a structured result; ALL must pass or
the caller aborts non-zero WITHOUT any destructive action (FR-004):
1. **Snapshot + coverage** (FR-004a): a fresh Restic snapshot AND proof `source_root` is in the
   backup set (restore/include-list check) OR an explicit `--attest-backup-coverage` flag.
   Recency alone (the existing `verify_restic_recent`) is INSUFFICIENT — add a coverage check or
   require the attestation flag; if neither, fail.
2. **Origin recoverability** (FR-004b): `git -C <source_root> ...` confirms HEAD is present on
   `origin` (e.g. `git branch -r --contains HEAD` / `git rev-list` check). Do not push.
3. **Quiesce + no live process** (FR-004c): stop the `felix-core-digest` user timer
   (`systemctl --user stop felix-core-digest.timer`); confirm no `summarize.py`/`log_action.py`
   process is running (bounded wait). If a writer is active → abort.
4. **inbox-prescan mtime** (FR-004e): no top-level `agents/logs/inbox-prescan-*.md` newer than the
   #656 cutover constant; else abort / require operator disposition.

`check_preconditions` MUST NOT walk the tree beyond the specific checks above; it references only
`source_root` and `source_root/agents/logs/inbox-prescan-*.md`.

### Subtask T009 — Final merge + root-only delete (module)

- Under quiesce, run a **final** `migrate_logs(source_root, vault_logs_dir)` (reuse WP02) to catch
  any straggler appends.
- Delete: a single root-level operation removing `source_root` (e.g. `shutil.rmtree(source_root)`
  or `subprocess rm -rf <source_root>`). MUST NOT enumerate/`rglob`/`os.walk`/`git status --ignored`
  the tree, MUST NOT use per-file delete callbacks that echo child paths. If `rmtree` needs an
  error handler, it may name only `source_root`, never a descendant (C-008/C-012).
- Restart the timer (`systemctl --user start felix-core-digest.timer`).
- Post-check: `source_root` absent.

### Subtask T010 — Phase-2 executable wrapper

- `decommission-observation-stray-tree.py`: shebang, mode `100755`, `sys.path` shim.
- argparse: `--dry-run` (default True), `--apply`, `--source-root`, `--vault-logs-dir`,
  `--attest-backup-coverage`.
- Dry-run prints a JSON plan + precondition results, mutates nothing, exits 0. `--apply` runs
  gate → (abort non-zero on any failure) → final merge → root-only delete → restart → post-check.
- stdout: one JSON object; stderr: structured progress. **No descendant path** ever appears in
  stdout or stderr — only `source_root`.

### Subtask T011 — Tests (`tests/deploy/test_observation_decommission.py`)

- For EACH gate condition, a test where it fails → the entrypoint exits non-zero AND no deletion
  happens (assert the target dir still exists / rmtree not called). Use temp dirs + mocks for
  Restic/git/systemctl.
- Dry-run via subprocess exits 0 and mutates nothing.
- Entrypoint has `+x` and the `sys.path` shim.
- **Privacy test**: create a fake `source_root` containing a `vault/02-Growth/_private/secret.md`;
  run dry-run and (mocked) apply; assert NO output/log/error string contains `_private`, `secret`,
  or any path below `source_root` other than `agents/logs/*` and `source_root` itself.
- Assert the delete is a single root-level call (mock `shutil.rmtree`/subprocess and check it was
  invoked once with `source_root`, never with a descendant).

## Branch Strategy

Base/merge target: `fix/observation-digest-repoint`. Depends on WP02 (import its helpers).
Worktrees per-lane from `lanes.json`.

## Test Strategy

`pytest tests/deploy/test_observation_decommission.py -q`. All external effects (Restic, git,
systemctl, filesystem delete) mocked — tests never delete anything real and never require office2.

## Definition of Done

- [ ] Gate enforces snapshot+coverage, origin, quiesce+no-proc, inbox-prescan mtime; any failure → abort non-zero, no delete.
- [ ] Delete is root-only; no walk/rglob/git-status-ignored; `_private` never read/logged.
- [ ] Wrapper `+x`, shim, dry-run-default exits 0 no-mutation.
- [ ] Privacy test proves no descendant/`_private` path leaks to stdout/stderr/logs.
- [ ] Timer stopped before delete and restarted after.

## Risks / Reviewer guidance

- **Highest-risk WP.** Reviewer greps the module + wrapper for `rglob`, `os.walk`, `iterdir(`,
  `git status`, `--ignored`, and any logging of child paths — ALL must be absent.
- Reviewer confirms every gate-failure path aborts BEFORE the delete (read the control flow; no
  delete reachable unless all gates passed).
- Reviewer confirms the privacy test actually exercises a `_private` fixture and asserts absence.
- Reviewer confirms the delete cannot run in dry-run.
