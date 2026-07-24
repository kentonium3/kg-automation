# Tasks: Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

**Mission**: retire-vikunja-felix-bot-01KY829X (Phase 1 consolidation)
**Branch**: `fix/860-retire-vikunja-felix-bot` (single_branch — planning base = merge target)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Behavior-preserving migration of every runtime Felix→Vikunja consumer onto the shared
`VikunjaClient` (still the felix-bot token — no identity change). WP01 extends the client with the
minimum shared surface; WP02–WP05 migrate the domains in parallel; WP06 migrates credential-health
and runs the final SC-001/SC-004 gate. Each migration is proven behavior-preserving by a per-consumer
parity test (request-level **plus** domain/CLI boundary — see NFR-001).

## Subtask Index (reference only — not a tracking surface)

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Add `patch()` + PATCH content-type to `VikunjaClient._request` + unit tests | WP01 | |
| T002 | Add raw POST-replace update method + unit tests | WP01 | [P] |
| T003 | Add safe read-modify-write update method (preserve `repeat_after`/`repeat_mode`) + unit tests | WP01 | [P] |
| T004 | Add shared read/comment/label ops the consumers need + unit tests | WP01 | [P] |
| T005 | Return/error-semantics adapter option (raw `None`/error-body vs client `{}`/exception); assert default token unchanged | WP01 | |
| T006 | Migrate `sync/http.py` urllib wrapper onto `VikunjaClient` | WP02 | |
| T007 | Migrate `sync/fetch.py` read algorithm (enumeration, `/info`, cache-abort, dedup) | WP02 | |
| T008 | Migrate `sync/cycle.py` driver; preserve `cycle_error` classification | WP02 | |
| T009 | Sync parity + golden tests (call order, `/info`, cache-abort, error tokens, exit codes) | WP02 | |
| T010 | Migrate `escalation/record_completion.py` (PATCH done/reschedule) + parity | WP03 | [P] |
| T011 | Migrate `escalation/reconcile_completions.py` + parity | WP03 | [P] |
| T012 | Migrate `enrichment/record_completion.py` + parity | WP03 | [P] |
| T013 | Migrate `enrichment/reconcile_completions.py` + parity | WP03 | [P] |
| T014 | Migrate `habits/record_completion.py` (GET-before-POST read-modify-write) + parity | WP04 | [P] |
| T015 | Migrate `habits/set_due_dates.py` + parity | WP04 | [P] |
| T016 | Migrate `habits/exclude_completed.py` + parity | WP04 | [P] |
| T017 | Migrate `habits/migrate_schedule.py` (narrow POST bodies) + parity | WP04 | [P] |
| T018 | Migrate `habits/sweeper.py` + parity | WP05 | [P] |
| T019 | Migrate `habits/identify_workout_task.py` + parity | WP05 | [P] |
| T020 | Migrate `habits/backfill_jsonl_from_comments.py` + parity | WP05 | [P] |
| T021 | Remove dead `_read_token()` from `habits/reconcile_completions.py` (cache-only) | WP05 | |
| T022 | Migrate `security/credential_health_check/vikunja_writer.py` + parity | WP06 | |
| T023 | SC-001 grep gate — no runtime raw HTTP / hand-loaded token remains; full suite green | WP06 | |
| T024 | SC-004 — confirm `DEFAULT_TOKEN_PATH` unchanged (felix-bot); behavior-preserving overall | WP06 | |

---

## WP01 — Extend VikunjaClient (shared surface)

- **Goal**: Give `VikunjaClient` every operation the raw consumers need, on the existing contract +
  error model, so migration loses no capability. **No default-token change.**
- **Priority**: P0 (foundation — unblocks all others).
- **Independent test**: `pytest tests/common/test_vikunja_client.py` — new methods unit-tested;
  `DEFAULT_TOKEN_PATH` still resolves to the felix-bot `vikunja-api` file.
- **Requirements**: FR-002, FR-003, FR-004.
- **Subtasks**:
  - [x] T001 Add `patch()` + PATCH content-type to `_request` + unit tests (WP01)
  - [x] T002 Add raw POST-replace update method + unit tests (WP01)
  - [x] T003 Add safe read-modify-write update method + unit tests (WP01)
  - [x] T004 Add shared read/comment/label ops + unit tests (WP01)
  - [x] T005 Return/error-semantics adapter option; assert default token unchanged (WP01)
- **Dependencies**: none.
- **Risks**: preserve Vikunja quirks (v0.24.6 POST-zeroing, pagination, id-vs-identifier); do NOT
  introduce an abstract port (FR-004); do NOT change the default token (SC-004).
- **Estimated size**: ~210 lines.

## WP02 — Migrate sync (cycle + fetch + http)

- **Goal**: Route sync's raw urllib (`http.py` wrapper, `fetch.py` algorithm, `cycle.py` driver)
  through `VikunjaClient`, behavior-preserving. Highest stakes — bidirectional.
- **Priority**: P1.
- **Independent test**: `pytest tests/sync/` green; parity proves identical requests **and** call
  order, `/info` best-effort suppression, empty-response cache-abort, dedup, `cycle_error` tokens,
  exit codes.
- **Requirements**: FR-001, FR-003, NFR-001.
- **Subtasks**:
  - [x] T006 Migrate `sync/http.py` onto `VikunjaClient` (WP02)
  - [x] T007 Migrate `sync/fetch.py` read algorithm (WP02)
  - [x] T008 Migrate `sync/cycle.py` driver; preserve `cycle_error` classification (WP02)
  - [x] T009 Sync parity + golden tests (WP02)
- **Dependencies**: WP01.
- **Risks**: `list_all_tasks()` pages `GET /projects?page=…` whereas `fetch.py` does one unpaged
  `GET /projects` — either preserve the raw algorithm behind a sync path or consciously accept +
  test the changed request profile. Bidirectional → most test care.
- **Estimated size**: ~230 lines.

## WP03 — Migrate escalation + enrichment

- **Goal**: Migrate the four completion/reconcile modules onto `VikunjaClient`, behavior-preserving.
- **Priority**: P1.
- **Independent test**: `pytest tests/escalation/ tests/enrichment/` green; per-consumer parity.
- **Requirements**: FR-001, FR-003, NFR-001.
- **Subtasks**:
  - [x] T010 Migrate `escalation/record_completion.py` (PATCH) + parity (WP03)
  - [x] T011 Migrate `escalation/reconcile_completions.py` + parity (WP03)
  - [x] T012 Migrate `enrichment/record_completion.py` + parity (WP03)
  - [x] T013 Migrate `enrichment/reconcile_completions.py` + parity (WP03)
- **Dependencies**: WP01.
- **Risks**: escalation uses `PATCH /tasks/{id}` (needs WP01 `patch()`); preserve the raw
  `None`-on-empty / error-body-in-message semantics or adapter-translate per consumer.
- **Estimated size**: ~200 lines.

## WP04 — Migrate habits (writes)

- **Goal**: Migrate the four write-path habits scripts, behavior-preserving. Highest-quirk group.
- **Priority**: P1.
- **Independent test**: `pytest tests/habits/test_record_completion.py tests/habits/test_set_due_dates*.py tests/habits/test_exclude_completed*.py tests/habits/test_migrate_schedule.py` green.
- **Requirements**: FR-001, FR-003, NFR-001.
- **Subtasks**:
  - [x] T014 Migrate `habits/record_completion.py` (GET-before-POST) + parity (WP04)
  - [x] T015 Migrate `habits/set_due_dates.py` + parity (WP04)
  - [x] T016 Migrate `habits/exclude_completed.py` + parity (WP04)
  - [x] T017 Migrate `habits/migrate_schedule.py` (narrow POST) + parity (WP04)
- **Dependencies**: WP01.
- **Risks**: `record_completion` GET-before-POSTs to preserve `repeat_after`/`repeat_mode`
  (v0.24.6 zeroing) → use WP01's read-modify-write method; `migrate_schedule` intentionally POSTs
  narrow bodies → use the raw-replace method. Do not conflate the two.
- **Estimated size**: ~220 lines.

## WP05 — Migrate habits (reads/misc) + dead-token cleanup

- **Goal**: Migrate the read/lookup habits scripts and remove the dead token reader that would
  noise the SC-001 gate.
- **Priority**: P1.
- **Independent test**: `pytest tests/habits/test_sweeper*.py tests/habits/test_identify_workout_task.py tests/habits/test_backfill_jsonl_from_comments.py tests/habits/test_reconcile_completions.py` green.
- **Requirements**: FR-001, FR-003, NFR-001.
- **Subtasks**:
  - [x] T018 Migrate `habits/sweeper.py` + parity (WP05)
  - [x] T019 Migrate `habits/identify_workout_task.py` + parity (WP05)
  - [x] T020 Migrate `habits/backfill_jsonl_from_comments.py` + parity (WP05)
  - [x] T021 Remove dead `_read_token()` from `habits/reconcile_completions.py` (WP05)
- **Dependencies**: WP01.
- **Risks**: `reconcile_completions.py` reads via the sync **cache**, not HTTP — do NOT migrate its
  read path onto the client; only delete the unused `_read_token()` and confirm cache-only.
- **Estimated size**: ~190 lines.

## WP06 — Migrate credential-health + final SC gate

- **Goal**: Migrate the last raw consumer and prove the whole consolidation is complete and
  behavior-preserving.
- **Priority**: P2 (last — the acceptance gate).
- **Independent test**: `pytest tests/security/test_vikunja_writer.py` green; SC-001 grep clean;
  full Vikunja/inbox/habits/escalation/enrichment/trust/sync suite green; `DEFAULT_TOKEN_PATH`
  unchanged.
- **Requirements**: FR-001, FR-003, NFR-002 (+ verifies SC-001/SC-004 for the mission).
- **Subtasks**:
  - [x] T022 Migrate `security/credential_health_check/vikunja_writer.py` + parity (WP06)
  - [x] T023 SC-001 grep gate + full suite green (WP06)
  - [x] T024 SC-004 confirm default token unchanged; behavior-preserving overall (WP06)
- **Dependencies**: WP01, WP02, WP03, WP04, WP05 (final gate needs every migration landed).
- **Risks**: the gate must account for `sync/http.py`+`fetch.py` and the removed `_read_token()`;
  only admin/one-shot + docs may still reference the raw token.
- **Estimated size**: ~180 lines.

---

## Dependencies & Parallelization

```
WP01 (foundation)
 ├─ WP02 (sync)          ┐
 ├─ WP03 (esc+enrich)    │ parallel after WP01
 ├─ WP04 (habits writes) │
 └─ WP05 (habits reads)  ┘
        └─ WP06 (credential-health + final gate)  ← depends on WP01–WP05
```

- **MVP / first WP**: **WP01** (the shared client surface) — nothing migrates until it lands.
- **Parallel band**: WP02–WP05 run concurrently once WP01 is merged.
- **Gate**: WP06 last (its SC-001/SC-004 checks require every migration done).
