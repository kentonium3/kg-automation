# WP05 implementation notes

## What changed

- Added one session-scoped research environment declaration. It verifies the `graphiti_core` import, the registered rendered corpus, and nonempty tokenizer and fastembed caches. Environment-dependent research tests use the one reason `ARMS849 research environment unavailable`, and the terminal summary counts that reason.
- Extracted the integration suite's serving/G/D/R fake kit into `tests/research/conftest.py`. The integration, grading, harness, and C8 tests now consume that kit directly.
- Added C8 coverage that runs the real host phase and the production `live_gates` container orchestration with a real `up_ts` and an explicit, fresh `process_start` for each session. The partial session includes a `sampler_unreadable_at_send` cell after the calibration population; the resumed session leaves that terminal row byte-identical, does not begin another attempt, preserves every earlier byte, and records no cell twice. The two negative cases record a failing fresh gate and refuse a session that skipped its gates.
- Added the commit-bound pre-merge checker. It runs office seeds 0 and 3 with live mode cleared, creates and removes a detached CI worktree, evaluates required nodes from JUnit rather than subprocess status alone, requires the live smoke, tears the live stack down in `finally`, and refuses a record that does not match `HEAD`.

## Red-first evidence

- FR-009: `tests/research/test_arms849_resume.py` initially failed collection because `tests.research.conftest` and its fake/environment seams did not exist. After the stub landed, the positive C8 case failed until the fresh gate outcome could be bound to `open_run_ledger`; the production-seam review then caught and corrected a hand-assembled outcome that bypassed `live_gates`. The final contract check injected the exact regression by removing `sampler_unreadable_at_send` from `CELL_TERMINAL_OUTCOMES`: resume produced 73 rows for 72 keys and the C8 test failed. Restoring the registered terminal set returns the test to green. This pins ledger-deltas item 1's “never retried by any session” clause at the resume seam.
- FR-014: the missing-environment regression initially observed more than one reason and an undercount because `test_arms849_serving.py` retained its local tokenizer/cache reason. The no-environment run now reports only the centralized reason for all seven environment skips in that slice.
- FR-015: `tests/research/test_check_849_premerge.py` initially failed collection because `scripts.research.check_849_premerge` did not exist. The checker tests then drove missing, skipped, failed, collection-error, commit-mismatch, omitted-live, failed-live, and cleanup-exception records to `FAIL` before their corresponding implementation paths were added.

## Required-node provenance

| Required node | Source |
|---|---|
| `test_live_runtime_registers_g_d_r_with_one_embedder` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_a_premise_violation_records_both_events_and_halts_before_later_work` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_an_unacknowledged_g_cancellation_records_stop_and_escapes_without_more_graph_work` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_graph_store_generation_and_boundaries_are_run_level_and_ordered` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_send_time_ceiling_breach_is_terminal_stops_and_sends_zero_bytes` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_measurement_is_ordered_exact_and_bound_to_commit_and_preflight` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_preflight_generation_refuses_dirty_or_changed_code_and_writes_nothing` | `23aea5fb0d399e957426ba262c8fb607b849102a` |
| `test_an_unregistered_arm_is_recorded_not_silently_skipped` | `82ca1fb23038d7de76ec7c8b1cee6c2c03a351d4` |
| `test_export_refuses_not_implemented_cells` | `2b473fb6b6509725dbfa7f2cf79b6b02b4df7cac` |
| `test_the_arms_share_one_refusal_class` | `3110b92aff206867ba9fb469f89753f7b860a383` |
| FR-016 `test_live_hybrid_search_returns_an_item_the_question_names` | `2355e2b9dd43b540e82d402f51e0e8aa3f18db0d` |
| `test_every_package_module_is_registered_in_the_isolation_inventory` | `409ccf0f72259836042f6a013aafbace1987a9dc` |
| `test_every_registered_module_exists_in_the_package` | `409ccf0f72259836042f6a013aafbace1987a9dc` |
| `test_attempt_start_carries_the_session_id_of_its_own_session` | `e53cb439913a57758465ffc5d2e8553c7fae5130` |
| `test_real_cgroup_writer_emits_bound_header_records_and_a_clean_trailer` | `b4085f4dc184919174e5ea66212e47d20a86f6eb` |
| `test_graph_store_report_round_trips_the_real_writer_against_a_fake_cgroup` | `b4085f4dc184919174e5ea66212e47d20a86f6eb` |
| `test_report_unavailable_conditions_are_honest_and_never_raise` | `b4085f4dc184919174e5ea66212e47d20a86f6eb` |
| `test_c19_only_the_canonical_isoformat_form_is_accepted` | `52f4d2e13989c9238cb0e58dadc3fab3d8a95ca4` |
| C-1 `test_view_carries_nothing_but_the_allowed_fields` | `2b473fb6b6509725dbfa7f2cf79b6b02b4df7cac` |
| C-2 `test_admin_report_holds_the_non_scored_cells_and_lives_apart` | `2b473fb6b6509725dbfa7f2cf79b6b02b4df7cac` |
| C-5 `test_assembly_priority_cap_dedup_and_frozen_layout` | `46d825ac56dbce76dc5bf5262f4972d5be78498a` |
| `test_live_style_resume_with_fresh_timestamped_gates_preserves_prior_rows` | This WP05 change set, `test_arms849_resume.py` |
| `test_live_style_resume_stops_and_records_a_failing_fresh_gate` | This WP05 change set, `test_arms849_resume.py` |
| `test_live_style_resume_cannot_write_after_skipped_gates` | This WP05 change set, `test_arms849_resume.py` |
| `test_missing_research_environment_has_one_named_counted_skip_reason` | This WP05 change set, `test_arms849_resume.py` |
| `test_passing_record_is_bound_to_head_and_verifies` | This WP05 change set, `test_check_849_premerge.py` |

The checker contains the 26 exact selectors. Collection against the office4 environment found all 26; no marker expression or discovery shortcut supplies this list.

## Live callers and dead-code check

| Symbol or surface | Live caller |
|---|---|
| `research_environment` fixture | The four environment/C8 tests in `test_arms849_resume.py`; the shared `CORPUS`, `CACHE`, and reason are also imported by the affected research modules |
| `pytest_terminal_summary` | pytest's plugin hook dispatch for every research-suite run |
| Extracted fake kit | `test_arms849_integration.py`, `test_arms849_grading.py`, `test_run_849_harness.py`, and `test_arms849_resume.py` |
| `run_premerge` | `check_849_premerge.main` in normal record-writing mode |
| `verify_record` / `--verify` | `check_849_premerge.main` when the merge operator supplies the cited JSON record; unit tests also exercise both matching and mismatched commits |
| `REQUIRED_NODES` and `LIVE_NODES` | `run_premerge`, `finalize_record`, and `verify_record` |

## Validation

- Focused C8: 5 passed.
- Checker contract tests: 36 passed.
- Integration, harness, grading, resume, checker, and serving slice: 316 passed, 1 expected live-only skip.
- Ledger, frozen-text, and loader slice: 389 passed.
- No-environment serving/resume slice: 20 passed, 7 skips, all seven counted under `ARMS849 research environment unavailable`.
- All four resource-heavy arm modules collect cleanly: 172 tests collected.
- New WP05 files pass Ruff; `py_compile` and `git diff --check` pass.

The terminal-resume mutation run failed as intended with 73 run rows for 72 unique keys; the unmutated production run passed and retained one attempt and one byte-identical `sampler_unreadable_at_send` row for `G/C1/repeat 2`.

The combined resource-heavy run was stopped after several minutes in its existing tokenizer/cache work. A gates-module run also encountered the execution sandbox's socket prohibition (`PermissionError: Operation not permitted`) after ten passing tests. Neither result is recorded as a code failure.

The mission-wide two-seed suite and real detached-worktree checker remain subject to the already-filed WP02 full-suite deadlock, kg-automation#1037. Per Kent's instruction, WP05 does not repair that state unless it blocks a later Spec Kitty gate. The full checker, including the required live smoke and the final commit-bound JSON record, remains the documented freeze-time step after mission merge.

## Scope notes

- Changes outside the five originally owned files only replace local research environment paths/reasons with the shared authority or point existing fake consumers at `conftest.py`.
- Unrelated Ruff rewrites in the integration, ledger, loader, and harness tests were reverted after structural review.
