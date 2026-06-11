---
work_package_id: WP01
title: Test-first deterministic verification helpers
dependencies: []
requirement_refs:
- FR-007
- FR-012
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/tests/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/tests/**
tags: []
agent_profile: python-pedro
role: implementer
agent: claude
---

# Work Package Prompt: WP01 – Test-first deterministic verification helpers

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree and records the lane branch in `base_branch`. Trust the printed lane workspace instead of guessing.

## Objectives & Success Criteria

Per Constitution DIRECTIVE_034, deterministic verification work is authored BEFORE production code. This WP creates the pytest helpers that will assert:

- `main/AGENTS.md` < 12,000 chars (NFR-001)
- `felix-admin-calendar/AGENTS.md` < 12,000 chars (NFR-004)
- `openclaw.json` contains a well-formed `felix-admin-calendar` registry entry with correct workspace + agentDir + model values

**Success criteria**:
- `pytest scripts/openclaw/agents/tests/ -v` runs cleanly.
- Initial state is RED: file-size tests fail (main is 25,982; felix-admin-calendar doesn't exist yet); openclaw-config schema test fails (fixture is a sanitized snapshot that does NOT yet contain felix-admin-calendar).
- WPs 02 and 03 transition these tests to GREEN as they land their respective implementations.

## Context & Constraints

- Mission spec: `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/spec.md` (NFR-001, NFR-004)
- Mission plan: `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/plan.md` (IC-01, IC-02, IC-03)
- Test surface convention: `scripts/openclaw/agents/tests/` (per plan.md). If this is the first pytest tree under `scripts/openclaw/`, ensure pytest discovery isn't shadowed by sibling trees.
- Fixture must contain NO real secrets. The live `~/.openclaw/openclaw.json` on office2 has `gateway.auth.token` in cleartext — replace with `REDACTED` or a placeholder UUID in the fixture.
- Python 3.11 (per plan.md Technical Context).

## Subtasks & Detailed Guidance

### Subtask T001 – Test package skeleton

- **Purpose**: Stand up the pytest discoverable test package under `scripts/openclaw/agents/tests/`.
- **Steps**:
  1. Create `scripts/openclaw/agents/tests/__init__.py` (empty file).
  2. Create `scripts/openclaw/agents/tests/conftest.py` exposing a `repo_root` fixture that resolves to the repository root (use `pathlib.Path(__file__).resolve().parents[N]` — pick the right N so it lands at the kg-automation repo root).
  3. Create `scripts/openclaw/agents/tests/fixtures/` directory.
- **Files**: `scripts/openclaw/agents/tests/{__init__.py,conftest.py,fixtures/}`
- **Parallel?**: No — blocks T002/T003/T004.
- **Notes**: Verify pytest discovers the directory: `pytest --collect-only scripts/openclaw/agents/tests/` should list zero tests (after T001) but no discovery errors.

### Subtask T002 – Sanitized openclaw.json fixture

- **Purpose**: A static fixture that the schema test can validate against. Snapshot the live office2 openclaw.json shape, but redact secrets.
- **Steps**:
  1. Live-probe `ssh office2-claude 'cat /home/claude/.openclaw/openclaw.json'` to get the current schema. (Already captured in plan-phase research; see research.md F-03 for the structure.)
  2. Write `scripts/openclaw/agents/tests/fixtures/openclaw-sample.json` matching the shape: `meta`, `wizard`, `auth`, `agents{defaults, list[5 entries: main + 4 subagents]}`, `tools`, `commands`, `session`, `channels.whatsapp`, `gateway`.
  3. Replace `gateway.auth.token` with the literal string `REDACTED-DO-NOT-USE`.
  4. Replace any other token / secret fields similarly.
- **Files**: `scripts/openclaw/agents/tests/fixtures/openclaw-sample.json`
- **Parallel?**: [P] with T003/T004 after T001 lands.
- **Notes**: The fixture does NOT contain felix-admin-calendar yet — that's a green-state condition that WP02+WP04 establish.

### Subtask T003 – test_agents_md_size.py

- **Purpose**: Assert NFR-001 and NFR-004 thresholds.
- **Steps**:
  1. Create `scripts/openclaw/agents/tests/test_agents_md_size.py` with two test functions:
     ```python
     from pathlib import Path

     CAP = 12_000

     def test_main_agents_md_under_12k(repo_root):
         p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
         assert p.exists(), f"missing: {p}"
         assert p.stat().st_size < CAP, f"main/AGENTS.md {p.stat().st_size} >= {CAP}"

     def test_felix_admin_calendar_agents_md_under_12k(repo_root):
         p = repo_root / "scripts/openclaw/agents/felix-admin-calendar/AGENTS.md"
         assert p.exists(), f"missing: {p}"
         assert p.stat().st_size < CAP, f"felix-admin-calendar/AGENTS.md {p.stat().st_size} >= {CAP}"
     ```
- **Files**: `scripts/openclaw/agents/tests/test_agents_md_size.py`
- **Parallel?**: [P] with T002/T004.
- **Notes**: Initial state — first test FAILS (main is 25,982); second test FAILS (file doesn't exist).

### Subtask T004 – test_openclaw_config_schema.py

- **Purpose**: Validate the openclaw.json shape, presence of felix-admin-calendar entry, and path patterns.
- **Steps**:
  1. Create `scripts/openclaw/agents/tests/test_openclaw_config_schema.py`. Load the fixture from `tests/fixtures/openclaw-sample.json` via the `repo_root` fixture; do NOT load from `~/.openclaw/openclaw.json` (the test is offline-safe).
  2. Tests to author:
     - `test_openclaw_json_parses()` — `json.load(...)` succeeds; top-level keys include `agents`.
     - `test_felix_admin_calendar_entry_present()` — `next(e for e in cfg["agents"]["list"] if e["id"] == "felix-admin-calendar")` does not raise.
     - `test_felix_admin_calendar_entry_complete()` — entry has all 5 required keys (`id`, `name`, `workspace`, `agentDir`, `model`).
     - `test_workspace_path_pattern()` — entry's `workspace` matches `^/data/services/openclaw/[a-z-]+-agent$` (regex).
     - `test_agentdir_path_pattern()` — entry's `agentDir` matches `^/home/claude/\.openclaw/agents/[a-z-]+/agent$`.
     - `test_model_known()` — entry's `model` is a key in `cfg["agents"]["defaults"]["models"]`.
- **Files**: `scripts/openclaw/agents/tests/test_openclaw_config_schema.py`
- **Parallel?**: [P] with T002/T003.
- **Notes**: Initial state — `test_openclaw_json_parses` PASSES; everything else FAILS (felix-admin-calendar entry not in fixture). This is the expected red state.

### Subtask T005 – Confirm pytest run shape

- **Purpose**: Document the expected pre-WP02/WP03 red state so reviewers can verify.
- **Steps**:
  1. Run `pytest scripts/openclaw/agents/tests/ -v` from repo root.
  2. Capture the failure summary (which tests fail, with what assertion message).
  3. Add a short README at `scripts/openclaw/agents/tests/README.md` (~15 lines) documenting: purpose of these tests, expected red→green progression, how to run.
- **Files**: `scripts/openclaw/agents/tests/README.md`
- **Parallel?**: No — runs after T002–T004.
- **Notes**: Expected failures:
  - `test_main_agents_md_under_12k` FAIL (size ~26K)
  - `test_felix_admin_calendar_agents_md_under_12k` FAIL (file missing)
  - `test_felix_admin_calendar_entry_present` and follow-ons FAIL (fixture lacks the entry)
  - All other tests PASS

## Test Strategy

The tests authored in this WP ARE the test surface for the mission's deterministic verification. There is no additional test-of-tests layer required.

To run: `pytest scripts/openclaw/agents/tests/ -v`

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| pytest discovery collision with other test trees in repo | Self-contained `__init__.py`; `conftest.py` scoped to this directory only |
| Fixture path resolution fragile (relative to test file vs repo root) | Use the `repo_root` fixture for any file-system check |
| Fixture contains real secret by accident | Reviewer compares against `research.md` F-03; `REDACTED-DO-NOT-USE` is the literal sentinel |
| Tests pass spuriously because fixture is too permissive | Tests assert SPECIFIC values (felix-admin-calendar, path patterns, model presence) — not just JSON parseability |

## Review Guidance

- All 4 test files present? (`__init__.py`, `conftest.py`, `test_agents_md_size.py`, `test_openclaw_config_schema.py`)
- Fixture present and free of real secrets?
- Run `pytest scripts/openclaw/agents/tests/ -v` and confirm the red state matches T005's documented expectation.
- `conftest.py`'s `repo_root` fixture resolves correctly (test it by adding a temporary assertion if uncertain).

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
- 2026-06-11T04:07:13Z – user – Review passed (verdict-pending due to issue-matrix gate, now resolved): 6 files present, fixture sanitized (REDACTED-DO-NOT-USE), shape matches live snapshot, RED state confirmed (7F/1P), README documents red→green progression, no scope creep
