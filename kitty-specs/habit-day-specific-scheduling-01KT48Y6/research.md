# Phase 0 — Research

**Mission**: `habit-day-specific-scheduling-01KT48Y6`
**Source issue**: [#408](https://github.com/kentonium3/issues/408)
**Spec**: [`spec.md`](./spec.md)

This document records the design decisions made during plan-phase discussion plus the live-probe research items deferred to implementer-phase code reading. Decisions on OD-1..OD-5 are resolved here (with implementation-time confirmation expected for the file-shape-dependent ones).

---

## OD-1: Schedule storage location — DECIDED (extend existing YAML)

**Decision**: Extend `scripts/habits/migrations/phase3-schedule.yaml` (or its successor in production) with an optional `designated_weekdays` field per habit entry. Default = unset = daily habit.

**Rationale**:
- Existing convention is to drive habit scheduling from a YAML config consumed by `migrate_schedule.py` and the runtime helpers. A single source of truth.
- Vikunja-label-based weekday assignment was an alternative but would require querying Vikunja per-habit to determine designation — adds latency and a Vikunja-dependency to the check-in builder.
- A sibling YAML file (`day-of-week.yaml`) would require synchronization across two files; rejected.

**Implementation-time confirmation**: implementer should `cat scripts/habits/migrations/phase3-schedule.yaml` on first WP to confirm the file's current shape on this branch (the migration script may have evolved). If the file shape has materially diverged from the snapshot in `migrations/`, the implementer surfaces a delta in the implementation report — but the design intent (extend the existing config in place) is locked.

**Field shape**: `designated_weekdays: ["Mon", "Wed"]` (list of three-letter ISO weekday abbreviations). Absent or empty list = daily habit.

---

## OD-2: Sweeper cadence — DECIDED (post-check-in, 7:30 AM ET)

**Decision**: The sweeper runs daily at **7:30 AM ET** (25 minutes after the morning check-in cron at 7:05 AM ET).

**Rationale**:
- The 48hr window's natural boundary is "the morning that's 48 hours after the original check-in." Running the sweeper shortly after each morning's check-in delivery catches any check-in delivered exactly 48 hours ago.
- Running BEFORE the morning check-in could race with the check-in itself if the morning cron is slow.
- Running at midnight ET would auto-skip yesterday's check-in entries that are only 17 hours old — violates the 48hr promise.
- 7:30 AM ET timer (`OnCalendar=*-*-* 07:30 America/New_York` equivalent — exact systemd syntax decided at implementation): one tick per day, well after the morning check-in completes.

**Risk**: if the morning check-in cron fails or runs late, the sweeper at 7:30 AM could see a check-in artifact for today missing. Mitigation: the sweeper reads the per-date check-in artifacts, NOT the live check-in. It evaluates artifacts >48hr old; today's missing-artifact doesn't affect any decision.

---

## OD-3: `--dry-run` flag — DECIDED (yes, default off)

**Decision**: The sweeper accepts `--dry-run` per the precedent in `set_due_dates.py`. Default is off (state mutation enabled). Dry-run mode produces the same tick artifact + journal `SUMMARY:` line but does NOT write to `habits-history.jsonl` and does NOT call Vikunja PUT.

**Rationale**: Matches `set_due_dates.py`'s precedent for operator testability. Useful for first deploy + threshold tuning + sanity checks during the cutover window.

---

## OD-4: Reply-correlation mechanism for 48hr window — RESEARCH AT IMPLEMENT TIME

**Decision (deferred to implementer)**: First WP reads `scripts/habits/parse_morning_reply.py` and determines whether:

- **Option A**: the parser already supports correlating to a specific check-in date (e.g., via WhatsApp quote-reply metadata in the inbound payload, OR via explicit `--checkin-date` flag, OR via inspection of the message body for date hints). If yes, the 48hr window is a small extension: the parser tries today's check-in first, falls back to yesterday's, then earlier (up to the 48hr boundary).

- **Option B**: the parser correlates ONLY to today's check-in artifact. The 48hr window requires either (a) parser extension to scan recent check-ins and disambiguate, (b) explicit operator command to mark yesterday's items, or (c) WhatsApp-quote-reply detection if the inbound channel forwards quote metadata.

**Implementation guidance**: if Option B, prefer (a) — extend the parser to handle multiple check-in candidates and prefer the most-specific match (exact quote-reply > date hint in message body > most-recent unresolved). This honors Kent's interaction pattern ("reply to Tuesday's message on Wednesday") without requiring him to add explicit date markers.

**Out of scope**: changing WhatsApp's inbound message format. We accept whatever the existing channel layer provides.

---

## OD-5: Manual reconciliation command (per FR-010) — DECIDED (new flag on existing script)

**Decision**: Add a `--reconcile-schedule` flag to `scripts/habits/set_due_dates.py`. Reads the (updated) `phase3-schedule.yaml`, for each habit whose `designated_weekdays` has changed, advances `due_date` to the next occurrence of the new designated weekday at EOD-ET. Logs to journal + writes a reconciliation record to `/data/services/openclaw/state/habits/reconcile-<datetime>.json`.

**Rationale**: matches the existing pattern of `set_due_dates.py` (a single helper that touches Vikunja due_dates) — the new flag is a focused use case. Alternative was a new dedicated `reconcile_schedule.py` helper, rejected as overkill for a config-change-only path Kent runs rarely.

---

## Existing-pattern adoption

This mission inherits two architectural precedents:

### A. felix-doc-auditor systemd-timer pattern (post-#343)

- Stateless Python oneshot per tick.
- Structured `last-tick.json` health signal.
- JSONL ledger for per-event audit trail (we'll use `habits-history.jsonl` + a new `auto_skipped` event type).
- Per-tick exit-status taxonomy: `success`, `partial`, `failure`.
- Journal `SUMMARY:` line.

Read `docs/runbooks/doc-auditor-driver-ops.md` for the canonical operational shape.

### B. felix-admin-habits existing helper-script pattern (mission #282 / Directive 6)

- Helper-scripts under `scripts/habits/` with thin agent prompts that just orchestrate.
- ET-aware timestamp handling via `compute_today.py`.
- Issue #112 regression-prevention: `set_due_dates.py` rejects `Z` suffix on `--iso-eod-et`. The sweeper's due_date advancement MUST use the same guard.
- Per-habit-failure resilience: continue with remaining habits on partial failure.

---

## Source code placement

```
scripts/habits/
├── compute_today.py                ← EXISTING (untouched)
├── set_due_dates.py                ← EXTENDED — new --reconcile-schedule flag (per OD-5)
├── parse_morning_reply.py          ← EXTENDED — 48hr window correlation per OD-4 outcome
├── query_active_habits_v2.py       ← EXTENDED — day-of-week filter (FR-002)
├── morning_checkin_list.py         ← EXTENDED — invokes day-of-week filter
├── exclude_completed_v2.py         ← EXISTING (consumed by morning_checkin_list)
├── record_completion.py            ← EXISTING (consumed by reply pipeline)
├── identify_workout_task.py        ← EXISTING (untouched)
├── migrate_schedule.py             ← EXISTING (untouched — but consumer of the new field)
├── sweeper.py                      ← NEW — entrypoint for 48hr auto-skip sweep
├── schedule_loader.py              ← NEW — central loader for phase3-schedule.yaml that returns day-of-week metadata
├── migrations/
│   └── phase3-schedule.yaml        ← EXTENDED — new `designated_weekdays` field per entry (FR-008)
└── tests/                          ← EXTENDED
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
├── felix-habit-sweeper.service     ← NEW
└── felix-habit-sweeper.timer       ← NEW (07:30 ET daily)

docs/runbooks/
└── habits-ops.md                   ← EXTENDED — new sweeper section, 48hr semantics, reconciliation command

docs/design/architecture/data/
├── service-inventory.json          ← EXTENDED — new felix-habit-sweeper entry (FR per CLAUDE.md standing requirement)
├── service-inventory.md            ← EXTENDED
└── service-dependencies.view.md    ← EXTENDED
```

---

## Test strategy

- Unit tests per new module, with mocked Vikunja (matching `scripts/habits/tests/` convention).
- Integration test that runs the sweeper against a representative fixture set of habits-history + morning-checkin artifacts.
- Reply-parser tests for 48hr window correlation: Kent replies to yesterday's check-in via quote-reply → correlates correctly.
- Coverage target: ≥85% line / ≥80% branch on new modules.

---

## Pre-rollout / cutover considerations

- No baseline measurement needed — this is a behavior fix, not a cost-reduction mission. Success criteria are direct (correct daily check-in contents + correct auto-skip behavior + 48hr window honored).
- Cutover risk is low: sweeper is silent (no WhatsApp output), idempotent, observable via tick artifact. Worst-case mistake (wrong skip) is recoverable via operator-edit of `habits-history.jsonl` + manual Vikunja due_date adjustment.
- First-week observation window: review `sweeper-tick-<date>.json` daily for unexpected auto-skips or errors.
