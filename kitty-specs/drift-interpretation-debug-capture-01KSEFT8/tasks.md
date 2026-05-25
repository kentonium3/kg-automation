# Tasks: Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Branch**: target=`main` | planning-base=`main` | merge-target=`main`

---

## Subtask Index

| ID    | Description                                                                                | WP   | Parallel |
|-------|--------------------------------------------------------------------------------------------|------|----------|
| T001  | Add module-level logger setup if not already present                                       | WP01 |          |
| T002  | Add `_log_raw_response_if_debug` helper function                                            | WP01 |          |
| T003  | Wire helper into every `_RetrySchemaError` raise site in `_parse_verdict`                  | WP01 |          |
| T004  | Unit tests for AS1 + AS2 + AS3 (env-var on/off + valid response behaviors)                  | WP01 |          |
| T005  | Parametrized unit test for AS4 (each raise site captures correctly)                         | WP01 |          |
| T006  | Confirm full test suite passes; commit; transition WP01 → for_review                        | WP01 |          |
| T007  | Pull `main` to office2; verify new helper symbol present                                   | WP02 |          |
| T008  | Add `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` env var on office2 via systemctl --user edit drop-in | WP02 |          |
| T009  | Trigger one tick; extract captured raw payload from journalctl                             | WP02 |          |
| T010  | Author `docs/diagnostics/drift-interpretation-payload-shape.md` with findings              | WP02 |          |
| T011  | Add one-line note about env var to `docs/runbooks/doc-auditor-driver-ops.md`                | WP02 |          |
| T012  | Disable env var on office2; verify clean state; confirm timer still disabled               | WP02 |          |
| T013  | Close #404 with summary comment + diagnostic doc link; file follow-up fix issue if needed  | WP02 |          |

Total: 13 subtasks across 2 work packages. No parallelizable subtasks within either WP (each subtask depends on the previous).

---

## Work Packages

### WP01 — Add env-var-gated debug capture to `_parse_verdict`

**Goal**: Ship a non-disruptive code change to `scripts/doc_audit/judgment/drift_interpretation.py` that captures the raw 200-OK LLM response body to stderr (WARNING level) at each `_RetrySchemaError` raise site, gated by the `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` env var. Pair the change with unit tests covering AS1–AS4.

**Priority**: P0 (blocks WP02).

**Independent test**: `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` passes locally with the new tests and all pre-existing tests still green.

#### Included subtasks

- [ ] T001 Add module-level logger setup if not already present (WP01)
- [ ] T002 Add `_log_raw_response_if_debug` helper function (WP01)
- [ ] T003 Wire helper into every `_RetrySchemaError` raise site in `_parse_verdict` (WP01)
- [ ] T004 Unit tests for AS1 + AS2 + AS3 (env-var on/off + valid response behaviors) (WP01)
- [ ] T005 Parametrized unit test for AS4 (each raise site captures correctly) (WP01)
- [ ] T006 Confirm full test suite passes; commit; transition WP01 → for_review (WP01)

#### Implementation sketch

1. Open `scripts/doc_audit/judgment/drift_interpretation.py`. Confirm the existing `import logging` and `logger = logging.getLogger(__name__)` setup (add if missing).
2. Add `_log_raw_response_if_debug(response_text: str, error_message: str) -> None` as a module-level helper near the other helpers.
3. Inside `_parse_verdict`, immediately before each `raise _RetrySchemaError(...)`, call `_log_raw_response_if_debug(response_text, "<message>")` with the response body and the error message. The response body variable name is `response_text` in the source — verify during implementation.
4. Add tests in `tests/doc_audit/judgment/test_drift_interpretation.py` using the existing mock pattern (see sibling tests in `test_audit_interpretation.py` or `test_drift_interpretation.py` for the established pattern).
5. Run the full test suite: `pytest tests/doc_audit/judgment/ -v`. Must be green.
6. Commit and transition to for_review.

#### Parallel opportunities

None within this WP. The subtasks are sequential (T002 depends on T001; T003 depends on T002; tests depend on the code).

#### Dependencies

None (this is the root WP).

#### Risks

- The response body variable name inside `_parse_verdict` may not be `response_text` everywhere — the implementer must confirm and adjust capture calls accordingly.
- A few raise sites may sit inside helper functions called from `_parse_verdict` (rather than the function body itself). Implementer must trace each raise site to its actual response-body context and pass the right value.
- The existing test suite may have brittle assertions about log behavior at `WARNING` level (sibling tests sometimes assert "no warnings emitted"). Implementer must check and update such assertions to use the env-var-gating pattern.

#### Estimated prompt size

~280 lines.

---

### WP02 — Deploy + capture payload + document findings + close #404

**Goal**: Operationalize the WP01 code change. Pull `main` to office2, set the debug env var for one tick, capture a real drift-event payload from `journalctl`, author the diagnostic doc with root-cause analysis, update the runbook, disable the env var, and close #404 with the findings.

**Priority**: P0 (closes the mission).

**Independent test**: `docs/diagnostics/drift-interpretation-payload-shape.md` exists on `main` with sections "Captured payload", "Raise-site", "Root-cause hypothesis", and "Recommended follow-up". GitHub issue #404 is closed with a comment linking to the diagnostic doc.

#### Included subtasks

- [ ] T007 Pull `main` to office2; verify new helper symbol present (WP02)
- [ ] T008 Add `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` env var on office2 via systemctl --user edit drop-in (WP02)
- [ ] T009 Trigger one tick; extract captured raw payload from journalctl (WP02)
- [ ] T010 Author `docs/diagnostics/drift-interpretation-payload-shape.md` with findings (WP02)
- [ ] T011 Add one-line note about env var to `docs/runbooks/doc-auditor-driver-ops.md` (WP02)
- [ ] T012 Disable env var on office2; verify clean state; confirm timer still disabled (WP02)
- [ ] T013 Close #404 with summary comment + diagnostic doc link; file follow-up fix issue if needed (WP02)

#### Implementation sketch

Follow [quickstart.md](quickstart.md) step by step. The 10-step runbook there IS the implementation plan for this WP — the WP prompt repeats it with WP-specific framing.

#### Parallel opportunities

T010 (author diagnostic) and T011 (one-line runbook note) could be done in parallel if implementer is splitting attention, but neither is large enough to make parallelism worthwhile. Sequential is fine.

#### Dependencies

Depends on WP01 (must be merged to `main` before T007 can pull a tree that includes the helper).

#### Risks

- Office2 ssh may fail if Tailscale is down. Retry; if persistent, the WP stalls until connectivity returns.
- The tick may not encounter a drift-eligible commit (unlikely given the current backlog, but possible). If no drift event fires during the tick, trigger again after a known drift-eligible commit lands on `main` (any commit touching `docs/` or `scripts/` content that the auditor inspects).
- The captured payload may exceed 4096 bytes by enough that key diagnostic signal is truncated. If so, implementer bumps the truncation limit and re-runs.
- The diagnostic may reveal a non-trivial root cause (e.g., model behavior change). The WP still closes by recording the finding; the follow-up fix is a separate mission.

#### Estimated prompt size

~320 lines.

---

## Size Validation

| WP    | Subtasks | Estimated lines | Within ideal range? |
|-------|----------|-----------------|---------------------|
| WP01  | 6        | ~280            | ✓ (3–7 subtasks, 200–500 lines) |
| WP02  | 7        | ~320            | ✓ (3–7 subtasks, 200–500 lines) |

Both WPs fit the ideal envelope. No splits or merges needed.

---

## MVP Scope

WP01 alone is **not** an MVP — the mission's value lands only with WP02's diagnostic capture. The mission's MVP is the full WP01 + WP02 sequence. WP01 is the precondition; WP02 is where the user-visible diagnostic record is produced.

---

## Next Suggested Command

`/spec-kitty.implement` (this command stops here; the implement command drives WP execution).
