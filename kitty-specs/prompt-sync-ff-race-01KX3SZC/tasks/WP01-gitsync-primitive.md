---
work_package_id: WP01
title: gitsync primitive — race-immune advance_checkout + AdvanceResult
dependencies: []
requirement_refs:
- FR-001
- FR-005
- FR-006
- NFR-001
- NFR-004
tracker_refs: []
planning_base_branch: fix/prompt-sync-ff-race
merge_target_branch: fix/prompt-sync-ff-race
branch_strategy: Planning artifacts for this mission were generated on fix/prompt-sync-ff-race. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/prompt-sync-ff-race unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent:
- scripts/deploy/lib/gitsync.py
- tests/deploy/test_gitsync.py
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- scripts/deploy/lib/gitsync.py
- tests/deploy/test_gitsync.py
role: implementer
tags: []
shell_pid: "64625"
---

# WP01 — gitsync primitive (race-immune advance)

## ⚡ Do This First: Load Agent Profile
Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries, and Python discipline for this WP.

## Objective
Create `scripts/deploy/lib/gitsync.py` providing the **race-immune fast-forward**
that structurally eliminates the `Cannot fast-forward to multiple branches`
failure (#667): fetch, then merge the atomic remote-tracking **ref**
`origin/main` — never `.git/FETCH_HEAD`. This is the foundation both deploy
actors will call.

## Context (read first)
- **Contract (authoritative)**: [../contracts/lib-api.md](../contracts/lib-api.md) — `advance_checkout()` step-by-step contract + `AdvanceResult` fields.
- **Research D1**: [../research.md](../research.md) — why ref-merge is race-immune; corrected divergence logic.
- **Data model**: [../data-model.md](../data-model.md) — `AdvanceResult` invariants.
- **Existing seams to mirror**: `scripts/deploy/felix-deployer/_tick.py:_git` (thin git wrapper) and `scripts/openclaw/deploy/deploy_agent_prompts.py:git_pull`.
- office2 is python3-only; module imports use `python3 -m scripts.<pkg>.<mod>`.

## Subtasks

### T001 — `AdvanceResult` frozen dataclass
Define `@dataclass(frozen=True) class AdvanceResult` with exactly the fields in
data-model.md: `ok, advanced, pre_head, post_head, origin_head, behind, ahead,
diverged, reason=None, stderr=""`. Honor the invariants (`ok` False iff `reason`
set; `diverged ⇒ not advanced and reason=="diverged"`).

### T002 — `advance_checkout()`
Implement per the contract:
1. `assume_locked: bool = False`. When False, acquire `deploylock` (import from
   the sibling module — but **do not** implement deploylock here; WP02 owns it;
   import lazily so tests can run without the lock). When True, run inside the
   caller's already-held lock.
2. `git fetch <remote> <branch>` → on non-zero: `ok=False, reason="fetch_failed"`.
3. `behind = rev-list --count HEAD..<remote>/<branch>`; `ahead = rev-list --count <remote>/<branch>..HEAD`.
4. `behind == 0` → clean no-op (`ok=True, advanced=False`) regardless of `ahead`.
5. `behind > 0 AND ahead > 0` → `diverged=True, ok=False, reason="diverged"`; DO NOT merge.
6. else `git merge --ff-only <remote>/<branch>` (NEVER FETCH_HEAD) → non-zero: `reason="merge_failed"`; success: `advanced=True`.
7. Populate `pre_head/post_head/origin_head` as short SHAs; truncate stderr ≤200.
Accept a `git_runner` callable seam (default: a `subprocess.run(["git",...])`
wrapper) so tests mock git. Never raise into the caller for expected git failures.

### T003 — unit tests (`tests/deploy/test_gitsync.py`)
Cover, with a mocked `git_runner` and/or a real temp git repo:
- `git fetch origin main` updates `refs/remotes/origin/main` (real temp repo) and the merge target is `origin/main`, never FETCH_HEAD (assert the merge argv).
- fast-forward path advances HEAD; `advanced=True`.
- already-current → `ok=True, advanced=False, behind==0`.
- **ahead-only** (`ahead>0, behind==0`) → clean no-op, NOT diverged.
- **diverged** (`behind>0, ahead>0`) → `diverged=True, reason="diverged"`, no merge attempted.
- `fetch_failed` / `merge_failed` reason mapping; stderr truncation.

### T004 — primitive concurrency test
With a real temp git repo + remote, run N (≥20) concurrent `advance_checkout()`
(threads/processes) and assert: 0 occurrences of "Cannot fast-forward to multiple
branches", and a consistent final HEAD. (Necessary-not-sufficient; the actor-level
proof is WP06.)

## Definition of Done
- `gitsync.py` implements the contract exactly; `python3 -m pytest tests/deploy/test_gitsync.py` green.
- Merge target is `origin/main` (grep-assertable); FETCH_HEAD never on the merge path.
- Divergence logic matches the corrected rule (behind&ahead only).
- Full `tests/deploy/` suite still green.

## Reviewer guidance
Verify the ref-merge (not FETCH_HEAD), the corrected divergence rule (ahead-only
is a no-op), the `assume_locked` seam, and that no expected git failure raises.
Confirm `AdvanceResult` invariants are enforced.

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Activity Log

- 2026-07-09T16:46:22Z – claude – shell_pid=45836 – Assigned agent via action command
- 2026-07-09T16:57:44Z – claude – shell_pid=45836 – gitsync green (13 passed; full deploy suite 384)
- 2026-07-09T16:57:48Z – claude – shell_pid=64625 – Started review via action command
- 2026-07-09T16:58:15Z – user – shell_pid=64625 – Review passed: ref-merge (origin/main, never FETCH_HEAD), corrected divergence logic, lazy-guarded lock seam, frozen invariants; 13 tests + full deploy suite (384) green
