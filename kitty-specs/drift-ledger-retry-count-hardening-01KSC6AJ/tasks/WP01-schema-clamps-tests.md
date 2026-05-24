---
work_package_id: WP01
title: Schema validator widening + clamp updates + test fixtures + regression test
dependencies: []
requirement_refs:
- C-001
- C-002
- C-004
- C-005
- C-006
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-drift-ledger-retry-count-hardening-01KSC6AJ
base_commit: 42dcab1d3548656c289126d4bac1c9788d9bbdf7
created_at: '2026-05-24T05:48:16.358824+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: '98779'
history: []
authoritative_surface: scripts/doc_audit/output/
execution_mode: code_change
mission_id: 01KSC6AJ2JK8N2NJT4QB6AB36Z
mission_slug: drift-ledger-retry-count-hardening-01KSC6AJ
owned_files:
- scripts/doc_audit/output/drift_ledger.py
- scripts/doc_audit/signals/drift_event.py
- scripts/doc_audit/helpers/handle_drift_events.py
- tests/doc_audit/output/test_drift_ledger.py
- tests/doc_audit/signals/test_drift_event.py
- tests/doc_audit/helpers/test_handle_drift_events.py
tags: []
---

# WP01 — Schema + Clamps + Tests

## Objective

Re-align the drift-ledger schema bound with the retry policy. The validator currently enforces `retry_count ∈ [0, 3]` while the retry policy attempts up to 4 calls. When retries exhaust, `signals/drift_event.py:464` hands the unclamped value through to the validator, which raises `ValueError` and crashes the drift event. This WP:

1. Widens the validator bound to `[0, retry_max]` where `retry_max = 1 + len(RETRY_DELAYS_SECONDS)` (currently 4).
2. Adds a defensive clamp at the bug site (`signals/drift_event.py:464`).
3. Updates the sister clamp at `helpers/handle_drift_events.py:643-645` so both write paths can record the actual attempt count (otherwise fidelity is only half-met).
4. Updates three existing tests that pin `retry_count = 3` or `retry_count = 4` as expected values, so CI stays green.
5. Adds a parametrized regression test that exercises the full `drift_event.commit` ledger-write path with `exc.attempts ∈ {0, 1, retry_max-1, retry_max}` and asserts no `ValueError`.
6. Runs the full `tests/doc_audit/` suite.

The change is **additive**: existing on-disk rows with `retry_count ∈ [0, 3]` continue to validate. No schema_version bump.

## Context (read first)

- **Spec**: [../spec.md](../spec.md) — full requirements with FR/NFR/C tables and success criteria
- **Plan**: [../plan.md](../plan.md) — implementation approach
- **Research**: [../research.md](../research.md) — Decision/Rationale for every choice, especially Decision 1 (retry_max source-of-truth) and Decision 4 (second clamp finding)
- **Data model**: [../data-model.md](../data-model.md) — `AuditLedgerEntry` post-fix schema
- **Contract preview**: [../contracts/drift-ledger-schema.md](../contracts/drift-ledger-schema.md) — what WP02 will create at `docs/design/architecture/contracts/drift-ledger-schema.md`

## Branch Strategy

- Planning branch: `main`
- Final merge target: `main`
- Worktree allocated per `lanes.json` at implementation time

## Subtasks

### T001 — Widen validator bound + update dataclass docstring

**File**: `scripts/doc_audit/output/drift_ledger.py`

**Changes:**

1. Import `RETRY_DELAYS_SECONDS` from `doc_audit.judgment.drift_interpretation`. Prefer top-of-module import; if it creates a circular import, move it inside `_validate_entry()` as a function-local import (verify with a one-line `python -c "from doc_audit.output.drift_ledger import _validate_entry"` smoke check).

2. Derive `RETRY_MAX_ATTEMPTS` (module-level constant) as `1 + len(RETRY_DELAYS_SECONDS)`. The `+1` accounts for the initial (zero-delay) call.

3. Update `_validate_entry()` retry_count check (currently lines 222-225):
   ```python
   # BEFORE
   if entry.retry_count < 0 or entry.retry_count > 3:
       raise ValueError(
           f"retry_count must be in [0, 3]; got {entry.retry_count!r}"
       )

   # AFTER
   if entry.retry_count < 0 or entry.retry_count > RETRY_MAX_ATTEMPTS:
       raise ValueError(
           f"retry_count must be in [0, {RETRY_MAX_ATTEMPTS}]; "
           f"got {entry.retry_count!r}"
       )
   ```

4. Update the `AuditLedgerEntry` dataclass docstring (currently at line 140-147) to:
   - Inline-document the schema (one-paragraph summary of fields + invariants)
   - Replace the `See contracts/ledger-schema.md` line with `See docs/design/architecture/contracts/drift-ledger-schema.md` (the live location that WP02 creates)

**Verification:**
- `python -c "from doc_audit.output.drift_ledger import _validate_entry; print('ok')"` exits 0
- `python -c "from doc_audit.output.drift_ledger import RETRY_MAX_ATTEMPTS; print(RETRY_MAX_ATTEMPTS)"` prints `4`

### T002 — Defensive clamp at `signals/drift_event.py:464`

**File**: `scripts/doc_audit/signals/drift_event.py`

**Change** (currently around line 464):

```python
# BEFORE
retry_count=getattr(exc, "attempts", 3),

# AFTER
retry_count=max(0, min(RETRY_MAX_ATTEMPTS, int(getattr(exc, "attempts", 0)))),
```

Import `RETRY_MAX_ATTEMPTS` from `doc_audit.output.drift_ledger` at the top of the file (the file already imports `AuditLedgerEntry` from the same module).

**Why the changed default**: the original default `3` was a magic number tied to the old clamp. With the bound widened, defaulting to `0` (then clamped through `min/max`) is cleaner — `0` means "we don't actually know how many attempts happened," which is the safest fallback when `exc.attempts` is missing.

### T003 — Update sister clamp at `helpers/handle_drift_events.py:643-645`

**File**: `scripts/doc_audit/helpers/handle_drift_events.py`

**Change** (currently around lines 643-645):

```python
# BEFORE
attempts = getattr(exc, "attempts", 3) or 3
# Clamp retry_count to the ledger schema's [0, 3] bound.
retry_count = min(3, max(0, int(attempts)))

# AFTER
attempts = getattr(exc, "attempts", 0)
# Clamp retry_count to the ledger schema's [0, RETRY_MAX_ATTEMPTS] bound.
retry_count = min(RETRY_MAX_ATTEMPTS, max(0, int(attempts)))
```

Import `RETRY_MAX_ATTEMPTS` from `doc_audit.output.drift_ledger`. The `attempts = getattr(...) or 3` idiom was masking missing-attribute cases as `3`; the new default `0` is honest.

### T004 — Update three existing test assertions

These tests correctly encoded the old contract. They ride along with the schema widening.

**File 1**: `tests/doc_audit/output/test_drift_ledger.py`

Around line 305-308 (`test_append_rejects_out_of_range_retry_count`):

```python
# BEFORE
def test_append_rejects_out_of_range_retry_count(tmp_path: Path) -> None:
    """retry_count outside [0, 3] is rejected by validator."""
    bad = _make_entry(retry_count=4)
    with pytest.raises(ValueError, match="retry_count must be in"):

# AFTER
def test_append_rejects_out_of_range_retry_count(tmp_path: Path) -> None:
    """retry_count outside [0, RETRY_MAX_ATTEMPTS] is rejected by validator."""
    from doc_audit.output.drift_ledger import RETRY_MAX_ATTEMPTS
    bad = _make_entry(retry_count=RETRY_MAX_ATTEMPTS + 1)
    with pytest.raises(ValueError, match="retry_count must be in"):
```

The match pattern `"retry_count must be in"` still works without modification because the new ValueError message preserves that prefix.

**File 2**: `tests/doc_audit/signals/test_drift_event.py`

Around line 925:

```python
# BEFORE
assert entry.retry_count == 3

# AFTER
assert entry.retry_count == 4
```

This test exercises the retry-exhaustion path. Pre-fix, the value was silently clamped to 3. Post-fix, it records the actual attempt count (4).

**File 3**: `tests/doc_audit/helpers/test_handle_drift_events.py`

Around line 1076:

```python
# BEFORE
assert row["retry_count"] == 3

# AFTER
assert row["retry_count"] == 4
```

Same reasoning — the sister code path now also records the actual attempt count.

### T005 — Add parametrized regression test

**File**: `tests/doc_audit/signals/test_drift_event.py`

Add a new test (place near the existing retry-exhaustion test):

```python
import pytest

from doc_audit.output.drift_ledger import RETRY_MAX_ATTEMPTS


@pytest.mark.parametrize(
    "attempts",
    [0, 1, RETRY_MAX_ATTEMPTS - 1, RETRY_MAX_ATTEMPTS],
)
def test_drift_event_commit_records_actual_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attempts: int,
) -> None:
    """Regression for #403.

    The full drift_event.commit ledger-write path must complete without
    raising for any attempts count in [0, RETRY_MAX_ATTEMPTS], and the
    persisted retry_count must equal the input.
    """
    # ... arrange a drift event with a stubbed DriftInterpretationError
    # whose .attempts is `attempts`. Use the existing test fixtures and
    # mocks from this file's test setup.
    # ... call the drift_event commit / retry-exhaust path
    # ... read the ledger row back and assert retry_count == attempts
```

Use the existing test setup helpers in this file as a template. The test should NOT mock the validator — it must exercise the real `_validate_entry()` to catch any future bound/policy drift.

**Acceptance**: all four parametrized cases pass. Removing the clamp in T002 (revert temporarily) should make the `RETRY_MAX_ATTEMPTS` case fail with `ValueError` — that's how you confirm the test catches the original bug.

### T006 — Run pytest and confirm green

```bash
pytest tests/doc_audit/ -v
```

Expected: all tests pass, including the new parametrized regression test.

If any test fails that isn't on the explicit update list above, it's hiding an assumption about the old bound somewhere — investigate before forcing the value.

## Definition of Done

- [ ] T001 complete — validator widened; docstring updated; `RETRY_MAX_ATTEMPTS` derivable
- [ ] T002 complete — `signals/drift_event.py:464` clamps the value
- [ ] T003 complete — `helpers/handle_drift_events.py:643-645` clamp uses new bound
- [ ] T004 complete — three existing test assertions updated and pass
- [ ] T005 complete — parametrized regression test added and passes
- [ ] T006 complete — `pytest tests/doc_audit/` green (no new failures)
- [ ] No on-disk JSON format change (NFR-001 — verify by reading any existing ledger row from a fixture and confirming it still parses)
- [ ] No circular-import regression

## Risks and Mitigations

- **R1: Circular import** (`output/drift_ledger.py` ← `judgment/drift_interpretation.py`). The judgment module already imports from output paths elsewhere, so this might cycle. **Mitigation**: use function-local import inside `_validate_entry()`. Smoke-test with `python -c "from doc_audit.output.drift_ledger import _validate_entry"`.

- **R2: Hidden test fixtures**. The 3 updates above are from grep; a manually-constructed fixture somewhere might assume `retry_count ≤ 3`. **Mitigation**: full pytest run; investigate any unexpected failure rather than mechanically updating.

- **R3: NFR-001 (no on-disk JSON change)**. The widening is additive but worth confirming. **Mitigation**: include a test fixture that loads a known pre-existing ledger row (or constructs one mimicking the on-disk shape) and asserts it still validates.

## Reviewer Guidance

- Confirm `RETRY_MAX_ATTEMPTS` is derived (not hardcoded to `4`)
- Confirm both write sites clamp; not just the bug site
- Confirm the new regression test would fail if the clamp at `signals/drift_event.py:464` is reverted (this proves it catches the original bug)
- Confirm the dataclass docstring's "See ..." reference points at the new live location (even though WP02 hasn't necessarily landed yet — the link is forward-referencing)
- Confirm pytest output shows 0 failures, 0 errors

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission drift-ledger-retry-count-hardening-01KSC6AJ --agent claude:opus:python-implementer:implementer
```

(Or use whichever agent profile is appropriate. Codex with `-p spec-kitty-review` for review, per [[codex_speckitty_profile]] memory note.)
