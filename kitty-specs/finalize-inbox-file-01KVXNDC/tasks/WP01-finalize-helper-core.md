---
work_package_id: WP01
title: Finalize helper core
dependencies: []
requirement_refs:
- C-001
- C-003
- C-004
- C-005
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- NFR-001
- NFR-002
- NFR-003
tracker_refs: []
planning_base_branch: feat/finalize-inbox-file
merge_target_branch: feat/finalize-inbox-file
branch_strategy: Planning artifacts for this mission were generated on feat/finalize-inbox-file. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/finalize-inbox-file unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Foundation
assignee: ''
agent: claude
history:
- at: '2026-06-24T20:35:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/inbox/finalize_inbox_file.py
create_intent:
- scripts/inbox/finalize_inbox_file.py
execution_mode: code_change
model: ''
owned_files:
- scripts/inbox/finalize_inbox_file.py
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP01 – Finalize helper core

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter (`python-pedro`), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match.

---

## Objectives & Success Criteria

Deliver `scripts/inbox/finalize_inbox_file.py`: a deterministic, atomic-per-step,
idempotent helper that finalizes one routed inbox file and reports its outcome via
exit code + single-line JSON stdout.

Done when:

- The helper performs, in order: validate → set `status: processed` → move to the
  processed dir → append a daily-log line, each step idempotence-guarded.
- Exit codes: `0` success/already-finalized; `1` validation failure; `2`
  filesystem failure (specific `OSError` on stderr).
- On success, stdout is a single-line JSON object
  `{"finalized": true, "steps_executed": [...], "file_final_path": "..."}`.
- No partially-written or partially-moved file is ever observable.
- WP02's suite (8 scenarios) passes against this helper.

## Context & Constraints

- Spec: `kitty-specs/finalize-inbox-file-01KVXNDC/spec.md` (FR/NFR/C).
- Plan: `kitty-specs/finalize-inbox-file-01KVXNDC/plan.md`.
- Research decisions: `kitty-specs/finalize-inbox-file-01KVXNDC/research.md` (D-01…D-07).
- Data model + invariants: `kitty-specs/finalize-inbox-file-01KVXNDC/data-model.md`.
- CLI contract: `kitty-specs/finalize-inbox-file-01KVXNDC/contracts/finalize_inbox_file.cli.md`.
- **Pattern reference (read before coding)**: `scripts/inbox/prescan.py` — copy its
  registry-path resolution (`scripts/vault/paths.json` via
  `Path(__file__).resolve().parent.parent / "vault" / "paths.json"`, with the
  same env override), its `yaml.safe_load`-only frontmatter parsing, its
  temp-file+fsync+rename atomic-write helper, and its single-line JSON stdout.
- **Existing primitives to reuse, not duplicate** (D-01): `scripts/inbox/mark_processed.py`
  (frontmatter status), `scripts/inbox/routing_log.py` / `append_routing_entry.py`
  (daily-log append). Import their core functions where their public surface
  supports an idempotence pre-check; only reimplement when it genuinely doesn't.
- Constraints: no hardcoded vault paths (C-001); UTC log date (C-003); atomic
  rename, no cross-FS copy fallback (C-004, NFR-001); stdout shape matches
  prescan (C-005).

## Branch Strategy

- **Strategy**: Current branch at workflow start: `feat/finalize-inbox-file`.
  Planning/base branch: `feat/finalize-inbox-file`. Completed changes merge into
  `feat/finalize-inbox-file`.
- Execution worktree is allocated per computed lane from `lanes.json` at
  `/spec-kitty.implement`; trust the path it prints; do not hand-create worktrees.

## Subtasks & Detailed Guidance

### T001 — Vault-path resolution + input validation
- **Purpose**: Establish roots and reject bad input before any mutation (FR-002, C-001).
- **Steps**:
  1. Resolve inbox root + processed dir from `scripts/vault/paths.json` using the
     prescan loader pattern; honor the same registry-path env override so tests
     can point at a tmp vault.
  2. Accept positional `<inbox_file_path>` and optional `--routed-by <agent-id>`
     (argparse).
  3. Validate: path exists; resolves under the inbox root (use resolved/realpath
     comparison); frontmatter present and parseable via `yaml.safe_load`.
  4. Any validation failure → exit `1` with a clear stderr message.
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: bad path, outside-root, missing/unparseable frontmatter each
  return exit 1.

### T002 — Atomic frontmatter status write (idempotent)
- **Purpose**: Set `status: processed` atomically; no-op if already set (FR-003, NFR-001).
- **Steps**:
  1. If frontmatter `status` already `processed`, skip (record nothing in
     `steps_executed`).
  2. Otherwise rewrite frontmatter via temp-file-in-same-dir + `fsync` +
     `os.replace`, preserving all other frontmatter keys and body verbatim.
  3. Prefer `mark_processed.py`'s core if it supports this cleanly.
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: status becomes `processed`; re-run is a no-op; partial write
  never observable.

### T003 — Atomic move + cross-FS rejection (idempotent)
- **Purpose**: Move to processed dir atomically; reject cross-FS (FR-004, C-004, NFR-001).
- **Steps**:
  1. If a file of the same basename already exists in the processed dir, treat
     move as done (no-op).
  2. Otherwise `os.rename(src, dst)`. Let `OSError` (incl. `EXDEV`) propagate to
     the exit-2 handler — never fall back to copy+unlink.
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: file ends in processed dir; re-run no-op; cross-FS → exit 2.

### T004 — Daily-log append + bootstrap (idempotent)
- **Purpose**: Append one line to today's UTC log, creating it if absent (FR-005, FR-006, C-003).
- **Steps**:
  1. Compute `inbox-processing-<YYYY-MM-DD>.md` from UTC date in the processed dir.
  2. Create with standard frontmatter if absent (match existing processing-log
     convention / `routing_log.py`).
  3. If a line for this basename already exists in today's log, skip (no-op).
  4. Else append `filename | routed_by | finalized_at_utc`.
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: exactly one line per file per day across repeated runs.

### T005 — Orchestration: exit codes + JSON stdout
- **Purpose**: Wire the steps; classify outcomes (FR-001, FR-007, FR-008, FR-009, NFR-002, NFR-003, C-005).
- **Steps**:
  1. Run steps in order; each preceded by its idempotence check (partial recovery).
  2. Catch validation errors → exit 1; `OSError`/filesystem → exit 2 with the
     specific message on stderr.
  3. On success print one-line JSON `{"finalized": true, "steps_executed": [...],
     "file_final_path": "..."}` and exit 0 (including the fully-idempotent re-run,
     where `steps_executed` is empty but `finalized` is `true`).
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: outcome deterministically derivable from exit code + stdout/stderr.

### T006 — Reconcile/reuse existing inbox primitives
- **Purpose**: Avoid behavior drift (D-01, DIRECTIVE_001).
- **Steps**:
  1. Audit `mark_processed.py`, `routing_log.py`, `append_routing_entry.py` for
     reusable cores; import rather than reimplement where clean.
  2. Where reuse isn't clean, leave a one-line code comment explaining why the
     helper owns that step.
- **Files**: `scripts/inbox/finalize_inbox_file.py`.
- **Validation**: no duplicated status/log logic that could diverge from the
  primitives' existing tested behavior.

## Definition of Done

- [ ] Helper implements all six subtasks and the CLI contract exactly.
- [ ] Exit codes + JSON stdout match `contracts/finalize_inbox_file.cli.md`.
- [ ] Atomic writes/move; no cross-FS copy fallback.
- [ ] Idempotent across repeated invocations.
- [ ] Reuses existing primitives where clean; reconciliation noted.
- [ ] `python3 -m py_compile` clean; ruff/mypy clean if configured.

## Risks

- Idempotence checks must be race-tolerant (basename presence in processed dir /
  today's log).
- `os.replace` vs `os.rename` semantics for the in-place frontmatter rewrite.
- Reuse vs reimplement of primitives — keep one source of truth per step.

## Reviewer Guidance

- Verify atomicity (temp+rename; `os.rename`) and the absence of any copy
  fallback. Verify each step's idempotence pre-check. Verify exit-code mapping and
  the exact JSON keys. Confirm no hardcoded vault paths.
