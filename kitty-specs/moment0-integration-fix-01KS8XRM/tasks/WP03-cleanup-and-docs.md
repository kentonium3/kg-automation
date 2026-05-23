---
work_package_id: WP03
title: cleanup_391 script + architecture docs correction
dependencies:
- WP02
requirement_refs:
- C-009
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T22:50:00+00:00'
subtasks:
- T010
- T011
- T012
- T013
history: []
authoritative_surface: scripts/doc_audit/helpers/cleanup_391.py
execution_mode: code_change
mission_id: 01KS8XRMC0EQZ8HCJ52GXCJ226
mission_slug: moment0-integration-fix-01KS8XRM
owned_files:
- scripts/doc_audit/helpers/cleanup_391.py
- tests/doc_audit/helpers/test_cleanup_391.py
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
agent: "claude:opus:python-implementer:implementer"
shell_pid: "55905"
---

# WP03 — cleanup_391 + architecture docs correction

## Objective

Close the 13 broken-pipeline artifact issues (#378-#390) via a one-shot script. Correct the architecture docs that named `handle_drift_events.py` as the Moment 0 integration site — the actual site is `signals/drift_event.py::commit()` invoking `routing/drift_moment0.py::route_drift_event`.

## Context

- **Spec**: FR-008 (cleanup script), C-009 (close artifacts as part of cutover)
- **Plan**: D4 (cleanup script design — mirrors `cutover_362.py`)
- **Dependencies**: WP02 (Moment 0 fix must be live before cleanup; otherwise the new pipeline could re-file similar issues)
- **Pattern source**: `scripts/doc_audit/helpers/cutover_362.py` is the direct template.

## Subtasks

### T010 — cleanup_391.py module

Steps:
1. Create `scripts/doc_audit/helpers/cleanup_391.py` based on `cutover_362.py`'s structure.
2. Module constants:
   ```python
   MARKER_PATH = Path.home() / ".config" / "doc-audit" / "cleanup-391.done"
   MISSION_SLUG = "moment0-integration-fix-01KS8XRM"
   MISSION_ID = "01KS8XRMC0EQZ8HCJ52GXCJ226"
   REPO = "kentonium3/kg-automation"
   ISSUE_NUMBERS = [378, 379, 380, 381, 382, 383, 384, 385, 386, 387, 388, 389, 390]
   COMMENT_BODY = (
       "Closing as part of mission {mission_slug} (#391). "
       "This issue was filed by the broken #362 pipeline replay on "
       "2026-05-22T22:28 UTC. The fixed pipeline (Moment 0 wired at "
       "signals/drift_event.py via routing/drift_moment0.py) now "
       "processes subsequent drift events via the LLM judgment path."
   )
   GH_RATE_DELAY_SECONDS = 0.5
   ```
3. Differences from `cutover_362.py`:
   - **Static issue list**, not a `gh search` query — these are exact known issues. NO `gh issue list` call.
   - No cursor reset — the new pipeline will process subsequent events naturally; we don't want to re-replay.
   - Otherwise identical structure: `_close_issue()`, `_close_all_issues()`, `_write_marker()`, `run()`, `main()` with `--dry-run` and `--force` flags, `_StructuredArgumentParser` pattern, exit codes 0/1/2/3.
4. Marker file contents include the static issue list + run_at_utc + mission identity.

Validation:
- [ ] `python3 scripts/doc_audit/helpers/cleanup_391.py --help` exits 0
- [ ] Module importable: `from doc_audit.helpers.cleanup_391 import run, CleanupResult`
- [ ] Static issue list is `[378..390]` (13 entries)

### T011 — Tests for cleanup_391

Steps:
1. Create `tests/doc_audit/helpers/test_cleanup_391.py` mirroring `test_cutover_362.py` patterns.
2. Mock `subprocess.run` (gh calls), use `tmp_path` for marker location.
3. Test cases:
   - Happy path: 13 issues processed; CleanupResult.issues_closed has 13 entries
   - Dry-run: no subprocess calls beyond the inspection ones; no marker write
   - Idempotent no-op: marker pre-exists → returns CleanupResult(already_done=True)
   - `--force` overrides marker
   - Partial failure tolerance: 1 of 13 fails → other 12 succeed; CleanupResult lists the 12
   - gh failure on issue → exit 1
   - Marker write failure → exit 2
   - Marker contents include all closed issue numbers
   - Rate-limit spacing (mock `time.sleep` called between calls)
4. Coverage target ≥85%.

### T012 — Architecture docs correction

Steps:
1. Read `docs/design/architecture/data/service-inventory.json`. Find the entries added by #362 (drift_interpretation, drift_ledger, drift_to_proposed_edit, cutover_362, handle_drift_events, judgment_moments references on felix-doc-auditor).
2. Update:
   - `felix-doc-auditor` entry: judgment_moments still lists drift_interpretation (good). Add reference to the new `routing/drift_moment0.py` as the integration helper.
   - `drift_interpretation` entry: `invoked_by` should be `signals/drift_event.py + routing/drift_moment0.py` (corrected from "handle_drift_events.py").
   - Add new entry `drift_moment0` (kind=routing_helper, path=`scripts/doc_audit/routing/drift_moment0.py`, introduced_by=`"#391"`).
   - `handle_drift_events` entry: note that it's a library/CLI surface that ALSO uses `routing/drift_moment0.py`. Not the cron-path entry point.
   - `updated_by` set to `"#391"` on touched entries.
3. Update `docs/design/architecture/data/data-flows.json`:
   - Correct the "doc-audit-drift-interpretation-llm" flow source: from `signals/drift_event.py` (not `handle_drift_events.py`).
   - Mark `updated_by: "#391"` on the flow.
4. Update markdown views (`service-inventory.md`, `data-flows.md`) to match JSON.
5. Validate JSON parses: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds.

### T013 — Runbook correction

Steps:
1. Read `docs/runbooks/doc-auditor-driver-ops.md`. Find the "Moment 0 — drift interpretation" section.
2. Replace any reference to `handle_drift_events.py::process_events()` as the Moment 0 invocation site with the correct path: `signals/drift_event.py::DriftEventSignalSource.commit()` → `routing/drift_moment0.py::route_drift_event()`.
3. Add a note that the library/CLI surface (`python3 -m doc_audit.helpers.handle_drift_events`) is for operator replay; the cron service does NOT use this entry point.
4. Update frontmatter: `last_validated: 2026-05-22`, `updated_by: '#391'`, bump version to v1.2.
5. Also fix the timer name reference from `felix-doc-auditor-driver.timer` to `felix-doc-auditor.timer` (discovered during #362 cutover; the runbook still has the assumed-but-incorrect name).

Validation:
- [ ] `grep "handle_drift_events" docs/runbooks/doc-auditor-driver-ops.md` only shows mentions in the library/CLI context, not the cron path
- [ ] `grep "felix-doc-auditor-driver.timer" docs/runbooks/doc-auditor-driver-ops.md` returns no matches (corrected to `felix-doc-auditor.timer`)
- [ ] Frontmatter `updated_by: '#391'`

## Definition of Done

- [ ] All 4 subtasks complete
- [ ] `pytest tests/doc_audit/helpers/test_cleanup_391.py -v` passes ≥85% coverage
- [ ] JSON files parse and have `updated_by: '#391'` on touched entries
- [ ] Markdown views match JSON
- [ ] Runbook correctly names the cron-path integration site

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission moment0-integration-fix-01KS8XRM --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-23T04:38:12Z – claude:opus:python-implementer:implementer – shell_pid=81509 – Started implementation via action command
- 2026-05-23T14:23:46Z – claude:opus:python-implementer:implementer – shell_pid=81509 – Ready for review: cleanup_391 script + arch docs; 23 tests / 98% coverage; full doc_audit suite passes (592 + 2 skipped)
- 2026-05-23T14:24:39Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=54686 – Started review via action command
- 2026-05-23T14:28:35Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=54686 – Moved to planned
- 2026-05-23T14:28:48Z – claude:opus:python-implementer:implementer – shell_pid=55905 – Started implementation via action command
