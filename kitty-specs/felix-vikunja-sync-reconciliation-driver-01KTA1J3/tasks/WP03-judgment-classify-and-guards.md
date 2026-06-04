---
work_package_id: WP03
title: 'Judgment: UC classification + delivery guards'
dependencies:
- WP02
requirement_refs:
- FR-002
- FR-005
- FR-007
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP03 from plan.md + contracts/cycle-pipeline.md § Phase 3, § Phase 4 guards
authoritative_surface: scripts/sync/
execution_mode: code_change
owned_files:
- scripts/sync/classify.py
- scripts/sync/guards.py
- tests/sync/test_classify.py
- tests/sync/test_guards.py
tags: []
---

# WP03 — Judgment: UC classification + delivery guards

## Objective

Classify each `DivergenceCandidate` from WP02's diff phase into `auto_resolved` or `unsafe_to_auto_resolve` using the four unsafe-class criteria (UC-1 through UC-4, with UC-1 collapsed into UC-2 per the research finding). Implement the three delivery guards (G-1, G-2, G-3) that gate WhatsApp delivery for unsafe events. Both modules are deterministic, pure-or-near-pure functions; no judgment by an LLM; no I/O beyond state-file reads.

After this WP, downstream WPs can:
- Call `classify(candidate, downstream_fields, has_override_signal) → ClassifiedConflict` to label each divergence with class + reason codes.
- Call `apply_guards(event, recent_events_24h, task_cache, guard_state) → GuardDecision` to decide whether to deliver, log-only, or suppress.

## Context

Per `research.md` Unknown 3, Vikunja v0.24.6 does NOT return `updated_by` on tasks, so UC-1 (`kent_edit_after_felix_write`) and UC-2 (`operator_authored_field`) cannot rely on a direct Vikunja author signal. They collapse into a single "the cache says X, Vikunja says Y" check — implemented in WP02's diff phase. By the time `classify` runs, every input is by definition a divergence; UC-1/UC-2 always fire.

UC-3 (`downstream_behavior_depends`) and UC-4 (`manual_override_signal`) remain independent:
- UC-3 fires if the diverged field is in the curated `DOWNSTREAM_AFFECTING_FIELDS` set.
- UC-4 fires if the task carries the `felix:ignore` label OR its title starts with `[NO FELIX]`. UC-4 INVERTS the classification to `auto_resolved` — operator-explicit "don't bother me" wins.

The three guards apply in order (cheapest first):
- **G-3 (hard daily cap)**: 5 unsafe pings per ET-calendar-day max. Stored in `guard-state.json`.
- **G-2 (post-Felix-write suppression)**: 30 minutes after Felix's last observed write to that field, suppress. Reads `TaskCacheRecord.felix_last_observed_at`.
- **G-1 (24h event-id-stem dedup)**: same (layer, entity, field) within 24h → suppress. Reads recent rows from `conflict-events.jsonl`.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP03 --agent <name>
```

Depends on WP02.

---

## Subtask T010 — `scripts/sync/classify.py`: UC classification

**Purpose**: Pure function from `DivergenceCandidate` + override-signal callable → `ClassifiedConflict` with class label and reason codes.

**Steps**:

1. Define `@dataclass(frozen=True) class ClassifiedConflict`:

   ```python
   @dataclass(frozen=True)
   class ClassifiedConflict:
       candidate: DivergenceCandidate
       class_: str                     # "auto_resolved" | "unsafe_to_auto_resolve"
       unsafe_reasons: tuple[str, ...] # subset of REASON_CODES
   ```

2. Define module-level constants:

   ```python
   REASON_CODES = ("uc1_uc2_divergence", "uc3_downstream_behavior", "uc4_manual_override")

   DOWNSTREAM_AFFECTING_FIELDS = frozenset({
       "due_date", "project_id", "done", "repeat_after", "repeat_mode", "title",
   })

   MANUAL_OVERRIDE_LABEL = "felix:ignore"
   MANUAL_OVERRIDE_TITLE_PREFIX = "[NO FELIX]"
   ```

3. Implement `has_override_signal(task: dict) → bool`:
   - True if any label in `task.get("labels", [])` has `title == MANUAL_OVERRIDE_LABEL`.
   - OR `task.get("title", "").startswith(MANUAL_OVERRIDE_TITLE_PREFIX)`.

4. Implement `classify(candidate: DivergenceCandidate, task: dict) → ClassifiedConflict`:
   - Always add `uc1_uc2_divergence` to reasons (every candidate is by definition a divergence).
   - If `candidate.field ∈ DOWNSTREAM_AFFECTING_FIELDS` → add `uc3_downstream_behavior`.
   - If `has_override_signal(task)` → add `uc4_manual_override` AND set class to `"auto_resolved"`. The override is the inverter.
   - Otherwise, class is `"unsafe_to_auto_resolve"`.

5. Pure function. No I/O. Deterministic on identical inputs.

**Files**:
- `scripts/sync/classify.py` (~140 lines)

**Validation**:
- [ ] Candidate without UC-3 trigger AND no UC-4 → unsafe with just `["uc1_uc2_divergence"]`
- [ ] Candidate with downstream field AND no UC-4 → unsafe with `["uc1_uc2_divergence", "uc3_downstream_behavior"]`
- [ ] Candidate with UC-4 override → auto_resolved with the relevant reasons including `"uc4_manual_override"`
- [ ] Classification is deterministic (same inputs → same outputs in two runs)

---

## Subtask T011 — `scripts/sync/guards.py`: G-1, G-2, G-3 delivery guards

**Purpose**: Determine, for each `unsafe_to_auto_resolve` event, whether to deliver it via WhatsApp or suppress it (and which guard fired).

**Steps**:

1. Define `@dataclass(frozen=True) class GuardDecision`:

   ```python
   @dataclass(frozen=True)
   class GuardDecision:
       decision: str                  # "approve" | "suppress"
       suppressed_by: str | None      # "g1" | "g2" | "g3" | None
   ```

2. Define module-level constants:

   ```python
   G1_LOOKBACK_HOURS = 24
   G2_POST_WRITE_SUPPRESSION_MINUTES = 30
   G3_DAILY_CAP_DEFAULT = 5
   ```

3. Implement `event_id_stem(layer: str, entity_id: int, diff_field: str) → str`:
   - Returns `sha256(f"{layer}|{entity_id}|{diff_field}".encode("utf-8")).hexdigest()[:16]`.
   - Used by G-1 to find prior events for the same (layer, entity, field) triple.

4. Implement `apply_g3(guard_state: GuardState, now_et_day: str) → GuardDecision | None`:
   - If `guard_state.g3_daily_cap.calendar_day_et == now_et_day` AND `unsafe_pings_sent_today >= cap` → return `GuardDecision("suppress", "g3")`.
   - Else return None (no decision).

5. Implement `apply_g2(candidate: DivergenceCandidate, task_cache: TaskCacheRecord, cycle_started_at: datetime) → GuardDecision | None`:
   - Read the task's `felix_last_observed_at` from the cache for the relevant entity.
   - If the gap between `cycle_started_at` and `felix_last_observed_at` is ≤ 30 minutes → return `GuardDecision("suppress", "g2")`.
   - Else return None.

6. Implement `apply_g1(candidate: DivergenceCandidate, recent_events: list[ConflictEvent]) → GuardDecision | None`:
   - Compute the candidate's event_id_stem.
   - Scan `recent_events` (the last 24 hours of conflict-events.jsonl) for any event with the same stem that was `delivered` or `auto_resolved`.
   - If found → return `GuardDecision("suppress", "g1")`. Else return None.

7. Implement `apply_guards(candidate, task_cache, guard_state, recent_events, cycle_started_at) → GuardDecision`:
   - Call apply_g3 first; if returns suppress → return it.
   - Then apply_g2; if returns suppress → return it.
   - Then apply_g1; if returns suppress → return it.
   - Otherwise → return `GuardDecision("approve", None)`.

8. Implement `now_et_day(now_utc: datetime) → str`:
   - Convert UTC to America/New_York → return ISO date `YYYY-MM-DD`.
   - Use stdlib `zoneinfo.ZoneInfo("America/New_York")` (Python 3.9+).

9. Implement `roll_g3_day_if_needed(guard_state, now_et_day) → GuardState`:
   - If `guard_state.g3_daily_cap.calendar_day_et != now_et_day` → reset `unsafe_pings_sent_today` to 0 and update the day.
   - Returns the (possibly rolled) GuardState.

**Files**:
- `scripts/sync/guards.py` (~230 lines)

**Reference precedent**: `scripts/security/credential_health_check/signals.py` for the deterministic-Python-driver pattern.

**Validation**:
- [ ] G-3 cap correctly suppresses the 6th unsafe ping on a day when default cap is 5
- [ ] G-3 day rollover resets the count after midnight ET
- [ ] G-2 suppresses events within 30 minutes of `felix_last_observed_at`
- [ ] G-1 suppresses duplicate event_id_stems within 24h regardless of value
- [ ] Guard order: G-3 first (cheapest), then G-2, then G-1 (most expensive — scans the log)

---

## Subtask T012 — `tests/sync/test_classify.py`: classification matrix [P]

**Purpose**: Cover the full UC matrix and confirm UC-4 inversion behavior.

**Steps**:

1. Build synthetic `DivergenceCandidate` + `task` fixtures.

2. Test cases:

   - `test_basic_unsafe_no_uc3_no_uc4`: candidate on field NOT in downstream set, task without override → unsafe, reasons = `("uc1_uc2_divergence",)`.
   - `test_unsafe_with_uc3`: candidate on `due_date` (downstream) → unsafe, reasons = `("uc1_uc2_divergence", "uc3_downstream_behavior")`.
   - `test_uc4_label_inverts_class`: task labels include `{"title": "felix:ignore"}` → auto_resolved.
   - `test_uc4_title_prefix_inverts_class`: task title `[NO FELIX] sensitive task` → auto_resolved.
   - `test_uc4_dominates_uc3`: candidate on downstream field BUT task has UC-4 override → auto_resolved (UC-4 wins).
   - `test_uc4_reason_present_in_auto_resolved`: when UC-4 inverts, `uc4_manual_override` IS in the reasons (so the log records why).
   - `test_classification_is_deterministic`: run classify twice with identical inputs → identical output.
   - `test_downstream_set_contains_expected_fields`: assert each of `{due_date, project_id, done, repeat_after, repeat_mode, title}` is a member.

3. Pure tests; no fixture I/O.

**Files**:
- `tests/sync/test_classify.py` (~220 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_classify.py -q` passes
- [ ] Every test asserts EXACT reason-code tuple (not just presence)

---

## Subtask T013 — `tests/sync/test_guards.py`: guard semantics [P]

**Purpose**: Cover the three guards independently and the order-of-application invariant.

**Steps**:

1. Test cases for G-3:
   - `test_g3_under_cap_does_not_suppress`: `unsafe_pings_sent_today=2, cap=5` → no suppression decision.
   - `test_g3_at_cap_suppresses`: `unsafe_pings_sent_today=5, cap=5` → suppressed_by g3.
   - `test_g3_day_rollover_resets_count`: stored day `2026-06-03`, now is `2026-06-04` → `roll_g3_day_if_needed` returns a GuardState with count=0 and day=`2026-06-04`.

2. Test cases for G-2:
   - `test_g2_within_30_min_suppresses`: `felix_last_observed_at` is 5 minutes before cycle start → suppressed_by g2.
   - `test_g2_outside_window_does_not_suppress`: `felix_last_observed_at` is 31 minutes before → no decision.
   - `test_g2_missing_cache_entry_does_not_suppress`: task not in cache → no decision (defaults to safe-to-classify).

3. Test cases for G-1:
   - `test_g1_no_recent_events_does_not_suppress`: empty recent_events → no decision.
   - `test_g1_matching_stem_within_24h_suppresses`: prior event with same (layer, entity_id, diff_field), `delivered` status → suppressed_by g1.
   - `test_g1_matching_stem_older_than_24h_does_not_suppress`: prior event 25h ago → no decision.
   - `test_g1_matching_stem_but_suppressed_does_not_suppress_again`: prior event with same stem but `suppressed_by_g3` status → no decision (G-1 only counts delivered + auto_resolved).
   - `test_g1_different_stem_does_not_suppress`: prior event on different field → no decision.

4. Test cases for `apply_guards` integration:
   - `test_apply_order_g3_first`: cap reached AND prior event AND within G-2 window → suppressed_by g3 (first guard fires).
   - `test_apply_order_g2_before_g1`: cap not reached, within G-2 window, prior event present → suppressed_by g2.
   - `test_apply_returns_approve_when_no_guard_fires`: cap not reached, outside G-2 window, no prior event → approve, suppressed_by None.

5. Use synthetic data; no real I/O.

**Files**:
- `tests/sync/test_guards.py` (~280 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_guards.py -q` passes
- [ ] Guard order tests assert which guard fired, not just that suppression happened

---

## Test strategy

Both new test files use pure unit tests (no mocks needed beyond synthetic fixtures). Run together:

```bash
python3 -m pytest tests/sync/test_classify.py tests/sync/test_guards.py -q
```

Combined target: ≥85% line coverage of `scripts/sync/classify.py` and `scripts/sync/guards.py` (both modules are pure, so high coverage is easy and expected).

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP03 worktree
- [ ] `python3 -m pytest tests/sync/ -q` passes (including WP01 + WP02 tests)
- [ ] No edits to files outside the WP's `owned_files` list
- [ ] `REASON_CODES`, `DOWNSTREAM_AFFECTING_FIELDS`, `MANUAL_OVERRIDE_LABEL`, `MANUAL_OVERRIDE_TITLE_PREFIX` exported as module-level constants (downstream WP04 emit imports them)
- [ ] `event_id_stem` exported from `guards.py` (downstream WP04 uses the same stem for `event_id` computation)
- [ ] Both modules importable cleanly; no I/O at import time

---

## Risks and mitigations

- **Risk: TZ handling for G-3 day boundary.** Mitigation: explicit `zoneinfo.ZoneInfo("America/New_York")`; never compare UTC strings as date prefixes. Test covers a date rollover scenario.
- **Risk: `felix:ignore` label matching is brittle (case-sensitive, exact match).** Mitigation: spec says label title is `felix:ignore` literal; tests assert exact match. Future generalization (e.g., regex on labels) would be a separate spec.
- **Risk: G-1 scan-the-log performance at scale.** Mitigation: tested-acceptable at expected log size (a year is single-digit MB). Future optimization: read in reverse byte chunks and stop at first row older than 24h. Documented as future work.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Classify is pure**: no I/O whatsoever. Same inputs → same outputs (test asserts).
2. **UC-1/UC-2 collapse honored**: every candidate has `uc1_uc2_divergence` in reasons. There is no separate "UC-1 only" vs "UC-2 only" path — they are one path.
3. **UC-4 inverts class**: this is the only criterion that REDUCES the urgency of an event. All others increase.
4. **Guard order**: G-3, G-2, G-1. Verify the order in `apply_guards` matches the documented sequence.
5. **`event_id_stem` matches the spec**: 16-char lowercase hex prefix of `sha256(layer | entity | field)`. WP04's full `event_id` will append the timestamp and value — same stem prefix lets G-1 dedup work.
6. **No edits to WP01/WP02 owned files** (state.py, http.py, fetch.py, diff.py).

Reject if classify has I/O, if guard order is wrong, if UC-4 is not the inverter, or if any owned-file boundary is violated.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Pipeline contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md` § Phase 3, § Phase 4
- Research finding (UC-1/UC-2 collapse): `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/research.md` § Unknown 3
- Data model: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/data-model.md` § Entity 7 (Guard)
- DivergenceCandidate (from WP02): `scripts/sync/diff.py`
- State types (from WP01): `scripts/sync/state.py`
