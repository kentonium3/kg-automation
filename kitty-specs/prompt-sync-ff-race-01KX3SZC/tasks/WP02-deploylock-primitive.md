---
work_package_id: WP02
title: deploylock primitive — actor-level advisory flock
dependencies: []
requirement_refs:
- FR-002
- NFR-002
tracker_refs: []
planning_base_branch: fix/prompt-sync-ff-race
merge_target_branch: fix/prompt-sync-ff-race
branch_strategy: Planning artifacts for this mission were generated on fix/prompt-sync-ff-race. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/prompt-sync-ff-race unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent:
- scripts/deploy/lib/deploylock.py
- tests/deploy/test_deploylock.py
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- scripts/deploy/lib/deploylock.py
- tests/deploy/test_deploylock.py
role: implementer
tags: []
---

# WP02 — deploylock primitive

## ⚡ Do This First: Load Agent Profile
Load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Objective
Create `scripts/deploy/lib/deploylock.py`: a **standalone** advisory-file-lock
context manager that both deploy actors wrap around their **entire** checkout-
mutating critical section. This is the Codex CRITICAL correction — the lock is
NOT embedded inside `advance_checkout`; it must be held across felix-deployer's
post-pull commit/push/stamp/watermark phase too.

## Context (read first)
- **Contract (authoritative)**: [../contracts/lib-api.md](../contracts/lib-api.md) — `deploylock()` + `LockUnavailable` + `DEFAULT_LOCK_PATH`.
- **Research D2**: [../research.md](../research.md) — actor-level scope rationale, non-blocking + defer.
- **Data model**: [../data-model.md](../data-model.md) — DeployLock aspect table.

## Subtasks

### T005 — `deploylock` context manager
- `class LockUnavailable(RuntimeError)`.
- `DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")`.
- `@contextmanager def deploylock(path: Path | None = None, timeout_s: float = 5.0)`:
  - Resolve path: explicit arg → env `DEPLOY_CHECKOUT_LOCK` → `DEFAULT_LOCK_PATH`.
  - Create the parent dir if missing (`mkdir(parents=True, exist_ok=True)`).
  - Open the lock file; `fcntl.flock(fd, LOCK_EX | LOCK_NB)` with a bounded retry
    loop (short sleeps) up to `timeout_s`; on continued failure raise
    `LockUnavailable`.
  - Release on exit (flock LOCK_UN + close); OS auto-releases if the process dies.
- Keep it dependency-free (stdlib `fcntl`, `os`, `time`, `contextlib`, `pathlib`).

### T006 — tests (`tests/deploy/test_deploylock.py`)
- Acquire then release; re-acquire succeeds after release.
- Second concurrent holder (separate fd/process or a pre-held flock) → the
  contending `deploylock(timeout_s=small)` raises `LockUnavailable` within ~timeout.
- Path resolution precedence (arg > env > default); parent-dir creation.
- Lock released on normal exit AND on exception inside the context.
- Use a tmp lock path (set `DEPLOY_CHECKOUT_LOCK` or pass `path=`); never touch the real `/data` path in tests.

## Definition of Done
- `deploylock.py` matches the contract; `python3 -m pytest tests/deploy/test_deploylock.py` green.
- Non-blocking + bounded-timeout; raises `LockUnavailable` (never hangs a tick indefinitely).
- Full `tests/deploy/` suite green.

## Reviewer guidance
Verify `LOCK_NB` (non-blocking) + bounded retry (no unbounded block), correct
path-resolution precedence, guaranteed release on exception, and that tests use a
temp path (not `/data`).

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.
