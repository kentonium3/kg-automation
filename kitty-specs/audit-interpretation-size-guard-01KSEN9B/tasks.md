# Tasks: Audit Interpretation Size Guard

**Mission**: audit-interpretation-size-guard-01KSEN9B
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Branch**: target=`main` | planning-base=`main` | merge-target=`main`

---

## Subtask Index

| ID    | Description                                                                          | WP   | Parallel |
|-------|--------------------------------------------------------------------------------------|------|----------|
| T001  | Add `INPUT_TOKEN_GUARD_THRESHOLD` constant + `_estimate_input_tokens(text)` helper    | WP01 |          | [D] |
| T002  | Insert size-guard check in `_interpret_one_doc()` between `_build_prompt` and call     | WP01 |          | [D] |
| T003  | Unit tests for AS1 + AS2 (over-threshold short-circuit; under-threshold proceeds)     | WP01 |          | [D] |
| T004  | Unit tests for AS3 + AS4 + AS5 (estimator conservatism; verdict shape parity; constant) | WP01 |          | [D] |
| T005  | Run `pytest tests/doc_audit/ -v`; commit; transition WP01 → for_review                | WP01 |          | [D] |

Total: 5 subtasks in 1 work package.

---

## Work Packages

### WP01 — Add size guard to `_interpret_one_doc`

**Goal**: Stop API budget burn on oversized-commit audits by short-circuiting to a synthetic `JUDGMENT_REQUIRED` before the LLM call.

**Independent test**: `pytest tests/doc_audit/judgment/test_audit_interpretation.py -v` passes with the new tests and all pre-existing tests still green.

#### Included subtasks

- [x] T001 Add `INPUT_TOKEN_GUARD_THRESHOLD` constant + `_estimate_input_tokens` helper (WP01)
- [x] T002 Insert size-guard check in `_interpret_one_doc()` (WP01)
- [x] T003 Unit tests for AS1 + AS2 (WP01)
- [x] T004 Unit tests for AS3 + AS4 + AS5 (WP01)
- [x] T005 Pytest + commit + transition WP01 (WP01)

#### Dependencies

None.

#### Estimated prompt size

~280 lines.

---

## Size Validation

| WP   | Subtasks | Est. lines | Within ideal range? |
|------|----------|-----------|---------------------|
| WP01 | 5        | ~280      | ✓                   |

---

## Next Suggested Command

`/spec-kitty.implement` (after finalize-tasks).
