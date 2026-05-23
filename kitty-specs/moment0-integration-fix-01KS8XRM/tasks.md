# Tasks: Fix Moment 0 wiring — integrate at signals adapter

**Mission**: `moment0-integration-fix-01KS8XRM`
**Mission ID**: `01KS8XRMC0EQZ8HCJ52GXCJ226`
**Branch**: `main`
**Generated**: 2026-05-22

3 work packages, 13 subtasks. Focused refactor + integration mission.

## Subtask Index

| ID | Description | WP |
|---|---|---|
| T001 | Create `routing/drift_moment0.py` with `route_drift_event()` + `RoutingOutcome` dataclass; promote helpers from `handle_drift_events.py` | WP01 | [D] |
| T002 | Refactor `handle_drift_events.py::process_events()` to call `route_drift_event()`; remove inlined Moment 0 helpers; preserve ledger append + RETRY_EXHAUSTED fallback semantics | WP01 | [D] |
| T003 | Update `routing/__init__.py` to export `route_drift_event` + `RoutingOutcome` | WP01 | [D] |
| T004 | Tests for new shared helper — all 6 verdict paths + retry exhaustion + ledger append + RoutingOutcome shape; ≥85% coverage | WP01 | [D] |
| T005 | Update existing `test_handle_drift_events.py` — assert calls to shared helper; remove now-orphaned mocks of inlined helpers; preserve all current behavioral tests | WP01 | [D] |
| T006 | Add `_judgment_client` lazy field + `_get_judgment_client()` to `DriftEventSignalSource.__init__` (per D2 lifecycle) | WP02 | [D] |
| T007 | Modify `DriftEventSignalSource.commit()` — when `config.drift_interpretation.enabled and mapping is not None`, call `route_drift_event()`; on `DriftInterpretationError` fall back to `file_doc_audit_issue()` + write RETRY_EXHAUSTED ledger row | WP02 | [D] |
| T008 | Preserve cursor/drain idempotency (existing behavior fully intact when flag disabled OR when mapping is None) | WP02 | [D] |
| T009 | Tests for `signals/drift_event.py` — Moment 0 path enabled (calls helper); disabled (falls through to file_doc_audit_issue); JudgmentClient NOT instantiated when disabled (FR-010); retry-exhausted fallback; cursor advance preserved | WP02 | [D] |
| T010 | Create `scripts/doc_audit/helpers/cleanup_391.py` — closes #378-#390 with comment; marker at `~/.config/doc-audit/cleanup-391.done`; `--dry-run` and `--force` flags (mirrors `cutover_362.py` structure) | WP03 |
| T011 | Tests for `cleanup_391.py` — happy path, dry-run, idempotent, partial failure tolerance; ≥85% coverage | WP03 |
| T012 | Architecture docs update — service-inventory.json + data-flows.json correct the Moment 0 integration site (signals/drift_event.py, not handle_drift_events.py); add routing/drift_moment0.py entry | WP03 |
| T013 | Runbook update — `docs/runbooks/doc-auditor-driver-ops.md` Moment 0 section: name `signals/drift_event.py::commit()` as the cron-path invocation site; reference the shared helper | WP03 |

## Dependency Graph

```
WP01 (shared helper + handle_drift_events dedup)
  └── WP02 (signals/drift_event.py integration; depends on WP01's helper)
        └── WP03 (cleanup script + arch docs; depends on WP02 being correct)
```

All sequential — lane-a.

## Phase 1 — Shared helper extraction

### WP01 — Extract Moment 0 routing into shared helper

**Goal**: Move Moment 0 routing logic from `handle_drift_events.py` (where it lives today, dead code) into a new shared helper module. Refactor `process_events()` to call the helper. Promote `RoutingOutcome` to public.

**Priority**: P0 (blocks WP02)
**Dependencies**: none
**Independent test**: `pytest tests/doc_audit/routing/test_drift_moment0.py -v` ≥85%; existing `tests/doc_audit/helpers/test_handle_drift_events.py` still passes.

**Estimated prompt size**: ~280 lines (5 subtasks)
**Prompt**: [WP01-shared-helper.md](tasks/WP01-shared-helper.md)

Included:
- [x] T001 Create `routing/drift_moment0.py` (WP01)
- [x] T002 Refactor `handle_drift_events.py` (WP01)
- [x] T003 Update `routing/__init__.py` (WP01)
- [x] T004 Tests for shared helper (WP01)
- [x] T005 Update existing handle_drift_events tests (WP01)

**Risks**: Refactoring inline helpers into a new module — ensure observable behavior is preserved (test before, test after). Function-level call equivalence (mock route_drift_event in process_events tests).

---

## Phase 2 — Cron-path integration

### WP02 — Wire helper into signals/drift_event.py

**Goal**: Integrate the shared helper into the actual cron entry point (the bug's root cause site).

**Priority**: P0 (blocks WP03 — cleanup needs the fix to be live)
**Dependencies**: WP01
**Independent test**: `pytest tests/doc_audit/signals/test_drift_event.py -v` ≥85% on new code paths. Full `tests/doc_audit/` suite passes.

**Estimated prompt size**: ~260 lines (4 subtasks)
**Prompt**: [WP02-signals-integration.md](tasks/WP02-signals-integration.md)

Included:
- [x] T006 JudgmentClient lazy lifecycle in adapter (WP02)
- [x] T007 `commit()` Moment 0 invocation (WP02)
- [x] T008 Preserve cursor/drain semantics (WP02)
- [x] T009 Tests for signals integration (WP02)

**Risks**: The `commit()` method has subtle idempotency + drain logic. Must NOT change cursor/drain behavior — only ADD the Moment 0 side-effect branch. Tests must lock down both the existing-path and the new-path behaviors.

---

## Phase 3 — Cleanup + docs

### WP03 — cleanup_391 + arch docs

**Goal**: Close the 13 broken-pipeline artifact issues; correct architecture docs that named the wrong integration site.

**Priority**: P1 (operational hygiene)
**Dependencies**: WP02 (cleanup makes sense after the fix is live)
**Independent test**: `pytest tests/doc_audit/helpers/test_cleanup_391.py -v` ≥85%; JSON files parse; markdown views match JSON.

**Estimated prompt size**: ~220 lines (4 subtasks)
**Prompt**: [WP03-cleanup-and-docs.md](tasks/WP03-cleanup-and-docs.md)

Included:
- [ ] T010 cleanup_391.py module (WP03)
- [ ] T011 Tests for cleanup script (WP03)
- [ ] T012 Architecture docs correction (WP03)
- [ ] T013 Runbook correction (WP03)

**Risks**: Static issue list — confirm #378-#390 are all the affected issues + still open at deploy time. Architecture docs: avoid renaming the "drift_interpretation" module entry; only correct the invocation site reference.

---

## Estimated size summary

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 5 | ~280 |
| WP02 | 4 | ~260 |
| WP03 | 4 | ~220 |
| **Total** | **13** | **~760** |

## Next step

Run `spec-kitty agent mission finalize-tasks --mission moment0-integration-fix-01KS8XRM --json` then `/spec-kitty.implement` (or auto-drive).
