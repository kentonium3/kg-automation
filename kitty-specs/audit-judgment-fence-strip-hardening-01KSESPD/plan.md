# Implementation Plan: Audit Judgment Fence-Strip Hardening

**Mission**: `audit-judgment-fence-strip-hardening-01KSESPD`
**Branch contract**: current=`main`, planning base=`main`, merge target=`main` (`branch_matches_target=true`)
**Date**: 2026-05-25
**Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/audit-judgment-fence-strip-hardening-01KSESPD/spec.md`

## Summary

Defensive parse-side fix for the Haiku-4.5 markdown-fence wrapping bug class in the doc-audit judgment pipeline. The fix extracts the proven `_strip_code_fence` helper from `drift_interpretation.py` (mission #55) into a shared module under `scripts/doc_audit/judgment/_llm_response.py`, then applies it at the three remaining unprotected `json.loads()` sites: `audit_interpretation._parse_verdict` (line 289), `cross_file_implication.py` (line 151), and `tier_classification.py` (line 157). `drift_interpretation._parse_verdict` is re-pointed to import the shared helper. Tests live in `tests/doc_audit/judgment/`: a new `test_llm_response.py` for the helper, plus fenced-input regression cases added to each existing call-site test file. No public APIs change; no prompt templates change; no systemd units change. Operationally verifiable on office2 via one tick post-deploy.

## Technical Context

**Language/Version**: Python 3.13 (confirmed via existing `__pycache__/test_*.cpython-313-pytest-9.0.2.pyc` in `tests/doc_audit/judgment/`)
**Primary Dependencies**: Standard library (`json`, `re` if needed). The existing `_strip_code_fence` implementation uses only `str.strip()`, `str.splitlines()`, and `str.startswith()` — no regex, no third-party deps.
**Storage**: N/A (pure function refactor + tests).
**Testing**: pytest 9.0.2. Existing test files at `tests/doc_audit/judgment/test_{audit,drift,cross_file,tier}_*.py` follow standard unit-test patterns. Add a new `tests/doc_audit/judgment/test_llm_response.py` for helper coverage; extend existing call-site test files with one fenced + one unfenced regression case each.
**Target Platform**: Linux server (office2 / Ubuntu 24.04 LTS). Local development on macOS Darwin 25.5.0. Pure Python — no platform-specific code.
**Project Type**: single (Python package under `scripts/doc_audit/`).
**Performance Goals**: NFR-001 — ≤ 1ms overhead per helper call on typical (≤ 200KB) response strings. Achievable trivially by the existing implementation (no regex, two `splitlines()` calls).
**Constraints**: C-001 through C-006 in [spec.md](spec.md). No prompt changes; no systemd-unit changes; the 180K-token size guard from mission #56 must remain unchanged.
**Scale/Scope**: 1 new module (~25 LoC including docstring), 4 modified call-site files (each ~1-3 line edits), 1 new test file + 4 modified test files. Total change footprint: ~150-200 LoC including tests.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter governance is currently in an **unresolved** state due to a known spec-kitty registry mismatch: the charter declares `pytest` and `python` as available tools, but spec-kitty's runtime `DEFAULT_TOOL_REGISTRY` does not include them, so the governance resolver fails (see memory `project_charter_tool_registry_mismatch`). This is a deferred upstream issue, not a blocker for this mission. No active charter directives or tactics apply to this work.

**Section Anchors consulted from the compact context**: Testing Standards, Quality Gates, Change-Risk Taxonomy (Tier Protocol).

**Change-Risk Taxonomy assessment**: This is a **Tier 3 — Standard** change (logic/workflow: Python scripts only). Proceed with sandbox/dry-run validation via pytest. No pre-flight checklist or snapshot required.

**Result**: PASS (no charter violations; governance noted as deferred).

## Project Structure

### Documentation (this feature)

```
kitty-specs/audit-judgment-fence-strip-hardening-01KSESPD/
├── plan.md              # This file
├── spec.md              # Specification
├── meta.json            # Mission metadata
├── research.md          # Phase 0 output (this command)
├── data-model.md        # Phase 1 output (this command) — minimal (no entities)
├── quickstart.md        # Phase 1 output (this command) — developer onboarding
├── contracts/           # Phase 1 output — empty (pure function, no APIs)
├── checklists/
│   └── requirements.md  # Spec-quality checklist (from /spec-kitty.specify)
├── tasks/               # Populated by /spec-kitty.tasks
├── research/            # (empty; created by mission scaffold)
└── status.events.jsonl  # Spec-kitty event log
```

### Source Code (repository root)

```
scripts/doc_audit/judgment/
├── __init__.py          # (existing; unchanged)
├── _llm_response.py     # NEW — shared helper module (≤ 25 LoC)
├── client.py            # (existing; unchanged)
├── audit_interpretation.py     # MODIFIED — import + apply helper at line 289
├── cross_file_implication.py   # MODIFIED — import + apply helper at line 151
├── drift_interpretation.py     # MODIFIED — remove local _strip_code_fence (lines 436-458), import from shared
└── tier_classification.py      # MODIFIED — import + apply helper at line 157

tests/doc_audit/judgment/
├── test_audit_interpretation.py    # MODIFIED — add fenced/unfenced regression cases
├── test_cross_file_implication.py  # MODIFIED — add fenced/unfenced regression cases
├── test_drift_interpretation.py    # MODIFIED — keep existing coverage; verify no regression after re-point
├── test_llm_response.py            # NEW — unit tests for the shared helper
└── test_tier_classification.py     # MODIFIED — add fenced/unfenced regression cases
```

**Structure Decision**: Single Python project. Helper lives next to its callers under `scripts/doc_audit/judgment/` (private naming via leading underscore per C-001). Tests mirror the source layout under `tests/doc_audit/judgment/`. No new top-level directories.

## Complexity Tracking

*No Charter Check violations. This table is intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|

## Phase 0 — Outline & Research

**Status**: COMPLETE. No outstanding unknowns. Findings consolidated in [research.md](research.md).

Key findings:
- **Decision**: Adopt the existing `_strip_code_fence` implementation from `drift_interpretation.py:436-458` verbatim. **Rationale**: It is in production today, behaves correctly per mission #55 operational verification, and re-implementing risks introducing subtle behavioral drift. **Alternatives considered**: regex-based stripping (rejected as over-engineered for a known prefix pattern); fence-aware JSON parser library (rejected as needless dependency for a 22-line function).
- **Decision**: Helper file naming follows the spec's C-001 constraint — `_llm_response.py` with the leading underscore. **Rationale**: Signals private-to-the-package status; matches Python convention for non-public helper modules.
- **Decision**: Test fixtures for fenced inputs are inlined in the test files (not in `tests/doc_audit/fixtures/anthropic_responses/`). **Rationale**: The fixture directory contains end-to-end Anthropic-response JSON, while the regression cases here test a string-in/string-out pure function. Inlining keeps tests readable and avoids creating fixture files whose only difference is added backtick fences.
- **Decision**: No new `__init__.py` exports. The shared helper is imported via `from scripts.doc_audit.judgment._llm_response import _strip_code_fence` (matching the existing import style in the package). **Rationale**: Avoids changing package public surface (C-002).

## Phase 1 — Design & Contracts

**Status**: COMPLETE.

### Data Model

See [data-model.md](data-model.md). **Summary**: no entities. This mission introduces a pure function (`str → str`), modifies call sites that already operate on local-scope strings, and adds tests. There are no persistent data structures, no schemas, and no state.

### Contracts

See [contracts/](contracts/). **Summary**: empty directory. No HTTP APIs, no CLI commands, no message schemas. The shared helper is an internal Python function whose signature is documented in its docstring; no external contract surface exists.

### Quickstart

See [quickstart.md](quickstart.md). Developer-facing onboarding for someone touching the helper post-merge.

## Work Package Hints (advisory; final list owned by /spec-kitty.tasks)

The following is a planning sketch only — `/spec-kitty.tasks` will own work-package decomposition and dependency graph.

| Hint | Subject | Approx. scope |
|---|---|---|
| WP-A | Extract `_strip_code_fence` to `scripts/doc_audit/judgment/_llm_response.py`; add `tests/doc_audit/judgment/test_llm_response.py` covering FR-006/007 + edge cases | new module + new test file |
| WP-B | Re-point `drift_interpretation._parse_verdict` to import shared helper; remove local def (lines 436-458); confirm existing tests still pass | 1 source file modified |
| WP-C | Apply shared helper at `audit_interpretation._parse_verdict` (line 289); add fenced/unfenced regression cases to `test_audit_interpretation.py` | 1 source + 1 test file |
| WP-D | Apply shared helper at `cross_file_implication.py:151`; add fenced/unfenced regression cases to `test_cross_file_implication.py` | 1 source + 1 test file |
| WP-E | Apply shared helper at `tier_classification.py:157`; add fenced/unfenced regression cases to `test_tier_classification.py` | 1 source + 1 test file |

**Dependency shape**: WP-A is the foundation (creates the shared module). WP-B/C/D/E all depend on WP-A but are mutually independent (different source + test files). `/spec-kitty.tasks` may parallelize WP-B through WP-E across lanes.

## Branch Contract (reconfirmed)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Merge target**: `main`
- **`branch_matches_target`**: `true` — proceed.

After `/spec-kitty.tasks` finalizes, `spec-kitty next --agent <agent> --mission 01KSESPD` will create the lane worktree(s); implementation commits land in those worktrees per the spec-kitty git-workflow boundary.
