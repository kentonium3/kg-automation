# Mission Specification: Felix RRULE recurrence adaptation

**Mission Branch**: `kitty/mission-felix-rrule-adaptation-01M7TKNX` (merges into `fix/felix-rrule-adaptation`, cut from `main` @ `cc4f2154`)
**Created**: 2026-11-19
**Status**: Draft
**Input**: kentonium3/kg-automation#1111 (issue body, "Scope widened", "Read-only audit" and "Handoff brief" comments), plus Kent's rulings of 2026-11-19 recorded as Decision Moments in `decisions/`.

## Context

Since Vikunja's RRULE cutover on 2026-10-30, a task's recurrence is a **rule** (RFC 5545 parts). The old interval fields no longer exist, and the server silently drops unknown keys. A v1 task update replaces the whole task, so any field the caller leaves out is cleared. Several Felix write paths send narrow bodies, and each such write strips the rule and the reminders. Habits stop repeating after an auto-skip or a completion. A recurring task completed through escalation or intake loses its rule. The weekly habit report comes out empty. The test suite still passes because about 30 fixtures encode the old shape.

**No damage found so far.** The Vikunja core worker's read-only audit of 2026-11-19 ([#1111 comment](https://github.com/kentonium3/kg-automation/issues/1111#issuecomment-7019366561)) found:

- 147 `auto_skipped` events since the cutover, all on the 7 **daily** habits (14, 15, 16, 18, 19, 20, 65). The sweeper writes Vikunja only for **day-specific** habits, so those events made no Vikunja write.
- All 7 daily habits still carry `FREQ=DAILY;INTERVAL=1`.
- The day-specific habits 75–77 (strength training) have been Done with no rule since July, before the cutover.
- The escalation history shows no `N done` reply since 2026-07-25.

The exposure is therefore latent: it starts with the first active day-specific habit, Felix-recorded completion, escalation `done` or intake move. `felix-habit-sweeper.timer` has been disabled since 2026-11-19 19:09:41 UTC as containment.

Kent's rulings (2026-11-19, each recorded as a Decision Moment):

1. **Fork-first.** Office2 stays on the Vikunja fork until upstream ships RRULE support, so "fork-only" is no reason to avoid the v2 endpoints. The v2 partial update is the main write path, and the v1 full-echo write is kept only where v2 does not fit.
2. **Live data changes are approved** and are part of this mission: repair of any stripped rules the final check finds. (Kent approved new rules on tasks 75, 76 and 77 too, but on 2026-11-19 ruled that they stay Done, since they have been Done since July. Their rule write is out of scope.) Before each live write, the task is saved exactly as read so it can be put back. Every change is recorded on #1111.
3. **`migrate_schedule` is retired.** The frozen YAML history is kept.

Merges to `main` and Office2 deploys remain Kent's gates.

## Domain Language

| Canonical term | Meaning | Avoid |
|---|---|---|
| **rule** | The task's recurrence definition, Vikunja's `repeat` object (frequency, interval, by-day, count, until, …) | "repeat interval", "repeat_after" |
| **repeat-from-completion** | The flag that makes the next occurrence count from the completion date, not the due date (`repeats_from_current_date`) | "repeat mode" |
| **strip** | A write that leaves a task with no rule (or no reminders) when it had one before | "reset", "clear" (unless intended) |
| **partial update** | A write that changes only the named fields and leaves all others as stored (v2 PATCH) | "narrow POST" |
| **full echo** | A v1 write that resends the task exactly as just read, with only the intended changes applied | "replace" |
| **exhausted series** | A rule with COUNT or UNTIL whose last occurrence has been completed. The task stays Done. | "closed habit" |
| **damage inventory** | The read-only list of tasks whose rule was stripped or changed since the cutover, with a proposed restore value | "damage list" (OK as a synonym in issue text) |
| **snapshot** | The task exactly as read from Vikunja immediately before a live write, kept so the write can be undone | "backup" |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Habits keep repeating (Priority: P1)

Kent records habit completions through Felix, and the 07:30 ET sweeper auto-skips any habit left unrecorded for 48 hours. After either write the habit still carries its rule and reminders, and it shows up again on its next scheduled day.

**Why this priority**: This is the highest-volume destructive path. Daily habits are hit every day, and the sweeper cannot be re-enabled until it is fixed.

**Independent Test**: Feed a habit task that carries a rule and reminders through the completion recorder and the sweeper auto-skip against a recorded Vikunja double. Assert that the rule, repeat-from-completion and reminders survive, and that the new due date is the rule's next occurrence.

**Acceptance Scenarios**:

1. **Given** a daily habit with a rule and a reminder, **When** Kent records a completion through Felix twice on consecutive days, **Then** after each completion the habit is open, due on the next day, and still carries the same rule and reminder.
2. **Given** a weekday habit with a weekly by-day rule (a test fixture; live tasks 75–77 stay Done per C-008), **When** the sweeper auto-skips it, **Then** its due date becomes the rule's next occurrence and the rule and reminders are unchanged.
3. **Given** a habit whose rule is missing, **When** the sweeper evaluates it, **Then** it does not write that habit, it records the habit as skipped with a reason, and it raises an alert.

---

### User Story 2 - Completing a recurring task through escalation keeps the series (Priority: P1)

Kent replies `N done` (or reschedules) to the escalation digest. Felix records the result through its helper, and a recurring task advances to its next occurrence with its rule intact.

**Why this priority**: This is destructive, cross-project and driven by agent instructions, so no code guard protects it. It is currently a live risk.

**Independent Test**: Run the escalation completion and reschedule helper against a recorded double for a recurring task and for a one-off task. Assert one successful write, an intact rule, and a JSONL record.

**Acceptance Scenarios**:

1. **Given** an overdue recurring task, **When** Kent replies `N done`, **Then** the task advances to its next occurrence, keeps its rule, and the escalation history records `done`.
2. **Given** the escalation agent's guidance, **When** it handles any reply, **Then** it never writes to Vikunja directly. It calls the Felix helper.
3. **Given** a recurring task whose due date advanced because it was completed, **When** reconcile runs, **Then** it records a completion, not a reschedule.

---

### User Story 3 - Intake and bulk tools never strip a rule (Priority: P2)

Kent replies to an intake digest to move, date or eliminate a task, or an operator runs a bulk move or migration tool. Recurring tasks keep their rule, except that "eliminate" deliberately ends the series.

**Why this priority**: Recurring tasks reach the inbox less often, but a single bulk run can strip many tasks at once.

**Independent Test**: Drive the intake reply and the bulk tools against recorded doubles of recurring tasks, and assert the rule after each write and in the readback check.

**Acceptance Scenarios**:

1. **Given** a recurring task in the inbox, **When** Kent moves it to another project, **Then** it arrives with the same rule, repeat-from-completion and reminders, and the readback check would fail had the rule changed.
2. **Given** a recurring task, **When** Kent eliminates it, **Then** the series ends: the task ends Done and is not reopened.
3. **Given** a recurring task, **When** it is shown in the intake digest, **Then** the "already recurring" note appears.

---

### User Story 4 - Recurring tasks can be created and proposed correctly (Priority: P2)

Kent, or the tasker or capture agents on his behalf, creates a recurring task, including "N times" and "until a date" series. Before a rule is proposed, Felix checks it and shows the next three dates.

**Why this priority**: Today a recurring create silently produces a one-off task. That is non-destructive but wrong.

**Independent Test**: Create tasks from rule text (plain, COUNT, UNTIL, repeat-from-completion) against a recorded double, and assert that the readback carries the rule. Run an invalid rule through the preview check and assert it is rejected.

**Acceptance Scenarios**:

1. **Given** the rule text "every 2 weeks, 6 times", **When** a task is created, **Then** the created task carries that rule and the create fails loudly if the readback shows no rule.
2. **Given** an invalid rule, **When** an agent proposes it, **Then** the preview check rejects it before anything is created.

---

### User Story 5 - Reports, schedule and sync see the real rules (Priority: P2)

The Monday weekly habit report lists each habit with its scheduled days. The habit schedule declares each habit's rule, and a load-time check flags any drift. The Felix-Vikunja sync notices when a rule disappears.

**Why this priority**: These are the detection surfaces that would have caught this incident.

**Independent Test**: Run the report against new-shape fixtures and assert that it is non-empty with correct scheduled days. Run the schedule check with one habit's rule removed and assert that it reports the drift. Run a sync cycle that removes a rule and assert that a divergence is raised, and run the first sync cycle and assert zero conflicts.

**Acceptance Scenarios**:

1. **Given** the current habits, **When** the weekly report runs, **Then** every active habit is classified and listed. None is dropped as "other".
2. **Given** a habit whose live rule differs from the schedule, **When** the schedule loads, **Then** the difference is reported and nothing is written.
3. **Given** the first sync cycle after the upgrade, **When** it runs, **Then** it baselines the rule fields with zero conflict alerts. A rule lost afterwards shows as a divergence.

---

### User Story 6 - The lost rules come back, reversibly (Priority: P1)

After the fixes are deployed, a final read-only check confirms that no rule was lost between the audit and the deploy, and any loss it finds is restored. Every live write can be undone, and every change is visible on #1111.

**Why this priority**: Any rule lost before the deploy would otherwise go unnoticed, and the habits it hit would silently stop repeating.

**Independent Test**: Run the damage inventory read-only and inspect its output. Run the repair in dry-run mode and assert that it lists the snapshot, before value, after value and restore command per task. In live mode, assert that every write is preceded by a snapshot and followed by a readback.

**Acceptance Scenarios**:

1. **Given** the damage inventory, **When** the repair runs, **Then** for each task it saves a snapshot first, writes the restored rule, reads it back, and posts the task id and before and after values on #1111.
2. **Given** any repaired task, **When** its restore command is run, **Then** the task returns to its snapshot state.
3. **Given** an empty inventory, **When** the check completes, **Then** the empty result is posted on #1111 and no live write is made.

---

### Edge Cases

- **Exhausted series** (COUNT/UNTIL): the last completion stays Done. Habit, escalation and report logic must not treat it as advanced or rescheduled.
- A **habit with no rule** at sweep time: skip it and alert, never guess a date.
- **Eliminating a recurring task**: clearing the rule and marking it done in one v1 write reopens the task. Ending the series must not reproduce that behaviour.
- A **concurrent UI edit** between a read and a full-echo write: v1 full echo can overwrite it. This is why partial update is preferred.
- A **stale COUNT** in an echoed rule: the server keeps the stored rule (verified rule 3). Tests must not assume otherwise.
- **Damage inventory with no restore source** for a task: report it as unresolved for Kent rather than inventing a rule.
- **Felix's credential lacks permission** for a v2 endpoint (occurrences/preview): fail loudly. Granting the permission is Kent's change.
- **Sync cache migration**: the first cycle sees the rule field on every task. It must baseline it, not raise a conflict storm.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Partial-update write | As a Felix maintainer, I want the shared Vikunja client to offer a partial update (v2 PATCH) that changes only the named fields, so that the rule, repeat-from-completion, reminders and all other fields stay as stored. | High | Open | [build] | no |
| FR-002 | Guarded full-echo fallback | As a Felix maintainer, I want every remaining v1 write to be a full echo, and a narrow v1 write that would drop the rule or reminders to be refused, so that the fallback cannot strip. Each remaining v1 use is named and justified in the plan. | High | Open | [build] | no |
| FR-003 | Habit completion keeps the rule | As Kent, I want recording a habit completion to keep its rule, so that a repeating habit advances and stays open on every completion, not only the first. | High | Open | [build] | no |
| FR-004 | Rule-driven sweeper auto-skip | As Kent, I want a sweeper auto-skip to move a missed habit to its rule's next occurrence with the rule and reminders intact, and to skip and alert on a habit with no rule rather than guess a date. | High | Open | [build] | no |
| FR-005 | Due-date setter keeps the rule | As Kent, I want the habit due-date setter (reconcile and bulk modes) to keep rules and reminders, or to be retired where FR-004 makes a mode redundant, so that no due-date write strips a habit. | High | Open | [build] | no |
| FR-006 | Escalation writes through the helper | As Kent, I want my `N done` and reschedule replies to go through the Felix helper, and the agent guidance never to write Vikunja directly, so that the helper's writes succeed on the live server and keep the rule. | High | Open | [build] | no |
| FR-007 | Intake moves keep the rule | As Kent, I want intake replies that move or re-date a task to keep its rule and reminders, with the post-write check failing if the rule changed. | Medium | Open | [build] | no |
| FR-008 | Intake eliminate ends the series | As Kent, I want eliminating a recurring task from intake to end its series, so that it ends Done and is not reopened. | Medium | Open | [build] | no |
| FR-009 | Intake recognises recurring tasks | As Kent, I want intake to recognise a recurring task, so that the "already recurring" note appears. | Low | Open | [build] | no |
| FR-010 | Bulk tools keep the rule | As an operator, I want the bulk move and date-migration tools to keep the rule, and their readback to catch a dropped rule, so that a bulk run cannot strip many tasks silently. | Medium | Open | [build] | no |
| FR-011 | Create recurring tasks from rule text | As Kent, I want the task-create helper to create a recurring task from rule text (including COUNT, UNTIL and repeat-from-completion), to read it back, and to fail if the rule is missing. | Medium | Open | [build] | no |
| FR-012 | Weekly report from rules | As Kent, I want the weekly habit report to classify habits from their rules and to take each window's scheduled days from the rule, so that the report lists every active habit. | Medium | Open | [build] | no |
| FR-013 | Schedule declares rules and checks drift | As Kent, I want the habit schedule to declare each habit's rule, and a read-only load-time check to report any habit whose live rule is missing or different. | Medium | Open | [build] | no |
| FR-014 | Exhausted series handled | As Kent, I want the last completion of a COUNT/UNTIL series to stay Done, and habits and escalation not to treat it as advanced or rescheduled. | High | Open | [build] | no |
| FR-015 | Reconcile labels recurring completions | As Kent, I want escalation reconcile to record a recurring task whose due date advanced (rule present) as a completion, not a reschedule. | Low | Open | [build] | no |
| FR-016 | Sync tracks the rule | As a Felix maintainer, I want the sync to track the rule and repeat-from-completion, to baseline them once on the first cycle with no conflicts, and to show a later rule loss as a divergence. | Medium | Open | [build] | no |
| FR-017 | Read-only reporters emit the rule | As a Felix maintainer, I want the read-only habit reporters to output the rule in place of the dead interval fields. | Low | Open | [build] | no |
| FR-018 | Retire migrate_schedule | As a Felix maintainer, I want the dormant phase-3 schedule migration tool and its tests removed from the active surface, with the frozen YAML history kept and every reference updated, so that its rollback can never strip rules. | Medium | Open | [build] | no |
| FR-019 | Agent guidance teaches the rule model | As Kent, I want the agent guidance (task-intelligence, vikunja-api, tasker, habits, escalation skill) to teach rules, partial updates and COUNT/UNTIL, and to route writes through helpers. A proposed rule is checked by preview and shown with its next three dates. | Medium | Open | [build] | no |
| FR-020 | Round-trip regression tests | As a Felix maintainer, I want every Felix write path to have a regression test proving the rule, repeat-from-completion and reminders survive, using a shared new-shape fixture factory with the old-shape fixtures converted. | High | Open | [build] | no |
| FR-021 | Read-only damage inventory | As Kent, I want a read-only inventory, run once after the deploy, of every task whose rule was present at the cutover baseline (or at the 2026-11-19 audit) and is now missing or different, with a proposed restore value and its source per task, and unresolved tasks flagged. An empty inventory is a valid, recorded result. | High | Open | [build] | no |
| FR-022 | Reversible, recorded live writes | As Kent, I want, after the fixes are deployed, each inventoried task classified `lost` (rule gone with Felix-write attribution) repaired automatically. Tasks classified `removed`, `changed`, `ended` or `unresolved` are listed for me and repaired only on my explicit choice (revised 2026-11-19, analysis finding I2; post-plan review findings 4 and 9). Each write is preceded by a snapshot of the task exactly as read, has a restore command, is confirmed by readback, and is recorded on #1111 with task id and before and after values. | High | Open | [build] | no |
| FR-023 | Normal deploy path and architecture docs | As Kent, I want the fixes shipped through kg-automation's normal deploy path, with the architecture docs and data updated for the v2 data flow. Helpers and agent docs ride the office2 self-pull and agent-prompt/skill sync. A `deploys/queued/` manifest is added only if a cron, unit or service config changes (corrected 2026-11-19 from plan research: `docs/runbooks/deploy/discipline.md:19-25`). | High | Open | [build] | no |
| FR-024 | Sweeper re-enabled and verified | As Kent, I want the sweeper timer re-enabled only after its fix is live and on my go, and its next tick verified to keep rules. | High | Open | [build] | no |
| FR-025 | Existing-task field update keeps the rule | As Kent, I want Felix's enrichment of existing tasks (retroactive_enrichment, detect_incomplete) to change a task's title, description, due date, priority or project only through a helper that uses v2 PATCH and reads the task back. A changed rule, repeat-from-completion flag or reminder set is reported as a failure. The helper refuses rule edits and due-date changes on a recurring task (those move the series anchor and stay in Vikunja for now). (Added 2026-11-20, Kent's in-mission ruling A on #1111: WP09 found these paths had no safe write; new WP12.) | High | Open | [build] | no |
| FR-026 | Habit pause, resume and remove keep history and the rule | As Kent, I want "pause", "resume" and "remove" for a habit to work through a Felix helper. Pause adds and resume removes a `(PAUSED)` description prefix (rule kept, verified by readback), and the morning check-in list and the sweeper skip paused habits; no code did this before, although the habits agent doc said it did. Remove ends the series (rule cleared, then done) and never deletes the task. (Added 2026-11-20, Kent's in-mission ruling A on #1111, pause semantics A.) | High | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | No dead fields | Zero occurrences of the retired interval fields (`repeat_after`, `repeat_mode`) in active Felix code and agent guidance, excluding frozen migration history, release tooling and their tests. | Maintainability | High | Open |
| NFR-002 | Tests that can fail | 100% of FR-020 regression tests are shown failing against the pre-fix code and passing after it, with both results captured in the work package's evidence. | Reliability | High | Open |
| NFR-003 | Suite green | The full local test suite passes (0 failures) at consolidate. | Reliability | High | Open |
| NFR-004 | Quiet first sync | The first sync cycle after deploy produces 0 conflict alerts and 0 unsafe signals attributable to the new rule fields. | Reliability | Medium | Open |
| NFR-005 | Every live write is reversible | 100% of live writes have a stored snapshot and a restore command before the write is issued, and 100% are confirmed by readback. | Safety | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Partial update first | The v2 partial update is the main write path. v1 full echo is used only where v2 does not fit, and each such use is named in the plan. | Technical | High | Open |
| C-002 | Kent's gates | Merges to `main`, Office2 deploys and timer changes wait for Kent's go. The sweeper stays disabled until its fix is live. | Business | High | Open |
| C-003 | No metered CI | No GitHub Actions workflows are enabled or triggered. Tests run locally. | Business | High | Open |
| C-004 | Live writes only via the procedure | Live Vikunja writes happen only through FR-022's snapshot, readback and record procedure, and only after the fixes are deployed. | Safety | High | Open |
| C-005 | Frozen history | The frozen `operations` block of `phase3-schedule.yaml` is not edited. | Technical | Medium | Open |
| C-006 | Credentials | Token files are never read or printed. If a v2 endpoint needs a new token permission, granting it is Kent's change. | Security | High | Open |
| C-007 | Out of scope | Google Calendar RRULE generation (audit row 30), Vikunja release tooling (row 34), sharing the calendar natural-language rule parser, and using occurrence end reasons in escalation messages are out of scope, and the last two become follow-up issues. | Business | Medium | Open |
| C-008 | Weekday habits stay Done | Tasks 75, 76 and 77 are not reopened or given rules (Kent, 2026-11-19). The day-specific habit code paths are built and tested against fixtures only. | Business | Medium | Open |

### Key Entities

- **Task rule**: a task's recurrence (frequency, interval, by-day/by-month-day, count, until) plus the repeat-from-completion flag. It owns when the next occurrence falls.
- **Reminder**: per-task reminder times. A v1 write rewrites them from the body, so they must be echoed or left alone.
- **Habit schedule entry**: Felix's declaration of a habit (task id, cadence, expected rule). Checked against the live task rule.
- **Damage inventory entry**: task id, rule at cutover baseline, current rule, proposed restore value, restore source, status (resolvable or unresolved).
- **Live-write record**: task id, snapshot reference, before value, after value, readback result, restore command, and the #1111 comment that recorded it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over the first 7 days after deploy, 100% of Felix habit completions and sweeper auto-skips leave the habit with its rule and reminders, checked by the schedule drift check on each day. — [build] · no-op passable: no
- **SC-002**: The first weekly habit report after deploy lists 100% of the active habits (the 7 daily habits today), with none dropped. — [build] · no-op passable: no
- **SC-003**: The post-deploy inventory is posted on #1111. 100% of inventoried tasks (possibly none) either carry their restored rule (confirmed by readback) or are listed as unresolved for Kent, and 100% of live changes appear on #1111 with before and after values. — [build] · no-op passable: no
- **SC-004**: After re-enable, the sweeper's next tick completes with 0 errors, and every habit it touched still carries its rule. — [build] · no-op passable: no
- **SC-005**: 100% of the Felix write paths named in the audit's rows 1–11 and 23 have a round-trip regression test that would fail if the rule were stripped. Rows 12–16 are the `migrate_schedule` write sites, which are dispositioned by retirement (FR-018). Revised 2026-11-19 after analysis finding I1. — [build] · no-op passable: no

## Assumptions

- The fork at `d7e202228` behaves as the audit describes. Its v2 PATCH leaves omitted fields unchanged, handles a `null` rule, and resolves token permission through the v1 "update" key (`pkg/models/api_routes.go:33-37, 272-281`). The plan re-verifies each against the source before relying on it.
- The v2 occurrences and preview endpoints may sit under a permission group Felix's token lacks. The plan checks this. A grant is Kent's change (C-006).
- The escalation helper's PATCH failing with 405 on v1 is inferred, not observed. The escalation history shows no `kent_reply` `done` since 2026-07-25. The plan settles it from code and logs.
- Restore sources are the cutover release baseline (the captured rule column) and the habit schedule. Where neither gives a rule, the task is reported unresolved rather than guessed.
- The audit's line numbers were taken at `cc4f2154`, which is the mission base, so they are current.
