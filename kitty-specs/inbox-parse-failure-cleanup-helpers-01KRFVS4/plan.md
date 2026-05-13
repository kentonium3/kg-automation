# Implementation Plan: Inbox parse-failure and cleanup helpers

**Branch**: `main` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/inbox-parse-failure-cleanup-helpers-01KRFVS4/spec.md`
**Source issue**: [#253](https://github.com/kentonium3/kg-automation/issues/253)

## Summary

Add two new orchestrator helpers in `scripts/inbox/` that consolidate the deterministic loops currently inlined in the felix-admin-capture agent prompt:

- **`handle_parse_failures.py`** — reads prescan output JSON, files-or-dedups the inbox-quality GitHub issue, then injects a parse-error marker for each `parse_failures` entry. Single CLI invocation replaces Step 6.1 + 6.2.
- **`handle_marker_cleanup.py`** — reads prescan output JSON, strips parse-error markers from every `marker_cleanup_needed` entry. Single CLI invocation replaces Step 5a.

Both helpers invoke the existing inbox modules' library functions directly via Python imports (`inject_marker`, `strip_marker`, `find_existing_open_issue`, `file_new_issue`). The existing CLI scripts remain unchanged and continue to work standalone for debugging. AGENTS.md and AGENTS.md.tmpl are updated to invoke each new helper as a single command.

## Technical Context

**Language/Version**: Python 3.10+ (office2 ships 3.12). Standard library + existing `scripts/inbox/` modules. No new pip dependencies.
**Primary Dependencies**: existing inbox modules (`inject_parse_error_marker`, `strip_parse_error_marker`, `file_inbox_quality_issue`). Each already exposes the library functions we need.
**Storage**: Reads prescan output from `/tmp/inbox-prescan-latest.json` (or any path passed via `@<path>` style argument). Writes marker edits to inbox notes (handled by underlying helpers). Issue filing via `gh` CLI inside the file-issue helper (unchanged behavior).
**Testing**: `pytest` with `tmp_path` fixtures and module-level mocking. New file `tests/inbox/test_handle_parse_failures.py` + `tests/inbox/test_handle_marker_cleanup.py`. Mock `inject_marker`, `strip_marker`, `file_new_issue`, `find_existing_open_issue` at the function level to avoid network and filesystem coupling.
**Target Platform**: office2 (Ubuntu 24.04 LTS), Python 3.12. Helpers invoked by the felix-admin-capture OpenClaw agent running as `claude`.
**Project Type**: Single project — Python scripts under `scripts/inbox/`, tests under `tests/inbox/`.
**Performance Goals**: NFR-001 — each helper completes within 15 s on a typical cron tick (≤ 5 entries each). Direct function calls (option B from planning) avoid Python startup overhead per entry.
**Constraints**: NFR-002 — no new pip deps. C-001 — `@<path>` JSON input convention. C-002 — AGENTS.md and AGENTS.md.tmpl must be updated together. C-003 — reuse existing library functions; do not rewrite logic. C-004 — no model swap.
**Scale/Scope**: 2 new scripts (~80–120 lines each), 2 new test files, AGENTS.md + AGENTS.md.tmpl updates. No new directories.

## Charter Check

Charter loaded in compact mode. Same governance posture as #254. This is Tier 3 (Standard) per `change-risk-taxonomy.json` — Python script logic + agent prompt edits, no service/credential/topology impact. No pre-flight checklist required.

**Gate**: PASS.

## Project Structure

### Documentation (this feature)

```
kitty-specs/inbox-parse-failure-cleanup-helpers-01KRFVS4/
├── plan.md              # This file
├── research.md          # Alignment record (decisions B/C-003 etc.)
├── quickstart.md        # Verification recipe (local + deploy + SC-003 canary)
├── spec.md              # Mission spec
├── meta.json            # Mission identity
├── checklists/
│   └── requirements.md  # Spec quality checklist (green)
└── tasks/               # Populated by /spec-kitty.tasks
```

`data-model.md` and `contracts/` are intentionally omitted — there is no new data model and no API contract.

### Source Code (repository root)

```
scripts/inbox/
├── handle_parse_failures.py             # NEW: orchestrator for Step 6
├── handle_marker_cleanup.py             # NEW: orchestrator for Step 5a
├── inject_parse_error_marker.py         # unchanged (imports as library)
├── strip_parse_error_marker.py          # unchanged (imports as library)
├── file_inbox_quality_issue.py          # unchanged (imports as library)
├── append_routing_entry.py              # unchanged
├── prescan.py                           # unchanged
└── routing_log.py                       # unchanged

scripts/openclaw/agents/felix-admin-capture/
├── AGENTS.md                            # MODIFY: Step 5a + Step 6 become single commands
└── AGENTS.md.tmpl                       # MODIFY: same edits as AGENTS.md

tests/inbox/
├── test_handle_parse_failures.py        # NEW
├── test_handle_marker_cleanup.py        # NEW
├── (existing 99 tests unchanged)
└── conftest.py                          # unchanged

scripts/deploy/
└── deploy-149.sh                        # reused — handles AGENTS.md + scripts/inbox/ deploy
```

**Structure Decision**: Standard single-project Python layout. Two new modules + their tests; AGENTS.md prompt edits. Same shape as #185 and #254.

## Complexity Tracking

*No Charter Check violations. Section intentionally empty.*

## Phase 0: Research / Alignment

See [research.md](research.md). Six decisions logged:

1. **Invocation style**: direct function imports (option B). The existing modules already expose clean library APIs. Subprocess was rejected as less standard, less durable, and harder to unit-test.
2. **Input format**: JSON tempfile via `@<path>` convention. Matches `file_inbox_quality_issue.py --parse-failures @<path>` precedent.
3. **Error handling**: helpers continue processing all entries on partial failure, then exit non-zero with stderr identifying failed entries.
4. **Logging**: helpers invoke `log_action.py` via subprocess for each operation (only place we use subprocess — `log_action.py` is the canonical Felix-side action-log CLI).
5. **Tests**: function-level mocking of the underlying library calls; orchestrator driven via subprocess.run for CLI surface coverage.
6. **AGENTS.md edits**: replace Steps 5a and 6 with a "if X is non-empty, run helper Y" single-command structure.

## Phase 1: Design

### `handle_parse_failures.py` interface

```bash
python3 handle_parse_failures.py @/tmp/inbox-prescan-latest.json [--date YYYY-MM-DD]
```

- Reads prescan output JSON. Extracts `parse_failures` list.
- If empty: exit 0 with no log emissions.
- If non-empty:
  1. Call `file_inbox_quality_issue.find_existing_open_issue()`; if found, use that issue number. Else call `file_inbox_quality_issue.file_new_issue(parse_failures, date_str)` to file a new one.
  2. Log `inbox_quality_issue_filed` or `inbox_quality_issue_deduped` via `log_action.py` subprocess.
  3. For each entry, call `inject_parse_error_marker.inject_marker(path, issue_number, date_str)`. On success, log `parse_error_marker_injected`. On failure, log `parse_failure_handling_error` and continue.
  4. Exit 0 if every leg succeeded, else 1 with stderr summary.
- Print `<issue_number>` to stdout on success (matches the existing `file_inbox_quality_issue.py` contract).

### `handle_marker_cleanup.py` interface

```bash
python3 handle_marker_cleanup.py @/tmp/inbox-prescan-latest.json
```

- Reads prescan output JSON. Extracts `marker_cleanup_needed` list.
- If empty: exit 0 with no log emissions.
- If non-empty:
  1. For each entry, call `strip_parse_error_marker.strip_marker(path)`. On success, log `marker_stripped`. On failure, log error and continue.
  2. Exit 0 if every leg succeeded, else 1 with stderr summary.

### AGENTS.md edits

**Current Step 5a** (paraphrased): multi-line `for each entry: python3 strip_*.py <path>; log_action.py ...` loop.

**After**:
```
If `marker_cleanup_needed` is non-empty:
  python3 /home/claude/kg-automation/scripts/inbox/handle_marker_cleanup.py @/tmp/inbox-prescan-latest.json
```

**Current Step 6** (see `scripts/openclaw/agents/felix-admin-capture/AGENTS.md:275-330`): two sub-steps with multi-line bash.

**After**:
```
If `parse_failures` is non-empty:
  python3 /home/claude/kg-automation/scripts/inbox/handle_parse_failures.py @/tmp/inbox-prescan-latest.json
```

Same edit applied identically to `AGENTS.md.tmpl`.

### Test plan (FR-006)

`tests/inbox/test_handle_parse_failures.py`:

| Case | Setup | Action | Assertion |
|---|---|---|---|
| `test_empty_parse_failures_exits_zero` | Prescan JSON with empty list | run helper | exit 0; no calls to `inject_marker` |
| `test_single_parse_failure_full_success` | One entry; mock `inject_marker` → True, `find_existing_open_issue` → None, `file_new_issue` → 123 | run helper | exit 0; one inject; logs include `inbox_quality_issue_filed` + `parse_error_marker_injected` |
| `test_dedup_hit` | One entry; `find_existing_open_issue` → 99 | run helper | exit 0; `file_new_issue` NOT called; log includes `inbox_quality_issue_deduped` |
| `test_partial_failure_exits_nonzero` | Three entries; 2nd `inject_marker` → False | run helper | exit non-zero; stderr names failing path; other two still attempted |
| `test_stdout_emits_issue_number` | Standard case | run helper, capture stdout | exact `<N>\n` matches issue number |

`tests/inbox/test_handle_marker_cleanup.py`:

| Case | Setup | Action | Assertion |
|---|---|---|---|
| `test_empty_marker_cleanup_exits_zero` | Empty list | run helper | exit 0; no strips |
| `test_all_strips_succeed` | Three entries; mock all `strip_marker` → True | run helper | exit 0; three calls; three `marker_stripped` logs |
| `test_partial_strip_failure` | Three entries; 2nd `strip_marker` → raises | run helper | exit non-zero; other two still attempted |

Drive each orchestrator via `subprocess.run` for CLI coverage. Use `pytest.MonkeyPatch` and module-level injection of mocks for the wrapped library functions.

### Deploy plan

Reuse `bash scripts/deploy/deploy-149.sh --apply --backup-confirmed`. Script already deploys both `scripts/inbox/` AND the felix-admin-capture AGENTS.md files.

### End-to-end verification (SC-003)

Operator-owned post-merge per quickstart.md §5:
1. Drop malformed-YAML canary into Mac inbox.
2. Wait for sync.
3. Trigger `openclaw cron run 7fa9b299-...`.
4. Verify action log has `inbox_quality_issue_filed` (or `_deduped`) AND `parse_error_marker_injected`.
5. Verify canary file has injected callout.
6. Cleanup.

## Charter Re-check (post-design)

No new gates raised. Plan remains within Tier 3 standard scope. **Gate**: PASS.

## Next Steps

Run `/spec-kitty.tasks` to materialize this plan into work packages.

**Branch contract reminder**: Current branch `main`. Planning/base branch `main`. Merge target `main`. `branch_matches_target=true`. No branch switching required.
