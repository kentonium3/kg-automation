---
work_package_id: WP03
title: Signal source adapters
dependencies:
- WP01
- WP02
requirement_refs:
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
phase: Phase 2 — Components
assignee: ''
agent: ''
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/signals/
execution_mode: code_change
owned_files:
- scripts/doc_audit/signals/**
- tests/doc_audit/signals/**
tags: []
---

# Work Package Prompt: WP03 — Signal source adapters

## Objective

Implement the `SignalSource` Protocol from `contracts/signal-source.contract.md` and its two initial concrete adapters: `GHIssueSignalSource` (consumes `Doc audit:` / `Weekly doc audit —` / pending-approval issues from GitHub) and `DriftEventSignalSource` (wraps `helpers/handle_drift_events.py` to consume drift events from audit.sh).

Adapters normalize their source's native data into `Signal` instances (data-model E-001). The driver iterates pending signals in priority order without knowing which adapter produced them.

## Context

- The `SignalSource` Protocol contract is at `contracts/signal-source.contract.md`. Read it first.
- `GHIssueSignalSource` handles three KINDS of GH issues: `doc_audit` (priority 20), `weekly_doc_audit` (priority 30), `pending_approval` (priority 10). Pending-approval has highest priority — it represents already-approved work waiting to land.
- `DriftEventSignalSource` calls into `doc_audit.helpers.handle_drift_events.process_events()` (the importable surface from WP01). It does NOT re-implement drift-event processing; it wraps the existing helper to fit the SignalSource Protocol.
- Both adapters MUST be idempotent within a tick: calling `.pending()` twice in a row returns the same set.
- `commit()` semantics differ between adapters: GH issue source's commit is a no-op (the GH issue state itself records the outcome); drift event source's commit advances the cursor file.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP03 --agent <name>`.

## Subtasks

### T011 — Define `SignalSource` Protocol + base types

**Purpose**: Establish the abstract surface that adapters implement.

**Steps**:

1. Create `scripts/doc_audit/signals/__init__.py` exporting the Protocol and public adapter classes (initially empty; later subtasks add to it).

2. Create `scripts/doc_audit/signals/base.py`:
   - Import `Signal` from `doc_audit.data_model`
   - Define the `SignalSource` Protocol matching `contracts/signal-source.contract.md`:
     ```python
     from typing import Protocol, Iterable
     from doc_audit.data_model import Signal

     class SignalSource(Protocol):
         name: str

         def pending(self) -> Iterable[Signal]: ...
         def commit(self, signal: Signal, outcome: str) -> None: ...
     ```
   - Define a `Outcome` Literal type: `Outcome = Literal["success", "partial", "failure"]`

3. Module-level docstring referencing the contract file.

**Files**:
- New: `scripts/doc_audit/signals/__init__.py` (~15 lines)
- New: `scripts/doc_audit/signals/base.py` (~50 lines)

**Validation**:
- [ ] `from doc_audit.signals.base import SignalSource, Outcome` works
- [ ] mypy/pyright accepts the Protocol definition

---

### T012 — Implement `GHIssueSignalSource`

**Purpose**: Adapter that turns open GH issues into `Signal` instances.

**Steps**:

1. Create `scripts/doc_audit/signals/gh_issue.py`.

2. Class structure:
   ```python
   from doc_audit.signals.base import SignalSource
   from doc_audit.data_model import Signal
   from doc_audit.config import Config
   import subprocess
   import json

   class GHIssueSignalSource:
       name = "gh_issue"

       def __init__(self, config: Config) -> None:
           self.config = config
           self.repo = config.github.repo
           self._cached: Optional[list[Signal]] = None  # idempotency cache

       def pending(self) -> list[Signal]:
           if self._cached is not None:
               return self._cached
           signals: list[Signal] = []

           # 1. Pending-approvals with decision labels (priority 10)
           signals.extend(self._fetch_pending_approvals())

           # 2. New Doc audit: issues (priority 20)
           signals.extend(self._fetch_doc_audits(weekly=False))

           # 3. Weekly doc audit issues (priority 30)
           signals.extend(self._fetch_doc_audits(weekly=True))

           self._cached = signals
           return signals

       def commit(self, signal: Signal, outcome: str) -> None:
           # No-op for GH issues — outcome is recorded in the GH issue state directly
           # (closed by routing layer, labels managed there).
           pass

       def _fetch_pending_approvals(self) -> list[Signal]: ...
       def _fetch_doc_audits(self, weekly: bool) -> list[Signal]: ...
   ```

3. `_fetch_pending_approvals()` implementation:
   - Run: `gh issue list --repo <repo> --label "audit-pending-approval" --state open --json number,title,labels,body`
   - Parse JSON; for each issue:
     - Skip if no decision label (`audit-approve`, `audit-reject`, `audit-skip`) is applied
     - Construct Signal with:
       - `id = f"gh-issue:{number}"`
       - `source = "gh_issue"`
       - `kind = "pending_approval"`
       - `priority = 10`
       - `payload = {"issue_number": number, "title": title, "body": body, "labels": labels, "area_labels": [l for l in labels if l.startswith("area/")]}`
       - `created_utc = issue.createdAt`

4. `_fetch_doc_audits(weekly: bool)` implementation:
   - Filter: title starts with `"Doc audit:"` or `"Weekly doc audit —"`
   - Skip issues with `status:in-progress` label UNLESS stale-lock recovery applies (per data-model E-002 state transitions — for now, simple skip; recovery is WP06)
   - Construct Signal with kind `"doc_audit"` (priority 20) or `"weekly_doc_audit"` (priority 30)

5. Error handling:
   - If `subprocess.run` fails (gh auth issue, network), raise the exception — DO NOT swallow per signal-source contract anti-patterns.
   - If JSON parse fails on `gh` output, raise with a clear error message.

**Files**:
- New: `scripts/doc_audit/signals/gh_issue.py` (~200 lines)

**Validation**:
- [ ] `pending()` returns expected `Signal` list against mocked `subprocess.run`
- [ ] `commit()` is a no-op
- [ ] Empty queue returns `[]` (NOT raises)
- [ ] Multi-issue queue returns in unsorted order (driver does the sorting)

---

### T013 — Implement `DriftEventSignalSource`

**Purpose**: Adapter that wraps `helpers/handle_drift_events.py` to fit the SignalSource Protocol.

**Steps**:

1. Create `scripts/doc_audit/signals/drift_event.py`.

2. Class structure:
   ```python
   from doc_audit.signals.base import SignalSource
   from doc_audit.data_model import Signal, DriftEvent
   from doc_audit.config import Config
   from doc_audit.helpers.handle_drift_events import process_events, ProcessResult
   from pathlib import Path

   class DriftEventSignalSource:
       name = "drift_event"

       def __init__(self, config: Config) -> None:
           self.config = config
           self._cached: Optional[list[Signal]] = None

       def pending(self) -> list[Signal]:
           if self._cached is not None:
               return self._cached
           # Process drift events via the wrapped helper.
           # This files [doc-audit] issues for mapped events and writes
           # unmapped events to the unmapped log. The GH issues filed
           # become next-tick signals via GHIssueSignalSource.
           # Return Signal instances representing the drift events themselves
           # (not the resulting GH issues — those are GHIssueSignalSource's
           # responsibility).
           # The result here is the per-event log of what was processed this
           # tick; the driver records this in TickResult for cost accounting.
           # Cursor is NOT advanced until commit() — handled below.
           ...

       def commit(self, signal: Signal, outcome: str) -> None:
           # Advance the cursor by re-running process_events committing
           # only signals matching `signal.id`. Or, simpler: keep cursor
           # state in memory and persist on commit.
           ...
   ```

3. Implementation approach (recommended):
   - `pending()` reads `drift-events.jsonl` from the cursor position to EOF
   - For each new event:
     - Parse JSON into `DriftEvent` (data-model E-007)
     - Construct Signal with `kind = "drift_event"`, `priority = 40`, `payload = drift_event.to_dict()`
   - DO NOT advance the cursor in `pending()` (idempotency requirement)
   - The driver's processing loop will call `process_events()` (the helper's library function) on `commit()` to advance the cursor for that specific event

4. Alternative simpler approach (consider trade-off):
   - `pending()` calls `process_events(dry_run=True)` which returns the event count + classified mappings WITHOUT advancing the cursor or filing issues
   - `commit()` calls `process_events(dry_run=False)` for that single event, advancing the cursor
   - Pro: reuses existing helper logic; Con: double-traverses the file

5. Document the chosen approach in the module docstring + add a note explaining why.

**Files**:
- New: `scripts/doc_audit/signals/drift_event.py` (~150 lines)

**Validation**:
- [ ] `pending()` returns Signal list from a fixture drift-events.jsonl
- [ ] `pending()` is idempotent — second call returns same list (no double-advance of cursor)
- [ ] `commit()` advances the cursor exactly one event
- [ ] Missing drift-events.jsonl returns `[]` (NOT raises — drift events are optional)
- [ ] Missing cursor file is treated as cursor=0

---

### T014 [P] — Unit tests for `GHIssueSignalSource`

**Purpose**: Lock in adapter behavior against representative `gh` outputs.

**Steps**:

1. Create `tests/doc_audit/signals/__init__.py` (empty).

2. Create `tests/doc_audit/signals/test_gh_issue.py`:
   - **test_pending_empty_queue**: mock `gh issue list` returns `[]` → `pending()` returns `[]`
   - **test_pending_one_doc_audit**: mock returns 1 `Doc audit:` issue → `pending()` returns 1 Signal with kind `doc_audit`, priority 20
   - **test_pending_one_weekly**: mock returns 1 `Weekly doc audit —` issue → kind `weekly_doc_audit`, priority 30
   - **test_pending_pending_approval_with_decision**: mock returns 1 audit-pending-approval with `audit-approve` label → kind `pending_approval`, priority 10
   - **test_pending_pending_approval_without_decision**: mock returns 1 audit-pending-approval WITHOUT decision label → skipped (not in result)
   - **test_pending_skips_in_progress**: mock returns 1 `Doc audit:` with `status:in-progress` → skipped
   - **test_pending_idempotent**: `pending()` returns same list across two calls
   - **test_commit_noop**: `commit()` returns None and does not call gh
   - **test_pending_raises_on_gh_error**: mock raises subprocess.CalledProcessError → `pending()` re-raises

3. Use fixtures from `tests/doc_audit/fixtures/gh_responses/` (set up in WP02).

**Files**:
- New: `tests/doc_audit/signals/__init__.py`
- New: `tests/doc_audit/signals/test_gh_issue.py` (~250 lines)

**Validation**:
- [ ] All tests pass
- [ ] Coverage of `gh_issue.py` ≥85%

---

### T015 [P] — Unit tests for `DriftEventSignalSource`

**Purpose**: Lock in drift-event adapter behavior against fixture jsonl.

**Steps**:

1. Create `tests/doc_audit/signals/test_drift_event.py`:
   - **test_pending_empty_file**: cursor at 0, empty drift-events.jsonl → returns `[]`
   - **test_pending_one_event**: cursor at 0, file has 1 event → returns 1 Signal
   - **test_pending_skip_processed**: cursor at 5, file has 7 lines → returns 2 Signals (lines 6, 7)
   - **test_pending_idempotent**: `pending()` returns same list across calls
   - **test_commit_advances_cursor**: `pending()` → `commit(signal[0], "success")` → next `pending()` skips that event
   - **test_pending_handles_missing_file**: file doesn't exist → returns `[]`, no error
   - **test_pending_handles_missing_cursor**: cursor file absent → treats as 0
   - **test_commit_partial_writes_correctly**: cursor advance is atomic (tempfile + rename)

2. Use fixture `tests/doc_audit/fixtures/drift_events_sample.jsonl` (set up in WP01).

**Files**:
- New: `tests/doc_audit/signals/test_drift_event.py` (~200 lines)

**Validation**:
- [ ] All tests pass
- [ ] Coverage of `drift_event.py` ≥80%

---

## Definition of Done

- [ ] `SignalSource` Protocol implemented per contract
- [ ] Both adapters functional with appropriate priority assignments
- [ ] `pending()` is idempotent on both adapters
- [ ] `commit()` semantics correct for both
- [ ] Unit tests pass; coverage targets met
- [ ] Module docstrings cross-reference the contract file

## Risks

| Risk | Mitigation |
|---|---|
| Adapter behavior diverges from existing AGENTS.md §2 semantics | Match the existing `gh` query patterns from SKILL.md §3 + §8.6; smoke test against a real audit queue snapshot |
| `DriftEventSignalSource` double-processes events on retry | Cursor advance via `commit()` is the only state mutation; failed processing leaves cursor where it was |
| `GHIssueSignalSource` returns issues that should have been skipped (stale lock with no recovery) | This WP intentionally implements the SIMPLE skip; WP06 adds stale-lock recovery atop this base |

## Reviewer Guidance

- Confirm priority assignments (pending_approval=10, doc_audit=20, weekly_doc_audit=30, drift_event=40) match `data-model.md` E-001 and `contracts/signal-source.contract.md`
- Verify the `_cached` idempotency cache is reset only on a new adapter instance (i.e., per tick — driver instantiates fresh adapters per tick)
- Spot-check that NO adapter swallows credential errors (per anti-patterns in contract)
- Confirm `DriftEventSignalSource`'s wrapping of `handle_drift_events.py` does NOT subprocess-out — it imports per WP01's library surface

## Implementation Command

```bash
spec-kitty agent action implement WP03 --agent <name>
```

## Cross-references

- **Contract**: `contracts/signal-source.contract.md`
- **Data model**: E-001 Signal, E-002 AuditIssue, E-003 PendingApproval, E-007 DriftEvent
- **Research**: D4 (Signal-source adapter abstraction), D9 (Drift-event processing cadence)
- **Spec**: FR-001, FR-003, FR-004
