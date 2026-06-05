# Tasks: Felix-Vikunja Sync — Project Layer and URL Config

**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Mission slug**: `felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7`
**Date**: 2026-06-05

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/common/vikunja_config.py` with `get_vikunja_base_url()` + `VikunjaConfigError` | WP01 | |
| T002 | Tests in `tests/test_vikunja_config.py` (7 scenarios) | WP01 | [P] |
| T003 | Verify NFR-006 grep contract in this WP's owned files | WP01 | [P] |
| T004 | Create `scripts/sync/cleanup.py` with `prune_schedule_yaml()` + `append_task_deleted_event()` | WP02 | |
| T005 | Tests in `tests/sync/test_cleanup.py` | WP02 | [P] |
| T006 | Document atomicity + idempotency in module docstring; spec event schema | WP02 | [P] |
| T007 | Replace `FetchedDelta` with `FetchedSnapshot`; replace `fetch_delta` with `fetch_full_poll`; include FR-012 abort guards | WP03 | |
| T008 | Rewrite `compute_divergences` in `diff.py` for 3-way set diff outputs | WP03 | [P] |
| T009 | Rewrite `tests/sync/test_fetch.py` for full-poll semantics + FR-012 cases | WP03 | [P] |
| T010 | Rewrite `tests/sync/test_diff.py` for set-diff outputs | WP03 | [P] |
| T011 | state.py — add `PerLayerSummary`+`LayerSummary`; remove `LayerPointerSnapshot`; update `PerTickHealthRecord` | WP04 | |
| T012 | cycle.py Phase 1 — call `fetch_full_poll` with FR-012 abort; remove `since_utc` / `known_project_ids` plumbing | WP04 | |
| T013 | cycle.py Phase 5 — replace `_apply_cache_updates` with set-diff; replace `_apply_project_updates` with canonical-snapshot replacement | WP04 | |
| T014 | cycle.py Phase 5b — implement deletion-cleanup orchestration using WP02 helpers (ordered) | WP04 | |
| T015 | cycle.py Phase 6 — write `PerTickHealthRecord` with `LayerSummary` instead of `layer_pointers` | WP04 | |
| T016 | tests/sync/test_state.py updates (additions + removals) | WP04 | [P] |
| T017 | tests/sync/test_cycle_*.py — update fixtures to `FetchedSnapshot`; integration assertions stable | WP04 | [P] |
| T018 | Migrate `scripts/habits/query_active_habits_v2.py` to `get_vikunja_base_url()` | WP05 | [P] |
| T019 | Migrate `scripts/habits/morning_checkin_list.py` | WP05 | [P] |
| T020 | Migrate `scripts/habits/set_due_dates.py` (preserves retained PUT path) | WP05 | [P] |
| T021 | Migrate `scripts/habits/reconcile_completions.py` | WP05 | [P] |
| T022 | Migrate `scripts/escalation/reconcile_completions.py` | WP05 | [P] |
| T023 | Migrate `scripts/enrichment/reconcile_completions.py` (preserves retained `_http_get` for comments) | WP05 | [P] |
| T024 | Migrate `scripts/sync/driver.py` CLI default to `get_vikunja_base_url()` | WP05 | [P] |
| T025 | NFR-006 grep verification — zero hardcoded URLs in runtime-path scripts | WP05 | |
| T026 | Update `docs/design/architecture/data/service-inventory.json` — driver config_files adds URL config | WP06 | [P] |
| T027 | Update `docs/design/architecture/service-inventory.md` narrative | WP06 | [P] |
| T028 | Update `docs/design/architecture/service-dependencies.view.md` diagram | WP06 | [P] |
| T029 | Update `docs/design/architecture/data/data-flows.json` — new flow URL config → consumers | WP06 | [P] |
| T030 | Update `docs/design/architecture/data-flows.md` + `data-flows.view.md` | WP06 | [P] |
| T031 | Update `docs/design/architecture/credentials-and-secrets.md` storage inventory | WP06 | [P] |
| T032 | Rewrite `docs/runbooks/sync-driver-ops.md` — full-poll, project-layer audit, deletion-cleanup, URL config | WP06 | |
| T033 | Update `docs/INDEX.md` (entry) + `docs/design/felix-capability-roadmap.md` (mark #507 complete) | WP06 | [P] |

**Note**: The `[P]` marker in this index indicates parallelizability (different files, no dependencies). Progress tracking happens via the per-WP checkbox rows below, not this table.

---

## Dependency Graph

```
WP01 (no deps) ─┐
                ├─→ WP05 (URL touchpoint migration)
WP02 (no deps) ─┐
                ├─→ WP04 (state + cycle rewrite) ─→ WP06 (architecture docs)
WP03 (no deps) ─┘
```

**Parallel opportunities**: WP01, WP02, WP03 can start simultaneously (no inter-dependencies; different files). WP04 funnels in WP02 + WP03 work. WP05 depends only on WP01.

**Critical path**: WP02/WP03 → WP04 → WP06 (4 sequential steps).

---

## Work Package 1 — URL Config Helper (WP01)

**Prompt**: [tasks/WP01-url-config-helper.md](./tasks/WP01-url-config-helper.md)

### Summary

**Goal**: Add a shared helper `scripts/common/vikunja_config.py` providing `get_vikunja_base_url()` — the single source of truth for the Vikunja API base URL across the codebase.

**Priority**: Foundation. WP05 (touchpoint URL migration) depends on this.

**Independent test**: `pytest tests/test_vikunja_config.py` covers all 7 contract scenarios from `contracts/url-config.md`.

**Estimated prompt size**: ~250 lines.

### Included subtasks

- [ ] T001 Create `scripts/common/vikunja_config.py` with `get_vikunja_base_url()` + `VikunjaConfigError` (WP01)
- [ ] T002 Tests in `tests/test_vikunja_config.py` (7 scenarios) (WP01)
- [ ] T003 Verify NFR-006 grep contract in this WP's owned files (WP01)

### Implementation sketch

1. Author the helper module with the public API specified in `contracts/url-config.md`.
2. Author unit tests using `monkeypatch` for the env var and a temporary file path for the config-file fallback.
3. Verify `grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/common/vikunja_config.py` returns exactly the matches expected by the design (file path constant + initial URL value).

### Dependencies

None. Can land first.

### Risks

- Trailing slash normalization edge cases (file has trailing slash vs file doesn't). Tests must cover both.
- Empty env var should fall through to file; tests must verify this precedence semantics.

---

## Work Package 2 — Deletion-Cleanup Helpers (WP02)

**Prompt**: [tasks/WP02-deletion-cleanup-helpers.md](./tasks/WP02-deletion-cleanup-helpers.md)

### Summary

**Goal**: Add a new module `scripts/sync/cleanup.py` providing two functions: `prune_schedule_yaml(task_id, path)` and `append_task_deleted_event(task_id, title, detected_at_utc, path)`. These are the building blocks WP04 uses for Phase 5b deletion-cleanup orchestration.

**Priority**: Foundation. WP04 depends on this.

**Independent test**: `pytest tests/sync/test_cleanup.py` covers prune + append behavior with idempotency assertions.

**Estimated prompt size**: ~280 lines.

### Included subtasks

- [ ] T004 Create `scripts/sync/cleanup.py` with `prune_schedule_yaml()` + `append_task_deleted_event()` (WP02)
- [ ] T005 Tests in `tests/sync/test_cleanup.py` (WP02)
- [ ] T006 Document atomicity + idempotency in module docstring; spec event schema (WP02)

### Implementation sketch

1. Add `prune_schedule_yaml(task_id: int, path: Path) -> bool`. Uses `ruamel.yaml` round-trip if available; falls back to `yaml` (PyYAML) for test environments. Returns True if entry was removed, False if not present (idempotent).
2. Add `append_task_deleted_event(task_id: int, title: str, detected_at_utc: str, path: Path) -> None`. Single-line JSON-Lines append, atomic write with `os.O_APPEND`. Event format per `data-model.md`.
3. Add tests covering: prune happy path, prune idempotency (re-run after first), append happy path, append with non-existent file (creates), append concurrency (skipped — single writer assumption per driver).

### Dependencies

None. Can land in parallel with WP01 and WP03.

### Risks

- YAML library availability: ruamel.yaml is available in production (verified via habits codebase grep); fall back to PyYAML for test environments only. Document this trade-off in module docstring.
- Atomicity of JSONL append: stdlib `open(path, "a")` is atomic at small write sizes (< PIPE_BUF). Acceptable.

---

## Work Package 3 — fetch.py + diff.py Rewrite (WP03)

**Prompt**: [tasks/WP03-fetch-diff-rewrite.md](./tasks/WP03-fetch-diff-rewrite.md)

### Summary

**Goal**: Replace `fetch_delta` + `FetchedDelta` with `fetch_full_poll` + `FetchedSnapshot`. Rewrite `compute_divergences` to operate on the snapshot via 3-way set diff. Add FR-012 abort guards inside `fetch_full_poll` so a malformed Vikunja response aborts the cycle cleanly before any cache mutation.

**Priority**: Foundation. WP04 depends on this.

**Independent test**: `pytest tests/sync/test_fetch.py tests/sync/test_diff.py` (rewritten) plus the NFR-004 regression guard `pytest tests/common/test_sync_cache.py` (unchanged).

**Estimated prompt size**: ~450 lines.

### Included subtasks

- [ ] T007 Replace `FetchedDelta` with `FetchedSnapshot`; replace `fetch_delta` with `fetch_full_poll`; include FR-012 abort guards (WP03)
- [ ] T008 Rewrite `compute_divergences` in `diff.py` for 3-way set diff outputs (WP03)
- [ ] T009 Rewrite `tests/sync/test_fetch.py` for full-poll semantics + FR-012 cases (WP03)
- [ ] T010 Rewrite `tests/sync/test_diff.py` for set-diff outputs (WP03)

### Implementation sketch

1. **fetch.py**: replace `fetch_delta(token, base_url, since_utc, known_project_ids) → FetchedDelta` with `fetch_full_poll(token, base_url) → FetchedSnapshot`. Two HTTP calls in sequence: `GET /tasks/all` then `GET /projects`. Remove the just-in-time per-project fetch logic. Add FR-012 abort guards: if either call returns 5xx, 401, 403, empty `[]` when cache non-empty (caller-supplied flag), or non-JSON body, raise `OSError` with structured token.
2. **diff.py**: rewrite `compute_divergences` to operate on `(snapshot, task_cache, project_cache, ts_observed_utc, private_project_ids)`. Compute three set partitions for tasks; emit `DivergenceCandidate` records for `in_both` with field-level differences. Compute project events (added, removed, renamed, archived, unarchived) from project set diff. Compute `LayerSummary` aggregate counts.
3. **test_fetch.py** rewrite: assert `fetch_full_poll` issues exactly two HTTP calls; verify FR-012 abort tokens (`auth_failure`, `vikunja_5xx`, `parse_error`, `empty_response_when_cache_nonzero`); cover both layers' error paths.
4. **test_diff.py** rewrite: assert 3-way set diff outputs (empty/pure-add/pure-delete/pure-update/mixed scenarios); verify privacy filter preserves structural operations; verify 5 project event types.

### Dependencies

None on other WPs of this mission. Can land in parallel with WP01 and WP02.

### Risks

- Existing `DivergenceCandidate` interface should remain stable (consumed by Phase 3 classify which is unchanged). Verify field-level diff output matches what classify expects.
- FR-012 "empty response when cache non-empty" requires the caller (cycle.py) to pass a flag indicating cache state. Document this contract in the function docstring.
- Privacy filter interaction with structural operations: per `contracts/set-diff.md`, private tasks STILL produce structural events (add/delete) but NOT content events. Verify this interpretation matches #518's privacy intent.

---

## Work Package 4 — state.py + cycle.py Driver Rewrite (WP04)

**Prompt**: [tasks/WP04-driver-rewrite-and-phase5b.md](./tasks/WP04-driver-rewrite-and-phase5b.md)

### Summary

**Goal**: Update state.py to replace `LayerPointerSnapshot` with `LayerSummary`. Rewrite cycle.py phases 1, 5, 5b (new), and 6 to use `fetch_full_poll`, 3-way set diff, canonical-snapshot project cache replacement, deletion-cleanup orchestration, and `LayerSummary` in `PerTickHealthRecord`. Integration tests (`test_cycle_*.py`) act as regression guards against the cache contract.

**Priority**: Core. Critical path. WP06 depends on this.

**Independent test**: `pytest tests/sync/test_state.py tests/sync/test_cycle_*.py` + `pytest tests/common/test_sync_cache.py` (NFR-004 regression).

**Estimated prompt size**: ~600 lines (at upper edge of budget; review carefully).

### Included subtasks

- [ ] T011 state.py — add `PerLayerSummary`+`LayerSummary`; remove `LayerPointerSnapshot`; update `PerTickHealthRecord` (WP04)
- [ ] T012 cycle.py Phase 1 — call `fetch_full_poll` with FR-012 abort; remove `since_utc` / `known_project_ids` plumbing (WP04)
- [ ] T013 cycle.py Phase 5 — replace `_apply_cache_updates` with set-diff; replace `_apply_project_updates` with canonical-snapshot replacement (WP04)
- [ ] T014 cycle.py Phase 5b — implement deletion-cleanup orchestration using WP02 helpers (ordered) (WP04)
- [ ] T015 cycle.py Phase 6 — write `PerTickHealthRecord` with `LayerSummary` instead of `layer_pointers` (WP04)
- [ ] T016 tests/sync/test_state.py updates (additions + removals) (WP04)
- [ ] T017 tests/sync/test_cycle_*.py — update fixtures to `FetchedSnapshot`; integration assertions stable (WP04)

### Implementation sketch

See `contracts/cycle-pipeline.md` for the phase-by-phase contract.

1. **state.py**: add `PerLayerSummary` + `LayerSummary` dataclasses; remove `LayerPointerSnapshot`; replace `layer_pointers` field in `PerTickHealthRecord` with `layer_summary: LayerSummary`; update `write_per_tick_health`.
2. **cycle.py Phase 1**: replace `fetch_delta(...)` call with `fetch_full_poll(token, base_url)`. Wire FR-012 abort: if fetch raises an OSError, record per-layer error tokens in `LayerSummary` and route through `_record_failure`.
3. **cycle.py Phase 2**: consume new `compute_divergences` outputs (5-tuple: divergences, first_observation_task_ids, deleted_task_ids, project_events, layer_summary).
4. **cycle.py Phase 5**: replace `_apply_cache_updates` (delta-apply) with set-diff-based update that consumes `in_vikunja_only` (adds) and `in_both` (updates); excludes `in_cache_only` (deletions). Replace `_apply_project_updates` (merge-only) with canonical-snapshot replacement per `data-model.md`.
5. **cycle.py Phase 5b** (NEW): orchestrate deletion-cleanup per FR-003. For each `task_id` in `deleted_task_ids`, in order: (a) append `task_deleted` event via WP02's `append_task_deleted_event`, (b) prune schedule.yaml via WP02's `prune_schedule_yaml`, (c) cache removal happens via Phase 6 atomic write. Per-task failure handling: log to `last-tick.errors.jsonl`, continue with other task_ids.
6. **cycle.py Phase 6**: construct `PerTickHealthRecord` with `layer_summary` field instead of `layer_pointers`. Atomic write ordering: task_cache, project_cache, guard_state, freshness (last).
7. **test_state.py**: add `PerLayerSummary` + `LayerSummary` tests; remove `LayerPointerSnapshot` tests; update `PerTickHealthRecord` test for new field shape.
8. **test_cycle_*.py**: integration tests get fixture updates (FetchedDelta mocks → FetchedSnapshot mocks); assertions on cache state, JSONL events, WhatsApp dispatch are STABLE (this is the regression-guard role per the operator's test-strategy decision).

### Dependencies

- WP02 (cleanup helpers — Phase 5b imports `prune_schedule_yaml` + `append_task_deleted_event`)
- WP03 (fetch_full_poll + compute_divergences signatures — Phase 1, 2, 5 call these)

### Risks

- This is the largest WP in the mission (~600 line prompt). Reviewer should validate phase-by-phase against `contracts/cycle-pipeline.md`.
- Test fixture migration in `test_cycle_*.py`: integration tests use `FetchedDelta` shape. The migration is mostly mechanical (rename type, drop `since_utc` argument, projects dict still passed). Assertions on outcomes stay stable.
- Atomic-cycle guarantee: any failure in phases 5-6 must NOT leave a partial state on disk. Existing #518 ordering (freshness written LAST) is preserved.
- WP04 owns `scripts/sync/state.py` — the `LayerPointerSnapshot` removal happens here, not in WP02 or WP03. This is intentional to keep ownership clean.

---

## Work Package 5 — Touchpoint URL Migration (WP05)

**Prompt**: [tasks/WP05-touchpoint-url-migration.md](./tasks/WP05-touchpoint-url-migration.md)

### Summary

**Goal**: Migrate the 6 #519 touchpoints + 2 retained write paths + the #518 driver CLI default to read the Vikunja base URL from `get_vikunja_base_url()` instead of hardcoded constants. NFR-006 grep verification confirms zero hardcoded URLs in runtime-path scripts.

**Priority**: Surface-area. Independent of driver rewrite (WP04). Depends only on WP01.

**Independent test**: each touchpoint's existing test suite continues to pass under the migrated code; NFR-006 grep returns expected hits.

**Estimated prompt size**: ~400 lines.

### Included subtasks

- [ ] T018 Migrate `scripts/habits/query_active_habits_v2.py` to `get_vikunja_base_url()` (WP05)
- [ ] T019 Migrate `scripts/habits/morning_checkin_list.py` (WP05)
- [ ] T020 Migrate `scripts/habits/set_due_dates.py` (preserves retained PUT path) (WP05)
- [ ] T021 Migrate `scripts/habits/reconcile_completions.py` (WP05)
- [ ] T022 Migrate `scripts/escalation/reconcile_completions.py` (WP05)
- [ ] T023 Migrate `scripts/enrichment/reconcile_completions.py` (preserves retained `_http_get` for comments) (WP05)
- [ ] T024 Migrate `scripts/sync/driver.py` CLI default to `get_vikunja_base_url()` (WP05)
- [ ] T025 NFR-006 grep verification — zero hardcoded URLs in runtime-path scripts (WP05)

### Implementation sketch

For each file: locate the existing hardcoded URL constant or CLI default value; replace with `BASE_URL = get_vikunja_base_url()` at module init. Import line at top: `from scripts.common.vikunja_config import get_vikunja_base_url`. For CLI args, the default value becomes a callable lambda or `get_vikunja_base_url()` evaluated at parser construction.

After all 7 migrations: run `grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/` from the repo root. Expected: hits only in `scripts/common/vikunja_config.py` and the 6 FR-010 exclusions. Any other hit is a regression.

### Dependencies

- WP01 (the `get_vikunja_base_url()` helper module must exist).

### Risks

- Per memory `feedback_wp_prompts_grep_codebase`: grep the actual import conventions in each touchpoint before writing the literal import line into the prompt. Some touchpoints may use a slightly different module-init style.
- The CLI args (`--vikunja-base-url`) on touchpoints that take this argument must continue to allow explicit override (useful for testing).

---

## Work Package 6 — Architecture + Runbook Updates (WP06)

**Prompt**: [tasks/WP06-architecture-and-runbook-updates.md](./tasks/WP06-architecture-and-runbook-updates.md)

### Summary

**Goal**: Update all architecture docs and the sync-driver-ops runbook to reflect the full-poll model, project-layer audit semantics, deletion-cleanup algorithm, and URL config plumbing. Per signal-to-doc-map for `service-added-or-modified`, `data-flow-added-or-modified`, and `runbook-modified` change classes. Mark Epic #507 complete in the capability roadmap.

**Priority**: Polish + governance. Depends on WP04 so the docs reflect the actual delivered code.

**Independent test**: `python3 tooling/scripts/validate_docs.py` passes; runbook contents match the new behavior.

**Estimated prompt size**: ~320 lines.

### Included subtasks

- [ ] T026 Update `docs/design/architecture/data/service-inventory.json` — driver config_files adds URL config (WP06)
- [ ] T027 Update `docs/design/architecture/service-inventory.md` narrative (WP06)
- [ ] T028 Update `docs/design/architecture/service-dependencies.view.md` diagram (WP06)
- [ ] T029 Update `docs/design/architecture/data/data-flows.json` — new flow URL config → consumers (WP06)
- [ ] T030 Update `docs/design/architecture/data-flows.md` + `data-flows.view.md` (WP06)
- [ ] T031 Update `docs/design/architecture/credentials-and-secrets.md` storage inventory (WP06)
- [ ] T032 Rewrite `docs/runbooks/sync-driver-ops.md` — full-poll, project-layer audit, deletion-cleanup, URL config (WP06)
- [ ] T033 Update `docs/INDEX.md` (entry) + `docs/design/felix-capability-roadmap.md` (mark #507 complete) (WP06)

### Implementation sketch

1. **service-inventory.json** (T026): in the `felix-vikunja-sync-driver` entry, add a `config_files` array (or extend it) listing `/data/services/openclaw/config/vikunja-base-url.txt`. Add the `VIKUNJA_BASE_URL` env var to the consumer's documented env vars.
2. **service-inventory.md narrative** (T027): describe the URL config dependency in the driver's section. Note that 8 touchpoints also consume it.
3. **service-dependencies.view.md** (T028): add a new edge from "URL config" node to "driver" and "touchpoints".
4. **data-flows.json** (T029): add a new flow object: `{name: "vikunja-base-url-config", source: "operator", sink: ["sync-driver", "habits-touchpoints", "escalation-touchpoint", "enrichment-touchpoint"], format: "text-file"}`.
5. **data-flows.md + .view.md** (T030): narrative + diagram update.
6. **credentials-and-secrets.md** (T031): add the URL config file to the Storage Mechanisms section (it's a non-secret config file but lives alongside secrets).
7. **sync-driver-ops.md** (T032): full rewrite of the operator-facing sections — replace incremental-poll description with full-poll, add project-layer audit semantics, add deletion-cleanup algorithm, add URL config reading + rotation.
8. **INDEX.md + felix-capability-roadmap.md** (T033): minor INDEX entry tweak if sync-driver-ops.md scope expanded; mark Epic #507 complete in capability roadmap.

### Dependencies

- WP04 (drivers actually deliver the behavior the docs describe).

### Risks

- `validate_docs.py` must remain green. Run before commit.
- `service-dependencies.view.md` is a Mermaid diagram; edge additions must follow existing conventions.
- The capability roadmap's "mark complete" edit should be a small targeted change — don't reorganize the document.

---

## Parallel Opportunities

- **WP01, WP02, WP03** all have no inter-dependencies and can be implemented in parallel. Each touches different files. They unblock WP04 and WP05.
- **WP04** is the critical-path funnel. It needs WP02 + WP03. Cannot start until both are approved.
- **WP05** can start as soon as WP01 is approved (in parallel with WP02/WP03/WP04 progress).
- **WP06** is the last WP; needs WP04 done.

Recommended sequencing for parallel agents (if dispatching via `/spec-kitty-implement-review`):
1. Start WP01, WP02, WP03 in parallel.
2. As WP01 approves, start WP05 in parallel with remaining WP02/WP03.
3. Once WP02 + WP03 approve, start WP04.
4. Once WP04 approves, start WP06.

---

## MVP Scope

This mission is the final piece of Epic #507; the MVP scope IS the full mission. Earlier missions (#518, #519) shipped the foundational pieces. Stopping #520 mid-flight would leave Felix with:
- Broken project-layer (merge-only behavior; no rename/archive detection)
- 15-min worst-case deletion latency (the documented NFR-002 gap)
- Two URL bases in concurrent use (the silent inconsistency risk)

All 6 WPs together constitute the MVP. There is no smaller deliverable that retires the Epic.

---

## Next Steps

1. `spec-kitty agent mission finalize-tasks --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --json` to parse dependencies, validate ownership, and commit.
2. `/spec-kitty.implement` (or `/spec-kitty-implement-review` skill for auto-drive) to begin WP execution.
3. Post-merge: deploy via git pull on office2, create the URL config file before the first cycle runs.
4. Post-merge: file the follow-up issue for FR-010 one-off scripts migration.
5. Post-merge: run the downstream-leftovers sweep per Kent's 2026-06-05 request.
