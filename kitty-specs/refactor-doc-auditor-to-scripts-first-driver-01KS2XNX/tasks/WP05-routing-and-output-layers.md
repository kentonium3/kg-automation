---
work_package_id: WP05
title: Routing and output layers
dependencies:
- WP01
- WP02
requirement_refs:
- FR-005
- FR-006
- FR-007
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
phase: Phase 2 — Components
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "76770"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/output/
execution_mode: code_change
owned_files:
- scripts/doc_audit/routing/**
- scripts/doc_audit/output/**
- tests/doc_audit/routing/**
- tests/doc_audit/output/**
tags: []
---

# Work Package Prompt: WP05 — Routing and output layers

## Objective

Implement the routing layer (wrapping `helpers/handle_audit_routing.py`) and the output layer (tick-signal artifact writer + activity-log appender). These are the side-effect surfaces the driver invokes after judgment is complete.

## Context

- **Routing** consumes a fully-judged audit state and produces the actual mutations: applies Tier-A edits, commits, files pending-approval issues, files debt issues, posts audit summary, closes audits. `handle_audit_routing.py` already does this — WP05 wraps the import surface.
- **Tick signal output** writes `last-tick.json` per `contracts/tick-signal.contract.md`. Atomic write semantics required.
- **Activity log output** appends to `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` in the existing format (per spec C-005).

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP05 --agent <name>`.

## Subtasks

### T022 — Implement `routing/apply_decisions.py`

**Purpose**: Adapt `helpers/handle_audit_routing.py` import surface for use from the driver.

**Steps**:

1. Create `scripts/doc_audit/routing/__init__.py` (empty).

2. Create `scripts/doc_audit/routing/apply_decisions.py`:

   ```python
   from doc_audit.helpers.handle_audit_routing import route_audit_decision, RoutingResult
   from doc_audit.data_model import AuditIssue, ProposedEdit, DebtIssue
   from doc_audit.config import Config
   from pathlib import Path
   import json
   import tempfile

   def apply(
       config: Config,
       audit: AuditIssue,
       proposed_edits: list[ProposedEdit],
       debt_issues: list[DebtIssue],
       missing_artifacts: list[dict],
   ) -> RoutingResult:
       """Execute the routing decision for one audit's outcomes.

       Constructs the audit-state JSON expected by handle_audit_routing.py,
       writes it to a tempfile, and invokes route_audit_decision().

       Returns the RoutingResult dataclass from the helper.
       """
       audit_state = _build_audit_state(audit, proposed_edits, debt_issues, missing_artifacts)

       with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
           json.dump(audit_state, f, indent=2)
           tmp_path = Path(f.name)

       try:
           result = route_audit_decision(tmp_path)
           return result
       finally:
           tmp_path.unlink(missing_ok=True)

   def _build_audit_state(...) -> dict:
       """Construct the audit-state JSON in the shape handle_audit_routing expects.
       See kitty-specs/auto-apply-audit-edits-01KRG1BG/data-model.md for the contract.
       """
       ...
   ```

3. The `_build_audit_state()` function maps **THIS mission's data-model entities** (E-002 `AuditIssue`, E-004 `ProposedEdit`, E-006 `DebtIssue` — see `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/data-model.md`) into the JSON shape `handle_audit_routing.py` consumes. **Do NOT** assume the legacy mission #259's entity shapes match this mission's — they may differ. Determine the helper's required input shape by:
   - Reading the docstring at the top of `scripts/doc_audit/helpers/handle_audit_routing.py` (especially the "Input JSON shape" section)
   - Reading `route_audit_decision`'s actual implementation (which fields it reads from the loaded state)
   - Cross-referencing this mission's data-model entities to map field-by-field
   - If a helper-expected field has no entity counterpart, raise this in a code comment AND propose a follow-up — DO NOT silently invent the mapping.

4. Module docstring cross-references the routing contract.

**Files**:
- New: `scripts/doc_audit/routing/__init__.py`
- New: `scripts/doc_audit/routing/apply_decisions.py` (~150 lines)

**Validation**:
- [ ] `from doc_audit.routing.apply_decisions import apply` works
- [ ] `apply()` constructs valid audit-state JSON and invokes `route_audit_decision()`
- [ ] Tempfile is cleaned up even on exception (use try/finally)
- [ ] Returns RoutingResult dataclass

---

### T023 — Implement `output/tick_signal.py`

**Purpose**: Write the structured tick signal artifact per `contracts/tick-signal.contract.md`.

**Steps**:

1. Create `scripts/doc_audit/output/__init__.py` (empty).

2. Create `scripts/doc_audit/output/tick_signal.py`:

   ```python
   from doc_audit.data_model import TickResult, TickSignal
   from doc_audit.config import Config
   from datetime import datetime, timezone
   from pathlib import Path
   import json
   import os
   import tempfile

   SCHEMA_VERSION = "1.0"
   DRIVER_VERSION = "0.1.0"

   def write_tick_signal(
       config: Config,
       result: TickResult,
       next_scheduled_tick_utc: str,
   ) -> Path:
       """Atomically write last-tick.json. Always succeeds (even on partial/failure)."""
       signal_dict = _build_signal_dict(result, next_scheduled_tick_utc)

       target = Path(config.paths.tick_signal_path)
       target.parent.mkdir(parents=True, exist_ok=True)

       # Atomic write: tempfile in same dir, then rename
       with tempfile.NamedTemporaryFile(
           mode="w",
           dir=target.parent,
           suffix=".json.tmp",
           delete=False,
       ) as f:
           json.dump(signal_dict, f, indent=2)
           tmp_path = Path(f.name)
       os.rename(tmp_path, target)
       return target

   def _build_signal_dict(result: TickResult, next_tick: str) -> dict:
       return {
           "schema_version": SCHEMA_VERSION,
           "timestamp_utc": result.ended_utc,
           "status": result.status,
           "exit_code": {"success": 0, "partial": 2, "failure": 1}[result.status],
           "driver_version": DRIVER_VERSION,
           "duration_seconds": _compute_duration(result),
           "host": os.uname().nodename,
           "tick": {
               "signals_seen": result.signals_seen,
               "signals_processed": result.signals_processed,
               "audits_processed": result.audits_processed,
               "pending_approvals_applied": result.pending_approvals_applied,
               "pending_approvals_filed": result.pending_approvals_filed,
               "tier_a_commits": result.tier_a_commits,
               "debt_filed": result.debt_filed,
               "drift_events_consumed": result.drift_events_consumed,
           },
           "judgment": {
               "tier_classification_calls": result.judgment_calls.get("tier_classification", 0),
               "debt_body_generation_calls": result.judgment_calls.get("debt_body_generation", 0),
               "cross_file_implication_calls": result.judgment_calls.get("cross_file_implication", 0),
               **result.token_usage,
           },
           "errors": result.errors,
           "next_scheduled_tick_utc": next_tick,
       }

   def print_summary_line(result: TickResult) -> None:
       """Print the stdout SUMMARY: line per contract."""
       tu = result.token_usage
       print(
           f"SUMMARY: status={result.status} "
           f"audits={len(result.audits_processed)} "
           f"debt={len(result.debt_filed)} "
           f"tier_a={len(result.tier_a_commits)} "
           f"drift={result.drift_events_consumed} "
           f"dur={_compute_duration(result):.1f}s "
           f"tokens=in:{tu['input_tokens']}(cache:{tu['cache_hit_input_tokens']})/"
           f"out:{tu['output_tokens']}"
       )
   ```

3. Always-write semantics: caller invokes from a `try/finally` block in the driver's main; on crash, a best-effort signal is written with `status="failure"` and partial counts.

4. Module docstring cross-references `contracts/tick-signal.contract.md`.

**Files**:
- New: `scripts/doc_audit/output/__init__.py`
- New: `scripts/doc_audit/output/tick_signal.py` (~150 lines)

**Validation**:
- [ ] `write_tick_signal()` produces JSON matching the contract schema (validate by parsing + checking required fields)
- [ ] Tempfile-then-rename is atomic (use os.rename, not shutil.move)
- [ ] Multiple consecutive writes correctly overwrite (current-state semantics)
- [ ] `print_summary_line()` produces the expected single-line format
- [ ] Parent directory is auto-created if absent

---

### T024 — Implement `output/activity_log.py`

**Purpose**: Append one entry per tick to the activity log, preserving the existing format from the current openclaw-agent path (per spec C-005).

**Steps**:

1. **The existing format — captured 2026-05-20 from office2 — match this EXACTLY**:

   Each audit run produces one entry. Format:

   ```
   ## Audit run — 2026-05-20T15:15:33-0400
   - Audit issue: #347
   - Title: Doc audit: cf0e0b9 (area/biz-ops)
   - In-scope docs: 3
   - Docs reviewed: 3
   - High-confidence edits proposed: 0
   - Pending-approval issue filed: none
   - Edits committed: 0
   - Debt issues created: 0
   - Missing artifacts flagged: 0
   - Items requiring human review: 0
   - Decision applied this tick: none
   - Errors: 0
   ```

   Key shape details:
   - `## Audit run — <local-tz ISO-8601>` header (note: timestamp is **local-tz with offset** like `-0400`, NOT UTC `Z`)
   - Bulleted key-value pairs (`- <Field>: <value>`)
   - One entry per audited issue per tick (NOT one entry per tick — if a tick processes 3 audits, write 3 entries)
   - File has NO YAML frontmatter at the top (just the entries directly — keep it simple, this is the existing convention)

   **Snapshot this format as a test fixture** at `tests/doc_audit/output/fixtures/activity_log_sample.txt` so the writer can be unit-tested against the canonical shape.

   The new driver also writes a per-TICK summary entry; place it directly above the per-audit entries OR omit it (the per-audit entries carry all relevant data). Discuss with the reviewer if a per-tick summary is needed.

2. Create `scripts/doc_audit/output/activity_log.py`:

   ```python
   from doc_audit.data_model import TickResult, AuditIssue
   from doc_audit.config import Config
   from datetime import datetime
   from pathlib import Path
   from zoneinfo import ZoneInfo

   # Default to America/New_York since the existing entries use -0400/-0500 offsets.
   # Make this configurable if a different TZ is required.
   LOCAL_TZ = ZoneInfo("America/New_York")

   def append_audit_entry(config: Config, result: TickResult, audit: AuditIssue, audit_outcome: dict) -> Path:
       """Append one ## Audit run entry to today's activity log. audit_outcome is the per-audit result counts."""
       # Use local-tz date for the filename (matches existing convention)
       today_local = datetime.now(LOCAL_TZ).date().isoformat()
       log_path = Path(config.paths.activity_log_dir) / f"doc-auditor-{today_local}.md"

       if not log_path.exists():
           _init_log_file(log_path)

       entry_text = _format_audit_entry(audit, audit_outcome)
       with open(log_path, "a", encoding="utf-8") as f:
           f.write(entry_text)
       return log_path

   def _init_log_file(path: Path) -> None:
       """Create new daily log file. NO frontmatter — existing convention is plain markdown."""
       path.parent.mkdir(parents=True, exist_ok=True)
       path.write_text("")  # empty file; entries appended below

   def _format_audit_entry(audit: AuditIssue, outcome: dict) -> str:
       """Format one ## Audit run entry matching the captured fixture format."""
       ts = datetime.now(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")
       # Insert colon in timezone offset (e.g., -0400 → -04:00) ONLY if the existing
       # fixture uses that form. The captured sample uses -0400 (no colon) — match it.
       lines = [
           f"## {ts}\n",
           f"**Status**: {result.status}",
           f"## Audit run — {ts}",
           f"- Audit issue: #{audit.issue_number}",
           f"- Title: {audit.title}",
           f"- In-scope docs: {outcome.get('in_scope_docs', 0)}",
           f"- Docs reviewed: {outcome.get('docs_reviewed', 0)}",
           f"- High-confidence edits proposed: {outcome.get('hc_edits_proposed', 0)}",
           f"- Pending-approval issue filed: {outcome.get('pending_approval_issue', 'none')}",
           f"- Edits committed: {outcome.get('edits_committed', 0)}",
           f"- Debt issues created: {outcome.get('debt_issues_created', 0)} {outcome.get('debt_issue_refs', '')}".rstrip(),
           f"- Missing artifacts flagged: {outcome.get('missing_artifacts', 0)}",
           f"- Items requiring human review: {outcome.get('human_review_items', 0)}",
           f"- Decision applied this tick: {outcome.get('decision_applied', 'none')}",
           f"- Errors: {outcome.get('error_count', 0)}",
           "",  # blank line between entries
       ]
       return "\n".join(lines) + "\n"
   ```

3. The `outcome` dict is populated by the driver's audit-processing loop and passed to `append_audit_entry()` per audit. Fields are documented in the contract docstring.

4. Module docstring notes this preserves the format from the previous openclaw-agent invocation (spec C-005), and references the fixture file at `tests/doc_audit/output/fixtures/activity_log_sample.txt`.

**Files**:
- New: `scripts/doc_audit/output/activity_log.py` (~120 lines)
- New: `tests/doc_audit/output/fixtures/activity_log_sample.txt` (canonical-format fixture from the 2026-05-20 capture above)

**Validation**:
- [ ] `append_audit_entry()` writes to today's file (using local-tz date for filename)
- [ ] File created empty on first call of the day; NO frontmatter prepended
- [ ] Subsequent calls append entries with one blank line between
- [ ] Output byte-for-byte matches the fixture file format (use a fixture-comparison test)
- [ ] Local-tz offset format matches the captured sample (`-0400`, no colon)

---

### T025 [P] — Unit tests for routing + output layers

**Purpose**: Test routing wrapper + output writers against fixtures.

**Steps**:

1. Create `tests/doc_audit/routing/__init__.py`.

2. Create `tests/doc_audit/routing/test_apply_decisions.py`:
   - **test_apply_builds_correct_state**: given AuditIssue + ProposedEdits + DebtIssues, `_build_audit_state()` produces JSON matching the expected shape
   - **test_apply_calls_router**: mock `route_audit_decision`; verify it's called with the tempfile path
   - **test_apply_cleans_up_tempfile**: even on exception, the tempfile is deleted
   - **test_apply_returns_routing_result**: returns the RoutingResult from the mocked router

3. Create `tests/doc_audit/output/__init__.py`.

4. Create `tests/doc_audit/output/test_tick_signal.py`:
   - **test_write_signal_atomic**: writes file via tempfile+rename (verify no .tmp file remains on success)
   - **test_write_signal_overwrites**: second call overwrites first (current-state semantics)
   - **test_write_signal_creates_parent_dir**: parent dir doesn't exist → created
   - **test_signal_schema_complete**: written JSON has every required field per contract
   - **test_print_summary_line_format**: format matches the canonical pattern
   - **test_failure_status_written**: TickResult with status="failure" → JSON has exit_code=1

5. Create `tests/doc_audit/output/test_activity_log.py`:
   - **test_append_creates_file_if_absent**: log file doesn't exist → created with frontmatter
   - **test_append_appends_to_existing**: log file exists → no re-init of frontmatter
   - **test_append_format_preserves_existing_pattern**: spot-check against the existing format snapshot
   - **test_append_handles_empty_result**: TickResult with no audits → entry written with "(none)" markers

**Files**:
- New: `tests/doc_audit/routing/__init__.py`
- New: `tests/doc_audit/routing/test_apply_decisions.py` (~120 lines)
- New: `tests/doc_audit/output/__init__.py`
- New: `tests/doc_audit/output/test_tick_signal.py` (~150 lines)
- New: `tests/doc_audit/output/test_activity_log.py` (~120 lines)

**Validation**:
- [ ] All tests pass
- [ ] Coverage of `routing/` ≥80%
- [ ] Coverage of `output/` ≥85%

---

## Definition of Done

- [ ] Routing layer wraps `handle_audit_routing.py` via import (not subprocess)
- [ ] Tick signal writer is atomic and overwrites correctly
- [ ] Activity log appender preserves the existing format
- [ ] Unit tests pass with appropriate coverage
- [ ] All three modules cross-reference their respective contracts/specs

## Risks

| Risk | Mitigation |
|---|---|
| audit-state JSON shape mismatch with `handle_audit_routing.py` expectations | Read the helper's docstring + run an end-to-end smoke (WP06 integration tests) against a real audit |
| Activity log format drift breaks operator workflows | Snapshot the existing format at WP05 start; spot-check after writing one entry |
| Non-atomic tick-signal write leaves partial JSON on disk | Verified by atomic-write tests; manual review of write path |

## Reviewer Guidance

- Confirm `apply()` cleans up the tempfile in `finally` (not just success path)
- Confirm `write_tick_signal()` uses `os.rename()` not `shutil.move()` (move is NOT atomic across filesystems)
- Confirm activity log format is byte-for-byte compatible with existing entries (Kent reads these manually)
- Spot-check tick-signal JSON against the contract example

## Implementation Command

```bash
spec-kitty agent action implement WP05 --agent <name>
```

## Cross-references

- **Contract**: `contracts/tick-signal.contract.md`
- **Data model**: E-008 TickResult, E-009 TickSignal, E-010 ActivityLogEntry
- **Helper docstring**: `scripts/doc_audit/helpers/handle_audit_routing.py` (audit-state JSON shape)
- **Research**: D7 (Structured tick signal format)
- **Spec**: FR-005, FR-006, FR-007, FR-008, FR-009; NFR-003, NFR-004; C-005

## Activity Log

- 2026-05-20T19:36:48Z – claude:opus-4.7:implementer:implementer – shell_pid=72937 – Started implementation via action command
- 2026-05-20T19:47:27Z – claude:opus-4.7:implementer:implementer – shell_pid=72937 – Ready for review: routing wrapper + tick-signal writer + activity-log appender. 54 new tests, all green. routing/ 100% cov, output/ avg 96% cov. Full suite 261 passed.
- 2026-05-20T19:48:21Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=74843 – Started review via action command
- 2026-05-20T19:51:58Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=74843 – Moved to planned
- 2026-05-20T19:52:03Z – claude:opus-4.7:implementer:implementer – shell_pid=75833 – Started implementation via action command
- 2026-05-20T19:56:29Z – claude:opus-4.7:implementer:implementer – shell_pid=75833 – Cycle 2: blank line between entries per spec
- 2026-05-20T19:57:03Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=76770 – Started review via action command
