# Tasks: Drift Interpretation Payload Capture

**Mission**: drift-interpretation-payload-capture-01KSEJD7
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Branch**: target=`main` | planning-base=`main` | merge-target=`main`

---

## Subtask Index

| ID    | Description                                                                                | WP   | Parallel |
|-------|--------------------------------------------------------------------------------------------|------|----------|
| T001  | Pull main to office2; verify `_log_raw_response_if_debug` present in deployed module        | WP01 |          | [D] |
| T002  | Add `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` via systemd drop-in (non-interactive)                | WP01 |          | [D] |
| T003  | Trigger one tick; extract captured payload from journalctl                                  | WP01 |          | [D] |
| T004  | Author `docs/diagnostics/drift-interpretation-payload-shape.md` with sanitized analysis     | WP01 |          | [D] |
| T005  | Add short env-var note to `docs/runbooks/doc-auditor-driver-ops.md`                          | WP01 |          | [D] |
| T006  | Remove drop-in; verify clean state; confirm timer still disabled                             | WP01 |          | [D] |
| T007  | Close #404 with diagnostic doc link; file follow-up fix issue if needed                      | WP01 |          | [D] |

Total: 7 subtasks in 1 work package.

---

## Work Packages

### WP01 — Deploy + capture + document + close #404

**Goal**: Complete the operational + documentation arc that mission #53's canceled WP02 was scoped to do, now that #53's code change has merged to main.

**Priority**: P0.

**Independent test**: `docs/diagnostics/drift-interpretation-payload-shape.md` exists on main with all mandatory sections filled; `docs/runbooks/doc-auditor-driver-ops.md` has the new env-var note; office2 is clean (no env var, timer disabled); #404 is closed with the right cross-references.

#### Included subtasks

- [x] T001 Pull main to office2; verify `_log_raw_response_if_debug` present in deployed module (WP01)
- [x] T002 Add `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` via systemd drop-in (non-interactive) (WP01)
- [x] T003 Trigger one tick; extract captured payload from journalctl (WP01)
- [x] T004 Author `docs/diagnostics/drift-interpretation-payload-shape.md` with sanitized analysis (WP01)
- [x] T005 Add short env-var note to `docs/runbooks/doc-auditor-driver-ops.md` (WP01)
- [x] T006 Remove drop-in; verify clean state; confirm timer still disabled (WP01)
- [x] T007 Close #404 with diagnostic doc link; file follow-up fix issue if needed (WP01)

#### Dependencies

None. (The prerequisite — mission #53's WP01 merged to main — is already satisfied by commit `fbfe2a0f`.)

#### Estimated prompt size

~280 lines.

---

## Size Validation

| WP   | Subtasks | Est. lines | Within ideal range? |
|------|----------|-----------|---------------------|
| WP01 | 7        | ~280      | ✓                   |

---

## MVP Scope

Mission delivers value only on full completion of WP01.

---

## Next Suggested Command

`/spec-kitty.implement` (after finalize-tasks).
