# Spec: Inbox parse-failure and cleanup helpers

**Mission**: `inbox-parse-failure-cleanup-helpers-01KRFVS4`
**Source issue**: [#253](https://github.com/kentonium3/kg-automation/issues/253)
**Mission type**: `software-dev`
**Status**: draft
**Target branch**: `main`

## Summary

The felix-admin-capture inbox-processing agent's prompt (`AGENTS.md`) currently encodes two deterministic loops as multi-step bash recipes: **Step 5a** (iterate `marker_cleanup_needed` → call strip script per entry) and **Step 6** (file inbox-quality issue, then iterate `parse_failures` → call inject script per entry). During the mission #185 canary on 2026-05-12, haiku 4.5 silently skipped Step 6.2 and fabricated a "script not found" explanation. Step 5a has the same shape and the same latent failure mode.

This mission collapses each multi-step recipe into a single CLI invocation by introducing two new helpers — `scripts/inbox/handle_parse_failures.py` and `scripts/inbox/handle_marker_cleanup.py` — that the agent calls once per turn. The agent prompt becomes "if X is non-empty, run helper Y" rather than "if X is non-empty, do these 3-7 bash steps and don't skip any."

## User Scenarios & Testing

### Primary scenario — Step 6 collapsed to one call

**As** the Felix inbox automation,
**when** prescan reports `parse_failures` is non-empty,
**then** I invoke a single helper that files (or dedups) the inbox-quality GitHub issue AND injects a parse-error marker for every entry, in one process,
**so that** there is no multi-step sequence in my prompt that I could partially execute.

**Acceptance**:
- The helper accepts a path to a JSON tempfile containing the prescan output (or just the parse_failures slice).
- The helper exits 0 on full success, non-zero on any partial failure (with stderr identifying which leg failed).
- The helper emits structured log entries for `inbox_quality_issue_filed`/`inbox_quality_issue_deduped` and `parse_error_marker_injected` matching the format the agent currently emits via `log_action.py`.

### Secondary scenario — Step 5a collapsed to one call

**As** the Felix inbox automation,
**when** prescan reports `marker_cleanup_needed` is non-empty,
**then** I invoke a single helper that strips the parse-error marker from every flagged note, in one process,
**so that** there is no multi-step strip loop in my prompt.

**Acceptance**:
- Helper accepts prescan output (or marker_cleanup_needed slice) via JSON tempfile.
- Helper exits 0 if all strips succeed; non-zero if any fails (continues processing the rest before exiting).
- Helper emits a structured log entry for each strip operation, matching the agent's existing `marker_stripped` action.

### Edge cases

- **Empty input list**: helper exits 0 immediately with no log emissions. (Caller is responsible for skipping the call when prescan output indicates an empty list, but the helper must be safe to call on an empty list anyway.)
- **Partial failure**: e.g., 3 of 5 marker injects succeed, 2 fail. Helper logs success for the 3, error for the 2, then exits non-zero. Agent's existing `parse_failure_handling_error` log action covers reporting.
- **Issue-filer dedup hit**: helper handles the dedup case identically to the agent's current flow (uses existing `file_inbox_quality_issue.py` dedup logic).
- **Concurrent runs**: same atomicity as today (multiple cron-tick races). No new locking required.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Add `scripts/inbox/handle_parse_failures.py` that accepts a JSON path (or `@<path>` form) containing prescan output, files-or-dedups the inbox-quality issue via the existing `file_inbox_quality_issue.py` logic, and injects a parse-error marker for each entry via the existing `inject_parse_error_marker.py` logic. | proposed |
| FR-002 | Add `scripts/inbox/handle_marker_cleanup.py` that accepts a JSON path containing prescan output and strips the parse-error marker from every `marker_cleanup_needed` entry via the existing `strip_parse_error_marker.py` logic. | proposed |
| FR-003 | Both helpers must exit 0 only when every operation in their loop succeeds; exit non-zero on any partial failure, with stderr identifying failed entries. | proposed |
| FR-004 | Both helpers must emit the same structured log entries (via `log_action.py`) that the agent's current multi-step recipes emit, preserving downstream observability. | proposed |
| FR-005 | Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` and `AGENTS.md.tmpl` so Step 5a is a single command invocation of `handle_marker_cleanup.py` and Step 6 is a single command invocation of `handle_parse_failures.py`. Remove the multi-step bash recipes. | proposed |
| FR-006 | Add unit tests in `tests/inbox/` for both new helpers, exercising: success path, partial-failure path, empty-input path, and dedup-hit path. | proposed |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | Each helper completes within 15 s on a typical inbox cron tick (≤ 5 parse_failures, ≤ 5 marker_cleanup_needed). | proposed |
| NFR-002 | No new pip dependencies — stdlib + existing `scripts/inbox/` modules only. | proposed |
| NFR-003 | The helpers must be backward-compatible with the existing helper script CLIs — they wrap them rather than rewriting their internals. (Reduces blast radius and keeps the existing unit tests valid.) | proposed |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Helper interfaces use a JSON tempfile (`@<path>` style) for input, matching the existing `file_inbox_quality_issue.py --parse-failures @<path>` convention. Avoids fragile shell quoting on parse-error reasons. | accepted |
| C-002 | The agent prompt (AGENTS.md and .tmpl) is the contract surface. Both files must be updated together to stay in sync; a deploy of one without the other would produce drift. | accepted |
| C-003 | Existing helpers (`file_inbox_quality_issue.py`, `inject_parse_error_marker.py`, `strip_parse_error_marker.py`) are not rewritten — their business logic (the library functions `inject_marker`, `strip_marker`, `find_existing_open_issue`, `file_new_issue`, etc.) is reused as-is. The new orchestrator helpers may invoke that logic via direct function import (the standard Python pattern, since each existing module already exposes a clean library API alongside its thin `main()` CLI wrapper). The existing CLI surfaces are preserved so the old helpers remain callable standalone for debugging and one-off operator use. | accepted |
| C-004 | No model swap. felix-admin-capture continues running haiku 4.5. The structural fix is sufficient; switching models is a separate decision documented in `feedback_scripts_vs_llm.md`. | accepted |

## Success Criteria

- **SC-001**: AGENTS.md (and AGENTS.md.tmpl) Step 5a contains a single command invocation rather than a multi-step loop.
- **SC-002**: AGENTS.md (and AGENTS.md.tmpl) Step 6 contains a single command invocation rather than the current 6.1+6.2 sub-step structure.
- **SC-003**: A live `openclaw cron run` on office2 with a synthesized parse_failure note results in BOTH the inbox-quality issue being filed AND the marker being injected, with structured log entries for each — verifying haiku 4.5 reliably executes the single-call form (this is the end-to-end replacement for the failed mission #185 canary).
- **SC-004**: All 99 existing tests in `tests/inbox/` continue passing; new helper tests pass.

## Assumptions

- The existing CLI surfaces of `file_inbox_quality_issue.py`, `inject_parse_error_marker.py`, and `strip_parse_error_marker.py` remain stable. (Already verified — those helpers haven't been touched since #254 merged.)
- The agent's `log_action.py` logging convention is the canonical observability format for inbox actions. (Verified by reading current AGENTS.md.)
- `claude` on office2 retains exec access to `python3` and the deployed scripts under `/home/claude/kg-automation/scripts/inbox/`. (Verified during #254 T005 deploy on 2026-05-13.)

## Dependencies

- Builds on #254 (perm preservation in `_atomic_write`), which is merged.
- No dependency on #185 (mission already merged).
- No external service or infrastructure changes.

## Out of Scope

- Model swap (haiku → sonnet/opus). The structural fix is intended to obviate that; if regression appears post-merge, model swap is a separate mission.
- Refactoring of the underlying helpers (`file_inbox_quality_issue.py` etc.) — they remain unchanged.
- A shared `scripts/inbox/_common.py` module. Future work if more helpers need orchestration.
- Other AGENTS.md steps (1–4, 5b, 5c, 7). Only Step 5a and Step 6 match the deterministic-loop pattern this mission targets.
- Updates to `docs/runbooks/inbox-ops.md` beyond logging-format changes (if any).
