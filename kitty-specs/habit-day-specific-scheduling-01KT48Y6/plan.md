# Implementation Plan — Day-Specific Habit Scheduling with Auto-Skip on Miss

**Mission**: `habit-day-specific-scheduling-01KT48Y6`
**Source issue**: [#408](https://github.com/kentonium3/kg-automation/issues/408)
**Spec**: [`spec.md`](./spec.md)
**Research**: [`research.md`](./research.md)
**Data model**: [`data-model.md`](./data-model.md)
**Contracts**: [`contracts/`](./contracts/)
**Quickstart**: [`quickstart.md`](./quickstart.md)

---

## Branch contract

- **Current branch at plan start**: `main`
- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **`branch_matches_target`**: true

(Restated per /spec-kitty.plan §"Branch Strategy Confirmation".)

---

## Summary

Fix the felix-admin-habits daily check-in so day-specific habits (e.g., "Strength training — Wednesday") appear only on their designated weekday, and add a 48-hour response window during which Kent can reply to a prior day's check-in. Habits not resolved within 48 hours are auto-marked `skipped`, logged to `habits-history.jsonl`, and (for day-specific habits) their Vikunja `due_date` advances to the next designated weekday. A new systemd-timer-driven sweeper at 7:30 AM ET runs the auto-skip pass daily. Operator changes to `designated_weekdays` are reconciled via a new `--reconcile-schedule` flag on the existing `set_due_dates.py`.

Fully deterministic mission — zero new LLM calls (Directive 6 compliant).

---

## Technical Context

| Topic | Resolution |
|---|---|
| **Architecture pattern** | Mirror `felix-doc-auditor` post-#343 + `felix-core-digest` post-#490: stateless Python oneshots on systemd user timers, structured per-tick artifact, append-only ledger, exit-status taxonomy (`success`/`partial`/`failure`), journal `SUMMARY:` line. |
| **Language/Version** | Python 3.11+ (matches existing helper-script pattern under `scripts/habits/`). |
| **Primary Dependencies** | PyYAML for schedule.yaml parsing (likely already in use), `urllib.request` for Vikunja PUT (matches `set_due_dates.py` precedent — no `requests` library), pytest for tests. |
| **Storage** | (existing) `scripts/habits/migrations/phase3-schedule.yaml` extended with `designated_weekdays`; (existing) `/data/services/openclaw/state/habits-history.jsonl` extended with `auto_skipped` event type; (new) `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` + `sweeper-ledger.jsonl`; (new) `/data/services/openclaw/state/habits/reconcile-<datetime>.json`. |
| **Testing** | pytest + mocked Vikunja (matching the existing `scripts/habits/tests/` convention if present, or `scripts/doc_audit/tests/` pattern otherwise). Coverage target ≥85% line / ≥80% branch on new modules. |
| **Target Platform** | office2 (Ubuntu 24.04 LTS) as the `claude` user. systemd user timers. |
| **Project Type** | Single project — extends `scripts/habits/`. |
| **Performance** | Sweeper completes within 30s for the current production set (≤20 habits per the production snapshot). |
| **Constraints** | (1) Issue #112 regression-prevention: due_date timestamps must be ET-offset, NOT `Z`. (2) AGENTS.md output discipline (Hard rules #1/#2) unchanged. (3) No new LLM calls (Directive 6). |
| **Scale/Scope** | Production has ≤20 habits today; this mission's surface scales linearly with habit count. |

---

## Charter Check

| Check | Result |
|---|---|
| Branch contract matches target | ✅ PASS |
| Charter governance loaded | ⚠ WARN — same known tool-registry mismatch (deferred per `project_charter_tool_registry_mismatch` memory) |
| No `[NEEDS CLARIFICATION]` markers in spec | ✅ PASS — OD-1..OD-5 resolved or documented for plan-phase research |
| All FRs / NFRs have measurable acceptance | ✅ PASS — see spec §3, §4, §6 |
| Architecture-impact section identifies affected JSON files | ✅ PASS — service-inventory.json, service-inventory.md, service-dependencies.view.md (per doc-impact resolver) |
| Change-risk tier classified | ✅ PASS — spec §11 |
| Test strategy committed | ✅ PASS — research.md "Test strategy" |
| Identity for any autonomous mutations | ✅ PASS — sweeper writes only to file artifacts + Vikunja via existing `kg-felix-bot`-equivalent (Vikunja token; no GitHub identity needed) |
| Bulk-edit check | ✅ PASS — `change_mode: regular` |
| Constitutional compliance | ✅ PASS — fully deterministic, Assisted Level 1 inherited from felix-admin-habits |

No gate failures.

---

## Project Structure

### Documentation (this mission)

```
kitty-specs/habit-day-specific-scheduling-01KT48Y6/
├── plan.md                              # This file
├── spec.md                              # Mission specification
├── research.md                          # Phase 0 — OD-1..OD-5 resolutions
├── data-model.md                        # Phase 1 — entities E1..E5
├── quickstart.md                        # Phase 1 — operator quickstart
├── contracts/
│   ├── schedule-config.contract.md      # YAML schema extension
│   ├── sweeper-tick.contract.md         # sweeper-tick-<date>.json schema
│   ├── history-event-auto-skipped.contract.md  # JSONL event extension
│   └── reply-correlation.contract.md    # 48hr correlation algorithm
├── meta.json
├── checklists/requirements.md
└── tasks/                               # Created by /spec-kitty.tasks
```

### Source code (kg-automation repo)

```
scripts/habits/                          # EXISTING package — extended
├── compute_today.py                     # UNCHANGED
├── set_due_dates.py                     # EXTENDED — new --reconcile-schedule flag
├── parse_morning_reply.py               # EXTENDED — 48hr window correlation per OD-4 outcome
├── query_active_habits_v2.py            # EXTENDED — day-of-week filter
├── morning_checkin_list.py              # EXTENDED — invokes day-of-week filter
├── exclude_completed_v2.py              # EXTENDED if needed — tolerate auto_skipped event_type
├── sweeper.py                           # NEW — entrypoint for 48hr auto-skip sweep
├── schedule_loader.py                   # NEW — central loader for designated_weekdays
├── migrations/
│   └── phase3-schedule.yaml             # EXTENDED — new designated_weekdays field
└── tests/                               # EXTENDED
    ├── test_query_active_habits_v2_day_of_week.py
    ├── test_morning_checkin_list_day_of_week.py
    ├── test_parse_morning_reply_48hr_correlation.py
    ├── test_sweeper_unit.py
    ├── test_sweeper_idempotent.py
    ├── test_set_due_dates_reconcile.py
    └── fixtures/
        ├── schedule_with_day_specific.yaml
        ├── morning_checkin_2026_05_25_with_dayspec.json
        └── habits_history_pre_sweep.jsonl

scripts/office2/
├── felix-habit-sweeper.service          # NEW
└── felix-habit-sweeper.timer            # NEW — OnCalendar=*-*-* 07:30 America/New_York

docs/runbooks/
└── habits-ops.md                        # EXTENDED — sweeper section + 48hr semantics + reconciliation

docs/design/architecture/data/
├── service-inventory.json               # EXTENDED — felix-habit-sweeper entry
├── service-inventory.md                 # EXTENDED
└── service-dependencies.view.md         # EXTENDED
```

**Structure Decision**: Single-project layout. Extends `scripts/habits/` per the existing helper-script pattern. Mirrors `felix-doc-auditor` for the systemd-timer-driven sweeper shape.

---

## Phase 0 — Research outputs

See [`research.md`](./research.md). Summary:

- **OD-1 resolved**: extend `phase3-schedule.yaml` in place with `designated_weekdays` list field; absent = daily.
- **OD-2 resolved**: sweeper runs at 7:30 AM ET daily (25 min after morning check-in cron).
- **OD-3 resolved**: `--dry-run` flag, default off, per `set_due_dates.py` precedent.
- **OD-4 (research at implement time)**: reply correlation mechanism — first WP reads `parse_morning_reply.py` to determine whether 48hr support is a parser extension or requires more work.
- **OD-5 resolved**: `--reconcile-schedule` flag on existing `set_due_dates.py` (not a new helper).
- **Architectural pattern adoption**: felix-doc-auditor post-#343 + felix-core-digest post-#490 shape (stateless Python oneshot, tick artifact, ledger).
- **Cost estimate**: $0/day — zero LLM calls.

---

## Phase 1 — Design outputs

### Data model

See [`data-model.md`](./data-model.md). Five entities:
- **E1** Habit schedule entry (config-time, extended)
- **E2** Morning check-in artifact (existing, lightly extended)
- **E3** habits-history.jsonl event (existing, new `auto_skipped` event_type)
- **E4** Sweeper tick record (new)
- **E5** Reconciliation record (new)

### Contracts

| Contract | Purpose |
|---|---|
| [`contracts/schedule-config.contract.md`](./contracts/schedule-config.contract.md) | YAML extension for `designated_weekdays` field; validation rules; backwards-compatibility commitment |
| [`contracts/sweeper-tick.contract.md`](./contracts/sweeper-tick.contract.md) | `sweeper-tick-<date>.json` schema; health-check semantics; #112 regression-prevention |
| [`contracts/history-event-auto-skipped.contract.md`](./contracts/history-event-auto-skipped.contract.md) | JSONL event extension; idempotency contract; reader-behavior expectations |
| [`contracts/reply-correlation.contract.md`](./contracts/reply-correlation.contract.md) | 48hr window correlation algorithm; failure modes; OD-4 research deferred to first WP |

### Quickstart

See [`quickstart.md`](./quickstart.md). Covers health check, schedule editing + reconciliation, sweeper troubleshooting, dry-run, cost statement.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ office2 (Ubuntu 24.04 LTS, claude user)                                │
│                                                                        │
│  ┌────────────────────────────┐    ┌──────────────────────────────┐    │
│  │ Existing morning cron      │    │ NEW felix-habit-sweeper      │    │
│  │   7:05 AM ET daily         │    │   7:30 AM ET daily           │    │
│  │ → felix-admin-habits agent │    │   (systemd user timer)       │    │
│  │   delivers WhatsApp        │    │                              │    │
│  │   check-in                 │    │                              │    │
│  └────────────┬───────────────┘    └────────────┬─────────────────┘    │
│               │                                 │                      │
│               ▼                                 ▼                      │
│  ┌────────────────────────────┐    ┌──────────────────────────────┐    │
│  │ morning_checkin_list.py    │    │ sweeper.py                   │    │
│  │  (EXTENDED — day-of-week   │    │  reads:                      │    │
│  │   filter via               │    │   - schedule_loader          │    │
│  │   schedule_loader)         │    │   - morning-checkin artifacts│    │
│  │                            │    │     >48hr old                │    │
│  │  writes:                   │    │   - habits-history.jsonl     │    │
│  │   morning-checkin-<date>.  │    │     (open vs resolved)       │    │
│  │   json                     │    │  writes:                     │    │
│  │                            │    │   - auto_skipped events to   │    │
│  │                            │    │     habits-history.jsonl     │    │
│  │                            │    │   - sweeper-tick-<date>.json │    │
│  │                            │    │   - sweeper-ledger.jsonl     │    │
│  │                            │    │   - Vikunja PUTs (day-spec   │    │
│  │                            │    │     habits: advance due_date)│    │
│  └────────────────────────────┘    └──────────────────────────────┘    │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ parse_morning_reply.py (EXTENDED — 48hr window correlation)      │  │
│  │  reads Kent's WhatsApp reply                                     │  │
│  │  scans recent morning-checkin artifacts within 48hr window       │  │
│  │  correlates reply tokens to the right check-in's habits          │  │
│  │  writes done/skipped events to habits-history.jsonl              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ set_due_dates.py (EXTENDED — new --reconcile-schedule flag)      │  │
│  │  operator-invoked when designated_weekdays changes mid-week      │  │
│  │  reads updated schedule.yaml                                     │  │
│  │  for each habit with changed designation, advances Vikunja       │  │
│  │   due_date to next new designated weekday                        │  │
│  │  writes reconcile-<datetime>.json record                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Vikunja (existing) — habit task store
```

Key properties:
- Fully deterministic — zero LLM calls in any path.
- Sweeper is silent (no WhatsApp output).
- Sweeper is idempotent — re-runs are safe.
- AGENTS.md output discipline unchanged.
- Existing morning cron + parse pipeline unchanged in structure; only their internals extended.

---

## Change-risk tier classification (per spec §11)

| Component | Tier | Plan-time confirmation |
|---|---|---|
| Helper-script extensions under `scripts/habits/` | Tier 3 (Standard logic/workflow) | pytest + dry-run validation before deploy. |
| New systemd units (`felix-habit-sweeper.service/.timer`) | Tier 3 (logic) + Tier 2 at first deploy (state-dir creation) | Confirm Restic backup currency before first deploy. |
| Schedule YAML extension (new field) | Tier 3 | Schema-additive; existing migration tests must still pass. |
| habits-history.jsonl new event_type | Tier 3 | Backwards-compatible reader-tolerance contract. |
| `service-inventory.json` update | Tier 4 (auto-commit) | Standard CLAUDE.md update protocol. |

No Tier 0 changes expected.

---

## Open items for /spec-kitty.tasks (WP-planning hints)

Suggested WP boundaries — this mission is small enough for 2 WPs:

1. **WP-01: Day-of-week filtering + schedule extension**
   - T: extend `phase3-schedule.yaml` schema + `schedule_loader.py` (new) + `query_active_habits_v2.py` day filter + `morning_checkin_list.py` integration
   - T: extend `set_due_dates.py` with `--reconcile-schedule` flag
   - T: unit + integration tests for filtering + reconciliation
   - Owned files: `scripts/habits/schedule_loader.py`, `migrations/phase3-schedule.yaml`, `query_active_habits_v2.py`, `morning_checkin_list.py`, `set_due_dates.py`, related tests

2. **WP-02: Sweeper + 48hr window + parser correlation + deployment**
   - T: research `parse_morning_reply.py` for OD-4 outcome
   - T: extend `parse_morning_reply.py` for 48hr window correlation
   - T: new `sweeper.py` per contracts
   - T: extend `exclude_completed_v2.py` for `auto_skipped` if needed
   - T: new systemd unit files + deployment in runbook
   - T: arch-doc updates (service-inventory.json + view.md + service-inventory.md + service-dependencies.view.md)
   - Owned files: `scripts/habits/sweeper.py`, `parse_morning_reply.py`, `exclude_completed_v2.py`, `scripts/office2/felix-habit-sweeper.{service,timer}`, arch JSON files, `docs/runbooks/habits-ops.md`

**Sequential**: WP-02 depends on WP-01's schedule_loader. Per the lane-rebase pattern from mission #59, expect to manually reset lane-b's HEAD to lane-a's tip before WP-02 starts.

**Single mission ok per the chronological-coupling test**: WP-02's sweeper consumes the schedule_loader from WP-01 by import; no need for WP-01 to be merged to main first.

---

## Branch contract (restated, 2nd)

- **Current branch**: `main`
- **Planning base**: `main`
- **Merge target**: `main`
- **`branch_matches_target`**: true

Completed changes merge into `main` via spec-kitty merge commit.

---

## ⛔ STOP

Per the /spec-kitty.plan mandatory stop, this command ends here. **Do not generate `tasks.md` or work-package files.** Operator runs `/spec-kitty.tasks` when ready.

**Generated artifacts**:
- `plan.md` (this file)
- `research.md`
- `data-model.md`
- `contracts/schedule-config.contract.md`
- `contracts/sweeper-tick.contract.md`
- `contracts/history-event-auto-skipped.contract.md`
- `contracts/reply-correlation.contract.md`
- `quickstart.md`

**Next suggested command**: `/spec-kitty.tasks`
