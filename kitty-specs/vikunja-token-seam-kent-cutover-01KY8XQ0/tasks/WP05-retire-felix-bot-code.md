---
work_package_id: WP05
title: Retire felix-bot code path (route_someday 403 removal, validator convergence)
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
phase: Phase 2 - Retire
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/inbox/route_someday.py
- scripts/vikunja/validate_refs.py
- tests/inbox/test_route_someday.py
- tests/vikunja/test_validate_refs.py
role: implementer
tags: []
agent: "claude"
shell_pid: "72212"
shell_pid_created_at: "1784864197.958657"
---

# Work Package Prompt: WP05 — Retire felix-bot code path

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Remove the felix-bot-specific fail-soft code that the kent identity makes moot, and converge the #748
drift validator onto the single-source token so declaration and runtime access can't silently diverge
again (the structural blindness that caused #860).

## Subtasks

### T012 — Remove `route_someday` felix-bot 403 fail-soft (#750)
- `scripts/inbox/route_someday.py` uses bare `VikunjaClient()` and carries a fail-soft branch that
  tolerated the felix-bot **403 on kent-label attach** (the #750 two-token symptom). Under the single
  kent token that 403 cannot occur. Remove the fail-soft branch so a genuine attach failure now surfaces
  (fail-loud) rather than being silently swallowed. Update `tests/inbox/test_route_someday.py` accordingly
  (drop the 403-tolerance test; assert the label attach now happens / errors surface).
- Do **not** change route_someday's other behavior (capture routing, q:schedule handling).

### T013 — Converge `validate_refs.py` on the single-source token (#748, FR-005)
- `scripts/vikunja/validate_refs.py:192` builds a `VikunjaClient(token=...)` from its own default. Make its
  default token resolve from the **same single source** as the runtime (`get_vikunja_token_path()`), so the
  validator exercises the runtime view. Keep the explicit `--token`/`--token-file` override for ops use.
- Add/adjust `tests/vikunja/test_validate_refs.py` to prove the validator's default now equals the runtime
  resolution point (no independent literal).

## Definition of Done
- `route_someday` no longer has the felix-bot 403 fail-soft branch; #750 symptom path removed; tests updated.
- `validate_refs` default token = `get_vikunja_token_path()` (single source); validator + runtime share the view.
- `python3 -m pytest tests/inbox/test_route_someday.py tests/vikunja/test_validate_refs.py -q` green.

## Reviewer guidance
- Confirm removing the 403 branch doesn't swallow a *different* real error and that the fail-loud path is sane.
- Confirm the validator can no longer diverge from the runtime token by construction (FR-005).

## Activity Log

- 2026-07-24T03:37:55Z – claude – shell_pid=72212 – Assigned agent via action command
