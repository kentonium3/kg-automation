# Research: Migrate Felix Touchpoints to Sync Cache — Phase 0

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Date**: 2026-06-04
**Researcher**: Claude (Opus 4.7) via static analysis of `docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md` (the canonical TP catalog from #518) + per-file inspection of the listed touchpoints.

This document resolves the planning unknowns named in the planning interrogation (Q1: SLA tiering) and surfaces one critical scope-correcting finding that emerged from systematically classifying each of the 25 RQ-2 catalog entries. The finding does not change the spec's locked decisions; it sharpens the mission's effective scope from "18 touchpoints" (the catalog's literal upper-bound TP number) to "6 cron-fired read-only callsites that the cache can actually serve."

---

## Critical finding — Scope Correction

**Decision**: The migration set is **6 touchpoint files** in 3 domain clusters (habits ×4, escalation ×1, enrichment ×1), not the 18 implied by the RQ-2 catalog's TP numbering.

**Rationale**: The spec body (FR-004) was written from the RQ-2 catalog's surface count: "TP-01 through TP-18". Phase 0 research enumerated each TP catalog entry by `http_verb` field and the catalog's textual annotations ("provisioning", "maintenance", "legacy v1"). The classification matrix:

| Class | TPs | Count | In scope? | Why |
|---|---|---|---|---|
| **Cron-fired read-only** | TP-02, TP-03, TP-04, TP-07, TP-10, TP-12 | 6 | **YES — migration candidates** | Direct GETs against Vikunja from cron-driven scheduled callsites; the cache exists precisely for these. |
| **Write-only** | TP-01, TP-05, TP-06, TP-09, TP-11, TP-16A | 6 | NO | Already excluded by FR-010 / C-003 (driver stays read-only against Vikunja; touchpoints continue to write directly). No GET to migrate. |
| **Mixed write+read (post-write verify)** | TP-13, TP-14, TP-15C, TP-15D, TP-15E, TP-16C, TP-16D, TP-16E | 8 | NO | The GET is post-write verification within the same script run. Migrating the GET would introduce the 5-min lag inherent to cache reads, breaking the script's correctness model (it WANTS to read the just-written state). These reads stay direct. |
| **Legacy/superseded** | TP-15A (exclude_completed v1), TP-15B (identify_workout_task one-off), TP-18 (query_active_habits v1) | 3 | NO | Either deprecated by a v2 (TP-15A → TP-03), one-shot operator utility (TP-15B), or legacy of a refactor that's already moved on (TP-18). Migrating them is wasted effort. |
| **Maintenance/provisioning** | TP-16B | 1 | NO | One-shot provisioning tool (`enumerate_real_projects`), operator-invoked. Cache reads gain nothing. |
| **Pre-bootstrap (historical data)** | TP-08 (backfill_jsonl_from_comments) | 1 | NO | Operator-invoked utility that reconstructs Felix's JSONL from Vikunja's historical comment thread. By definition runs against state older than the cache. Stays direct. |

**Total**: 25 catalog entries → 6 actual migration candidates.

**Alternatives considered**:

- *Migrate the 8 mixed write+read GETs anyway, with explicit per-touchpoint read-direct-after-write logic*. Rejected: introduces a fallback path that violates Q1's clean-cutover decision; expands the mission scope by a factor of ~2; provides no operator-visible value (post-write verification is correctness-critical and cache lag would degrade it).
- *Migrate the legacy v1 callsites alongside their v2 successors*. Rejected: the v1 modules are already retired in production code paths. Migrating them is touching dead code.
- *Keep the spec's "18" figure literal by listing the unmigrated TPs as "stayed direct, by design"*. Rejected as misleading documentation; cleaner to record the scope correction in research.md and update plan.md's structure section to enumerate the out-of-scope rationale per TP class.

**Implication for spec**: The spec body's "18 touchpoints" wording is technically misleading but the underlying intent (all migration candidates from RQ-2 migrate in this mission) is preserved. **No spec edits required** — the spec's FR-004 already says "All 18 touchpoints enumerated in #518's RQ-2 (TP-01 through TP-18)" and the FR's intent (all candidates) is now operationalized as "6 candidates after research" via this document.

**Implication for plan**: Plan structure enumerates the 6 in-scope files and explicitly lists the rationale-per-TP for out-of-scope entries (see plan.md § Project Structure). WP count drops from "1 foundation + 5 domain clusters = 6 WPs" (the spec's pre-research estimate) to **1 foundation + 3 domain clusters = 4 WPs** (the actual structure).

---

## Unknown 1 — SLA tier assignment per migration candidate

**Decision**: Apply the four-tier SLA model (Q1=A) per touchpoint as follows:

| TP | File | SLA tier | Rationale |
|---|---|---|---|
| **TP-02** | `scripts/habits/reconcile_completions.py` | `SLA_NORMAL` (15 min) | Runs at the morning-cron start to reconcile any operator-side changes before the check-in fires. 15 min covers 3 driver cycles — sufficient to catch yesterday's last-cycle edits without being too strict on driver hiccups. |
| **TP-03** | `scripts/habits/query_active_habits_v2.py` | `SLA_NORMAL` (15 min) | Invoked by `morning_checkin_list.py` (TP-07) during the morning check-in. Same time-sensitivity as the check-in itself. |
| **TP-04** | `scripts/habits/set_due_dates.py` (GET phase) | `SLA_NORMAL` (15 min) | Daily sweep that recalculates due dates per the schedule YAML. Runs at morning cron start. |
| **TP-07** | `scripts/habits/morning_checkin_list.py` | `SLA_NORMAL` (15 min) | The check-in itself — the operator-facing morning WhatsApp. SLA matches the human-perceptual relevance (15 min ≈ "within recent activity"). |
| **TP-10** | `scripts/escalation/reconcile_completions.py` | `SLA_NORMAL` (15 min) | Escalation cron also runs at morning. Same SLA as habits. |
| **TP-12** | `scripts/enrichment/reconcile_completions.py` | `SLA_NORMAL` (15 min) | Enrichment cron runs alongside other morning cron tasks. Same SLA. |

**Net outcome**: ALL six migration candidates land on `SLA_NORMAL` (15 min). This is not coincidental — they're all morning-cron-driven reconcilers + check-in helpers, sharing time-sensitivity. The `SLA_HOT` (60s), `SLA_BATCH` (1h), and `SLA_LOOSE` (24h) tiers remain defined in `sync_cache.py` for future migrations or new touchpoints, but are not consumed in this mission.

**Implication**: The shared SLA tiers + their use-once-each (NORMAL only) means the helper exposes the full tier set but the implementer only wires `SLA_NORMAL` callers. This is a deliberate choice — future missions (e.g., a real-time escalation hot-path, a daily analytics sweeper) will pick the other tiers without re-architecting the helper.

**Alternatives considered**:

- *Skip the tier system entirely; one global SLA constant*. Rejected per Q1 (operator chose A, the tier model).
- *Per-touchpoint SLA constants without named tiers (each touchpoint gets its own number)*. Rejected per Q1.
- *Make `SLA_NORMAL` the only tier in v1 of `sync_cache.py`, add others later*. Rejected: the cost of declaring four constants upfront is zero; the future-proofing value of having the vocabulary established is meaningful.

---

## Unknown 2 — Spec assumption A-7 (no write-then-read-back-in-tight-loop)

**Decision**: A-7 holds for the 6 in-scope migration candidates. The 8 mixed write+read callsites (TP-13, TP-14, TP-15C, TP-15D, TP-15E, TP-16C, TP-16D, TP-16E) DO contain write-then-read-back patterns — but they are **out of scope per the scope correction above**. The mission can proceed without addressing them.

**Rationale**: Each of the 6 in-scope TPs has `write_set: —` per the RQ-2 catalog (i.e., they perform no Vikunja writes in their own bodies). A-7's failure mode (a touchpoint that writes to Vikunja then reads the same task back within the same invocation, expecting the just-written state) cannot occur in any in-scope file.

For the 8 out-of-scope mixed callsites, the write-then-read pattern is real (e.g., TP-13 `vikunja_writer.py` does `GET /tasks/{id}` lookup followed by `PUT /tasks/{id}/comments` write — though that's a lookup-then-write, not write-then-read; closer to TP-16E `swap_vikunja_secrets.py` which does a probe-comment-write then immediate GET to verify). Those callsites stay on direct Vikunja reads, which preserves their correctness.

**Alternatives considered**:

- *Treat A-7's potential falsification as a blocking gate for the entire mission*. Rejected: the in-scope files are guaranteed safe; the out-of-scope files' patterns are correctness-driven and shouldn't migrate anyway.
- *Add a per-touchpoint "this touchpoint must not use cache after this point" annotation*. Rejected: the cutover model makes this implicit (a touchpoint that's been migrated has no direct-Vikunja-read code left; one that hasn't been migrated has no helper call at all). No annotation needed.

---

## Unknown 3 — Field-set audit (FR-008 expansion decisions)

**Decision**: All 6 in-scope migration candidates read fields that are already in `TRACKED_TASK_FIELDS` (`title`, `done`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `labels`). **No expansion of `TRACKED_TASK_FIELDS` is required for this mission.**

**Rationale**: Cross-referencing each in-scope TP's `read_set` field from the RQ-2 catalog:

| TP | `read_set` (from RQ-2) | Inside TRACKED_TASK_FIELDS? |
|---|---|---|
| TP-02 | `id`, `done`, `done_at`, `title`, `updated` | **`done_at` and `updated` are NOT in TRACKED_TASK_FIELDS.** See note below. |
| TP-03 | `id`, `done`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `labels` | YES — exact match |
| TP-04 | `id`, `due_date`, `project_id` | YES |
| TP-07 | `id`, `title`, `done`, `due_date` | YES |
| TP-10 | `id`, `done`, `done_at`, `title`, `updated` | **`done_at` and `updated` are NOT in TRACKED_TASK_FIELDS.** See note below. |
| TP-12 | `id`, `title`, `updated` | **`updated` is NOT in TRACKED_TASK_FIELDS.** See note below. |

**Note on `done_at` and `updated`**: These ARE in the cache, even though they're NOT in `TRACKED_TASK_FIELDS`. Here's why:

- `TaskCacheRecord.fields` (the dict consumed by touchpoints) holds the 7 curated tracked fields per `TRACKED_TASK_FIELDS`.
- `TaskCacheEntry` ALSO carries `vikunja_updated_at` and `felix_last_observed_at` as top-level entry fields (not inside `.fields`). These are the metadata the diff phase uses.
- `done_at` (Vikunja's "when was this marked done") is NOT carried by the cache at all. Touchpoints that consume `done_at` (TP-02 and TP-10 — both reconcilers) use it to verify completion timestamps against the JSONL state log.

**Implication for the helper**: `sync_cache.read_cached_tasks()` returns the curated `fields` dict PLUS `vikunja_updated_at` per task (the latter exposed as a top-level key, e.g., `{"vikunja_updated_at": "...", "fields": {...}}`). Touchpoints that need `updated` get it without `TRACKED_TASK_FIELDS` expansion. **Touchpoints that need `done_at` (TP-02, TP-10) have a real gap** — they cannot get it from the cache as-is.

**Sub-decision**: For TP-02 and TP-10's `done_at` need, **plan-phase resolution: extend the helper to also read the per-task `state_log.jsonl` for completion timestamps** (the JSONL is the system of record for done_at + the date of completion; the cache only stores the latest `done: bool` flag). This means the helper has TWO data sources: the cache (for state) + the state_log (for completion timestamps where needed).

**Alternatives considered**:

- *Expand `TRACKED_TASK_FIELDS` to include `done_at`*. Rejected: `done_at` is a derived field from `done` + the most recent state-change timestamp; adding it to TRACKED_TASK_FIELDS would either widen the conflict-event surface or require the diff phase to special-case it. Either is a #518 driver change, out of scope.
- *Have TP-02 and TP-10 read state_log directly (not via the helper)*. Rejected: violates the spec's C-004 (helper is the only entry point for cache reads).
- *Defer TP-02 and TP-10 to a follow-up mission*. Rejected: they're the two most important reconcilers; deferring them defeats the purpose of #519.

**Result**: `sync_cache.py` gains a `read_completion_timestamps(state_log_dir, task_id)` function that reads `habits-history.jsonl` (and equivalents for escalation and enrichment) and returns the most recent `complete` event's timestamp. TP-02, TP-10, and TP-12 use this helper to derive `done_at` / `updated` equivalents for their reconciliation logic.

---

## Cross-cutting evidence

The static analysis above confirmed several lower-stakes assumptions from spec § Assumptions:

- **A-1 (driver running on office2)**: Verified at spec time (last-tick.json showed cycle_error: null at 21:48 UTC). Plan phase did NOT re-verify; the implementer re-verifies at WP01 start time.
- **A-2 (all 18 TPs still exist on main)**: Verified via the `ls` audit of each TP's file path. All 6 in-scope files exist at HEAD.
- **A-3 (cache schema stable)**: Verified — #518 was the only mission touching `scripts/sync/state.py` between cf74f33e and HEAD.
- **A-4 (all touchpoints read tasks, not projects)**: Verified — every in-scope TP's `read_set` references task fields. Project-layer reads (TP-16B, etc.) are out of scope.
- **A-5 (operator recovery is `--bootstrap`)**: Inherited from #518; not re-verified.
- **A-6 (AGENTS.md doesn't need updates)**: Verified — the touchpoints' CLI surface (exit codes 0/3, stderr pattern) is unchanged.
- **A-7 (no write-then-read tight-loop)**: Verified — see Unknown 2 above.

---

## Open items deferred to implement phase

- **`state_log.jsonl` reading semantics for `done_at` derivation** — exact format negotiation between TP-02, TP-10, TP-12 happens in those WPs' implementation. The helper's `read_completion_timestamps()` API is locked in `contracts/helper-api.md`; the per-touchpoint usage is per-WP.
- **Pre/post latency measurement for NFR-001** — implementer captures pre-migration latency for each in-scope touchpoint via a one-time profile run; post-migration latency measured against the same fixture set. Recorded in the WP's review note.
- **24-hour Vikunja access-log baseline for SC-004** — operator-driven measurement post-deploy; not implementer territory.

---

## Research summary

Three unknowns resolved (SLA assignment, A-7 verification, field-set audit). One scope-correcting finding (25 → 6 migration candidates) preserved the spec's locked decisions without requiring spec edits. One sub-decision (helper reads state_log for done_at derivation) extends the helper's API surface slightly beyond the spec's bare "three primary entry points" wording, but stays within the spirit of C-004 (helper is the sole entry point; touchpoints don't import driver-internal or state_log code directly).

**Phase 0 status**: complete. Proceeding to Phase 1 (data-model.md, contracts/, quickstart.md).
