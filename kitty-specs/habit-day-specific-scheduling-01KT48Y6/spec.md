# Mission Spec: Day-Specific Habit Scheduling with Auto-Skip on Miss

**Mission ID**: `01KT48Y6F2BMXDQY3YDCS5GZ61`
**Mission slug**: `habit-day-specific-scheduling-01KT48Y6`
**Source issue**: [kentonium3/kg-automation#408](https://github.com/kentonium3/kg-automation/issues/408)
**Mission type**: software-dev
**Target branch**: `main`

---

## 1. Source Description

The felix-admin-habits morning check-in (delivered via WhatsApp every day at 7:05 AM ET) currently includes day-specific habit tasks — concretely *"Strength training — Wednesday"* and *"Strength training — Friday"* — on every day of the week, not just on their designated weekday. Observed on 2026-05-24 (Sunday): both day-specific habits appeared in the daily list, and when Kent replied with completion tokens, the agent's reply logged both items as "Not yet reported" — confirming the system tracks them as open on days they cannot be completed.

**Root cause** (per `scripts/habits/AGENTS.md` and `query_active_habits_v2.py`): the daily list is built from a Vikunja query `due_date <= today AND done = false`. When a day-specific habit's `due_date` is set to a past Wednesday (Kent missed last Wednesday), the filter returns it every day until completed. There is no logic that recognizes "this habit is Wednesday-only — if it wasn't done by end-of-day Wednesday, mark it missed and advance to next Wednesday."

**Design call** (load-bearing, operator-confirmed during /spec-kitty.specify and /spec-kitty.plan):

1. **Day-of-week visibility.** Day-specific habits appear in the daily check-in **only on their designated weekday**, NOT on the day-before as a reminder. Daily habits appear every day as today.

2. **48-hour response window** (clarified during plan-phase discovery; carried forward from the system's original requirements). All habits — daily AND day-specific — remain **open in `habits-history.jsonl` for 48 hours after their check-in delivery**. Kent can reply to yesterday's WhatsApp check-in message and have today's parser correctly attribute the reply to yesterday's habits. After 48 hours, unresolved items are auto-marked as **skipped** (event_type: `auto_skipped`) with history log. The visibility rule from (1) is independent: Wednesday's strength training appears only in Wednesday's check-in, but stays open for 48 hours so Kent can reply on Thursday morning to mark it complete (or skipped).

3. **Sweeper trigger** changes from "end-of-ET-day" to "48hr-after-check-in" to honor the response window.

These two rules combined: clean daily check-ins with only today's relevant items, but a forgiving 48hr response window so Kent's late replies still land correctly without polluting future check-ins. The miss is recorded in history; accountability preserved.

---

## 2. User Scenarios & Testing

### 2.1 Primary actor

- **Kent** (operator) — receives the daily WhatsApp check-in and replies with completion tokens. Authors the habit schedule. Operates on Eastern Time.

### 2.2 Primary user flows

**Flow A — Day-specific habit on its designated day (happy path):**
1. Tuesday 7:05 AM ET: morning cron fires. Daily check-in includes *only* habits scheduled for Tuesday plus all daily habits. *"Strength training — Wednesday"* does NOT appear.
2. Wednesday 7:05 AM ET: morning cron fires. Daily check-in includes *"Strength training — Wednesday"* plus all daily habits.
3. Kent completes the workout sometime Wednesday, sends completion reply.
4. System marks the habit done, advances its `due_date` to next Wednesday's end-of-ET-day per existing Vikunja-native repeat semantics.
5. Thursday 7:05 AM ET: daily check-in does NOT include strength training.

**Flow B — Day-specific habit, late completion via late reply (within 48hr window):**
1. Wednesday 7:05 AM ET: daily check-in includes *"Strength training — Wednesday"*.
2. Kent doesn't reply Wednesday.
3. Thursday 7:05 AM ET: Thursday's check-in is delivered — does NOT include strength training (not Thursday's day).
4. Thursday 10:00 AM ET: Kent realizes he forgot. Replies to **Wednesday's** WhatsApp message: *"workout done"*. (Whether he uses WhatsApp's quote-reply feature or plain text is a plan-phase research item.)
5. Reply parser correlates the reply to Wednesday's `morning-checkin-2026-MM-DD.json` artifact (within 48hr window). Marks strength training done; Vikunja-native repeat advances `due_date` to next Wednesday.

**Flow C — Day-specific habit truly missed (no reply within 48hr window):**
1. Wednesday 7:05 AM ET: check-in includes strength training. Kent doesn't reply Wed or Thu.
2. Friday 7:05 AM ET: Friday's check-in is delivered. The sweeper runs after check-in delivery and identifies that Wednesday's `morning-checkin-2026-MM-DD.json` is now >48hr old and contains unresolved strength training.
3. Sweeper appends an `auto_skipped` entry to `habits-history.jsonl` with `task_id`, `designated_weekday`, `original_checkin_date_et`, `tick_id`.
4. Sweeper advances strength training's `due_date` to next Wednesday's end-of-ET-day.
5. Subsequent Wednesdays: strength training appears in check-in normally.

**Flow D — Daily habit, late reply within 48hr window:**
1. Tuesday 7:05 AM ET: check-in includes "Wake at 5:00 AM" (daily habit). Kent doesn't reply Tuesday.
2. Wednesday 7:05 AM ET: Wednesday's check-in delivered — also includes "Wake at 5:00 AM" (today's instance).
3. Wednesday 8:00 AM ET: Kent replies to Tuesday's WhatsApp message: *"wake done"*. Parser correlates to Tuesday's `morning-checkin-2026-MM-DD.json`, marks Tuesday's wake done.
4. Wednesday 8:01 AM ET: Kent replies to Wednesday's WhatsApp message: *"wake done"*. Parser correlates to Wednesday's check-in.
5. Both updates land cleanly; no overlap.

**Flow E — Daily habit auto-skip after 48hr window:**
1. Monday 7:05 AM ET: check-in includes "Meditate" (daily habit). Kent doesn't reply Mon or Tue.
2. Wednesday 7:05 AM ET: sweeper runs after check-in delivery, identifies Monday's `morning-checkin` >48hr old with unresolved meditate.
3. Sweeper appends `auto_skipped` entry to `habits-history.jsonl` for Monday's meditate.
4. Tuesday's check-in's meditate (its own entry, ≤48hr old) remains open.
5. Wednesday's check-in's meditate is fresh.

**Flow F — Schedule change mid-week (operator action):**
1. Tuesday: Kent decides Wed strength training should become Mon strength training.
2. Kent edits the schedule config, then runs a manual reconciliation command (per OD-1's plan-phase decision) that updates the habit's `designated_weekdays` field AND advances its `due_date` to the next NEW designated weekday (next Monday's EOD-ET).
3. Wednesday's check-in: strength training does NOT appear (no longer designated for Wed).
4. Following Monday's check-in: strength training appears.

### 2.3 Edge cases

- **Day-of-week assignment changes** for an existing habit (e.g., Wed → Mon): the next sweeper pass recognizes the new designated day; the habit's next `due_date` advances to the next occurrence of the new designated day. Migration of historical missed entries is out of scope.
- **Multi-day habits** (e.g., a habit scheduled for both Wed AND Fri): treated as multi-designated; the sweeper iterates the designated set and advances to the next upcoming designated day. Initial scope: single-designated-day habits only; multi-day handled identically by iterating the designated set.
- **DST transitions**: the sweeper uses the same ET-aware logic as `compute_today.py` and `set_due_dates.py`; no special-case behavior needed. Existing #112 regression-prevention guards apply.
- **Sweeper missed a run** (office2 reboot, cron failure): the next sweeper pass catches up. Habits whose designated day passed multiple times without sweeper action get one `missed` entry per skipped designated day (idempotency via `(task_id, missed_on_date_et)` key in `habits-history.jsonl`).
- **Habit removed from schedule mid-week**: the next sweeper pass treats it as a daily habit by default (no day-of-week filter applies); no auto-skip. Operator should explicitly delete or pause the habit if desired.
- **Vikunja API failure during sweeper**: per-habit-failure resilience like `set_due_dates.py` — continue with remaining habits, log per-habit failure to the tick artifact, signal partial-state via exit code.

---

## 3. Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The system MUST distinguish day-specific habits (assigned to one or more weekdays) from daily habits (every day) via persistent metadata stored alongside the habit schedule. | Proposed |
| FR-002 | The morning check-in helper MUST exclude day-specific habits whose designated weekday is not today (ET) from the daily check-in list, even when their `due_date` is in the past. | Proposed |
| FR-003 | All habits (daily AND day-specific) MUST remain open for response in `habits-history.jsonl` for **48 hours after their check-in's delivery time**. The reply parser MUST correlate Kent's WhatsApp reply to the appropriate `morning-checkin-<date>.json` artifact (today's, yesterday's, or older, within the 48hr window). | Proposed |
| FR-004 | A sweeper MUST run daily after the morning check-in delivery and, for each habit whose containing `morning-checkin-<date>.json` is >48 hours old AND whose status remains unresolved (not done, not skipped): append an `auto_skipped` entry to `habits-history.jsonl` with `task_id`, `original_checkin_date_et`, `original_designated_weekday` (if day-specific), `tick_id`. For day-specific habits, also advance the Vikunja `due_date` to the next occurrence of its designated weekday. | Proposed |
| FR-005 | The sweeper MUST be idempotent: re-running it for the same `(task_id, original_checkin_date_et)` pair MUST NOT append a duplicate `auto_skipped` entry or double-advance the `due_date`. | Proposed |
| FR-006 | The sweeper MUST produce a structured per-tick artifact at `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` with: `tick_id`, `started_at_utc`, `expired_checkin_dates_evaluated[]`, `habits_evaluated[]`, `habits_auto_skipped[]`, `errors[]`, `exit_status`. | Proposed |
| FR-007 | The daily completion-marking flow MUST continue to work for both daily and day-specific habits when Kent replies within the 48hr window (no regression in existing `parse_morning_reply` / `set_due_dates` behavior). | Proposed |
| FR-008 | Day-of-week metadata MUST be authored declaratively in a config file under `scripts/habits/` (extending the existing `migrations/phase3-schedule.yaml` shape or a sibling) and consumed by both the morning-checkin helper and the sweeper. | Proposed |
| FR-009 | Day-of-week metadata MUST support multi-day assignment (e.g., a habit scheduled for both Monday and Thursday) without code change — i.e., the field is a list of designated weekdays. | Proposed |
| FR-010 | When a habit's `designated_weekdays` is changed mid-week, the operator MUST run a manual reconciliation command that updates the habit's metadata AND advances its `due_date` to the next new designated weekday. The sweeper does NOT special-case schedule changes. | Proposed |

---

## 4. Non-Functional Requirements

| ID | Requirement | Measurable Threshold | Status |
|---|---|---|---|
| NFR-001 | Sweeper latency | Sweeper completes within 30 seconds for the current production set (≤20 habits per the snapshot at `/data/services/openclaw/state/habits-pre-phase3-snapshot.json`). | Proposed |
| NFR-002 | Test coverage of new code | ≥85% line / ≥80% branch on all new modules under `scripts/habits/` (matches the existing `scripts/doc_audit/` and `scripts/openclaw/observation/` conventions). | Proposed |
| NFR-003 | Backwards compatibility | All existing helper-script tests (under `scripts/habits/tests/` if present, otherwise the repo's `pytest` defaults) MUST still pass without modification. | Proposed |
| NFR-004 | Observability of sweeper behavior | An operator inspecting `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` MUST be able to determine, within 30 seconds, which habits were evaluated, which were marked missed, and whether the tick succeeded. | Proposed |
| NFR-005 | Issue #112 regression-prevention | The existing UTC-vs-ET due_date guard in `set_due_dates.py` (`--iso-eod-et` rejection of `Z` suffix) MUST remain intact and the sweeper's advancement of `due_date` MUST use the same guard, NOT auto-convert UTC. | Proposed |

---

## 5. Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Day-specific filtering and sweeper logic live in `scripts/habits/` per Directive 6 (deterministic-vs-stochastic split). No new LLM call is introduced. | Confirmed |
| C-002 | The sweeper runs as a systemd timer (`felix-habit-sweeper.timer` or equivalent) firing once per day shortly after 00:00 ET, NOT as a cron job. (Matches the existing `felix-doc-auditor.timer` and `felix-core-digest.timer` precedent.) | Confirmed |
| C-003 | All ET-aware timestamp handling reuses `compute_today.py`'s logic; no new timezone code is introduced. | Confirmed |
| C-004 | The mission ships into `main` via spec-kitty merge (merge commit, not PR). Any new GitHub Actions added by this mission trigger on `push` to `main`. | Confirmed |
| C-005 | Habit history JSONL (`/data/services/openclaw/state/habits-history.jsonl`) is the existing append-only state log; new `missed` entries follow the existing JSONL schema with a new `event_type: "auto_missed"` field. | Confirmed |
| C-006 | No changes to felix-admin-habits AGENTS.md output discipline (Hard rule #1 / Hard rule #2 — emit zero text between tool calls; final reply starts with identity line). Sweeper runs independently of the agent; no WhatsApp messages emitted. | Confirmed |
| C-007 | Architecture documentation updates (per CLAUDE.md standing requirement): `data/service-inventory.json` gains a new entry for the sweeper service. | Confirmed |

---

## 6. Success Criteria

Measurable, technology-agnostic outcomes:

1. **No day-specific habit appears in the daily check-in on a day it is not scheduled for.** Validated by an integration test that builds the daily list for each weekday with a representative habit set including both daily and day-specific habits.
2. **End-of-day-missed habits are recorded in habits-history.jsonl with `event_type: "auto_missed"`.** Validated by an integration test that simulates a sweeper run against a fixture set including completed, missed, and not-yet-due habits.
3. **A missed day-specific habit's `due_date` advances to its next designated weekday's end-of-ET-day** — validated by inspecting the post-sweep Vikunja state (mockable via the existing Vikunja-mock pattern in the habits test suite).
4. **The sweeper is idempotent** — validated by an integration test that runs the sweeper twice against the same fixture and asserts no duplicate `missed` entries and no double `due_date` advancement.
5. **No regression in existing daily-habit behavior** — validated by the existing `pytest` suite passing without modification.
6. **Observed in production on the first full week post-deploy**: at most one weekly miss-recovery per day-specific habit per week (i.e., the sweeper does not surface the same habit on consecutive days).

---

## 7. Key Entities

| Entity | Purpose | Key attributes |
|---|---|---|
| **Day-specific habit** | A habit scheduled for one or more specific weekdays rather than every day. | `task_id`, `designated_weekdays` (set of `Mon`..`Sun`), Vikunja `repeat_after` set to 7 days (or 7×N for N-day cycles), Vikunja `due_date` aligned to next designated weekday EOD-ET. |
| **Habit schedule entry** | Declarative config entry binding a Vikunja task to its day-of-week metadata. | `task_id`, `title`, `designated_weekdays`, plus existing schedule fields (`repeat_after`, etc.). |
| **Sweeper tick record** | One sweeper run's structured output. | `tick_id` (ULID), `started_at_utc`, `target_date_et`, `habits_evaluated[]`, `habits_marked_missed[]`, `errors[]`, `exit_status` (`success` / `partial` / `failure`). |
| **`auto_missed` history event** | One entry in `habits-history.jsonl` recording an auto-skip. | `event_type: "auto_missed"`, `task_id`, `designated_weekday`, `missed_on_date_et`, `tick_id`, `recorded_at_utc`. |

---

## 8. Assumptions

These assumptions are inherited from the operator's design call and existing habits-agent architecture; plan-phase research validates them on office2:

- **A1**: The existing habit-schedule data shape (`scripts/habits/migrations/phase3-schedule.yaml` and Vikunja's `repeat_after` / `repeat_mode`) can be extended with a `designated_weekdays` field without breaking the existing migration helpers (`migrate_schedule.py`). Plan phase confirms by reading the YAML schema and a sample.
- **A2**: The systemd timer infrastructure used by `felix-doc-auditor.timer` and `felix-core-digest.timer` is the right precedent for the sweeper timer. Plan phase confirms timer-vs-cron decision against the `mutation-surfaces.json` taxonomy.
- **A3**: `habits-history.jsonl` is append-only and schema-extensible (existing readers tolerate new optional fields). Plan phase confirms by inspecting the file's current readers.
- **A4**: The morning-checkin helper consumes the day-of-week filter inline (no separate query path) — i.e., the existing `query_active_habits_v2` or `morning_checkin_list` is the right place to add the filter, NOT a new helper. Plan phase confirms by reading `morning_checkin_list.py`.
- **A5**: Day-specific habit `due_date` reflects the designated weekday's end-of-ET-day timestamp (not 08:00 UTC as the migration text hints). Plan phase confirms by inspecting the production snapshot.

---

## 9. Out of Scope

- ❌ Day-before reminders for day-specific habits (operator decided: designated day only, no advance reminders).
- ❌ Multi-day habit cycles (e.g., "every 3rd day"). Initial scope: weekly cadence only. The `repeat_after` field already supports multiples-of-7-days for those edge cases via existing logic.
- ❌ Migration of historical missed-but-not-recorded habits (cleaning up the existing pre-mission state). Out of scope; the sweeper applies from cutover forward.
- ❌ Operator UI/CLI for changing day-of-week assignment (config-file edits only; same as existing schedule changes).
- ❌ Notifying Kent via WhatsApp when a habit is auto-missed (silent; the history log is the audit trail).
- ❌ Changes to felix-admin-habits AGENTS.md output discipline (Hard rules #1/#2 remain).

---

## 10. Architecture Impact

Per CLAUDE.md standing requirement, any feature that changes deployed services updates the relevant files in `docs/design/architecture/data/` and their markdown counterparts in the same merge. Per the doc-impact resolver (commit `d43b7387`), filtering `signal-to-doc-map.json` by `match.source == "mission-architecture-impact"`:

| Change class | doc_targets |
|---|---|
| `service-added-or-modified` | `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`, `docs/design/architecture/service-dependencies.view.md`, `docs/design/felix-capability-roadmap.md` |
| `systemd-unit-added-or-modified` | `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md` |
| `runbook-modified` | `docs/INDEX.md` (if title/scope of `docs/runbooks/habits-ops.md` changes) |

Concrete updates expected:
- `service-inventory.json`: new entry for `felix-habit-sweeper` systemd timer
- `service-inventory.md`: matching narrative entry
- `service-dependencies.view.md`: edge from sweeper → Vikunja
- `docs/runbooks/habits-ops.md`: extended with the new sweeper's operational surface (health check, cutover, troubleshooting, rollback)

`updated_by` on all modified JSON entries references this mission's source issue (#408).

---

## 11. Change-Risk Tier (per CLAUDE.md taxonomy)

| Component | Tier | Notes |
|---|---|---|
| New helper scripts under `scripts/habits/` | Tier 3 (Standard logic/workflow) | Dry-run + replay-against-fixture validation before deploy. |
| Schedule YAML extension (new `designated_weekdays` field) | Tier 3 | Schema-additive; existing migration tests must still pass. |
| New systemd timer/service for sweeper | Tier 2 (Application/state) | Confirm Restic backup currency before first deploy. |
| Habits-history JSONL schema extension (new event_type) | Tier 3 | Backwards-compatible — readers tolerate unknown event types. |
| `docs/design/architecture/data/service-inventory.json` update | Tier 4 (auto-commit) | Standard CLAUDE.md update protocol. |

No Tier 0 changes expected.

---

## 12. Constitutional Compliance (Felix Constitution)

- **Autonomy level**: Assisted (Level 1). felix-admin-habits remains Level 1 per its existing registration. The sweeper is a deterministic helper running under the existing autonomy posture — no new autonomy boundary introduced.
- **Scope boundary**: Modifies only the felix-admin-habits scheduling/sweeper layer. No other agents touched.
- **Failure behavior**: Sweeper failures surface in the structured tick artifact + systemd journal. A sweeper that errors does NOT block the next morning check-in (the morning helper reads from Vikunja directly, not from sweeper output).
- **Privacy boundary**: Reads existing habits-schedule.yaml + Vikunja state + appends to existing habits-history.jsonl. No new credential surface. No second-brain access.
- **Directive 6 (deterministic vs stochastic split)**: Fully deterministic. Filtering logic is a YAML lookup + day-of-week comparison; sweeper is a YAML scan + Vikunja PUT. Zero LLM calls in this mission.

---

## 13. Open Decisions for Plan Phase

These are deferred to plan-phase live-probe research, not unresolved spec ambiguity:

- **OD-1**: Exact storage location for `designated_weekdays` metadata — extending `phase3-schedule.yaml` vs a sibling `day-of-week.yaml` vs a Vikunja label convention. Plan phase reviews the existing schedule.yaml schema and decides.
- **OD-2**: Sweeper invocation cadence — single morning tick shortly after the 7:05 AM ET check-in delivery vs a separate scheduled time. Plan phase decides based on the existing `felix-doc-auditor.timer` precedent.
- **OD-3**: Whether to add a `--dry-run` flag to the sweeper for operator-side testing pre-deploy. Plan phase decides; recommended default: yes (matches `set_due_dates.py` precedent).
- **OD-4**: Reply-correlation mechanism — does the existing `parse_morning_reply.py` already detect WhatsApp's quote-reply feature for correlating to a specific check-in date, or does the parser default to most-recent check-in? Plan phase inspects `parse_morning_reply.py` and the morning-checkin helper to decide whether 48hr support is a parser extension or already implicit.
- **OD-5**: Manual reconciliation command (per FR-010) — extend an existing script (e.g., `set_due_dates.py`) with a `--reconcile-schedule` flag vs a new dedicated helper. Plan phase decides.
