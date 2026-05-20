---
work_package_id: WP01
title: Lift and refactor existing helpers
dependencies: []
requirement_refs:
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
base_commit: 588121de726428f153214eb20372046a50772c0f
created_at: '2026-05-20T16:54:25.115654+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 — Foundation
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "46024"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/helpers/
execution_mode: code_change
owned_files:
- scripts/doc_audit/helpers/**
- scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py
- scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py
- docs/design/helper-script-conventions.md
- docs/design/architecture/data/signal-to-doc-map.json
- tests/doc_audit/helpers/**
tags: []
---

# Work Package Prompt: WP01 — Lift and refactor existing helpers

## Objective

Move the two reusable helper scripts (`handle_drift_events.py`, `handle_audit_routing.py`) from `scripts/openclaw/agents/felix-doc-auditor/` into the new `scripts/doc_audit/helpers/` location, and refactor each to expose its internal functions as importable Python — while preserving the existing CLI entry point so external callers (and the legacy AGENTS.md §2 path, which will be retired in WP09) continue to work during cutover.

This is foundational. WP03 (signal source adapter `DriftEventSignalSource`) and WP05 (routing layer `apply_decisions.py`) both import from `helpers/` directly per research.md D3's hybrid library+CLI pattern.

## Context

- **Why we're moving these files**: at cutover (WP09), the entire `scripts/openclaw/agents/felix-doc-auditor/` directory is deleted (per spec FR-010). The two helpers are not openclaw-agent-specific — they're well-built Python that any caller can use. Keeping them under the about-to-be-deleted directory invites confusion.
- **Why we're keeping the CLI entry point**: `handle_drift_events.py` is still invoked via subprocess by today's openclaw agent (AGENTS.md §2). WP09's cutover deletes that caller, but during the WP01→WP08 development window, the existing pipeline keeps running. Preserving the CLI surface means no operational disruption.
- **The hybrid library+CLI pattern**: standard Python `if __name__ == "__main__":` guard. Existing top-level `main()` function extracts argparse + invokes internal building blocks; internal functions are also importable directly.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane (see `lanes.json` produced by `finalize-tasks`). Run `spec-kitty agent action implement WP01 --agent <name>` to enter the worktree.

## Subtasks

### T001 — Move `handle_drift_events.py` to `scripts/doc_audit/helpers/`

**Purpose**: Relocate the script to its new permanent home.

**Steps**:
1. Create the directory: `mkdir -p scripts/doc_audit/helpers/`
2. Add an empty `scripts/doc_audit/helpers/__init__.py` (makes it a Python package).
3. `git mv scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py scripts/doc_audit/helpers/handle_drift_events.py`
4. Verify the file content is unchanged: `git diff HEAD --stat` should show only the rename.

**Files affected**:
- New: `scripts/doc_audit/helpers/__init__.py`
- Moved: `scripts/doc_audit/helpers/handle_drift_events.py` (from `scripts/openclaw/agents/felix-doc-auditor/`)

**Validation**:
- [ ] File exists at new path with executable bit preserved (`ls -la scripts/doc_audit/helpers/handle_drift_events.py`)
- [ ] Old path returns "No such file" (`ls scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py` → error)
- [ ] `python3 scripts/doc_audit/helpers/handle_drift_events.py --help` produces the existing help text (no functional change yet)

---

### T002 — Move `handle_audit_routing.py` to `scripts/doc_audit/helpers/`

**Purpose**: Same as T001 for the second helper.

**Steps**:
1. `git mv scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py scripts/doc_audit/helpers/handle_audit_routing.py`
2. Verify file content unchanged.

**Files affected**:
- Moved: `scripts/doc_audit/helpers/handle_audit_routing.py`

**Validation**:
- [ ] File exists at new path with executable bit preserved
- [ ] `python3 scripts/doc_audit/helpers/handle_audit_routing.py --help` produces existing help text

---

### T003 — Refactor each helper: separate `main()` from internal functions

**Purpose**: Make every meaningful internal function importable so callers (the new driver) don't need to subprocess-out to use them. Preserve the existing CLI surface 1:1.

**Steps**:

1. **`handle_drift_events.py` refactor**:
   - Verify the file already has a structure that separates CLI handling from logic. Today's structure (per Phase 0 research):
     - `Mapping` dataclass (line ~50)
     - `find_mapping()`, `append_unmapped()`, `file_doc_audit_issue()`, `write_cursor_atomic()` — already importable
     - `main()` — argparse + orchestration
     - `if __name__ == "__main__":` guard
   - If any of these functions are inside `main()`, hoist them to module-level so they can be imported.
   - Add a single new function `process_events(events_path, cursor_path, mapping_path, unmapped_path, repo, limit, dry_run) -> ProcessResult` that mirrors what `main()` does internally but takes plain Python args (not argparse.Namespace). `main()` becomes a thin wrapper that parses args and calls `process_events`.
   - Define a small `ProcessResult` dataclass (or named-tuple) with: `processed: int, matched_filed: int, unmapped: int, errors: int, new_cursor: int`.

2. **`handle_audit_routing.py` refactor**:
   - Apply the same pattern: identify the orchestration in `main()`, extract a `route_audit_decision(state_path: Path) -> RoutingResult` function that takes the JSON state path and returns a structured result.
   - `RoutingResult` dataclass with: `applied_count: int, gated: bool, pending_approval_issue: int | None, debt_issues: list[int], missing_issues: list[int], errors: list[str]`.
   - `main()` becomes a thin wrapper.

3. **Module-level docstring update**: add a paragraph noting that the helpers are now importable as `from doc_audit.helpers.handle_drift_events import process_events, find_mapping, ...` etc.

**Files affected**:
- Modified: `scripts/doc_audit/helpers/handle_drift_events.py`
- Modified: `scripts/doc_audit/helpers/handle_audit_routing.py`

**Validation**:
- [ ] `from doc_audit.helpers.handle_drift_events import process_events, find_mapping` works in a Python REPL (with `PYTHONPATH=scripts/`)
- [ ] `from doc_audit.helpers.handle_audit_routing import route_audit_decision` works
- [ ] `python3 scripts/doc_audit/helpers/handle_drift_events.py --help` still works (CLI preserved)
- [ ] `python3 scripts/doc_audit/helpers/handle_audit_routing.py --help` still works
- [ ] Existing AGENTS.md §2 invocation (the one with the explicit `/home/claude/...` path) still works when invoked manually: run it in `--dry-run` mode against a fixture and verify it produces the same output as before

**Edge cases**:
- If the helpers have classes/dataclasses that are already at module level (Mapping, etc.), they stay as-is.
- Do NOT change behavior. This is a structural refactor only.

---

### T004 [P] — Update doc references

**Purpose**: Doc-update sweep for the three files that reference the old paths.

**Steps**:

1. **`docs/design/helper-script-conventions.md`**:
   - Search for references to `scripts/openclaw/agents/felix-doc-auditor/handle_*.py`
   - Replace with `scripts/doc_audit/helpers/handle_*.py`
   - Add a note: "These helpers were lifted from felix-doc-auditor's agent workspace in #343 to a more durable location."

2. **`docs/design/architecture/felix-d6-survey.md`**:
   - **Out of scope for this WP** — WP10 (T049) owns this file and will perform BOTH the path update AND the verdict-context note in one place. T004 hands off the path update to T049.

3. **`docs/design/architecture/data/signal-to-doc-map.json`**:
   - The `description` field references `felix-doc-auditor/handle_drift_events.py` — update to new path
   - Set `updated_by` to `#343-wp01`
   - Bump `last_updated` to today's date

**Files affected**:
- Modified: `docs/design/helper-script-conventions.md`
- Modified: `docs/design/architecture/felix-d6-survey.md`
- Modified: `docs/design/architecture/data/signal-to-doc-map.json`

**Validation**:
- [ ] `grep -rln "scripts/openclaw/agents/felix-doc-auditor/handle_" docs/` returns nothing
- [ ] `signal-to-doc-map.json` parses as valid JSON
- [ ] `last_updated` and `updated_by` fields reflect the change

---

### T005 [P] — Unit tests for importable surfaces

**Purpose**: Lock in the new import surface so future refactors don't regress it.

**Steps**:

1. Create `tests/doc_audit/__init__.py` (empty).
2. Create `tests/doc_audit/helpers/__init__.py` (empty).
3. Create `tests/doc_audit/helpers/test_handle_drift_events.py`:
   - Import `process_events`, `find_mapping`, `append_unmapped`, `file_doc_audit_issue`, `write_cursor_atomic` from `doc_audit.helpers.handle_drift_events`
   - Test `find_mapping`: given a fixture event JSON + a fixture mapping list, returns the expected mapping or None
   - Test `write_cursor_atomic`: writes the cursor file via tempfile+rename; preserves prior content on failure
   - Test `process_events` end-to-end with mocked `subprocess.run` (for `gh issue create`) against a fixture events file
4. Create `tests/doc_audit/helpers/test_handle_audit_routing.py`:
   - Import `route_audit_decision` and any other now-importable functions
   - Test `route_audit_decision` with a fixture audit-state JSON: applies expected operations against mocked filesystem + mocked `gh` subprocess
5. Create `tests/doc_audit/helpers/fixtures/`:
   - `drift_events_sample.jsonl` — a few representative events
   - `signal_to_doc_map_sample.json` — minimal mapping
   - `audit_state_sample.json` — minimal Tier-A + Tier-B mix

**Files affected**:
- New: `tests/doc_audit/__init__.py`
- New: `tests/doc_audit/helpers/__init__.py`
- New: `tests/doc_audit/helpers/test_handle_drift_events.py`
- New: `tests/doc_audit/helpers/test_handle_audit_routing.py`
- New: `tests/doc_audit/helpers/fixtures/drift_events_sample.jsonl`
- New: `tests/doc_audit/helpers/fixtures/signal_to_doc_map_sample.json`
- New: `tests/doc_audit/helpers/fixtures/audit_state_sample.json`

**Validation**:
- [ ] `pytest tests/doc_audit/helpers/` passes (all tests green)
- [ ] Coverage of the new importable functions is ≥80%

---

## Definition of Done

- [ ] Both helpers moved to `scripts/doc_audit/helpers/`
- [ ] Existing CLI invocations work unchanged for both helpers
- [ ] Importable functions exported per T003 (`process_events`, `route_audit_decision`, supporting functions)
- [ ] Documentation paths updated (no stale references to the old path)
- [ ] Unit tests pass
- [ ] No behavioral change vs HEAD; this is structural-only

## Risks

| Risk | Mitigation |
|---|---|
| `git mv` leaves dangling references in docs not enumerated above | After moves, grep the whole repo for the old paths; flag any unexpected hits |
| Refactor accidentally changes helper behavior | Run existing manual smoke (the helpers process drift events and route audit decisions) before and after — outputs should match |
| `__init__.py` placement breaks Python's import resolution | Use `PYTHONPATH=scripts/` when testing; consider whether `scripts/` itself needs an `__init__.py` (it doesn't if we treat `scripts/` as a `PYTHONPATH` root) |

## Reviewer Guidance

Reviewer should confirm:
- The move preserves file content (`git log --follow` works correctly post-move)
- The CLI entry points behave identically (run `--help` and compare output to pre-move)
- The new importable surfaces are documented (module docstrings updated)
- Tests pass and cover the key importable functions
- Doc references are exhaustive — no other docs in the repo reference the old paths

## Implementation Command

```bash
spec-kitty agent action implement WP01 --agent <name>
```

## Cross-references

- Research D3: hybrid library+CLI pattern
- Spec FR-001, FR-005, FR-006 (helpers contribute to these)
- Existing helpers' module docstrings (current shape)

## Activity Log

- 2026-05-20T16:54:27Z – claude:opus-4.7:implementer:implementer – shell_pid=38129 – Assigned agent via action command
- 2026-05-20T17:05:31Z – claude:opus-4.7:implementer:implementer – shell_pid=38129 – Ready for review
- 2026-05-20T17:06:19Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=40333 – Started review via action command
- 2026-05-20T17:15:35Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=40333 – Moved to planned
- 2026-05-20T17:16:57Z – claude:opus-4.7:implementer:implementer – shell_pid=42233 – Started implementation via action command
- 2026-05-20T17:20:35Z – claude:opus-4.7:implementer:implementer – shell_pid=42233 – Cycle 2: addressed both codex findings
- 2026-05-20T17:21:03Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=42990 – Started review via action command
- 2026-05-20T17:30:54Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=42990 – Moved to planned
- 2026-05-20T17:31:05Z – claude:opus-4.7:implementer:implementer – shell_pid=44672 – Started implementation via action command
- 2026-05-20T17:36:45Z – claude:opus-4.7:implementer:implementer – shell_pid=44672 – Cycle 3: coverage at >=80% per file
- 2026-05-20T17:38:32Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=46024 – Started review via action command
