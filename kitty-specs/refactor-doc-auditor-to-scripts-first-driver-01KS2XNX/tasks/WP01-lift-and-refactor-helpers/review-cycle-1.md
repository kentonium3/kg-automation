# Review feedback for WP01 — cycle 1

**Reviewer**: codex (gpt-5, profile spec-kitty-review)
**Verdict**: Changes requested
**Date**: 2026-05-20

## Verified passing

- `PYTHONPATH=scripts python3 -m pytest tests/doc_audit/helpers/` → 35 tests pass
- Both helpers' CLI `--help` work at new paths
- Doc references in `helper-script-conventions.md` and `signal-to-doc-map.json` updated correctly

## Critical findings — must address

### Finding 1: Broken existing test file references deleted helper

**File**: `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py:31`

**Issue**: This existing test imports / executes `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` which WP01 deleted via `git mv`. Result: 9 test failures.

**Verification**: `python3 -m pytest tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py tests/openclaw/agents/main/test_felix_file_issue.py` → 9 failures, all from the deleted legacy routing path.

**Required fix**: Either DELETE the now-broken legacy test file (recommended — its replacement is `tests/doc_audit/helpers/test_handle_audit_routing.py` which already covers the contract), OR update it to import from the new path. Delete is cleaner because the test was testing a file at a path that no longer exists, and the new path has dedicated tests.

**Owned-files expansion required**: Add `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py` to WP01's `owned_files` to allow the deletion.

### Finding 2: AGENTS.md references point to deleted paths

**File**: `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` lines 89 and 350

**Issue**: These reference invocations like `python3 /home/claude/kg-automation/scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py` (or similar). The repo path component matches a file that WP01 deleted. While the **deployed** path on office2 still resolves until WP09 retires that workspace, in-repo CI / `validate_docs.py` see broken references.

**Context**: WP01's prompt context note said the AGENTS.md invocation "will be retired in WP09 — preserving the CLI surface means no operational disruption." But that compat applies to the production runtime, not the in-repo consistency.

**Required fix**: Either UPDATE the two AGENTS.md references to the new paths (`scripts/doc_audit/helpers/handle_*.py`), OR add a comment explaining the imminent retirement.

**Owned-files expansion required**: Add `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` to WP01's `owned_files` to allow the update.

## Recommendation for cycle 2

1. Add `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py` to WP01's owned_files
2. Delete that file (its replacement is already in `tests/doc_audit/helpers/`)
3. Add `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` to WP01's owned_files
4. Update lines 89 and 350 to the new helper paths
5. Re-run `pytest` against the full repo (not just `tests/doc_audit/helpers/`) — confirm no regressions outside WP01's scope

## Notes

- The pre-commit guard warnings about `tests/doc_audit/__init__.py` and `tests/doc_audit/conftest.py` are NOT findings — those files are mechanically required and within the lane's overall write_scope. Carry forward.
- The structural refactor itself (the new library entry points `process_events`, `route_audit_decision` + dataclasses) is well-done and unchanged in cycle 2.
