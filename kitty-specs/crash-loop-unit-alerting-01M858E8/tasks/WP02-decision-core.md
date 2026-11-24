---
work_package_id: WP02
title: Crash-loop decision core
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- NFR-001
- NFR-004
- NFR-006
- SC-001
- SC-002
- SC-003
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crash-loop-unit-alerting-01M858E8
base_commit: 24e1008d70903b7245e3ebe9ebe4163d4a8f4323
created_at: '2026-11-23T23:29:12.919595+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- scripts/canary/crash_loop.py
- tests/canary/test_crash_loop.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/crash_loop.py
- tests/canary/test_crash_loop.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Crash-loop decision core

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Implement `scripts/canary/crash_loop.py`. It is **pure**: no I/O, no clock reads, no subprocess and no model call (NFR-006, INV-CL-8). It provides:

- `evaluate_tick(readings, prior_state, config, now, boot_id) -> TickOutcome`
- `plan_emissions(events, config) -> list[Emission]` (the cap plus the aggregate)
- `render_alert(event, config) -> Alert` and `render_aggregate(events) -> Alert`

This module is the heart of the mission. Every rule below has a test.

## Context to read first

- `kitty-specs/crash-loop-unit-alerting-01M858E8/data-model.md`: every invariant (INV-CL-1 to INV-CL-9), the state machine and the within-tick order.
- `research.md` R-04, R-05 (the proven-crossing rule and its stated limits), R-06 (resets, generations, boot rebase, the consumption boundary), R-07 (history and clock), R-08 (no retry), R-13 (complete versus incomplete) and R-15 (the cap and the bounded aggregate).
- `contracts/crash-loop-alert.md` §1 to §4 for Alert text and fields.
- `plan.md` "Post-plan Codex review dispositions" (rounds 1 and 2): the tick sequences named there **must** become tests.
- WP01's `scripts/canary/crash_loop_model.py` and `crash_loop_state.py`, which you import. Do not modify them; if they need a change, record it in the WP history and ask the orchestrator.
- `scripts/common/alert_bus/model.py` for `Alert` and `Severity`. `scripts/canary/dedup.py` for `DEFAULT_WINDOW`, the 6 h re-remind interval.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`. Get the worktree with `spec-kitty agent action implement WP02 --agent claude --mission crash-loop-unit-alerting-01M858E8`. Never edit `kitty-specs/` from the lane.

## Subtasks

Follow data-model.md "Per-unit order within one tick" **exactly**. The steps below describe it in detail.

### T006 — The proven-crossing rule (R-05)

- `prove(candidates, current_count, now, config) -> tuple[Proof | None, Proof | None]` returns `(best_holding_proof, tightest_unverified)`.
  - The candidates are every `history` entry, all strictly before `now`. `history[-1]` is the previous observation.
  - For each candidate `b`, compute:
    - `L = now − b.at`, in seconds as a float;
    - `m = max(1, ceil(L / window_seconds))`;
    - `Δ = current − b.count`;
    - `bound = m·(N − 1) + 1`.
  - The best holding proof is the candidate with `Δ ≥ bound` and the **smallest L** (the tightest interval); ties go to the larger Δ.
  - The tightest unverified candidate is the one with `Δ ≥ N`, no holding proof, and the smallest L.
  - Use exact integer or `Fraction` arithmetic for `ceil(L/window)` on whole seconds plus microseconds, so a float error cannot cross a boundary. Test L = exactly 900 s (m = 1) and 900.000001 s (m = 2).
- **History maintenance** (R-07, dominance compaction), applied after the decision unless the unit was rebased this tick:
  - If `current == history[-1].count`, **replace** that entry with `(now, current)`: a later baseline with the same count dominates.
  - Otherwise **append** `(now, current)`.
  - Then prune: **keep every entry with `at ≥ now − window`** (round-4 M1: single-window proofs are never lost). Among older entries, drop those older than `HISTORY_RETENTION` (24 h) and keep at most `HISTORY_MAX` (64), dropping the oldest. Always keep the newest.
  - Write `_maintain_history` and unit-test it.

### T007 — Clock, resets, generations, first sight, removal, scopes, ignore

The checks run in this order:

1. **Clock (INV-CL-9)**: if `now ≤ history[-1].at`, carry the unit's state over unchanged, emit nothing, and count `clock_skipped`.
2. **Boot change (per unit, round-3 HIGH)**: if the unit's stored `boot_id` differs from the current `boot_id`, rebase it (history `[(now, current)]`, store generation and boot ID) and close any episode **silently**. Count `rebased_on_boot`. This applies to containers too. Because the check is per unit, a unit whose scope was unreadable on the first post-reboot tick is still rebased at its next complete read. A None `boot_id` cannot reach here: WP03 fails all three scopes when the boot ID is unreadable.
3. **Reset**: if the container ID (generation) differs, or `current < history[-1].count`, replace the history with `[(now, current)]`, store the new generation, and count `resets` (FR-009). No alert or re-remind. With an open episode, the tick counts as **quiet** (T008 with `rose=False` and no proof), so it **may** emit the INFO `cleared` when quiet reaches K (round-3 M1).
4. **First sight** (no prior state): store a new `UnitState` with no event, and count `first_seen` (FR-010).

Per scope:

- **Incomplete** (`complete=False`): carry forward every prior unit whose key starts with `<scope>:` unchanged (INV-CL-7). `scope_status[scope] = ("unknown", f"could not check: {error}")`.
- **Complete**: `("healthy", f"{watched} watched, {ignored} ignored, {excluded} excluded, {elapsed_ms} ms")`. Prior units of the scope that are absent from the reading are dropped, and an open episode ends silently.
- **Ignored** (`obs.key in config.ignore`): skip the unit, do not store it (drop any prior state), and count it (INV-CL-6).
- A scope in `SCOPES` with no reading at all is `("unknown", "could not check: not read")`.
- Set `new_state.boot_id = boot_id`, or keep the prior value if the current one is None.

### T008 — The episode state machine

1. `rose = current > history[-1].count` (False on a reset).
2. **No episode**:
   - If a proof holds, open `Episode(started_utc=now, last_alert_utc=now, quiet_ticks=0, peak_delta=proof.delta)` and emit `alert`.
   - Else, if an unverified candidate exists, record an `UnverifiedRise`.
3. **Episode open**:
   - If `rose`, set `quiet = 0`; otherwise `quiet += 1`.
   - If `quiet ≥ K`, emit `cleared` (its proof field records the last interval), set `episode = None`, and **rebase the history to `[(now, current)]`** (INV-CL-5, CX-2).
   - Else, if a proof holds and `now − last_alert_utc ≥ DEFAULT_WINDOW`, emit `reremind` and set `last_alert_utc = now`.
   - Update `peak_delta`.
4. **Delivery never changes state** (INV-CL-10, R-08: no retry). There is no `apply_delivery` function.

### T009 — Emission plan and rendering

- `plan_emissions(events, config) -> list[Emission]`:
  - Sort by `(alert=0, reremind=1, cleared=2, key)`.
  - The first `max_alerts_per_tick` become individual `Emission(alert=render_alert(e, config), events=(e,))`.
  - **All** the rest fold into one `Emission(alert=render_aggregate(rest, today), events=tuple(rest))`.
- `render_alert` and `render_aggregate` follow `contracts/crash-loop-alert.md` §1 to §4 exactly: `source`, severities, titles, descriptions, and `details` with **string** values including `m` and `bound`.
  - The aggregate's description adds `"<key> <kind> +<Δ>/<period> <state>"` entries, separated by `; `, only while the total stays ≤ 900 characters. It then appends `"... and <k> more - see canary ledger <YYYY-MM-DD>"`.
  - `details.count` and `details.units_listed` are strings.
  - Assert in a test that the rendered description is ≤ `scripts.common.alert_bus.render.DESCRIPTION_MAX`.
- Render the period as whole minutes, rounded up, with a minimum of 1.

### T010 — Tests (`tests/canary/test_crash_loop.py`)

Inject `now` everywhere. Required tests, named so a reviewer can find them:

- `test_incident_replay_obsidian_sync_39_restarts` (SC-001): t0 count 0, t0 + 16 min count 39, both `active (running)`. Exactly one `alert` for `system:obsidian-sync.service`, with Δ = 39, period 960 s, m = 2 and bound 5.
- `test_user_unit_and_container_alert` (US1-2, US1-3, SC-004).
- `test_between_tick_loop_caught` (FR-005).
- `test_five_tick_episode_one_alert_then_one_cleared` (SC-002): loop for 5 ticks, each 16 min apart with +10. Then K quiet ticks. Exactly 1 alert and 1 cleared.
- `test_reremind_after_six_hours_only_with_proof`, and `test_no_reremind_when_rise_unproven`.
- `test_new_episode_after_clear_alerts_again` (US2-4).
- **CX-2**: `test_clear_does_not_replay_burst`, using minutes `(0,0) → (5,3) ALERT → (6,3) → (7,3) CLEARED → (8,3)`, with no event at minute 8. Include a `window_seconds=3600` variant.
- **Proof rule**:
  - `test_dense_observations_prove_within_one_window`: `(0,0),(1,1),(14,3)` alerts at 14 with m = 1.
  - `test_three_restarts_over_sixteen_minutes_is_unverified`: `(0,0),(16,3)` gives an UnverifiedRise with m = 2, bound 5, and no event. This is plan.md judgment call 1.
  - `test_three_restarts_in_spread_minutes_not_paged`: Codex round 2's 0.1 / 8 / 15.9 sequence, sampled at 0 and 16, gives no page.
  - `test_long_gap_requires_scaled_bound`: `(0,0),(180,3)` is unverified; `(0,0),(180,25)` pages, because m = 12 and the bound is 25.
  - `test_late_tick_still_catches_real_loop`: `(0,0),(17,39)` pages.
  - `test_straddled_burst_limit_documented`: `(0,0),(15,2),(30,4)` gives no page. This is the accepted limit, judgment call 2.
  - `test_boundary_exactly_one_window`.
  - **A property test**: for random restart timestamps and random sample times, whenever the code pages, some window-length interval really contains ≥ N restarts. Use `random.Random(seed)` with 2000 cases. No hypothesis dependency unless the repo already has it.
- US3:
  - `test_single_restart_no_alert` and `test_threshold_restarts_alert`, on the same fixture with m = 1 dense samples;
  - `test_ignored_unit_never_alerts` and its paired non-ignored control;
  - `test_decrease_is_reset_no_alert`;
  - `test_container_id_change_is_reset_no_alert`, with a higher count (CX-8);
  - `test_boot_change_rebases_all_scopes_including_containers` (round-2 B7);
  - `test_first_seen_is_baseline`.
- `test_reset_during_episode_counts_quiet`.
- `test_incomplete_scope_preserves_state_and_reports_unknown` and `test_complete_scope_drops_removed_unit_silently`.
- `test_clock_not_advanced_skips_unit`.
- `test_history_dominance_compaction`: an equal count replaces the newest entry, and a higher count appends. Codex round 3's `(0,0),(30,0),(60,2),(915,3)` **alerts** at 915. Entries older than 24 h are pruned, and the 64-entry cap drops the oldest **pre-window** entries. Codex round 4's `N=100` case (observations `(i,i)` for `i=0..64`, then `(65,100)`) **alerts**, because in-window entries are never pruned. The newest entry is always kept.
- `test_reboot_during_unreadable_scope_still_rebases`: boot A, count 0, then boot B with the container scope incomplete, then boot B with the same container ID at count 39. Rebase, no alert (round-3 HIGH).
- `test_reset_in_episode_may_clear_but_never_alerts` and `test_boot_change_closes_episode_silently`.
- `test_cap_folds_all_extra_events_into_one_bounded_aggregate`: 50 alerts give 3 individual plus 1 aggregate. The description is ≤ 1000 characters, ends "... and k more - see canary ledger", and `units_listed + k == 47`.
- `test_alert_text_and_details_match_contract`.
- `test_evaluate_tick_does_not_mutate_prior_state`.

## Definition of Done

- [ ] Every test above exists and passes. `.venv/bin/python -m pytest tests/canary -q` passes.
- [ ] The module is pure: grep shows no `open(`, `subprocess`, `datetime.now` or `time.` in `scripts/canary/crash_loop.py`.
- [ ] Commits use conventional messages and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- Re-run the CX-1, CX-2, CX-8, CX-10 and round-2 sequences mentally against the code, not just the tests.
- Check INV-CL-3: no `alert`/`reremind` without a holding proof. The property test is the backstop.
- Check that an incomplete scope never deletes state.
- Check that every `details` value is a string.
- The straddled-burst and unverified-3-in-16 tests assert **accepted** limits (plan.md judgment calls 1 and 2); that is intentional.
