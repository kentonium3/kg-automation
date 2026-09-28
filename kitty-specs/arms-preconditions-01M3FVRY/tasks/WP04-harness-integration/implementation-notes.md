# WP04 implementation notes

## What changed

- Registered G, D, and R through lazy factories. Live construction creates one embedder shared by G and R, and registrations are closed on every session exit after the worker has terminated. A repeated controller interrupt that leaves a worker alive deliberately skips close hooks so resources are not torn down underneath active arm code; this bounded safety exception is regression-tested.
- Preserved domain exceptions across the timeout grace race. Premise violations and unacknowledged G cancellation now stop the session with their registered events.
- Bound a fresh GTT ceiling callback at every live send boundary and at the secondary probe. A breach records `exceeds_memory_ceiling` and stops; an unreadable send records `sampler_unreadable_at_send` and continues.
- Bound the host graph-store descriptor to the ledger, recorded the pre-build listing boundary and the eighth-successful-build boundary, and removed the per-attempt RSS path.
- Added the ten-cell smoke plan and its calibration ordering, plus the freeze-time exact-request measurement tool.
- Made the process start injectable through the CLI gate path.
- Refused `--measure` unless the checkout is clean and its HEAD and corpus fingerprints match the cited preflight record.
- Refused preflight generation on a dirty checkout and re-verified the same clean HEAD at the write boundary. This mitigates the check/use window; it does not eliminate it. A stored tree hash would make the evidence content-verifiable, and an injectable checkout-state seam would keep unrelated tests independent of the real worktree. Both are tracked as follow-up scope in kg-automation#1043.

## Red-first evidence

The new tests failed against the pre-WP04 harness for the intended missing behavior:

- live G/D/R registration and shared embedder;
- timeout-grace propagation for a breach, unreadable send, premise violation, and fatal G cancellation;
- premise and cancellation stop events;
- graph-store descriptor and boundary events;
- send-time ceiling outcomes and zero-send behavior;
- smoke identity and ordering;
- exact token-table binding and mismatch refusal.

The owned sampler retirement guard produced five failures before the legacy RSS classes were removed and is green after the coupled cleanup. The two remaining cross-file RSS failures were then retired under the team lead's terminal-owner ruling. FR-004 remains the declared regression-only exemption: the existing ledger and export gates already refuse an all-`not_implemented` primary.

## Stable required nodes

- `tests/research/test_arms849_integration.py::test_live_runtime_registers_g_d_r_with_one_embedder`
- `tests/research/test_arms849_integration.py::test_a_premise_violation_records_both_events_and_halts_before_later_work`
- `tests/research/test_arms849_integration.py::test_an_unacknowledged_g_cancellation_records_stop_and_escapes_without_more_graph_work`
- `tests/research/test_arms849_integration.py::test_graph_store_generation_and_boundaries_are_run_level_and_ordered`
- `tests/research/test_arms849_integration.py::test_send_time_ceiling_breach_is_terminal_stops_and_sends_zero_bytes`
- `tests/research/test_run_849_harness.py::test_measurement_is_ordered_exact_and_bound_to_commit_and_preflight`
- `tests/research/test_run_849_harness.py::test_preflight_generation_refuses_dirty_or_changed_code_and_writes_nothing`

## Live production callers

| Symbol | Production caller |
|---|---|
| `ARM_FACTORIES` | `live_runtime` through `build_arms` |
| `arm_g.make_bridge` / `Bridge.answer` / `Bridge.build_graph` / `Bridge.drop_graph` / `Bridge.list_graphs` / `Bridge.close` | the G factory and `Session` |
| `arm_d.bind` | the D factory |
| `arm_r.bind` / `arm_r.calibration_inputs` | the R factory and `Session.ensure_calibration` |
| shared `errors.*` | `_call_with_timeout`, `Session._record_raised`, `run_session`, and the before-send guard |
| `serving.complete(..., before_send=...)` | `ServingFacade.complete` for every cell and `live_secondary_gate` |
| `sampler.require_breached` | `Session._one_attempt` and `live_secondary_gate` at sampler bind time |
| `CgroupSeriesWriter` | `substrate.run` |
| `graph_store_report` | `Ledger.summarise` and `grading.export` |
| `ledger.is_smoke` / `SMOKE_PLAN` | `status_line`, `plan`, `open_run_ledger`, and smoke calibration ordering |
| `measure_requests` | CLI `--measure` |

## Coupled cleanup

- Removed the per-attempt RSS sampler and all `RssRecord` / `RssSeries*` APIs and tests from `sampler.py` and `test_arms849_sampler.py`.
- Removed the harness RSS context, refusal, runtime field, and row plumbing.
- Removed the two obsolete `RssSampler` sections from `test_arms849_gates.py` after the authoritative primary `status.json` showed its owner WP01 terminal in `approved`. The RSS half of `test_samplers_never_raise_into_the_arm` retired while its GTT assertion survived; `test_rss_sampler_parses_docker_stats` and its `_to_mib` checks were wholly specific to the retired RSS parser. No outliving gate, threshold, or refusal assertion was removed. The crossing and authorisation are recorded in WP04 history; kg-automation#1041 tracks the missing terminal-owner workflow concept.
- Added the bounded unowned `preflight.py` integrity fix authorised as consequent scope: dirty-tree refusal, same-HEAD re-verification at the write boundary, and one refusal-path regression covering dirty entry and changed exit. Pre-existing preflight tests use an explicit local clean-head fixture by name; no autouse seam can hide the new guard from future tests. The crossing and stronger tree-hash/injectable-seam follow-up are recorded in WP04 history.
- Ledger references to `falkordb_rss_peak_mib` remain intentionally as rejection guards for legacy or injected per-cell columns.

## Validation

- `pytest-randomly` seed 0: 279 passed, 1 live-only skip across the three WP04-owned test modules.
- `pytest-randomly` seed 3: 279 passed, 1 live-only skip across the same modules.
- The surviving `test_samplers_never_raise_into_the_arm` GTT assertion passes after the terminal-owner cleanup.
- `tests/research/test_arms849_ledger.py` plus `tests/research/test_arms849_grading.py`: 386 passed.
- `py_compile` and `git diff --check`: pass.
- The full-suite/fresh-worktree run remains subject to the already-filed WP02 full-suite deadlock, kg-automation#1037. Per Kent's instruction, WP02 state is not repaired unless it blocks a subsequent Spec Kitty gate.
