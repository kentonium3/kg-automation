# Habits cutover to JSONL v2 flow — Specification

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Mission ID**: `01KS1FKE0QHYEHZW684YEJNEPW`
**Mission type**: software-dev
**Source**: GitHub issue [#308](https://github.com/kentonium3/kg-automation/issues/308) (Phase 5 of ADR-0002)
**Risk tier**: 2 (Application / State — Restic snapshot required)
**Created**: 2026-05-19 (UTC 2026-05-20)

---

## Overview

Phase 5 of ADR-0002 — switch the felix-admin-habits agent's standing orders (`AGENTS.md`) from the v1 comment-parsing flow to the v2 JSONL-based flow. This is the cutover that makes the data-layer work from Phases 3-4 actually take effect in the morning check-in cron.

This mission is **cutover-only** per Q2 discovery decision. V1 file decommission (deleting `query_active_habits.py` + `exclude_completed.py`, renaming `_v2.py` to canonical names) is deferred to a separate post-soak mission. The 2-3 day soak (Q1 decision) is a *stabilization observation window*, not a rollback evaluation window — issues found during soak become forward-fix commits, not reverts.

After this mission merges and the operator runs the deploy command, Tuesday morning check-ins will no longer surface a workout (the original #306 evidence bug). Wednesday morning will surface the new "Strength training — Wednesday" task (id 76).

---

## User Scenarios & Testing

### Primary actors

- **Kent** (operator) — runs the deploy command post-merge; monitors morning check-ins during the 2-3 day soak; receives the WhatsApp messages.
- **felix-admin-habits agent** (claude-haiku-4-5 on office2) — consumes the updated AGENTS.md on its next cron invocation.
- **Cron jobs**: `habits-morning-checkin` (daily 11:00 UTC = 7:00 AM ET) and `habits-weekly-report` (Sunday 22:00 UTC = 6:00 PM ET).

### Scenario 1 — Operator deploys the cutover

Kent merges this mission to main. Repo `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` now contains the v2 workflow. Operator runs the documented sync command from `docs/runbooks/habits-ops.md`:

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

Operator verifies via `ssh office2-claude 'sha256sum /data/services/openclaw/habits-agent/AGENTS.md'` matching the local file's sha256.

### Scenario 2 — Next morning cron tick (post-cutover)

At 7:00 AM ET on a non-Tuesday (e.g., Wednesday), the cron fires. The agent:

1. **Step 0 (NEW)**: invokes `python3 -m scripts.habits.reconcile_completions`. Detects no drift, no backfill needed (or backfills any Vikunja UI completions Kent did the night before).
2. **Step 1 (CHANGED)**: invokes `python3 -m scripts.habits.query_active_habits_v2`. Gets today's active habits via Vikunja-native filter `due_date <= now/d AND done = false`, project-scoped to Habits.
3. **Step 2 (CHANGED)**: pipes the result through `python3 -m scripts.habits.exclude_completed_v2`. Drops any habit with a `complete` JSONL entry for today.
4. **Step 3**: composes the WhatsApp check-in message with the remaining habits.
5. **Step 4 (CHANGED)**: on Kent's WhatsApp reply confirming completions, agent invokes `python3 -m scripts.habits.record_completion` for each completed habit (three-write atomic: Vikunja done=true + comment + state_log.append). State log gains entries with `source="whatsapp"`.

The WhatsApp UX from Kent's perspective is unchanged in format and frequency.

### Scenario 3 — Tuesday morning (the structural fix)

Tuesday at 7:00 AM ET. Step 1 query returns no workout task (the old workout task 17 has `done=true` from Phase 3 retire; the new MWF tasks 75/76/77 only have due_dates on Mon/Wed/Fri). The check-in message correctly omits any workout.

### Scenario 4 — Kent ticks a habit done in Vikunja UI

Kent opens Vikunja during the day, ticks "Meditate" done. Next morning's cron tick runs Step 0 (reconcile). Reconcile detects `done=true` with no JSONL entry for that date and backfills the record with `source="vikunja-ui"`. The Step 2 exclude_completed_v2 then correctly skips meditate from today's check-in (it's already complete in JSONL).

### Scenario 5 — Operator observes non-catastrophic anomaly during soak

Day 1 post-cutover: morning check-in is mostly correct but the message format has an extra newline or a slightly-off ordering. Operator notes the issue, files a small fix-up issue (or edits AGENTS.md inline if trivial), and re-deploys via the sync command. **No revert.** Soak continues with the corrected version.

### Scenario 6 — Catastrophic failure response (high-bar, expected to never trigger)

Hypothetical: the morning cron fails to deliver any check-in for 24+ hours, OR the agent crashes on every invocation, OR JSONL data corruption is detected. Operator:

1. `git revert <cutover-commit>` in the repo.
2. Re-runs the sync command from the runbook.
3. Next cron tick uses the v1 path (which is still on disk per C-001).
4. Files an incident triage issue.

This is the explicit catastrophic-only rollback path. Non-catastrophic issues fail forward.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` is edited to add `reconcile_completions.py` as Step 0 of the morning check-in workflow. Step 0 runs before any habit enumeration. | Active |
| FR-002 | AGENTS.md Step 1 (query active habits) references `query_active_habits_v2.py` instead of `query_active_habits.py`. | Active |
| FR-003 | AGENTS.md Step 2 (exclude completed) references `exclude_completed_v2.py` instead of `exclude_completed.py`. | Active |
| FR-004 | AGENTS.md response-handling section instructs the agent to invoke `record_completion.py` for each WhatsApp-confirmed habit completion. The agent NO LONGER makes inline POST/PUT calls to Vikunja for habit completion. | Active |
| FR-005 | AGENTS.md removes all instructions for parsing `[Felix]` comments in-prompt. The historical context (why this approach existed, what `[Felix]` comments mean for legacy data) MAY remain as a short note pointing to the JSONL log as the canonical history source. | Active |
| FR-006 | The new AGENTS.md preserves the message identity line, the message format conventions, the WhatsApp delivery rules, and the weekly report Step. Weekly report semantics may need to consult the JSONL log instead of comments — TBD during plan phase. | Active |
| FR-007 | The deploy command in `docs/runbooks/habits-ops.md` § Update workspace files is unchanged; the operator runs that exact command post-merge. No new deploy machinery is introduced by this phase. | Active |
| FR-008 | After deploy: sha256 of `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (repo) equals sha256 of `/data/services/openclaw/habits-agent/AGENTS.md` (office2). | Active |
| FR-009 | V1 sibling scripts (`scripts/habits/query_active_habits.py`, `scripts/habits/exclude_completed.py`) remain present in the repo and on office2 during this mission. They become unreferenced by AGENTS.md but are NOT deleted. Their tests remain valid. | Active |
| FR-010 | `docs/runbooks/habits-ops.md` is updated to document the cutover date and reference the new workflow (Step 0 reconcile, v2 query/exclude, record_completion). | Active |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | The post-cutover morning check-in cron runtime stays within the existing 120-second cron timeout (per `habits-ops.md` schedule documentation). | < 120s wall-clock | Active |
| NFR-002 | The new AGENTS.md does not exceed 1.5x the byte size of the current 16,367-byte file (so the LLM context budget stays reasonable). | < ~24,500 bytes | Active |
| NFR-003 | All existing 314 habits tests pass post-cutover (no test changes expected since the AGENTS.md edit doesn't touch the Python helpers). | 314+ tests passing | Active |
| NFR-004 | Pre-deploy and post-deploy sha256 verification: the byte equality check completes in under 5 seconds. | < 5s | Active |
| NFR-005 | Token contents and other secrets continue to be unreferenced in AGENTS.md (no new secrets exposure surface). | 0 new secrets in AGENTS.md | Active |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | V1 sibling scripts (`query_active_habits.py`, `exclude_completed.py`) are NOT deleted by this mission. Their removal is deferred to a separate post-soak mission filed ~2-3 days after this mission merges (per Q2=A discovery decision). | Active |
| C-002 | `_v2.py` files are NOT renamed by this mission. The post-soak mission will rename them to the canonical names (Q3=A direction). | Active |
| C-003 | The cron schedule and openclaw cron configuration are NOT modified. The 11:00 UTC daily + 22:00 UTC Sunday cadence remains. | Active |
| C-004 | The agent's model selection (claude-haiku-4-5 per `~/.openclaw/openclaw.json` on office2) is NOT modified. | Active |
| C-005 | No Python code changes in `scripts/habits/`, `scripts/common/`, or anywhere else. This mission is exclusively a Markdown edit (AGENTS.md) plus the runbook documentation update. | Active |
| C-006 | felix-bot identity authentication continues to be the only Vikunja write attribution path. The agent does NOT introduce direct kent-token usage. | Active |
| C-007 | The 2-3 day soak posture is FAIL-FORWARD. Non-catastrophic issues during soak (formatting, off-by-one, drift, edge cases) become forward-fix follow-up commits — NOT triggers to revert the cutover. Rollback is reserved for catastrophic failure only (cron silent for 24+ hours, agent crashes, JSONL data corruption). | Active |

---

## Key Entities

### AGENTS.md (the deliverable)

Repo source: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
Deployed: `/data/services/openclaw/habits-agent/AGENTS.md` on office2

Current state (pre-mission): 16,367 bytes; sha256 = `471545db698f9a50cee83eb72261a3fbbdccf55e2da7bf94a2dff733448a2de6` (both repo and office2 confirmed identical 2026-05-19 17:38 ET).

Post-mission state: edited to reference the v2 workflow (helpers, steps, response handling); v1 instructions removed from the workflow but historical context may remain as a short note.

### v2 helpers (consumed by post-cutover AGENTS.md)

All already on main and deployed to office2:

- `scripts/habits/reconcile_completions.py` (Phase 3) — Step 0
- `scripts/habits/query_active_habits_v2.py` (Phase 3) — Step 1
- `scripts/habits/exclude_completed_v2.py` (Phase 3) — Step 2
- `scripts/habits/record_completion.py` (Phase 3) — Step 4

### Cron jobs (consumers, not modified)

- `habits-morning-checkin` — daily 11:00 UTC, target `+16179300916` WhatsApp.
- `habits-weekly-report` — Sunday 22:00 UTC, target `+16179300916` WhatsApp.

Both are openclaw cron entries. Configuration is in `~/.openclaw/openclaw.json` on office2.

### JSONL state log (downstream consumer)

`/data/services/openclaw/state/habits-history.jsonl` — currently has 31 historical records from Phase 4 backfill (mission #41). Post-cutover, accumulates new `source="whatsapp"` entries from each daily check-in's record_completion calls + occasional `source="vikunja-ui"` entries from reconcile backfills.

---

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | After deploy: `sha256sum scripts/openclaw/agents/felix-admin-habits/AGENTS.md` equals `ssh office2-claude 'sha256sum /data/services/openclaw/habits-agent/AGENTS.md'`. |
| SC-002 | The next `habits-morning-checkin` cron tick post-cutover produces a WhatsApp message delivered to Kent at +16179300916. The message format is recognizable to Kent (same identity line, same structural layout). |
| SC-003 | The cron's openclaw session log shows the four v2 helpers being invoked in order: reconcile_completions → query_active_habits_v2 → exclude_completed_v2 → record_completion (the last one only if Kent confirms completions). |
| SC-004 | The `habits-history.jsonl` log accumulates at least one new entry with `source="whatsapp"` after Kent responds to a check-in. |
| SC-005 | Tuesday morning check-ins do NOT include any workout task. Wednesday/Friday/Monday check-ins DO include the appropriate Strength training task (76/77/75 respectively). |
| SC-006 | All 314 habits tests pass on main post-merge. |
| SC-007 | At least one Vikunja UI completion (operator manually ticks done in the web UI) gets backfilled to JSONL on the next morning's reconcile, with `source="vikunja-ui"`. |
| SC-008 | After 2-3 day soak: zero catastrophic failures observed. Any non-catastrophic anomalies are documented as forward-fix follow-ups (issues or PRs), not rollbacks. |

---

## Assumptions

1. The Phase 4 backfill outcome (31 records in `habits-history.jsonl`) is stable; nothing has modified the JSONL since 2026-05-19 21:22 UTC.
2. The deployed openclaw configuration (cron entries, agent definitions) does not require changes for Phase 5. Only the workspace file `AGENTS.md` changes.
3. The agent's claude-haiku-4-5 model can correctly follow the new structured Step 0 → 1 → 2 → 3 → 4 workflow. (Prior phases used similar multi-step orchestration with this model; baseline behavior expected.)
4. The 2-3 day soak window starts when the operator runs the deploy command, not at PR merge time. Operator decides when to deploy.
5. The next `habits-morning-checkin` cron tick after deploy will exercise the new workflow on its first invocation.
6. No other process is writing to `habits-history.jsonl` during the soak (Phase 2's state_log fcntl-locked appends handle concurrency safely anyway, but the only writers in the Phase 5 timeframe are the cron's record_completion calls and operator-driven reconcile invocations).

---

## Out of scope

The following are explicitly NOT part of this mission and are deferred to a post-soak follow-up mission:

- Deleting `scripts/habits/query_active_habits.py` (v1)
- Deleting `scripts/habits/exclude_completed.py` (v1)
- Renaming `scripts/habits/query_active_habits_v2.py` → `query_active_habits.py`
- Renaming `scripts/habits/exclude_completed_v2.py` → `exclude_completed.py`
- Updating `data-flows.json` to remove the legacy-v1 entries
- Updating `service-inventory.json` registrations to reflect v2-as-canonical
- Removing v1 tests from `tests/habits/`
- Updating AGENTS.md to drop the `_v2` suffix in script invocations (will happen at the same time as the rename)

Also out of scope:

- Phase 6 (#309) — escalation migration to JSONL
- Phase 7 (#310) — tasker/enrichment migration to JSONL
- Cron schedule changes
- Model changes
- WhatsApp delivery mechanism changes
- New helper functionality (the current 4 v2 helpers are sufficient)
- Webhook receiver per ADR-0002 Q4 — deferred to ADR-0002 Phase 8
