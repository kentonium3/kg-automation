---
work_package_id: WP02
title: Pending-token rebaseline engine
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-004
- FR-005
- FR-007
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
- T008
agent: claude
shell_pid: '95679'
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/rebaseline.py
create_intent:
- scripts/deploy/felix-deployer/rebaseline.py
- tests/deploy/test_rebaseline.py
execution_mode: code_change
owned_files:
- scripts/deploy/felix-deployer/rebaseline.py
- tests/deploy/test_rebaseline.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity,
governance scope, and boundaries before reading further.

## Objective

Implement the **deferred-confirm rebaseline engine** as a new module
`scripts/deploy/felix-deployer/rebaseline.py`. Pure logic + filesystem/audit
side-effects, with all subprocess/audit calls injectable for testing. WP03 wires
it into the tick.

Read first: `../contracts/rebaseline-lifecycle-v1.md` (the behavioral contract —
C1–C5), `../data-model.md` (token schema + drift classification), `../research.md`
(R2 timing model, R5 execution context), `../spec.md` (FR-002/004/005/007/008/009).

## Context

felix-deployer runs on office2 as `claude`. The engine never crashes the tick;
failures are observability events. It imports the shared matcher from WP01
(`tooling/scripts/audited_surfaces.py`). Audit/rebaseline commands run locally
via `sg docker -c <audit.sh>` (no sudo, no SSH). `expected_baseline_count` comes
from the registry, never hardcoded.

**Probe first (DIRECTIVE_031):** before implementing T006/T007, confirm on
office2 that `audit.sh` run *with baselines present* is a non-destructive drift
check, distinct from the `rm baselines/* && audit.sh` regenerate path, and that
the regenerate path restores `count == expected_baseline_count`. Record the
finding in the WP. Tests mock the audit invocation.

## Subtasks

### T004 — Pending-token store (atomic)
`/data/services/felix-deployer/state/rebaseline-pending.json` per data-model.md
(schema_version, pending_since_utc, observed_head_sha, surface_ids,
expected_baselines, matched_files, last_check_utc, alerts_emitted). Functions:
`read_token()`, `write_token()` (atomic `.tmp`+`os.replace`), `clear_token()`.
Absent file = nothing pending. Make the state dir + path injectable (default
constants) so tests use tmp paths.

### T005 — Observe
`observe(pre_pull_head, post_pull_head, ...)`: if equal, no-op. Else compute
changed paths via `git diff --name-only <pre>..<post>` (injectable runner), run
WP01 `match_surfaces`. If matches: merge into the token — union new `surface_ids`
and `expected_baselines` (union of matched surfaces' `affected_baselines`), keep
earliest `pending_since_utc`, refresh `matched_files`. Return an outcome enum
(`pending_set` / `not_required`).

### T006 — Reconcile (classification core)
`reconcile(...)`: if no token, no-op. Else run the read-only audit (injectable;
`sg docker -c <audit.sh>` with baselines present) and parse the drifted-baseline
set `D`. Let `E = token.expected_baselines`. Classify per data-model.md:
`D == ∅` → `cleared_clean` (clear token); `D ⊆ E and D ≠ ∅` → call T007 rebaseline;
`D ⊄ E` → `unexpected_drift` (do NOT reset; signal WP03 to alert; leave token — FR-009).
Parsing the audit output into `D` must be tolerant — if it can't parse, treat as
inconclusive (leave token, no reset) rather than guessing.

### T007 — Rebaseline + verify
`rebaseline_and_verify(...)`: run `rm <baselines>/* && sg docker -c <audit.sh>`
(the documented command from `audited-surfaces.json.rebaseline_command`). Then
verify regenerated baseline count == `registry.expected_baseline_count` AND the
audit reports clear. Success → `completed` (clear token, return
rebaselined_at_utc + count). Failure → `failed` (leave token, return
error_summary; WP03 alerts). Never raises to the caller — returns an outcome.

### T008 — Unit tests `tests/deploy/test_rebaseline.py`
Mock git/audit/filesystem. Cover: token read/write/clear round-trip + atomicity;
observe set/merge/not_required; reconcile `cleared_clean` (D=∅), `completed`
(D⊆E), `failed` (count mismatch / audit not clear), `unexpected_drift` (D⊄E,
no reset), inconclusive parse (leave token); stale-age handling input.

## Branch Strategy
Planning base `main`; merge target `main`; lane worktree at implement time.
WP02 depends on WP01 — its lane includes WP01's `audited_surfaces.py`.

## Definition of Done
- `rebaseline.py` implements observe/reconcile/rebaseline_and_verify + token store
  per the C1–C5 contract; all side-effects injectable; never raises to caller.
- `pytest tests/deploy/test_rebaseline.py` passes for every classification +
  failure + stale branch.
- `expected_baseline_count` read from the registry, not hardcoded.

## Risks / Reviewer guidance
- The expected-vs-unexpected drift split is the safety boundary — review T006
  classification against data-model.md `D⊆E`/`D=∅`/`D⊄E` exactly.
- Atomic token writes (`.tmp`+`os.replace`); no partial token on crash.
- Verify the office2 audit-invocation probe result is recorded (DIRECTIVE_031).
