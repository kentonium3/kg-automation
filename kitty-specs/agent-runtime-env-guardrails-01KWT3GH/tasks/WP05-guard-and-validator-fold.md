---
work_package_id: WP05
title: Test-CI fleet guard + validate_workspace fold + doc-auditor disposition
dependencies:
- WP02
- WP03
- WP04
requirement_refs:
- FR-003
- FR-004
- FR-008
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
- T021
- T022
agent: "claude"
shell_pid: "14634"
history:
- 2026-07-05 authored from plan IC-02/IC-03/IC-05 (guard + fold + doc-auditor disposition)
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/agents/tests/test_env_assumptions_guard.py
create_intent:
- scripts/openclaw/agents/tests/test_env_assumptions_guard.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/tests/test_env_assumptions_guard.py
- scripts/openclaw/agents/validate_workspace.py
- scripts/openclaw/agents/tests/test_validate_workspace.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile
Run `/ad-hoc-profile-load python-pedro` (role: implementer). Then read this WP.

## Objective
Add the Test-CI fleet guard and fold the checker into the workspace validator. This WP depends
on WP02-04: the fleet guard is GREEN only after the fleet is converted. Read
`../contracts/checker-contract.md` (both consumers) and the existing `validate_workspace.py`.

## Subtasks
- **T019 — fleet guard** (`tests/test_env_assumptions_guard.py`): `test_fleet_has_no_env_assumptions()`
  calls `env_assumptions.scan_agents_root(_default_root())` and asserts no non-waived Findings;
  on failure, the assert message enumerates each `path:line kind — remediation` (NFR-004). Keep
  it deterministic and < 5 s (NFR-002). This test is collected by the existing Test CI (it lives
  in `scripts/openclaw/agents/tests/`) — **no `.github/workflows/` change** (C-001, FR-003).
- **T020 — validator fold** (`validate_workspace.py`): add
  `check_runtime_env_assumptions(workspace_dir) -> CheckResult` that runs `scan_file` over the
  workspace's prompt files and returns `CheckResult(name="runtime_env_assumptions", ok=not findings, detail=…)`.
  **The dataclass field is `ok`, NOT `passed`** (Codex MED-3). Append it to the `checks` list in
  `validate_workspace()` beside `check_privacy_boundary`/`check_output_discipline` — do NOT
  regress those. `--json` exit status reflects the new check.
- **T021 — doc-auditor disposition** (Codex MED-5): record that `felix-doc-auditor` is a retired
  scripts-first driver (no live agent, in `validate_workspace.EXCLUDED`) — an explicit disposition,
  not an active audit. A short note in the validator's EXCLUDED comment (or a disposition line in
  the WP06 docs) suffices; the point is the exclusion is intentional and documented.
- **T022 — validator tests** (`tests/test_validate_workspace.py`): extend for the new check — a
  workspace with a bare/hardcoded invocation fails `runtime_env_assumptions`; a clean one passes;
  the existing privacy/output-discipline tests still pass. Run the FULL guard + validator green.

## Branch Strategy
Base/merge: `feat/agent-runtime-env-guardrails`. Lane worktree from `lanes.json`. This lane
rebases on the converted fleet (WP02-04) — the guard cannot be green before those land.

## Definition of Done
- `pytest scripts/openclaw/agents/tests/` all green (fleet guard + checker units + validator).
- `validate_workspace.py --json` includes `runtime_env_assumptions` and exits non-zero on a
  violating workspace; privacy/output-discipline checks unregressed.
- doc-auditor disposition recorded.

## Reviewer guidance
- Confirm the guard uses `.ok` (not `.passed`) and the CheckResult contract is intact (MED-3).
- Confirm the guard actually scans the WHOLE fleet and is green ONLY because WP02-04 converted it
  (temporarily revert one converted line in a scratch check → guard should go red).
- Confirm no `.github/workflows/` change; test lives in the existing collected tests dir.

## Activity Log

- 2026-07-05T22:40:23Z – claude – shell_pid=11765 – Assigned agent via action command
- 2026-07-05T22:48:40Z – claude – shell_pid=14634 – Assigned agent via action command
