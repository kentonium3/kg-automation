# Tasks: Atomic in-place inbox finalize (mark_processed hardening)

**Mission**: `finalize-inbox-file-01KW8MSQ` · **Issue**: #325 · **Branch**: `feat/finalize-inbox-file-v2`

3 work packages, 13 subtasks. WP01 is foundational; WP02 and WP03 each depend on
WP01's exit-code contract and run in parallel (distinct file domains, no overlap).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Add inbox-root validation (exit 1 outside root) | WP01 | |
| T002 | Wrap atomic write → catch OSError, exit 2 + stderr JSON | WP01 | |
| T003 | Emit single-line JSON on stdout on success | WP01 | |
| T004 | Preserve guarantees; update docstring exit table to 0/1/2/3 | WP01 | |
| T005 | Extend `test_mark_processed.py` for the new contract | WP01 | |
| T006 | Full `pytest tests/inbox/` green, no regressions | WP01 | |
| T007 | Step 5c exit-code handling table (0/1/2/3 → action) | WP02 | [P] |
| T008 | Reaffirm "do NOT move" invariant tied to the helper | WP02 | [P] |
| T009 | Surface-on-nonzero note; verify no stale inline-Edit refs | WP02 | [P] |
| T010 | Update `service-inventory.json` felix-admin-capture entry | WP03 | [P] |
| T011 | Update `service-inventory.md` narrative counterpart | WP03 | [P] |
| T012 | Review/update `audited-surfaces.json` mapping | WP03 | [P] |
| T013 | Review `openclaw-agent-setup.md` + `agent-prompt-sync-ops.md` | WP03 | [P] |

---

## WP01 — Harden `mark_processed.py` + tests

**Goal**: Close the silent-finalize-failure class in the existing helper — add the
exit-2 filesystem-error path, single-line JSON stdout, and inbox-root validation,
without weakening atomicity/idempotency/round-trip. **Priority**: P1 (foundational).
**Independent test**: `pytest tests/inbox/ -v` green, with new coverage for the
five outcomes (happy/idempotent/validation/fs-fail/private).
**Dependencies**: none. **Requirements**: FR-001, FR-002, FR-003, FR-004; NFR-003, NFR-004.
**Prompt**: [tasks/WP01-harden-mark-processed.md](tasks/WP01-harden-mark-processed.md) (~320 lines). Est. 6 subtasks.

- [ ] T001 Add inbox-root validation via `prescan.resolve_registry()`; path outside root → exit 1 (WP01)
- [ ] T002 Wrap the atomic write; catch `OSError` → exit 2 + `{"error":"fs_error",...}` on stderr; original uncorrupted (WP01)
- [ ] T003 Print single-line success JSON on stdout (finalized/already_processed/status/file_final_path) (WP01)
- [ ] T004 Preserve atomicity/idempotency/round-trip/exit-3; update module docstring exit table to 0/1/2/3 (WP01)
- [ ] T005 Extend `tests/inbox/test_mark_processed.py`: exit-2 perm-denied (root-skip) + uncorrupted, exit-2 mocked replace, exit-1 outside-root, stdout JSON shape (WP01)
- [ ] T006 Run full `pytest tests/inbox/ -v` — green, no regression in existing tests (WP01)

---

## WP02 — `felix-admin-capture` Step 5c cutover

**Goal**: Give Step 5c explicit exit-code handling so a non-zero finalize is
surfaced/escalated, not silently continued; retain the "do NOT move" invariant.
**Priority**: P1. **Independent test**: AGENTS.md Step 5c documents the 0/1/2/3 →
action mapping and reaffirms the invariant; no stale inline-Edit finalize references.
**Dependencies**: WP01. **Requirements**: FR-005.
**Prompt**: [tasks/WP02-step5c-cutover.md](tasks/WP02-step5c-cutover.md) (~210 lines). Est. 3 subtasks.

- [ ] T007 Add an exit-code handling table to Step 5c: 0→proceed, 1→surface validation, 2→surface/escalate, 3→skip private (WP02)
- [ ] T008 Reaffirm "do NOT move; preserve in 01-Inbox/" invariant, tied to the helper call (WP02)
- [ ] T009 Add "a non-zero finalize must be surfaced" note; verify no stale inline-`Edit` finalize references remain (WP02)

---

## WP03 — Required architecture/doc updates

**Goal**: Land the `agent-prompt-changed` doc-map updates so the finalize contract
change is reflected in the architecture record. **Priority**: P2. **Independent
test**: service-inventory JSON+md reflect the error-surfacing finalize; audited-
surfaces + runbooks reviewed; architecture-data validator passes.
**Dependencies**: WP01. **Requirements**: FR-006.
**Prompt**: [tasks/WP03-architecture-doc-updates.md](tasks/WP03-architecture-doc-updates.md) (~230 lines). Est. 4 subtasks.

- [ ] T010 Update `service-inventory.json` felix-admin-capture entry (finalize now error-surfacing; depends_on mark_processed) (WP03)
- [ ] T011 Update `service-inventory.md` narrative counterpart to match (WP03)
- [ ] T012 Review/update `audited-surfaces.json` agent-prompt surface mapping (gap #621 context; no fabrication) (WP03)
- [ ] T013 Review `openclaw-agent-setup.md` + `agent-prompt-sync-ops.md`; record rebaseline-not-required reasoning (WP03)

---

## Dependencies

```
WP01 (foundational)
 ├── WP02 (Step 5c cutover)        [parallel with WP03]
 └── WP03 (architecture/docs)      [parallel with WP02]
```

## MVP scope

WP01 alone closes the silent-failure class at the helper level (SC-001/002/003).
WP02 wires the orchestrator to act on it; WP03 keeps the architecture record honest.
