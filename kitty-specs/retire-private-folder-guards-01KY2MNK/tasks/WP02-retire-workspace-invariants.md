---
work_package_id: WP02
title: Retire the workspace-validator privacy invariants
dependencies: []
requirement_refs:
- FR-002
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
agent: "claude:sonnet:implementer:implementer"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/validate_workspace.py
- scripts/openclaw/agents/tests/test_validate_workspace.py
- tests/openclaw/test_privacy_pointer.py
- docs/design/openclaw-workspace-authoring-standard.md
role: implementer
tags: []
shell_pid: "22263"
shell_pid_created_at: "1784651109.595756"
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load implementer-ivan` before anything else.

## Objective

Stop `validate_workspace` from forcing a `_private` red-line into every agent prompt. Remove the two
privacy invariants + their exclusive constants + the registry-tie pointer test + the authoring-
standard requirement. Authoritative detail: `data-model.md` IC-02 rows; FR-002. **This WP must land
before WP04** (which strips the red-line from prompts) so validation accepts a prompt without it.

## Context

`validate_workspace.py` enforces **Invariant A** (`check_privacy_boundary` — a red-line must be
present in an owner file) and **Invariant D** (`check_privacy_path_canonical` — HOME-prefixed privacy
path must be physical `/home/kgale/...`). Both exist only to police the `_private` rule.

## Subtasks

- **T006** — `scripts/openclaw/agents/validate_workspace.py`: remove `check_privacy_boundary` and
  `check_privacy_path_canonical`, the constants `PRIVACY_TOKEN` / `CANONICAL_PRIVATE_PATH` /
  `NONCANONICAL_PRIVATE_TOKEN`, the privacy owner-set config, and their entries in the checks list
  returned by the runner. **Leave every OTHER invariant intact** (output-discipline, staleness, byte
  budgets, etc.). Remove now-unused imports.
- **T007** — `scripts/openclaw/agents/tests/test_validate_workspace.py`: remove the test cases that
  assert the privacy invariants (A and D) and the removed constants; keep all other validator tests.
- **T008** — Delete `tests/openclaw/test_privacy_pointer.py` (ties `PRIVACY_TOKEN` to the vault
  registry — moot once the token is gone).
- **T009** — `docs/design/openclaw-workspace-authoring-standard.md`: remove the authoring requirement
  that "every agent prompt must carry the enforceable privacy red-line" (this pairs with the invariant
  removal). Reframe any residual mention to the physical-exclusion model or delete it.

## Definition of Done

- `pytest scripts/openclaw/agents/tests/test_validate_workspace.py -q` passes with the privacy checks
  gone and all other invariants still enforced.
- `grep -rn "PRIVACY_TOKEN\|check_privacy_boundary\|check_privacy_path_canonical\|CANONICAL_PRIVATE_PATH\|NONCANONICAL_PRIVATE_TOKEN" scripts/ tests/` returns zero hits.
- `tests/openclaw/test_privacy_pointer.py` no longer exists.
- The authoring standard no longer requires a privacy red-line in prompts.

## Risks & reviewer guidance

- Do NOT weaken other invariants — excise ONLY the two privacy checks + their exclusive constants.
- Reviewer: confirm `validate_workspace` still runs and reports its remaining invariants, and that no
  other module imports the removed constants (grep the repo).

## Activity Log

- 2026-07-21T16:25:44Z – claude:sonnet:implementer:implementer – shell_pid=22263 – Assigned agent via action command
