# Tasks: Drift Ledger Retry Count Hardening

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ`
**Plan**: [plan.md](plan.md)
**Spec**: [spec.md](spec.md)
**Target branch**: `main`
**Risk tier**: 3 (Logic / Workflow)

This mission decomposes into **2 work packages** (9 subtasks total). WP01 is the code+test surface change. WP02 is the parallel doc-lift. They can run in either order because their owned files are disjoint.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Widen drift_ledger validator bound + update AuditLedgerEntry dataclass docstring (inline schema + reference to new live doc location) | WP01 | |
| T002 | Add defensive clamp at `signals/drift_event.py:464` | WP01 | |
| T003 | Update existing clamp at `helpers/handle_drift_events.py:643-645` to use new bound | WP01 | [P] |
| T004 | Update three existing test assertions that pin `retry_count` to old bound | WP01 | [P] |
| T005 | Add parametrized regression test in `tests/doc_audit/signals/test_drift_event.py` | WP01 | |
| T006 | Run full `pytest tests/doc_audit/` and confirm green | WP01 | |
| T007 | Create `docs/design/architecture/contracts/` dir + add `drift-ledger-schema.md` (lifted from kitty-specs archive with widened bound) | WP02 | [P] |
| T008 | Update `docs/design/architecture/README.md` to add contracts/ subdirectory to the index | WP02 | |
| T009 | Verify cross-link from `drift_ledger.py` docstring resolves to new contract doc | WP02 | |

**Note:** The `[P]` column flags subtasks that can run in parallel *within their WP*. The top-level cross-WP parallelism is already captured by WP01 and WP02 having disjoint owned files.

---

## Work Package 1 — Schema + Clamps + Tests (code surface)

- **Goal**: Re-align the drift-ledger schema bound with the retry policy. Widen the validator to `[0, retry_max]`, clamp both ledger-write sites, update existing test fixtures, and add the parametrized regression test that proves the integration.
- **Priority**: P1 (primary mission deliverable)
- **Independent test**: `pytest tests/doc_audit/` runs green, including the new parametrized regression test exercising `exc.attempts ∈ {0, 1, retry_max-1, retry_max}` through `drift_event.commit`.
- **Prompt**: [tasks/WP01-schema-clamps-tests.md](tasks/WP01-schema-clamps-tests.md)
- **Estimated prompt size**: ~450 lines
- **Dependencies**: none
- **Owned files**:
  - `scripts/doc_audit/output/drift_ledger.py`
  - `scripts/doc_audit/signals/drift_event.py`
  - `scripts/doc_audit/helpers/handle_drift_events.py`
  - `tests/doc_audit/output/test_drift_ledger.py`
  - `tests/doc_audit/signals/test_drift_event.py`
  - `tests/doc_audit/helpers/test_handle_drift_events.py`
- **Risks**:
  - **R1**: If the `RETRY_DELAYS_SECONDS` import creates a circular import (output → judgment), the bound derivation must move to a different module or use a lazy import. **Mitigation**: import inside `_validate_entry()` if needed; verify with a quick `python -c "from doc_audit.output.drift_ledger import _validate_entry"` smoke check after the change.
  - **R2**: Hidden test fixtures that assume `retry_count ≤ 3` may exist beyond the three grep'd lines. **Mitigation**: full pytest run before declaring done.

### Included subtasks

- [ ] T001 Widen drift_ledger validator bound + update AuditLedgerEntry dataclass docstring (WP01)
- [ ] T002 Add defensive clamp at signals/drift_event.py:464 (WP01)
- [ ] T003 Update existing clamp at helpers/handle_drift_events.py:643-645 to use new bound (WP01)
- [ ] T004 Update three existing test assertions that pin retry_count to old bound (WP01)
- [ ] T005 Add parametrized regression test in tests/doc_audit/signals/test_drift_event.py (WP01)
- [ ] T006 Run full pytest tests/doc_audit/ and confirm green (WP01)

### Implementation sketch

1. Widen the validator first (T001) — gates everything else.
2. Add and update clamps (T002, T003) — straightforward `min()` updates.
3. Update existing test fixtures (T004) — required to keep CI green before adding the new test.
4. Add the parametrized regression test (T005) — proves the end-to-end fix.
5. Run the suite (T006) — Definition of Done check.

T003 and T004 are independent of T001/T002 and can run in parallel within the same worktree if the implementer prefers.

---

## Work Package 2 — Lift Contract Doc to Live Arch Docs

- **Goal**: Create the live home for the drift-ledger schema contract at `docs/design/architecture/contracts/drift-ledger-schema.md` (sibling to `data/`), lifted from the kitty-specs archive with the widened bound applied. Update the architecture-docs README index. Establishes the pattern for future contract docs (audit-ledger, event format, signal maps).
- **Priority**: P1 (NFR-004 requires the schema reference doc to be updated)
- **Independent test**: The file exists at `docs/design/architecture/contracts/drift-ledger-schema.md`, line 23 of its row schema shows `retry_count` with bound `[0, retry_max]`, and the architecture README lists `contracts/`. The cross-link from `drift_ledger.py`'s dataclass docstring resolves to this file.
- **Prompt**: [tasks/WP02-contract-doc-lift.md](tasks/WP02-contract-doc-lift.md)
- **Estimated prompt size**: ~200 lines
- **Dependencies**: none (the cross-link target string is set by WP01's docstring update; both WPs can run in parallel since they own disjoint files; the link becomes resolvable once both merge)
- **Owned files**:
  - `docs/design/architecture/contracts/**` (new directory)
  - `docs/design/architecture/README.md`
- **Risks**:
  - **R1**: A future schema change might land in WP01's docstring inline but not propagate here. **Mitigation**: docstring's "See ..." note is short — the live doc is canonical; the docstring should be terse pointer text, not duplicated schema.

### Included subtasks

- [ ] T007 Create docs/design/architecture/contracts/ dir + add drift-ledger-schema.md (lifted from kitty-specs archive with widened bound) (WP02)
- [ ] T008 Update docs/design/architecture/README.md to add contracts/ subdirectory to the index (WP02)
- [ ] T009 Verify cross-link from drift_ledger.py docstring resolves to new contract doc (WP02)

### Implementation sketch

1. Lift the contract content (T007) — base source is `kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md`. Update line 23 (`retry_count` row) to `[0, retry_max]` and add the "Source-of-truth for `retry_max`" subsection. Add change history row.
2. Update the architecture README (T008) — add a brief entry for `contracts/` in the "Documents" table or as a new "Contracts" subsection.
3. Verify cross-link (T009) — manual check; ensure `scripts/doc_audit/output/drift_ledger.py`'s "See ..." reference resolves to the new file path. WP01 sets the link; this WP verifies it.

---

## Cross-WP Sequencing

- **Parallel-safe**: WP01 and WP02 own disjoint files. They can run in either order.
- **Co-merge desirable**: WP01 updates the "See ..." docstring reference to point at the WP02-created file. Until WP02 merges, that link is briefly stale. Aim to merge both in the same session.
- **Office2 verification** is operator work post-merge (per [quickstart.md](quickstart.md)) — not a WP.

---

## MVP Recommendation

The mission has no MVP slice — both WPs are required for the spec's success criteria (SC-001 through SC-006). WP01 alone fixes the crash and adds fidelity; WP02 alone is purely documentation. Both must land.

If forced to pick: **WP01 first** — it's the actual bug fix. The timer on office2 can be re-enabled after WP01 lands even if WP02 hasn't yet (the docstring just temporarily points at a not-yet-existing file).

---

## Requirement Coverage

To be registered via `spec-kitty agent tasks map-requirements --batch` after WP files are written.

**Planned mapping:**
- WP01 → FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, NFR-001, NFR-002, NFR-003, C-001, C-002, C-004, C-005, C-006
- WP02 → NFR-004, C-001, C-002, C-003

C-001 (scope limited to drift-ledger path), C-002 (no audit_ledger changes), and C-003 (no #404 investigation) apply globally to both WPs.

---

## Next Command

After this file and the two WP prompts are written: `spec-kitty agent mission finalize-tasks --mission drift-ledger-retry-count-hardening-01KSC6AJ --json` (commits everything and parses dependencies).
