# Tasks: Drift Interpretation Fence Strip Fix

**Mission**: drift-interpretation-fence-strip-fix-01KSEM6S
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Branch**: target=`main` | planning-base=`main` | merge-target=`main`

---

## Subtask Index

| ID    | Description                                                                                | WP   | Parallel |
|-------|--------------------------------------------------------------------------------------------|------|----------|
| T001  | Add `_strip_code_fence(text: str) -> str` helper                                            | WP01 |          | [D] |
| T002  | Wire helper into `_parse_verdict` immediately before `json.loads()`                         | WP01 |          | [D] |
| T003  | Add unit tests for AS1 + AS2 + AS3 (fenced w/ hint, fenced w/o hint, unfenced)              | WP01 |          | [D] |
| T004  | Add unit tests for AS4 + edge cases (EC1 empty-after-strip, EC2 multi-fence, EC4 trailing)  | WP01 |          | [D] |
| T005  | Run full `pytest tests/doc_audit/ -v`; commit; transition WP01 → for_review                 | WP01 |          | [D] |

Total: 5 subtasks in 1 work package.

---

## Work Packages

### WP01 — Add fence-stripping helper to `_parse_verdict`

**Goal**: Restore drift-interpretation success rate by stripping markdown code fences before `json.loads()`.

**Independent test**: `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` passes with the new tests and all pre-existing tests still green.

#### Included subtasks

- [x] T001 Add `_strip_code_fence(text: str) -> str` helper (WP01)
- [x] T002 Wire helper into `_parse_verdict` immediately before `json.loads()` (WP01)
- [x] T003 Add unit tests for AS1 + AS2 + AS3 (WP01)
- [x] T004 Add unit tests for AS4 + edge cases (WP01)
- [x] T005 Run full pytest; commit; transition WP01 → for_review (WP01)

#### Dependencies

None.

#### Estimated prompt size

~250 lines.

---

## Size Validation

| WP   | Subtasks | Est. lines | Within ideal range? |
|------|----------|-----------|---------------------|
| WP01 | 5        | ~250      | ✓                   |

---

## Next Suggested Command

`/spec-kitty.implement` (after finalize-tasks).
