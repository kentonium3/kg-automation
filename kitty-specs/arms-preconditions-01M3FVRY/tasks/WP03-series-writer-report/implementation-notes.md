# WP03 implementation evidence

## Environment handoff for WP04

`substrate.run()` passes one atomic JSON descriptor in `ARMS849_SERIES_GENERATION_JSON`. The object contains `series_id`, runner-visible `path`, `container_id`, `interval_s`, canonical `started_ts`, `writer_status`, and nullable `writer_reason`. WP04 consumes this descriptor to record the generation and graph-store boundary events.

## Coupled wiring

- `Ledger.summarise()` returns the existing cell mapping through `RunSummary` and attaches the run-level report as `.graph_store`; premise-violation refusal still runs first.
- `grading._admin()` adds the same report under top-level `graph_store`; completeness and unusable-ledger refusals still run before admin output or export.
- Malformed, unreadable, unrepresentable, or unavailable series evidence becomes `could_not_check: <reason>` and cannot add, remove, or alter a cell outcome.

## Live production callers

| Symbol | Production caller |
|---|---|
| `docker_container_id` | `substrate.run()` resolves the immutable FalkorDB container once. |
| `CgroupSeriesWriter` | `substrate.run()` owns its lifecycle around the runner process. |
| `cgroup_memory_mib` | `CgroupSeriesWriter` uses it as the default direct cgroup-v2 reader. |
| `graph_store_report` | `Ledger.summarise()` and `grading._admin()` compute the report at read/export time. |
| `CgroupRecord`, `CgroupSeriesHeader`, `CgroupSeriesTrailer` | The writer emits them and the report parser validates them. |

The legacy `RssSeriesWriter`, `RssSeriesSampler`, and their schemas remain live only for the pre-WP04 harness path. WP04 removes that path and its vestiges.

## Test-first and review evidence

- Initial sampler/report red: `16 failed, 71 passed` from missing cgroup/report symbols and the formerly accepted non-UTC offset.
- Initial substrate red: four lifecycle/descriptor tests failed before T014 wiring.
- First integrated green: `498 passed, 2 skipped` across sampler, substrate, ledger, and grading modules.
- Independent pre-commit review requested changes for resumed-generation scalar handling, interval overflow totality, path confinement, start-time ordering, and unavailable-result provenance. Each finding received a focused failing regression before its fix. The final focused integration set is `510 passed, 2 skipped` under both `PYTHONHASHSEED=0` and `PYTHONHASHSEED=3`; `py_compile`, full CI collection (8,185 tests), and `git diff --check` pass.
- The team lead approved the conservative resumed-generation selector in ruling `20260928T031145496975Z22b5607322`. The ruling was registered as a dated rubric §5 amendment before use, then synchronized into the memory-series contract, data model, research decision and WP task. Baseline remains bound to the first generation; all-resident never skips a selected CTC source for a later number; the interval requires running-generation consensus; the marginal requires the same source generation; and `source_series_ids` exposes every scalar's governing generations.
- Caller-isolation regressions preserve a real G cell's run row, terminal outcome, completeness result and `Summary` while malformed or unrepresentable series evidence becomes CTC through both `Ledger.summarise()` and grading admin output.
- Full repository seed validation is blocked by [kg-automation#1037](https://github.com/kentonium3/kg-automation/issues/1037): an unchanged WP02 Arm G bridge test leaves the caller waiting in `Bridge._wait` while the bridge loop is idle. The same hang reproduces in isolation under seeds 0 and 3. The team lead ruled this a known-open blocker for mission completion, not for WP03 review, because WP03 does not change `arm_g.py` or its tests and its 510-test focused integration gate is green. A bounded scratch run with the pre-cycle-5/6 `arm_g.py` still hung, excluding those production changes as the sole cause; diagnosis then stopped without a fix.

The authorised wrong-checkout recovery and byte-identity evidence are recorded in [recovery-2026-09-28.md](recovery-2026-09-28.md).
