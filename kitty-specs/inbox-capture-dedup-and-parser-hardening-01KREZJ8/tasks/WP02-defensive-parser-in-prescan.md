---
work_package_id: WP02
title: Defensive parser in prescan.py
dependencies:
- WP01
requirement_refs:
- C-002
- FR-003
- FR-004
- FR-005
- FR-010
- NFR-001
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: scripts/inbox/prescan.py
execution_mode: code_change
owned_files:
- scripts/inbox/prescan.py
- tests/inbox/test_prescan_parse_failure.py
tags: []
---

# WP02 — Defensive parser in prescan.py

## Objective

Extend `scripts/inbox/prescan.py` to (a) classify malformed-frontmatter notes as a distinct `parse_failure` state (not silently treated as `unprocessed`) and (b) consult the routing log to filter already-routed notes out of `unprocessed_paths`. The agent's read-side dedup happens here, invisibly.

## Context

- **Spec** anchors: FR-003 (dedup before route), FR-004 (halt routing on parse failure), FR-005 (4 malformation cases), FR-010 (marker cleanup flag).
- **Contracts** anchor: `contracts/prescan-classifier.md` is the authoritative spec.
- **Data-model** anchor: §ParseFailure, §dedup-skipped flow.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`

## Subtasks

### T004 — Extend classifier with 4 parse-failure cases

**Purpose**: Add detection for the 4 malformation classes per `contracts/prescan-classifier.md`.

**Steps**:

1. In `scripts/inbox/prescan.py`, find the existing per-file classification function (around line 240 — the function returning a `ClassificationResult` or equivalent).
2. Before the existing well-formed branch, add detection in this order:
   - **UTF-8 BOM check**: read raw bytes; if first 3 bytes are `b'\xEF\xBB\xBF'`, classify as `parse_failure` with reason `"UTF-8 BOM at start of file"`.
   - **Leading whitespace before `---` check**: read raw text (after BOM strip for measurement); if first non-blank character is not `-` AND the raw text contains `---` within the first 50 chars, classify as `parse_failure` with reason `"leading whitespace before opening ---"`. (Subtle: distinguish "leading blank lines only" — already handled by mission 027's `_extract_frontmatter_block` — from "leading non-newline whitespace" or "mixed whitespace + non-empty content before ---". A useful distinguisher: if `splitlines()[0]` is empty AND `splitlines()[non-empty-index] == "---"`, it's the mission-027 case → classify as `unprocessed`. If first non-empty token isn't exactly `---`, it's parse_failure.)
   - **Missing closing `---`**: if raw text starts with `---` (after BOM/whitespace) but `_extract_frontmatter_block` returns None due to no closing fence, classify as `parse_failure` with reason `"missing closing --- (unterminated frontmatter block)"`. (Distinguish from no-frontmatter — that case is when there's no `---` at all; classify as before.)
   - **YAML parse error**: wrap the existing `yaml.safe_load(block)` call. On `yaml.YAMLError`, classify as `parse_failure` with reason `f"invalid YAML inside frontmatter block: {exc}"` (truncate the message to 200 chars).
3. For all parse-failure cases, return a result with `classification = "parse_failure"` and `reason = <one of the above strings>`. Do NOT include in `unprocessed_paths`. Do NOT treat as `unprocessed`.

**Files**: `scripts/inbox/prescan.py` (modify — ~50 line addition in the classifier).

**Validation**: covered in T007.

**Edge cases**:

- Mission 027 regression: a note with a single leading blank line then `---` must STILL classify as `unprocessed`, not `parse_failure`. Tests in T007 explicitly cover this.
- File starts with BOM AND has leading whitespace: classify as `parse_failure` with the BOM reason (BOM check fires first).

---

### T005 — Extend prescan output JSON

**Purpose**: Add 3 new top-level fields to prescan's JSON output: `parse_failures`, `dedup_skipped`, `marker_cleanup_needed`.

**Steps**:

1. In `prescan.py`'s `main()` (or equivalent function that emits the JSON), extend the output dict to include:
   ```python
   {
       "unprocessed_count": ...,         # existing
       "unprocessed_paths": [...],       # existing
       "archived_count": ...,            # existing
       "archived": [...],                # existing
       "warnings": [...],                # existing
       "parse_failures": [               # NEW
           {"path": <abs>, "reason": <str>},
           ...
       ],
       "dedup_skipped": [                # NEW
           {"path": <abs>, "filename": <basename>, "existing_issue": <int or null>},
           ...
       ],
       "marker_cleanup_needed": [        # NEW
           <abs_path>, ...
       ],
   }
   ```
2. `existing_issue` may be null for v1 — the routing-log entry has the issue number but the dedup filter doesn't need to expose it (the agent doesn't act on this field). Leave the field in the contract for future use, populate from the routing-log entry where convenient.
3. Backward compat: existing JSON consumers that read only `unprocessed_paths` and `archived` keep working — fields are purely additive.

**Files**: `scripts/inbox/prescan.py` (modify).

**Validation**: covered in T007.

---

### T006 — Wire routing-log dedup filter into the classifier

**Purpose**: Use `RoutingLogReader` (from WP01) to filter already-routed paths out of `unprocessed_paths`.

**Steps**:

1. Import the routing-log module at the top of `prescan.py`:
   ```python
   try:
       from routing_log import RoutingLogReader
   except ImportError:
       # Allow prescan.py to function in environments without routing_log.py
       # (degraded mode: no dedup; existing behavior).
       RoutingLogReader = None
   ```

   (Note: if `scripts/inbox/` is on PYTHONPATH per WP01's conftest, the import works from prescan.py too. Verify during implementation; if needed, use a relative-path bootstrap.)

2. In `main()`, instantiate the reader once per cron tick:
   ```python
   reader = RoutingLogReader() if RoutingLogReader else None
   ```

3. As each file is classified, if the result would have placed the file in `unprocessed_paths`, check `reader.has(filename)` first. If hit: add to `dedup_skipped` instead.

4. If `RoutingLogReader` is unavailable (None): skip dedup; emit a warning. Preserves existing behavior in degraded environments.

**Files**: `scripts/inbox/prescan.py` (modify).

**Validation**: covered in T007.

---

### T007 — Tests for the extended classifier

**Purpose**: Lock the new behavior. Cover each parse-failure case + dedup-filter + regression on existing behavior.

**Steps**:

1. Create `tests/inbox/test_prescan_parse_failure.py`. Use fixtures from WP01.
2. Cases:
   - `test_well_formed_unprocessed_classified_unprocessed` (regression — happy path unchanged).
   - `test_leading_blank_line_classified_unprocessed_not_parse_failure` (regression — mission-027 fix preserved).
   - `test_leading_non_blank_whitespace_classified_parse_failure`.
   - `test_utf8_bom_classified_parse_failure`.
   - `test_missing_close_fence_classified_parse_failure`.
   - `test_invalid_yaml_classified_parse_failure`.
   - `test_already_processed_classified_processed` (regression).
   - `test_no_frontmatter_classified_unprocessed` (regression).
   - `test_dedup_filter_removes_filename_from_unprocessed_paths` — write a routing-log entry for the well-formed fixture's basename, run prescan with `RoutingLogReader` pointed at the tmp log, verify the path appears in `dedup_skipped` not `unprocessed_paths`.
   - `test_dedup_filter_passes_through_when_log_empty` — empty routing log; verify well-formed unprocessed file still appears in `unprocessed_paths`.
   - `test_parse_failures_field_in_json_output` — run prescan against fixture directory; verify the JSON has the `parse_failures` field with expected entries.
   - `test_no_dedup_when_routing_log_module_missing` — monkeypatch `routing_log` import to fail; verify prescan continues in degraded mode (logs warning, no dedup).
3. Use `monkeypatch` to redirect prescan's inbox-directory scan to point at `tests/inbox/fixtures/` for the test runs.

**Files**: `tests/inbox/test_prescan_parse_failure.py` (create, ~200 lines).

**Validation**:

- `pytest tests/inbox/test_prescan_parse_failure.py -v` — all green.
- `pytest tests/inbox/ -v` — combined with WP01 tests, total green.

---

## Definition of Done

- All four subtasks complete.
- `pytest tests/inbox/ -v` is green.
- Mission-027 regression test (`test_leading_blank_line_classified_unprocessed_not_parse_failure`) explicitly passes — guarantees Kent's existing notes don't get falsely flagged.
- Commit prefix: `feat(WP02):` referencing #185.

## Risks

- **Mission-027 regression**: easy to introduce. The mission-027 fix is the `_extract_frontmatter_block` blank-line-skip; the new parse-failure check must NOT undo that. The regression test guards against this.
- **Import path of `routing_log`**: prescan.py must be able to import the module at runtime on office2. WP01's conftest adds the path for tests; production needs either a `sys.path.insert` at the top of prescan.py or for `routing_log.py` to live alongside `prescan.py` in the same directory (it does per WP01's owned_files). Verify the import works when prescan runs as `python3 /home/claude/kg-automation/scripts/inbox/prescan.py`.

## Reviewer guidance

- Verify: each parse-failure case has a clear, single detection rule. No fall-through ambiguity.
- Verify: BOM, leading-whitespace, missing-close, and invalid-YAML reasons are distinguishable in the output (each has its own string).
- Verify: the mission-027 regression test exists and passes.
- Verify: degraded-mode (no routing_log) path is tested and emits a warning, not an error.

## Suggested implement command

```bash
spec-kitty agent action implement WP02 --agent <name>
```
