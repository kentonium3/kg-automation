---
work_package_id: WP04
title: Route sync + credential-health through the token seam (preserve sync failure classification)
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
- T009
- T010
- T011
phase: Phase 1 - Consumers
history: []
agent_profile: python-pedro
authoritative_surface: scripts/sync/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/sync/cycle.py
- scripts/sync/fetch.py
- scripts/security/credential_health_check/vikunja_writer.py
- tests/sync/test_cycle.py
- tests/sync/test_fetch.py
- tests/security/test_vikunja_writer.py
role: implementer
tags: []
agent: "claude"
shell_pid: "72212"
shell_pid_created_at: "1784864197.958657"
---

# Work Package Prompt: WP04 — Sync + credential-health consumers

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Route sync + the credential-health writer through WP01's `get_vikunja_token_path()`. **Sync is the
highest-care consumer** (bidirectional; the token identity determines which user's tasks it reconciles).
Behavior-preserving (NFR-001), with one explicit invariant to protect: sync's failure classification.

## Subtasks

### T009 — sync token resolution + **preserve failure classification**
- `scripts/sync/cycle.py` resolves the token via `config.secrets_dir / "vikunja-api"` (lines ~143, ~427)
  and `scripts/sync/fetch.py` receives the token. Re-point token resolution to `get_vikunja_token_path()`.
- **CRITICAL (Codex MED):** `run_cycle()`'s preamble currently catches only `OSError` and records
  `phase="preamble"`, `exit_code=1` with the existing `cycle_error` token (`cycle.py:141-157`). The
  helper's fail-loud error may be a non-`OSError` typed exception. **Adapt it into the existing preamble
  path** so a token-resolution/read failure still yields the same `phase`, `exit_code`, and `cycle_error`
  classification as HEAD. Do not let a token failure change sync's error taxonomy.
- Preserve `fetch_full_poll()`'s enumeration/pagination unchanged.

### T010 — credential-health writer
- `scripts/security/credential_health_check/vikunja_writer.py:35` (`VIKUNJA_TOKEN_PATH = .../vikunja-api`)
  → resolve via `get_vikunja_token_path()`. Preserve the writer's behavior + redaction.

### T011 — tests incl. failure-classification parity
- `tests/sync/test_cycle.py`, `tests/sync/test_fetch.py`, `tests/security/test_vikunja_writer.py` green.
- Add/extend a test proving a token-path failure is still classified as the preamble `cycle_error`
  (same phase + exit_code=1) — the NFR-001 sync invariant.

## Definition of Done
- Sync + credential-health resolve the token via the helper; no felix-bot literal remains in them.
- Sync failure classification is provably unchanged; sync + credential-health suites green.

## Reviewer guidance
- Focus on the failure path: confirm the helper's typed error is caught and re-mapped into the existing
  preamble outcome (phase/exit_code/cycle_error identical to HEAD). Confirm `fetch` pagination untouched.

## Activity Log

- 2026-07-24T03:37:26Z – claude – shell_pid=72212 – Assigned agent via action command
