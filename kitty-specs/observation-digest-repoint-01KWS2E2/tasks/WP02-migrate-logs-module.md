---
work_package_id: WP02
title: Migration logic module + Phase-1 entrypoint
dependencies: []
requirement_refs:
- FR-002
- FR-005
tracker_refs: []
planning_base_branch: fix/observation-digest-repoint
merge_target_branch: fix/observation-digest-repoint
branch_strategy: Planning artifacts for this mission were generated on fix/observation-digest-repoint. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/observation-digest-repoint unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
agent: "claude"
shell_pid: "45480"
history:
- created by /spec-kitty.tasks 2026-07-05
agent_profile: python-pedro
authoritative_surface: scripts/deploy/observation_migration.py
create_intent:
- scripts/deploy/observation_migration.py
- scripts/deploy/migrate-observation-logs.py
- tests/deploy/test_observation_migration.py
execution_mode: code_change
owned_files:
- scripts/deploy/observation_migration.py
- scripts/deploy/migrate-observation-logs.py
- tests/deploy/test_observation_migration.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile: `/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity and
boundaries, then read this WP fully and skim the reuse references before editing.

## Objective

Build the **Phase 1 (non-destructive)** migration: an importable module
`scripts/deploy/observation_migration.py` that union-merges the observation runtime logs from the
stray tree into the vault, atomically; and a thin executable wrapper
`scripts/deploy/migrate-observation-logs.py` that felix-deployer runs. **No deletion in this WP.**

## Context & reuse

- Study `scripts/deploy/migrate-inbox-state-and-logs.py` (the #656 migrator): reuse the shape of
  its `_union_merge_jsonl_files`, `_emit` structured logger, `--dry-run`/`--apply`, `sys.path`
  shim, and Restic snapshot gate (`scripts/deploy/lib/snapshot.py::verify_restic_recent`). Tests
  for it live in `tests/deploy/test_migrate_inbox_state.py` — mirror that test style.
- **Codex Major 3 fix**: the #656 union-merge appends directly to the destination. You MUST make
  the merge **atomic**: build the merged content, write to a temp file in the destination dir,
  `os.fsync`, then `os.replace` onto the destination (NFR-005).
- **Codex Major 4 fix**: filename `migrate-observation-logs.py` is hyphenated and NOT importable;
  put ALL logic in the underscore module `observation_migration.py` (importable as
  `scripts.deploy.observation_migration`) and make the hyphenated file a thin wrapper.
- Constants: `DEFAULT_SOURCE_ROOT = Path("/home/claude/second-brain")`,
  `DEFAULT_VAULT_LOGS_DIR = Path("/home/kgale/second-brain/agents/logs")`.

### Subtask T004 — Atomic union-merge (module)

- In `observation_migration.py`, implement `union_merge_jsonl(src_file, dst_file)`:
  read the union of lines from `src_file` and existing `dst_file` (dedup identical lines,
  preserve order: existing dst lines first, then new src lines), write to
  `dst_file.with_suffix(".tmp")`, `fsync`, `os.replace` onto `dst_file`. Idempotent.
- Implement `iter_source_log_files(source_root)` that globs **ONLY**
  `source_root/agents/logs/*/*.jsonl` (per-agent subdir JSONL). It MUST NOT `rglob`/`os.walk`
  the tree or touch top-level `.md` files (C-008 — never walk toward `_private`).

### Subtask T005 — Migrate flow + writability (module)

- Implement `migrate_logs(source_root, vault_logs_dir, dry_run)`:
  for each source jsonl at `agents/logs/<agent>/<date>.jsonl`, ensure
  `vault_logs_dir/<agent>/` exists (create with correct mode), then `union_merge_jsonl` into
  `vault_logs_dir/<agent>/<date>.jsonl`. In dry-run, only collect and return the plan; mutate nothing.
- Implement `check_vault_writable(vault_logs_dir)` (C-011): append+remove a temp `.jsonl` under the
  target; raise a clear error if not writable by the current user.
- Return a JSON-serializable result: `{migrated: [<agent>/<date>...], plan_only: bool}`. Never
  include any path outside `agents/logs/*` (no descendant of `_private`).

### Subtask T006 — Phase-1 executable wrapper

- `scripts/deploy/migrate-observation-logs.py`: shebang `#!/usr/bin/env python3`, file mode `100755`
  (`chmod +x`), `sys.path` shim (`_REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(_REPO_ROOT))`).
- argparse: `--dry-run` (default True), `--apply`, `--source-root` (default `/home/claude/second-brain`),
  `--vault-logs-dir` (default `/home/kgale/second-brain/agents/logs`).
- `--apply` runs the snapshot gate (Tier-2) then `migrate_logs(..., dry_run=False)` then
  `check_vault_writable`. Dry-run prints the JSON plan to stdout and exits 0 with **no** mutation.
- Print a single JSON object to stdout; structured progress/errors to stderr.

### Subtask T007 — Tests (`tests/deploy/test_observation_migration.py`)

- `union_merge_jsonl`: given overlapping src/dst temp files, result == set-union of lines, no dup,
  and the write used a temp file replaced atomically (assert no partial file left; can assert via
  monkeypatching or checking `os.replace` called / tmp absent after).
- Dry-run via subprocess (`subprocess.run([sys.executable, "scripts/deploy/migrate-observation-logs.py", "--dry-run", "--source-root", <tmp>, "--vault-logs-dir", <tmp2>])`) exits 0 and mutates nothing.
- Entrypoint file has the executable bit and contains the `sys.path` shim.
- The JSON plan output contains no `_private` and no path outside `agents/logs/*`.
- `iter_source_log_files` ignores top-level `.md` and never descends into non-`agents/logs` dirs.

## Branch Strategy

Base/merge target: `fix/observation-digest-repoint`. Worktrees are per-lane from `lanes.json`;
do not create branches manually.

## Test Strategy

`pytest tests/deploy/test_observation_migration.py -q`. Mirror `test_migrate_inbox_state.py`
conventions (temp dirs, subprocess dry-run). Do not require live office2 or Restic — mock the
snapshot gate.

## Definition of Done

- [ ] `observation_migration.py` importable; atomic union-merge; globs only `agents/logs/*/*.jsonl`.
- [ ] `migrate-observation-logs.py` wrapper: `+x`, shim, dry-run-default, exits 0 no-mutation.
- [ ] No deletion logic anywhere in this WP.
- [ ] Tests pass; output never contains a non-`agents/logs` path.

## Risks / Reviewer guidance

- **Risk**: non-atomic merge losing a concurrent append — reviewer verifies temp+fsync+os.replace.
- **Risk**: any `rglob`/`os.walk`/full-tree traversal — reviewer greps the module for `rglob`,
  `os.walk`, `iterdir` on the tree root; only `agents/logs/*/*.jsonl` globbing is allowed.
- **Risk**: import-name mismatch — reviewer confirms logic is in the underscore module and the
  hyphenated file is a thin wrapper.

## Activity Log

- 2026-07-05T13:15:02Z – claude – shell_pid=41154 – Assigned agent via action command
- 2026-07-05T13:22:52Z – claude – shell_pid=41154 – Moved to for_review
- 2026-07-05T13:23:18Z – claude – shell_pid=45480 – Started review via action command
- 2026-07-05T13:23:30Z – user – shell_pid=45480 – Review passed: atomic union-merge (temp+fsync+os.replace), glob agents/logs/*/*.jsonl only (no rglob/walk) + defensive _private filter, no deletion, wrapper 100755+shim, 13 tests green, 295 deploy tests no regression
