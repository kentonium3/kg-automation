# Contract: ledger deltas

These are additive to arms-run-01M3APTA `contracts/ledger-schema.md`. Each is dated 2026-09-26 under design-lead rulings.

1. **Outcome `exceeds_memory_ceiling`**: a breach detected at `before_send`. It is terminal for the attempt, not scored, and never included in any average or summary statistic. It carries `memory_ceiling: {measured_gib, ceiling_gib, stage}`. It is never produced for an unreadable sampler. A sampler unreadable BEFORE the attempt remains the `sampler_unreadable` event, with no attempt. A sampler unreadable AT SEND (the attempt already durably begun) is its own terminal outcome `sampler_unreadable_at_send`. A breach STOPS the session (its own stop signal). An unreadable-at-send refuses the cell and does NOT stop the session (§5, "refuses the cell"). A breached cell is TERMINAL and never retried by any session (rubric §5 @`a00abc03`, Kent 2026-09-26 22:41Z). A ledger containing either cannot be primary-complete while the cell stays un-scored (design lead, 20260926T223312278643Zbb9e71a68a, narrowed 20260926T223436721075Z2f274189c3).

   **Dated clarification (2026-09-27, design lead 20260927T034310853223Za953d8513e, INTERIM pending Kent's §5 ruling):**
   - `sampler_unreadable_at_send` is **cell-terminal**: it is never retried by this or any session, the same footing as a breach, because a failed send-time read may correlate with the memory extreme (informative missingness).
   - It remains a distinct outcome from `exceeds_memory_ceiling`, carries no `memory_ceiling`, and still does NOT stop the session.
   - A three-way classification (a transient read failure vs. evidence of the extreme vs. undetermined) is proposed and awaits Kent. The implementer notes that the send-time guard reads host amdgpu GTT sysfs, not the graph-store cgroup (bus 20260927T034524353399Z2c355a8adb).

   **Dated addition (2026-09-27, Kent's approval relayed on bus 20260927T042849445103Z818cb5fc71; rubric §5 amended on main @`eb45658e`):**
   - The five-outcome classification is REGISTERED.
   - Until a device-health probe and a plausibility bound both exist, every send-time read failure is (D) `sampler_unreadable_at_send`: cell-terminal and never retried. This is the sanctioned behaviour, no longer an interim.
   - Building the health probe and the plausibility bound is NOT in this mission's scope (C-001, C-007).
   - This mission owes one thing to §5: WP04 states whether (D) and `telemetry_incomplete` are disjoint, and how a ledger reader tells them apart.
2. **Graph-store boundary events**: `series_generation`, `graph_store_first_build` and `graph_store_all_resident` are validated on write and replay. The run-level graph-store REPORT (baseline, peak, all-resident) is computed at summary/export time and validated when produced; it is never persisted (rubric §5 third correction @`91e679e6`).
3. **No per-cell graph-store column.** `falkordb_rss_peak_mib` is retired, and any graph-store column on a per-cell row is refused, on write and replay.
4. **`attempt_start.session_id`** is required. **Dated addition to item 2 (2026-09-26):** the per-session clause, "an attempt is authorised only by its own session's passing gates", becomes enforceable. Replay requires the attempt's `session_id` to equal that of the most recent `session_gates` above it, which must be passing, and must not be skipped unless the header binds `SKIP_GATES_SHA`.
5. **`premise_violated` event**: a ledger containing one is refused as a primary (`require_complete_primary`), refused by the grading export, and refused by `Ledger.summarise()`. Rows are untouched, but they are not usable (correction C).
6. Sampler/series timestamps are accepted only in canonical UTC isoformat (C12).
7. **Dated addition (2026-09-27; team-lead ruling bus 20260927T082853961708Z91beadc33c and design-lead refinement 20260927T082948674022Zc8ccbe6b30): primary completeness is judged against the plan's grid, never against runtime enumerations.**
   - **Rule:** primary completeness is evaluated against the cell count carried by the plan identity in the ledger's immutable header. It is never evaluated against any runtime enumeration of arms, questions or repeats, and never against the rows present.
   - **Why:** an arm that fails at REGISTRATION writes no rows at all, so it produces no `not_implemented` markers. A row-keyed or `len(ARM_FACTORIES)`-derived check therefore passes on exactly the partial-registration failure it exists to catch.
   - **Refusal:** it names the missing cells, not only a count.
   - **Session:** a registration failure terminates it loudly, as a second, independent barrier.
