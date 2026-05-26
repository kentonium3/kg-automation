# Tasks: Documentation Developer Portal

**Mission**: documentation-developer-portal-01KSJ75K
**Date**: 2026-05-26
**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md)

**Branch contract**: planning/base = `main`; merge target = `main`; `branch_matches_target = true`.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Frontmatter reader + audience bucket assignment | WP01 | | [D] |
| T002 | Block emitter (sort, format, marker semantics) | WP01 | | [D] |
| T003 | Default mode (drift check, exit 0/1 with diff) | WP01 | | [D] |
| T004 | `--write` mode (rewrite block in place) | WP01 | | [D] |
| T005 | Error paths (exit 2/3/4 with clear messages) | WP01 | | [D] |
| T006 | Happy-path tests (clean / drift / `--write` regen) | WP01 | [D] |
| T007 | Bucket / sort / empty-bucket tests | WP01 | [D] |
| T008 | Error-case tests (missing portal / markers / fields / invalid enum) | WP01 | [D] |
| T009 | Author `docs/DEVELOPER_PORTAL.md` body (4 sections + marker pair) | WP02 | | [D] |
| T010 | Run `build_runbook_filter.py --write` to populate filter section | WP02 | | [D] |
| T011 | Extend `validate_docs.py` with portal drift check (gated on portal existing) | WP02 | | [D] |
| T012 | Add smoke test: validate_docs flags a tampered portal block | WP02 | | [D] |
| T013 | Add portal entry to `docs/INDEX.md` | WP03 | [P] |
| T014 | Add single additive pointer line to `CLAUDE.md` under "Architecture Documentation" | WP03 | [P] |
| T015 | Run full local verification (`pytest`, `validate_docs.py`, `git diff CLAUDE.md`) | WP03 | |

15 subtasks across 3 work packages. Dependencies: WP01 → WP02 → WP03 (sequential).

---

## Work Packages

### WP01 — Build runbook-filter helper script

**Goal**: Deliver `tooling/scripts/build_runbook_filter.py` per `contracts/build_runbook_filter.md`, with unit tests covering every contract row. The script is fully usable from a fresh checkout: contributors can run it without the portal existing yet (the next WP creates the portal).

**Priority**: P0 (foundational — WP02 and WP03 cannot proceed without it).

**Independent test**: Running `pytest tests/tooling/test_build_runbook_filter.py` passes all listed cases. The script can be invoked manually against synthetic fixtures.

**Subtasks** (8):

- [x] T001 Frontmatter reader + audience bucket assignment (WP01)
- [x] T002 Block emitter (sort, format, marker semantics) (WP01)
- [x] T003 Default mode (drift check, exit 0/1 with diff) (WP01)
- [x] T004 `--write` mode (rewrite block in place) (WP01)
- [x] T005 Error paths (exit 2/3/4 with clear messages) (WP01)
- [x] T006 Happy-path tests (clean / drift / `--write` regen) (WP01)
- [x] T007 Bucket / sort / empty-bucket tests (WP01)
- [x] T008 Error-case tests (missing portal / markers / fields / invalid enum) (WP01)

**Prompt**: [tasks/WP01-build-runbook-filter-script.md](tasks/WP01-build-runbook-filter-script.md) (estimated ~430 lines)

**Owned files**:
- `tooling/scripts/build_runbook_filter.py`
- `tests/tooling/test_build_runbook_filter.py`

**Dependencies**: none

**Parallel opportunities**: T006/T007/T008 can be drafted in parallel with each other once T001–T005 are in place.

**Risks**:
- YAML frontmatter parsing must match `validate_docs.py`'s strategy to avoid two divergent parsers. Mitigate by reusing PyYAML (already a transitive dependency of `validate_docs.py`).
- The audience enum must stay in sync with `validate_docs.py`'s `ALLOWED_VALUES['audience']`. Prefer importing it; if cyclic-import risk, replicate the literal set with a comment pointing back to the source of truth.

---

### WP02 — Wire portal + validation drift check

**Goal**: Author the portal markdown (Quick-Start, Execution Loop, Verification Quick-Reference, and the marker pair for the auto-generated filter), populate the filter section by running the helper script, and extend `validate_docs.py` so CI fails on stale portal blocks.

**Priority**: P1 (delivers the user-facing value once foundation is in place).

**Independent test**: Running `python tooling/scripts/validate_docs.py` against the freshly populated portal exits 0. Hand-tampering the block then re-running exits non-zero with the `run:` hint from the contract.

**Subtasks** (4):

- [x] T009 Author `docs/DEVELOPER_PORTAL.md` body (4 sections + marker pair) (WP02)
- [x] T010 Run `build_runbook_filter.py --write` to populate filter section (WP02)
- [x] T011 Extend `validate_docs.py` with portal drift check (gated on portal existing) (WP02)
- [x] T012 Add smoke test: validate_docs flags a tampered portal block (WP02)

**Prompt**: [tasks/WP02-portal-and-validation-drift.md](tasks/WP02-portal-and-validation-drift.md) (estimated ~380 lines)

**Owned files**:
- `docs/DEVELOPER_PORTAL.md`
- `tooling/scripts/validate_docs.py`
- `tests/tooling/test_validate_docs_portal_drift.py`

**Dependencies**: WP01

**Risks**:
- Execution Loop section is the highest-risk drift surface (C-005). Stay under 3 paragraphs, link aggressively, do not paraphrase the runbooks' content.
- Portal frontmatter must use a `doc_type` from the allowed enum. Plan recommends `index`.
- `validate_docs.py` drift hook must be a no-op when the portal does not exist (e.g., for older branches), or it'll break unrelated CI checks.

---

### WP03 — Register portal and update CLAUDE.md

**Goal**: Link the portal from `docs/INDEX.md`, add the single additive pointer in `CLAUDE.md`, and run the full local verification suite.

**Priority**: P1 (closes the loop — readers can find the portal from established entry points).

**Independent test**: After this WP, a reader opening `CLAUDE.md` and `docs/INDEX.md` finds the portal pointer in both. `git diff CLAUDE.md` shows only added lines. `python tooling/scripts/validate_docs.py` and `pytest` exit 0.

**Subtasks** (3):

- [ ] T013 Add portal entry to `docs/INDEX.md` (WP03)
- [ ] T014 Add single additive pointer line to `CLAUDE.md` under "Architecture Documentation" (WP03)
- [ ] T015 Run full local verification (`pytest`, `validate_docs.py`, `git diff CLAUDE.md`) (WP03)

**Prompt**: [tasks/WP03-register-and-pointer.md](tasks/WP03-register-and-pointer.md) (estimated ~250 lines)

**Owned files**:
- `docs/INDEX.md`
- `CLAUDE.md`

**Dependencies**: WP02

**Risks**:
- The `CLAUDE.md` edit is the load-bearing constraint of the mission. Any rephrasing of existing text fails review. Mitigation: implementer uses a single `Edit` operation with `old_string` being the surrounding section header context and `new_string` being the same plus the additive line — never re-types surrounding text from memory.

---

## Phase Summary

| Phase | WPs | Subtask count | Notes |
|---|---|---|---|
| Foundation | WP01 | 8 | Pure tooling — no doc changes |
| Wiring | WP02 | 4 | Portal + drift-check integration |
| Registration | WP03 | 3 | INDEX + CLAUDE.md + verification |

MVP scope = the entire mission (3 WPs); nothing in this mission is reasonably skippable.

## Next command

`/spec-kitty.implement` (or `spec-kitty next --agent <agent> --mission documentation-developer-portal-01KSJ75K`).
