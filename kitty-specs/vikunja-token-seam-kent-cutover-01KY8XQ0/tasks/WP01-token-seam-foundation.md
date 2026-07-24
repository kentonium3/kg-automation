---
work_package_id: WP01
title: Token seam foundation (config helper + client routing + flip proof)
dependencies: []
requirement_refs:
- FR-001
- FR-003
- NFR-002
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
phase: Phase 0 - Foundation
history: []
agent_profile: python-pedro
authoritative_surface: scripts/common/
create_intent:
- tests/common/test_vikunja_config.py
- tests/common/test_vikunja_token_seam.py
execution_mode: code_change
owned_files:
- scripts/common/vikunja_config.py
- scripts/common/vikunja_client.py
- tests/common/test_vikunja_config.py
- tests/common/test_vikunja_client.py
- tests/common/test_vikunja_token_seam.py
role: implementer
tags: []
agent: "claude"
shell_pid: "65348"
shell_pid_created_at: "1784863132.600278"
---

# Work Package Prompt: WP01 — Token seam foundation

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/vikunja-token-seam-kent-cutover`
- **Final merge target**: `feat/vikunja-token-seam-kent-cutover`
- `/spec-kitty.implement` populates the actual worktree `base_branch`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Create the **single Vikunja token-resolution point** and route `VikunjaClient` through it. This is
the foundation the other 7 WPs depend on. It is the corrective for #860 Phase 1, which left token
resolution split across N sites. Mirror the existing `get_vikunja_base_url()` seam in the same file.

**The default resolves to the KENT token** (`/data/services/openclaw/secrets/vikunja-api-kent`) — the
mission end-state. The felix-bot→kent *runtime* transition is inert until merge→office2 pull (the
attended cutover); unit tests mock HTTP, so the token value does not change test outcomes here.

## Subtasks

### T001 — `get_vikunja_token_path()` in `scripts/common/vikunja_config.py`
- Add `get_vikunja_token_path() -> pathlib.Path`, mirroring `get_vikunja_base_url()` in the same file.
- Resolution order: (1) `VIKUNJA_TOKEN_PATH` env var if set & non-empty; (2) module default constant
  `Path("/data/services/openclaw/secrets/vikunja-api-kent")`.
- Fail-loud (NFR-002): if the *resolved* file is missing/unreadable, raise a single typed error
  (reuse/extend `VikunjaConfigError`) naming both the env var and the resolved path. No silent fallback.
- Export it in `__all__`.

### T002 — Route `VikunjaClient` default-token load through the helper (`scripts/common/vikunja_client.py`)
- `VikunjaClient._load_default_token()` MUST call `get_vikunja_token_path()` **at call time** (not
  import time) and read that path. Do not keep the standalone felix-bot `DEFAULT_TOKEN_PATH` literal
  as the source of truth.
- Keep the module-level `DEFAULT_TOKEN_PATH` name only if other code imports it — and if kept, define it
  as `get_vikunja_token_path()` (or clearly deprecate). Grep `git grep -n "vikunja_client import" -- scripts tests`
  for importers before deciding; do not break them.
- Preserve the existing typed error surface (`VikunjaError` family) and redaction policy.

### T003 — Tests
- `tests/common/test_vikunja_config.py`: env override wins; default is the kent path; missing/unreadable
  file → the typed fail-loud error (NFR-002).
- `tests/common/test_vikunja_client.py`: update for helper-based resolution; default load reads the helper
  path; fail-loud parity.
- **`tests/common/test_vikunja_token_seam.py` (NEW — SC-002 single-point-flip proof)**: setting
  `VIKUNJA_TOKEN_PATH` to an arbitrary path changes what `get_vikunja_token_path()` and a default
  `VikunjaClient()` resolve — proving one lever moves the shared default. Also assert the negative:
  `intake/apply_reply.py`'s kent-pinned path does **not** follow the override toward felix-bot (import
  its token constant / resolver and assert it stays the kent file) — documenting the intentional exception.

## Definition of Done
- `get_vikunja_token_path()` exists, is the sole default token-path source, defaults to the kent path,
  fails loud on a bad path.
- `VikunjaClient` default-token loading resolves through it; no importer broken.
- All three test files green; `python3 -m pytest tests/common/ -q` passes.
- No abstract `TaskService` port introduced (C-001).

## Reviewer guidance
- Confirm resolution is **call-time**, not import-time (else env overrides + tests break).
- Confirm the fail-loud path is single-sourced (NFR-002) and the redaction policy is intact.
- Confirm SC-002 test actually proves the single-point property (one lever moves the default) AND the
  apply_reply-stays-kent negative assertion is present.

## Activity Log

- 2026-07-24T03:19:06Z – claude – shell_pid=65348 – Assigned agent via action command
