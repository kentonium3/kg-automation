# Implementation Plan: Felix-Vikunja Sync — Project Layer and URL Config

**Status**: Phase 1 design (post-planning interrogation, pre-`/spec-kitty.tasks`)
**Spec**: [spec.md](./spec.md)
**Mission slug**: `felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7`
**Date**: 2026-06-05

## Technical Context

| Field | Value |
|---|---|
| Language | Python 3.10+ (matches #518 / #519) |
| Stdlib only | yes (matches #518 doctrine: `urllib`, `json`, `pathlib`; no third-party HTTP libs) |
| Driver location | `scripts/sync/` (extend existing modules; do not introduce parallel package) |
| Touchpoint locations | `scripts/habits/`, `scripts/escalation/`, `scripts/enrichment/` (existing) |
| Shared helpers | `scripts/common/` (existing, for new `vikunja_config.py`) |
| Tests | `tests/sync/` (rewrite affected unit tests in place); integration tests as regression guards (operator decision 2026-06-05) |
| Cache state location | `/data/services/openclaw/state/sync/` (existing; canonical per `STATE_DIR_DEFAULT`) |
| URL config location | `/data/services/openclaw/config/vikunja-base-url.txt` (new, file mode 0644) |
| Env var | `VIKUNJA_BASE_URL` (exported in `~/.bashrc` for `claude` user + systemd EnvironmentFile) |
| Runtime cadence | 5-minute cycle via `felix-vikunja-sync.timer` (no change) |
| change_mode | `regular` (per spec C-008) |
| Branch contract | current=main, planning_base=main, merge_target=main, branch_matches_target=true |

## Branch Strategy

Per `setup-plan --json`:

- **Current branch at planning start**: `main`
- **Planning/base branch for this feature**: `main`
- **Final merge target for completed changes**: `main`
- **branch_matches_target**: ✅ true
- **Branch strategy summary**: Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.

No long-lived feature branch is required; spec-kitty mission lanes are computed at task finalization. The mission ships in a single merge commit to `main`.

## Charter Check

Mode: `compact` (returned by `spec-kitty charter context --action plan --json`). The compact governance context is consumed; no first-run bootstrap required. No charter gate violations identified — the spec aligns with Directive 6 (deterministic-vs-stochastic split: all driver work is deterministic), Directive 8 (operational symptom recorded in spec), and the standing architecture-documentation directive (signal-to-doc-map entries identified in spec's Architecture Impact).

## Engineering Alignment

The spec is unusually complete because the operator drove the architectural decisions during discovery (full-poll over incremental, three-action cleanup, narrow FR-3 scope). Planning surfaces:

1. **Existing #518 code is well-factored.** The 6-phase pipeline (`fetch → diff → classify → emit → update → complete`) is preserved structurally. Phase 1 (fetch) and Phase 5 (update) get the largest rewrites; phases 2-4 (diff, classify, emit) keep their interfaces but consume a `FetchedSnapshot` instead of a `FetchedDelta`.

2. **The project layer is partially built but degraded.** `scripts/sync/cycle.py:543` `_apply_project_updates` is merge-only — it never removes a project from cache. The deployed `project-cache.json` accumulates over time and currently holds 7 projects (the subset that were referenced by tasks at some point). FR-004 isn't "add new" but "fix the broken merge-only behavior" by making project handling symmetric with task handling: 3-way set diff with explicit add/remove/rename/archive/unarchive events.

3. **`fetch_delta` does just-in-time project fetching too** (`scripts/sync/fetch.py:80-100`). This logic disappears under full-poll: `GET /projects` always runs, and per-project resolution is replaced by the cached snapshot.

4. **Test strategy**: in-place rewrite of unit tests for `fetch.py`, `diff.py`, `cycle.py`. Integration tests in `tests/sync/test_cycle_*.py` and the `tests/common/conftest.py` fixtures from #519 act as regression guards against the cache-read contract (`scripts/common/sync_cache.py`).

5. **URL config helper is a small, clean addition**. A new module `scripts/common/vikunja_config.py` provides `get_vikunja_base_url()` that reads `VIKUNJA_BASE_URL` env var first, falls back to the canonical file, raises a structured error if neither is present.

## Gate Evaluation

- [x] All FRs/NFRs/C have `Status: Approved` (spec verified)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Operator confirmed test strategy (in-place rewrite + integration as regression guard)
- [x] Branch contract is unambiguous
- [x] change_mode locked (regular)
- [x] Predecessors deployed (#518 verified at 2026-06-05 16:07 UTC; #519 verified 2026-06-05 same window)
- [x] Charter context loaded; no violations

## Project Structure

### Existing files (modified by this mission)

```
scripts/sync/
├── cycle.py           # MODIFIED — replace _apply_cache_updates + _apply_project_updates; add deletion cleanup orchestration; replace layer_pointers with layer_summary
├── fetch.py           # MODIFIED — replace fetch_delta with fetch_full_poll
├── diff.py            # MODIFIED — replace compute_divergences to operate on FetchedSnapshot + cache
├── state.py           # MODIFIED — deprecate LayerPointerSnapshot; add LayerSummary; add task_deleted_events JSONL helper
├── driver.py          # MINOR — CLI surface unchanged; arg passthrough only
├── http.py            # MINOR — base_url parameter contract preserved; the URL source moves to vikunja_config.py
├── classify.py        # UNCHANGED
├── emit.py            # UNCHANGED (consumes classified divergences; format unchanged)
├── guards.py          # UNCHANGED
├── __init__.py        # UNCHANGED

scripts/habits/
├── query_active_habits_v2.py    # MODIFIED — read URL from get_vikunja_base_url()
├── morning_checkin_list.py      # MODIFIED — read URL from get_vikunja_base_url()
├── set_due_dates.py             # MODIFIED — read URL from get_vikunja_base_url() (used by retained _http_put)
├── reconcile_completions.py     # MODIFIED — read URL from get_vikunja_base_url()

scripts/escalation/
├── reconcile_completions.py     # MODIFIED — read URL from get_vikunja_base_url()

scripts/enrichment/
├── reconcile_completions.py     # MODIFIED — read URL from get_vikunja_base_url() (used by retained _http_get + _fetch_comments)

scripts/common/
├── sync_cache.py     # UNCHANGED (NFR-004 contract)
├── vikunja_config.py # NEW — get_vikunja_base_url() helper

tests/sync/
├── test_fetch.py     # REWRITTEN — assert full-poll semantics; remove updated_since coverage
├── test_diff.py      # REWRITTEN — assert 3-way set diff outputs
├── test_cycle_*.py   # MODIFIED — integration tests act as regression guards; unit-test surface rewritten
├── test_state.py     # MODIFIED — add LayerSummary tests; deprecate LayerPointerSnapshot tests

tests/common/
├── test_sync_cache.py # UNCHANGED (the NFR-004 cache-read contract test from #519 stays)
├── conftest.py        # UNCHANGED (the mock fixtures from #519 are used as regression guards)

tests/
├── test_vikunja_config.py # NEW — unit tests for scripts/common/vikunja_config.py
├── conftest.py            # UNCHANGED (the urlopen guard from #519 stays)

docs/runbooks/
├── sync-driver-ops.md  # MODIFIED — full-poll model, project-layer audit semantics, deletion-cleanup algorithm, URL config

docs/design/architecture/
├── credentials-and-secrets.md   # MODIFIED — add URL config file to storage mechanisms inventory
├── data/service-inventory.json  # MODIFIED — driver config_files list adds the URL config file
├── service-inventory.md         # MODIFIED — narrative reflects driver config additions
├── service-dependencies.view.md # MODIFIED — driver consumes URL config (new edge)
├── data/data-flows.json         # MODIFIED — new flow: URL config → driver + touchpoints
├── data-flows.md                # MODIFIED — narrative
├── data-flows.view.md           # MODIFIED — diagram

docs/design/
├── felix-capability-roadmap.md  # MODIFIED — mark Epic #507 as complete after this mission ships

docs/
├── INDEX.md                     # MODIFIED — sync-driver-ops.md entry updated for new scope
```

### New artifact paths (deployed)

```
/data/services/openclaw/config/
├── vikunja-base-url.txt                # NEW — single line URL, mode 0644, owner claude:claude

/data/services/openclaw/state/sync/
├── project-cache.json                  # EXISTS but schema unchanged (full-poll just replaces merge semantics)
├── task-cache.json                     # EXISTS, schema unchanged
├── freshness.json                      # EXISTS, schema unchanged
├── guard-state.json                    # EXISTS, schema unchanged
├── last-tick.json                      # MODIFIED schema — add layer_summary, deprecate layer_pointers
├── last-tick.errors.jsonl              # EXISTS, schema unchanged
├── conflict-events.jsonl               # EXISTS, schema unchanged

scripts/habits/state/
├── habits-history.jsonl                # MODIFIED schema — new event type "task_deleted"
```

## Phase 0: Research

The bulk of the architectural research happened during `/spec-kitty.specify` discovery. This Phase 0 captures implementation-level decisions that need to be locked before Phase 1 design.

See [research.md](./research.md) for the implementation-level decision log (R-001 through R-006).

## Phase 1: Design

See:
- [data-model.md](./data-model.md) — Entity definitions for new and modified structs
- [contracts/cycle-pipeline.md](./contracts/cycle-pipeline.md) — 6-phase pipeline contract under full-poll
- [contracts/url-config.md](./contracts/url-config.md) — URL config file format + env-var precedence
- [contracts/set-diff.md](./contracts/set-diff.md) — 3-way set-diff algorithm contract
- [quickstart.md](./quickstart.md) — Reviewer-facing 5-minute validation flow

## Phase 1 Re-Gate Evaluation

- [x] Data model captures all new and modified entities
- [x] Contracts document the boundaries the WPs must respect
- [x] Quickstart provides an end-to-end smoke test
- [x] No charter violations introduced by the design

---

## Risk Considerations

- **R-001 (medium)**: rewriting `cycle.py` Phase 5 has the largest blast radius — the cycle's atomic-commit guarantee must hold under the new code paths. Mitigated by NFR-004 (cache-read contract unchanged) and the integration-test regression guards.
- **R-002 (low)**: URL config file becomes a deploy-step dependency. Mitigated by the env var fallback in `get_vikunja_base_url()` and by the deploy script creating the file before any consumer reads it.
- **R-003 (low)**: project-layer set-diff produces a much larger event volume than today's merge-only path. Mitigated by the diff phase recording change-only events (no event when projects match cache); the LayerSummary records aggregate counts always.
- **R-004 (medium)**: deletion cleanup (FR-003) requires writing to two state files (`schedule.yaml` and `habits-history.jsonl`) plus the sync cache. If schedule.yaml prune succeeds but the history-log append fails, we leak partial state. Mitigated by ordering: write history-log first (append-only, atomic), then prune schedule.yaml, then remove from sync cache. Any failure after history-log mid-cleanup leaves a benign over-counted state — next cycle's full poll will retry the cleanup since the task will still be in_cache_only.
- **R-005 (low)**: the in-place test rewrite means PRs will show large diffs in `tests/sync/`. Reviewer fatigue risk. Mitigated by per-WP grouping (test changes co-located with the source they verify).

## Branch Strategy (restated per skill)

- **Current branch at planning start**: `main`
- **Planning/base branch for this feature**: `main`
- **Final merge target for completed changes**: `main`
- **branch_matches_target**: ✅ true

Mission ships as a single merge commit to `main`. No long-lived feature branch.

## Next step

`/spec-kitty.tasks` — generate work packages.
