---
work_package_id: WP03
title: Route escalation + enrichment consumers through the token seam
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- NFR-001
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
phase: Phase 1 - Consumers
history: []
agent_profile: python-pedro
authoritative_surface: scripts/escalation/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/escalation/record_completion.py
- scripts/escalation/reconcile_completions.py
- scripts/enrichment/record_completion.py
- scripts/enrichment/reconcile_completions.py
- tests/escalation/test_record_completion.py
- tests/escalation/test_reconcile_completions.py
- tests/enrichment/test_record_completion.py
- tests/enrichment/test_reconcile_completions.py
role: implementer
tags: []
---

# Work Package Prompt: WP03 — Escalation + enrichment consumers

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Route the escalation + enrichment completion consumers through WP01's `get_vikunja_token_path()`.
**These four modules were missed in the first inventory and caught by the post-plan Codex review** —
leaving them on their own felix-bot literal would have been a silent split-brain (some consumers kent,
these still felix-bot). Behavior-preserving (NFR-001): only the token-path source changes.

## Subtasks

### T006 — escalation
- `scripts/escalation/record_completion.py:111` and `scripts/escalation/reconcile_completions.py:136`
  define `DEFAULT_TOKEN_PATH = Path(".../vikunja-api")`. Re-point the `--token-path` default to
  `get_vikunja_token_path()` (`from scripts.common.vikunja_config import get_vikunja_token_path`).
- Preserve `_read_token()` behavior/error shape and the `VikunjaClient(..., token=token, ...)` calls.

### T007 — enrichment
- Same for `scripts/enrichment/record_completion.py:118` and `scripts/enrichment/reconcile_completions.py`
  (imports the constant). Re-point the default to the helper; preserve behavior.

### T008 — tests green
- Update any test pinning the old literal; `python3 -m pytest tests/escalation/ tests/enrichment/ -q` green.
- Confirm `git grep -nE "secrets/vikunja-api([^-]|$)" -- scripts/escalation scripts/enrichment ':!**/__pycache__/**'`
  returns no match in these 4 files.

## Definition of Done
- All 4 modules resolve their default token via `get_vikunja_token_path()`; no felix-bot literal remains.
- Behavior unchanged vs HEAD; escalation + enrichment suites green.

## Reviewer guidance
- Diff should be import + constant-default only per file. Verify `_read_token`/error semantics and the
  reschedule/PATCH + comment flows are untouched.
