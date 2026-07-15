# Tasks: Felix Vikunja reference seam + capture routing alignment

**Mission**: vikunja-reference-seam-01KXK68Z
**Branch**: feat/vikunja-reference-seam
**Issues**: kentonium3/kg-automation#748 + #745 (epic #747)
**Inputs**: spec.md, plan.md, data-model.md, contracts/vikunja-refs.contract.md, research.md, quickstart.md

Tests are **required** for this mission (spec Testing Strategy + NFR-001/002 + SC-002 regression guard).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Seed registry JSON (`vikunja_refs.json`) from live post-reset ids | WP01 | |
| T002 | `VikunjaRefError` + memoized no-network registry loader | WP01 | |
| T003 | Project accessors (`project_id`/`project_title`/`selector`) fail-loud | WP01 | |
| T004 | Label + private accessors (`label_id`/`private_project_ids`) fail-loud | WP01 | |
| T005 | Accessor unit tests (injected loader, no network) | WP01 | |
| T006 | `validate()` pure function → findings (missing/id_drift/title_drift/unprovisioned) | WP02 | |
| T007 | CLI `validate_refs.py` (≤2 live calls, unreachable path, exit codes) | WP02 | |
| T008 | Validator unit tests (each finding kind, unreachable, clean) | WP02 | |
| T009 | `vikunja_scope` read-through + derive `ESCALATION_EXCLUDED` | WP03 | |
| T010 | Migrate `query_active_habits_v2` onto accessor | WP03 | [P] |
| T011 | Migrate `reconcile_completions` onto accessor | WP03 | [P] |
| T012 | Migrate `backfill_jsonl_from_comments` onto accessor | WP03 | [P] |
| T013 | Collapse `query_active_habits_weekly` mirror onto seam | WP03 | [P] |
| T014 | Migrate `vikunja_writer` inbox lookup onto accessor | WP03 | [P] |
| T015 | Migrate sync `PRIVATE_PROJECT_IDS` onto registry | WP04 | |
| T016 | Migrate sync `felix:ignore` label onto accessor (per-token) | WP04 | |
| T017 | Sync tests + #743 fail-loud regression guard | WP04 | |
| T018 | Rework `route_someday` → `q:schedule`+no-due-date; retire Someday-project lookup | WP05 | |
| T019 | Apply Tier-1 labels on routing where determinable; else Inbox | WP05 | |
| T020 | Fix capture AGENTS.md fall-through wording (Inbox, not Someday) | WP05 | |
| T021 | Routing tests (SC-005: someday→q:schedule+no-due-date; unclassifiable→Inbox) | WP05 | |
| T022 | SC-001 acceptance grep gate over migrated runtime surface | WP05 | |

---

## WP01 — Registry data file + typed fail-loud accessor

- **Goal**: The single declared registry (`scripts/common/vikunja_refs.json`) + a typed accessor (`scripts/common/vikunja_refs.py`) that resolves logical Vikunja project/label names to identities with **zero network** and **fail-loud** on undeclared/unprovisioned/wrong-kind. Foundation every other WP depends on.
- **Priority**: P1 (MVP — nothing resolves without it).
- **Independent test**: `project_id("inbox") == 1`; `project_id("someday")` raises `VikunjaRefError`; `project_id("personal")` (unprovisioned) raises; no network on any accessor call (injected loader).
- **Requirements**: FR-001, FR-003, FR-007, FR-008, FR-009, NFR-001, NFR-003.
- **Dependencies**: none.
- **Estimated prompt size**: ~330 lines.

Included subtasks:
- [x] T001 Seed registry JSON from live post-reset ids (WP01)
- [x] T002 `VikunjaRefError` + memoized no-network loader (WP01)
- [x] T003 Project accessors fail-loud (WP01)
- [x] T004 Label + private accessors fail-loud (WP01)
- [x] T005 Accessor unit tests (WP01)

## WP02 — Drift / unreachable validator + CLI

- **Goal**: An on-demand validator that lists live Vikunja once (≤2 calls) and reports every declared reference that is `missing` / `id_drift` / `title_drift` / `unprovisioned`, plus a distinct `unreachable` state — fail-loud, non-zero exit on any finding. The reality-vs-registry honesty check (#743 guard).
- **Priority**: P1.
- **Independent test**: injected live data with a drifted id → one `id_drift` finding; unreachable list → single `unreachable` finding + non-zero exit; clean → empty + exit 0; ≤2 injected list calls.
- **Requirements**: FR-004, NFR-002.
- **Dependencies**: WP01.
- **Estimated prompt size**: ~250 lines.

Included subtasks:
- [ ] T006 `validate()` pure function → findings (WP02)
- [ ] T007 CLI `validate_refs.py` (≤2 live calls, unreachable, exit codes) (WP02)
- [ ] T008 Validator unit tests (WP02)

## WP03 — Migrate project-id resolution consumers (scope + habits + security)

- **Goal**: Move every runtime **project-id** resolution consumer onto the accessor and delete the old by-title / hardcoded-id lookups. `vikunja_scope` stays the selector layer but reads identity through the registry; `ESCALATION_EXCLUDED_PROJECT_IDS` derives from `project_id("habits")`; the `{kind,value}` selector shape is preserved (FR-008).
- **Priority**: P1.
- **Independent test**: each migrated site resolves via the seam; a deleted/renamed reference fails loud rather than returning empty (SC-002); habit/escalation queries still scope correctly.
- **Requirements**: FR-002, FR-005, FR-008.
- **Dependencies**: WP01.
- **Estimated prompt size**: ~340 lines.

Included subtasks:
- [ ] T009 `vikunja_scope` read-through + derive `ESCALATION_EXCLUDED` (WP03)
- [ ] T010 Migrate `query_active_habits_v2` (WP03)
- [ ] T011 Migrate `reconcile_completions` (WP03)
- [ ] T012 Migrate `backfill_jsonl_from_comments` (WP03)
- [ ] T013 Collapse `query_active_habits_weekly` mirror (WP03)
- [ ] T014 Migrate `vikunja_writer` inbox lookup (WP03)

## WP04 — Migrate sync consumers (private set + felix:ignore label)

- **Goal**: Move the sync driver's `PRIVATE_PROJECT_IDS` onto the registry (`private_project_ids()`) and resolve the `felix:ignore` manual-override label through the accessor's per-token namespace, deleting the `title ==` resolution. `felix:ignore` is the only live runtime label consumer; taxonomy labels are deferred to #749.
- **Priority**: P1.
- **Independent test**: `felix:ignore` still classifies a manual-override task via the seam; private-set filtering unchanged (empty default); deleted label reference fails loud.
- **Requirements**: FR-002, FR-005, FR-006.
- **Dependencies**: WP01.
- **Estimated prompt size**: ~230 lines.

Included subtasks:
- [ ] T015 Migrate sync `PRIVATE_PROJECT_IDS` (WP04)
- [ ] T016 Migrate sync `felix:ignore` label per-token (WP04)
- [ ] T017 Sync tests + #743 fail-loud regression guard (WP04)

## WP05 — #745 capture routing alignment + SC-001 gate

- **Goal**: Retarget capture routing onto the post-#714 model — fall-through → **Inbox**, "someday" → a `q:schedule`-tagged **no-due-date** task (retiring `route_someday`'s Someday-project lookup), Tier-1 labels where determinable — correct the capture AGENTS.md, and land the SC-001 acceptance grep gate over the fully-migrated runtime surface.
- **Priority**: P1 (the #745 half; also the final consolidation gate).
- **Independent test**: someday block → `q:schedule` + no due date task in Inbox/topic project (SC-005); unclassifiable → Inbox; routing-log/dedup preserved; SC-001 grep finds zero remaining by-title/hardcoded-id runtime lookups.
- **Requirements**: FR-010, FR-011, FR-012, FR-013 (SC-001 gate also backstops FR-002).
- **Dependencies**: WP01, WP03, WP04 (the grep gate must run over the fully-migrated surface).
- **Estimated prompt size**: ~320 lines.

Included subtasks:
- [ ] T018 Rework `route_someday` → `q:schedule`+no-due-date (WP05)
- [ ] T019 Apply Tier-1 labels where determinable (WP05)
- [ ] T020 Fix capture AGENTS.md fall-through wording (WP05)
- [ ] T021 Routing tests (SC-005) (WP05)
- [ ] T022 SC-001 acceptance grep gate (WP05)

---

## Dependencies & Parallelization

- **WP01** is the foundation (no deps). MVP scope.
- **WP02, WP03, WP04** each depend only on WP01 and can run in parallel after it.
- **WP05** depends on WP01 + WP03 + WP04 (the SC-001 grep must run over the fully-migrated surface).

```
WP01 ──┬─→ WP02
       ├─→ WP03 ──┐
       └─→ WP04 ──┴─→ WP05
```

## MVP

WP01 (registry + accessor) is the minimum that makes the seam real. WP01→WP03→WP05
is the thinnest end-to-end slice that closes the #743 class on the capture path.
