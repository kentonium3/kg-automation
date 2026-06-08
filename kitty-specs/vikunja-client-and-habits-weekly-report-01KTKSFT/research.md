# Phase 0 Research: Vikunja client + habits weekly report

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT`
**Spec**: [spec.md](./spec.md) (revision 2) | **Plan**: [plan.md](./plan.md) (revision 2)

Live-probe research conducted during plan phase per Felix Constitution Directive 6. Findings here drove the revision-2 scope correction in the spec and plan.

---

## R-001 — Vikunja recurrence model is a hybrid (daily-cadence + weekday-in-title), NOT uniform repeat_after

**Decision**: The weekly helper classifies habits into two kinds based on the live Vikunja data, NOT the assumption in spec revision 1.

- **Daily-cadence habits**: `repeat_after == 86400`. Examples observed: "Wake at 5:00 AM", "Meditate", "Morning shoulder PT", "Get steps in today", "Read 30 min minimum", "Evening shoulder PT", "Morning hip PT". Vikunja auto-creates the next instance when the current is marked done.
- **Weekday-in-title habits**: `repeat_after == 0`, title contains a weekday name (e.g., "Strength training — Monday", "Strength training — Wednesday", "Strength training — Friday"). Per-occurrence one-off tasks; Kent or some other process creates the next instance manually (Vikunja does NOT auto-recur).

**Rationale**:
- Probe results from `GET /projects/13/tasks` showed exactly this pattern for all 11 habits Kent tracks today.
- The morning-check-in path already handles this via the day-of-week filter introduced in mission #408 (`_weekday_name_for_date` in `query_active_habits_v2.py`). The weekly helper mirrors that discipline.

**Alternatives considered**:
- *Spec revision 1's assumption (uniform `repeat_after=604800` for weekly habits)*: rejected — disproved by live data. The Strength training habits have `repeat_after=0`, not 604800.
- *Generalize to "any title containing a day word"*: too aggressive; risks false positives on habits like "Sunday school" or similar. Plan-phase contract pins the regex.

**Verification**:
- `ssh office2-claude` + `GET /projects/13/tasks` returned the data above.

---

## R-002 — Vikunja exposes per-task completion history via `done_at` + `?filter=done=true`

**Decision**: The weekly helper queries Vikunja directly for historical completion data via the shared client. No new audit-log infrastructure needed.

- `GET /projects/13/tasks?filter=done=true` returns historical completed tasks with `done_at` populated.
- Sample data observed: `Workout 45 min done_at: 2026-05-19T20:08:41Z`, `Strength training — Wednesday done_at: 2026-06-03T13:24:17Z`.

**Rationale**:
- Direct access to the authoritative source — no parallel state to keep fresh.
- Avoids needing to extend `sync_cache.py` to record history (much bigger scope).

**Alternatives considered**:
- *Read from sync cache*: rejected. The cache holds current state only (`done == false` for active tasks); no history.
- *Build a new audit log of completion events*: rejected. Vikunja already records this; building parallel infrastructure violates Directive 6 and adds maintenance burden.
- *Compute from Vikunja activities endpoint*: `/projects/13/activities` returned 404 in the probe. Not available.

**Open verification for plan phase**:
- Confirm the date-range filter syntax: `?filter=done=true&filter=done_at>=<iso>` OR `?filter=done_at>=<iso>` etc. Memory `reference_vikunja_filter_gotchas.md` notes server-side filter rejection class — plan phase tests the actual syntax.

---

## R-003 — Morning check-in uses the local sync cache (NOT Vikunja API directly)

**Decision**: `query_active_habits_v2.py` is NOT modified by this mission. FR-007 is DROPPED.

- `query_active_habits_v2.py` reads from `/data/services/openclaw/state/sync/task-cache.json` via `scripts.common.sync_cache.read_tasks_or_raise`.
- The cache is populated and kept fresh by the felix-vikunja-sync driver (mission #518).
- v2's filter: `done == False AND due_date <= <today>T23:59:59Z AND project_id == 13` plus day-of-week filtering when `schedule_path` is provided (mission #408).
- The cache holds current state only — no `done_at` history; no completion timeline.

**Rationale**:
- Originally (spec revision 1, FR-007) we planned to migrate v2 to the new shared client as the first migration target for #542. But v2 doesn't call Vikunja API — it reads the cache. There's nothing to migrate.
- Preserving v2's cache discipline matches the existing performance and reliability characteristics; morning check-in remains fast and works during transient Vikunja outages (the cache is read-only at v2-invocation time).

**Implication for #542's "two existing migrations" criterion**:
- This mission achieves ZERO existing migrations. The new weekly helper is new code, not a migration.
- First existing-migration target becomes a deliberate follow-up issue. Natural candidate: `scripts/sync/fetch.py` (the felix-vikunja-sync driver), which DOES consume Vikunja API to populate the cache. Migrating it would carry the highest impact for client maturity (the sync driver is the hot path).

**Alternatives considered**:
- *Extend the cache to carry done_at history*: rejected as out of scope; would require co-designing with mission #518 / #520's cache discipline and is a much larger sync-pipeline change.

---

## R-004 — Weekly cron schedule and configuration confirmed

**Decision**: The weekly cron is `habits-weekly-report` at `0 22 * * 0` (Sunday 10pm America/New_York), `announce` delivery to `whatsapp:+16179300916`. FR-014 is verified.

**Rationale**:
- `ssh office2-claude` + `openclaw cron list` returned the entry: `e4214634-bfb8-4141-9f39-6f7f0ad49b23 habits-weekly-report cron 0 22 * * 0 (exact) ... ok ... isolated announce -> whatsapp:+16179300916 (explicit)`.
- Last run "16h ago" at probe time (2026-06-08 ~14:30 UTC), consistent with Sunday evening cadence.

**Implication for AGENTS.md**:
- FR-009's documented weekly-report procedure must match this cadence.
- The pre-existing "weekly reports out of scope" statement in felix-admin-habits/AGENTS.md is the source of the contradiction the agent self-debated about; revising it to in-scope reflects this confirmed cron reality.

---

## R-005 — Sibling-agent deployed paths differ from assumed; repo paths exist

**Decision**: Locate the actual deployed paths during plan-phase (specifically, before WP03 implementer dispatch). Update FR-010 audit invocations accordingly.

- Probe `find /home/claude -maxdepth 5 -name "AGENTS.md"` returned only:
  - `/home/claude/kg-automation/AGENTS.md` (the repo root AGENTS.md)
  - `/home/claude/.openclaw/agents/felix-admin-capture/AGENTS.md` (capture)
  - `/home/claude/.openclaw/workspace/AGENTS.md` (Felix main workspace)
- No `felix-admin-habits`, `felix-admin-escalation`, `felix-admin-tasker` AGENTS.md found at `/home/claude/.openclaw/agents/`.
- Per memory `reference_office2_agent_deploy_paths.md`: agent slug ≠ deploy dir (e.g., capture deploys at `/data/services/openclaw/inbox-agent/`).

**Rationale**:
- The repo source AGENTS.md files at `scripts/openclaw/agents/felix-admin-*` ARE the canonical source. The mission edits THOSE; deploy-to-office2 is a separate pipeline.
- Plan phase locates the deployed paths via `find /data -name "AGENTS.md"` or similar so post-deploy verification can check the runtime AGENTS.md content.

**Alternatives considered**:
- *Edit deployed copies directly via SSH*: rejected. Violates the "edit in repo, deploy via sync" pattern. The repo is the source of truth.

---

## R-006 — felix-admin-escalation IS user-facing-WhatsApp; sibling audit IS in scope

**Decision**: felix-admin-escalation's AGENTS.md is in scope for FR-010 audit + Hard Rules addition. felix-admin-tasker's cron status is confirmed in plan phase.

- Probe `openclaw cron list` returned `escalation-daily` at `0 12 * * *` (noon every day), `announce` → WhatsApp. Confirmed escalation IS user-facing-WhatsApp.
- felix-admin-tasker did not appear in the cron list output (only inbox-noon, inbox-5pm, inbox-7am, inbox-10pm, health-check-evening, health-check-morning, habits-morning-checkin, habits-weekly-report, escalation-daily appeared).

**Rationale**:
- Phase-0 confirms escalation needs the audit treatment.
- Tasker's status (cron-driven user-facing WhatsApp or not) determines whether it gets Hard Rules or just the "no user-facing WhatsApp" annotation. Plan phase confirms via reading tasker's AGENTS.md content and verifying no cron exists.

---

## Open items for plan phase

- **OP-001**: Confirm Vikunja's date-range filter syntax for `done_at` (per R-002 open verification).
- **OP-002**: Locate the deployed AGENTS.md paths for felix-admin-habits, felix-admin-escalation, felix-admin-tasker on office2 (per R-005).
- **OP-003**: Confirm felix-admin-tasker's cron status (cron-driven WhatsApp or not) (per R-006).
- **OP-004**: Audit all 11 habits' titles against the weekday-in-title regex pattern `(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?` to confirm no false positives or false negatives (per R-001).
- **OP-005**: Run `validate_docs.py` against the architecture JSON changes in WP04 to confirm schema compliance (standard discipline, not mission-specific).
