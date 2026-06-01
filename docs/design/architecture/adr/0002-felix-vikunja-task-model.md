---
title: ADR-0002 — Felix ↔ Vikunja task model
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-05-17'
version: v1.0
audience: agents_and_humans
tags: [2032]
---

# ADR-0002 — Felix ↔ Vikunja task model

**Status**: Approved
**Date**: 2026-05-17
**Deciders**: Kent Gale
**Supersedes**: the implicit task model embedded in the original `habits` / `escalation` / `tasker` agents (comment-as-completion, in-prompt comment parsing, agent-as-Kent attribution).

## Context

Felix uses Vikunja as the canonical task store and UI. Four agents currently read and write Vikunja: `habits` (morning + evening check-in), `escalation` (overdue-task surfacing), `tasker` (task enrichment), and the WhatsApp-driven completion writers used by all three. Over time these agents converged on a shared but unstated task model:

- **No native recurrence.** All habit and stake-bearing tasks were one-off (`repeat_after=0, repeat_mode=0`); the agent owned the schedule via description-string parsing.
- **Completion-as-comment.** Rather than setting `done=true`, agents wrote `[Felix] YYYY-MM-DD | state | note` comments. The `done` flag was reserved for "this task is permanently closed."
- **In-prompt comment parsing.** Each agent's AGENTS.md included LLM instructions to read the comment trail and infer "is this habit done today?" — a stochastic step over deterministic content.
- **No agent identity at the API layer.** All Felix writes attributed to the `kent` user via Kent's personal API token. There was no structured signal distinguishing "Kent wrote this" from "Felix wrote this" except the `[Felix]` prefix in comment text.

This worked while Felix was the only writer. It broke the moment Kent and Felix both wrote to the same task.

### The triggering incident

Saturday 2026-05-16, 7:05am ET. Kent's morning habit check-in surfaced 2 of his usual 8 habits. Investigation found that Kent had reviewed Vikunja in his UI Friday night and manually ticked 6 habits done that Felix had already recorded via WhatsApp comments. `query_active_habits.py` filters out any task where `done=true`, permanently. The 6 tasks dropped out of tomorrow's surface — and the day after's, and indefinitely. There was no reconciliation between Kent's UI click and the agent's comment trail.

The root cause was structural, not a script bug: Felix had built a completion model that fought Vikunja's native UI affordances, and there was no reconciliation layer between the two.

### Why the workaround existed

The most likely original justification was **history preservation**. Vikunja's native recurring tasks mutate the same task in place (advancing date fields rather than creating new instances) and `done_at` is scalar (overwritten each cycle). The comment-as-completion model preserved a durable historical record at the cost of fighting the UI.

### What the research established

Two research reports preceded this ADR:

- [`vikunja-task-model-research.md`](<../../research/vikunja-task-model-research.md>) — Vikunja v0.24.6 capability survey, current-code audit, and completion-record data-model exploration. Key findings: native recurrence is interval-only (`repeat_mode` 0/1/2; no RRULE, no day-of-week); repeating tasks mutate in place; no native activity/completion-history API; webhooks ARE enabled but unconfigured; filter language supports date math and boolean operators; all current writes attribute to `kent`; three distinct `[Felix*]` comment conventions are LLM-parsed (D6 violation in 2 of 3 cases).
- [`vikunja-rrule-upstream-state.md`](<../../research/vikunja-rrule-upstream-state.md>) — Track B feasibility. PR #2032 is actively migrating Vikunja to RFC 5545 RRULE using `teambition/rrule-go`. Maintainer kolaente directed the contributor to this approach. PR is blocked on review bandwidth, not philosophical opposition. kolaente offered a €600 sponsorship path. Conclusion: RRULE is months-not-years away; worth tracking, not worth depending on for this redesign.

## Decision

**Adopt a Vikunja-native task model in which (1) native recurrence is canonical, (2) `done=true` is the canonical "completed today" signal, (3) a per-domain JSONL log is canonical history, (4) Vikunja comments are UI-visible mirrors of JSONL records, and (5) Felix writes attribute to a dedicated `felix-bot` Vikunja user.**

The redesign was structured as ten sequential design questions. Each decision below records the choice and the rejected alternatives.

### Q1 — Schedule expression

**Decision**: Native Vikunja recurring tasks for all habits. Day-of-week patterns expressed as N separate weekly tasks.

| Pattern | Encoding |
|---|---|
| Daily | `repeat_mode=0, repeat_after=86400` |
| MWF (e.g. strength training) | 3 separate weekly tasks (Mon/Wed/Fri), each `repeat_after=604800` |
| Every 2 weeks (e.g. men's team meeting) | `repeat_after=1209600` |
| Monthly | `repeat_mode=1` |
| Quarterly | `repeat_after=7776000` (~90d; accepted drift of ~5 days/year) |

Labels (`personal`, `intentional`, `metalcasework`, plus new ones like `strength-training`) aggregate multi-task habits for reporting.

**Rationale**: Vikunja's native recurrence covers every near-term pattern Kent uses. N-task expansion adds at most ~5–8 tasks to the full Vikunja list view; WhatsApp UX is unaffected (each cron only surfaces today's tasks).

**Rejected**: native daily + custom for day-of-week (incomplete — Kent's real schedule includes day-of-week patterns); description-parser uniform + reconcile UI writes (preserves the workaround forever instead of fixing the root cause).

### Q2 — Completion signal

**Decision**: `done=true` is canonical for "completed today" and drives Vikunja's native auto-advance. JSONL log is canonical for history. Vikunja comment is a UI-visible mirror.

Q1 plus Q3 force this: with native recurrence, `done=true` is required to trigger auto-advance. Each role — current state, history, UI audit trail — has exactly one canonical store.

### Q3 — History preservation

**Decision**: Q3-D — a single completion-write helper performs three writes atomically.

New helper: `scripts/<domain>/record_completion.py`. Three writes:

1. `POST /tasks/{id}` with `done=true` — triggers Vikunja's native auto-advance.
2. `PUT /tasks/{id}/comments` with `[Felix] YYYY-MM-DD | state | optional note` — UI-visible audit mirror.
3. Append to `/data/services/openclaw/state/<domain>-history.jsonl` — durable history independent of Vikunja task lifecycle.

Idempotent on `task_id + date + state`. If any write fails, exit nonzero; do not claim success.

Unified JSONL schema (per Q5-C):

```jsonl
{"domain": "habits", "task_id": 14, "title": "Wake at 5:00 AM", "date": "2026-05-16", "state": "complete", "source": "whatsapp", "note": null, "timestamp": "2026-05-16T11:05:11Z"}
```

`date` is the day the completion is *for*; `timestamp` is when it was recorded. This lets agents retroactively log "yesterday's PT was done" without timestamp confusion.

A companion helper, `scripts/<domain>/reconcile_completions.py`, runs at the start of every morning cron tick. For each habit task where `done=true` but no JSONL entry exists for `done_at`'s date, it appends a backfill record with `source: vikunja-ui` and `timestamp: <done_at>` (Q7).

**Rejected**: Q3-A (Vikunja comment as canonical history — task deletion = permanent history loss); Q3-B (JSONL only, no Vikunja comment — sacrifices UI visibility for marginal benefit); Q3-C (webhook-driven reconciliation — right tool, deferred to Q4).

### Q4 — Webhooks vs cron polling

**Decision**: Cron polling now. Webhooks deferred.

For habits, the morning cron is the daily synchronization event; real-time reconciliation buys nothing the morning reconciler doesn't already deliver. For escalation, the `done=false` filter already self-excludes UI-completed tasks. Webhooks would be additive (Vikunja's at-most-once delivery requires polling fallback anyway), so strictly more code for the same robustness floor. A webhook receiver also requires a new HTTP service (port binding, systemd unit, HMAC verification, log rotation, monitoring) — a Tier-2 deploy.

**Re-evaluation criteria**: sub-day reactivity becomes valuable — e.g., real-time WhatsApp confirmation of a UI tick, comments as a bidirectional channel, a new agent requiring real-time signals.

### Q5 — One parser or N

**Decision**: Q5-C — extend the JSONL pattern from habits to all state-tracking agents. One shared schema, one reader library. Vikunja comments remain readable mirrors in their existing per-domain formats.

Applies to `habits`, `escalation`, and `tasker` (enrichment). Shared library at `scripts/common/state_log.py` (proposed name; final naming during implementation) exposes `append(domain, record)` and `read(domain, **filters)`. Per-domain log files at `/data/services/openclaw/state/{habits,escalation,enrichment}-history.jsonl`.

**D6 win**: three LLM-in-prompt parsers replaced by one shared deterministic helper. Aligned bonus: simplifies historical analysis and LLM-behavior assessment.

### Q6 — Identity attribution

**Decision**: Provision a dedicated `felix-bot` Vikunja user. Share Kent's projects with `felix-bot` at read-write. Rotate the API token.

Mirrors the existing `kg-felix-bot` pattern on GitHub. Verified by live probe of office2's Vikunja v0.24.6:

- Registration is open (`registration_enabled: true`).
- Project sharing endpoints exist: `/projects/{id}/users`, `/projects/{id}/teams`.
- Labels are global (no per-user duplication needed).
- Teams as a grant model are available but unused.

**Implementation steps**:

1. `POST /api/v1/register` with felix-bot credentials.
2. Generate felix-bot's long-lived API token.
3. Share Habits (project ID 13) and other Felix-touched projects with felix-bot R/W.
4. Replace `/data/services/openclaw/secrets/vikunja-api` with felix-bot's token.
5. Verify a sample write attributes to `created_by: felix-bot`.

**Caveat**: existing comments will remain attributed to `kent` — cosmetic inconsistency, not worth rewriting.

**Reconciliation benefit**: `comment.author == kent` becomes the structured signal for "human wrote this" vs. `[Felix]` regex on comment text. D6 alignment.

### Q7 — Parallel-write reconciliation policy

**Decision**: Silent backfill via reconciler. Source-tagged `vikunja-ui`, timestamp = `done_at`.

For habits: reconciler detects `done=true + no JSONL entry for done_at date` and appends a backfill record. For escalation: reconciler detects `escalated-task-marked-done + no closure JSONL entry` and appends a closure record. The Q3-D reconciler handles both.

**UX note**: Vikunja's auto-advance fires at the moment of `done=true`, not at the next cron tick. Kent ticking a habit done at 10pm Tuesday immediately advances the task to Wednesday with `done=false`. The system self-heals instantly; the reconciler's job is just to ensure JSONL has the matching record.

**Rejected**: prompting Kent for confirmation — the `done=true` flag IS the confirmation.

### Q8 — Frequency lexicon expansion

**Decision**: Dissolved under Q1.

No description-parser, no lexicon (`Daily`, `Mon-Sat`, `Mon/Wed/Fri`, etc.). All schedule expressivity lives in Vikunja's native repeat fields. The `description` field becomes free-form for habit notes, instructions, and links.

**Re-evaluation criteria**: if RRULE upstream lands (PR #2032), migrate quarterly drift to exact-quarterly via RRULE.

### Q9 — Filter scope

**Decision**: Code-canonical filters. View-creation helpers as optional future polish.

Filter logic lives in agent helpers (constants or args) — version-controlled, grep-able, testable. Vikunja's saved views are project-scoped; cross-project queries (e.g., escalation candidates) don't fit the per-project view model natively.

**Optional future polish**: a one-time setup script could create matching saved views per project so Kent gets "escalation candidates" in his Vikunja sidebar. Not blocking.

### Q10 — Failure-mode hardening

**Decision**: Domain-specific failure policy.

| Domain | Behavior on malformed/missing JSONL | Reasoning |
|---|---|---|
| habits | Soft-fail: treat as "not addressed today," re-ask in check-in. Log WARN. | Asking again is mild friction; silently skipping risks Kent thinking the habit was dropped. |
| escalation | Hard-fail: do NOT silently downgrade to Level 1. Skip the task this tick AND file a `P2-bug` via `felix-file-issue.py`. | Compounding consequences if wrong — over- or under-alerting Kent on stakes work. |
| enrichment (tasker) | Soft-fail: treat as "not yet offered," may re-propose. Log WARN. | Re-proposing is annoying but harmless. |

**Vikunja-vs-JSONL disagreement resolution**:

- `done=true` in Vikunja but no JSONL entry for date → reconciler backfills with `source: vikunja-ui`.
- `done=false` in Vikunja but JSONL shows complete for today → JSONL wins for "what was the disposition"; Vikunja wins for "should this re-surface today."
- JSONL has entry but Vikunja comment missing → reconciler backfills the comment.

## Consequences

### Positive

- **Native UI affordances work.** Kent's UI clicks are first-class completion signals, not exceptions to handle. The system self-heals at the moment of click via Vikunja's native auto-advance.
- **One canonical store per role.** No more "what's the source of truth" ambiguity. Current state lives in Vikunja; history lives in JSONL; UI audit lives in comments. Each store has one job.
- **D6 win across three agents.** Three LLM-in-prompt completion parsers collapse into one shared deterministic helper. Stochastic work becomes deterministic work. Easier to test, easier to debug, lower token spend.
- **Durable history independent of task lifecycle.** Vikunja task deletion no longer destroys historical completion records. JSONL is append-only, backed by Restic.
- **Structured agent identity.** `felix-bot` attribution makes "who wrote this" queryable via API rather than regex over comment text. Pattern parallels the existing `kg-felix-bot` GitHub identity.
- **Future-proof for sub-day reactivity.** Webhook receiver can be added later without rearchitecting the data model — the reconciler logic translates cleanly from polling to push.
- **Aligns with Vikunja upstream direction.** When RRULE lands (PR #2032), only schedule encodings change; the completion model and JSONL history remain stable.

### Negative

- **Multi-task expansion for day-of-week patterns.** MWF habits become 3 tasks instead of 1. Kent's full Vikunja list view grows by ~5–8 tasks. Mitigated by labels for reporting aggregation and by the fact that WhatsApp UX (which only surfaces today's tasks) is unaffected.
- **Quarterly drift of ~5 days/year.** Interval-only recurrence cannot express "first day of each quarter" exactly. Acceptable for Kent's quarterly check-ins; flips to exact when RRULE upstream lands.
- **One-time backfill complexity.** Phase 4 must read existing `[Felix]` comments from production tasks and replay them into JSONL so historical analysis isn't lost. Bounded work, but real.
- **Two writers, three writes per completion.** `record_completion.py` performs three API/file writes. Each must be idempotent; failure handling must not claim success on partial completion. Increases the surface area of "things that can go wrong on a single tick" relative to a single `done=true` POST.
- **felix-bot provisioning is a Tier-2 change.** Requires a new Vikunja user, project shares across all Felix-touched projects, and rotation of the API token in `/data/services/openclaw/secrets/`. Snapshot before, verify after.

### Neutral

- **`description` field semantics change.** From "structured schedule string" to "free-form notes." No automation reads it after Phase 5 cutover.
- **Existing comments stay attributed to `kent`.** Cosmetic inconsistency in the historical record; not worth rewriting.
- **JSONL log location.** `/data/services/openclaw/state/<domain>-history.jsonl` colocates with other agent state. Backed up by the existing Restic schedule.

## Implementation phases

Sequenced by dependency. Each phase delivers a useful increment and can be merged independently.

1. **Phase 1 — Identity provisioning.** Register `felix-bot` Vikunja user. Share Kent's Felix-touched projects R/W. Rotate API token in `/data/services/openclaw/secrets/vikunja-api`. Verify with a sample write attributes to `created_by: felix-bot`.
2. **Phase 2 — Shared JSONL infrastructure.** Build `scripts/common/state_log.py` (proposed name) with `append(domain, record)` and `read(domain, **filters)`. Define JSONL schema formally. Write unit tests covering idempotency, malformed-record handling, and concurrent-append safety.
3. **Phase 3 — Habits migration.** PATCH the 8 production habit tasks from `repeat_after=0` to their actual schedules (currently all daily; future MWF/biweekly/etc. as Kent introduces them). Build `scripts/habits/record_completion.py` and `scripts/habits/reconcile_completions.py`. Update `query_active_habits.py` and `exclude_completed.py` to read from JSONL instead of parsing comments in-prompt.
4. **Phase 4 — Habits backfill.** One-time migration script reads existing `[Felix]` comments from production habit tasks and appends to the habits JSONL log so historical analysis isn't lost.
5. **Phase 5 — Habits cutover.** Update `habits` AGENTS.md to use the new helpers. Switch the morning check-in cron over. Monitor for one week. Decommission the comment-parsing LLM step.
6. **Phase 6 — Escalation migration.** Apply Q5-C and Q10 patterns. Build `scripts/escalation/record_completion.py` and reconciler. Backfill JSONL from existing `[Felix-Escalation]` comments. Update the escalation skill. Cutover.
7. **Phase 7 — Tasker (enrichment) migration.** Same pattern. Build `scripts/enrichment/record_completion.py` and reconciler. Backfill JSONL from existing `[Felix] enrichment | ...` comments. Update the tasker skill. Cutover.
8. **Phase 8 — Future enhancements (deferred).** Webhook receiver (Q4). Saved-view creation helpers (Q9). RRULE migration once PR #2032 lands (Q1, Q8).

## Alternatives Considered

### Preserve the comment-as-completion model and add a reconciliation layer

Add a layer that watches `done=true` events and updates the comment trail accordingly, leaving the rest of the system unchanged. Rejected because it preserves the root cause: Felix continues to fight Vikunja's native UI affordances, and every future agent inherits the workaround. Tightens the fence around a known structural defect rather than removing the defect.

### Wait for RRULE upstream (PR #2032) before redesigning

Defer the redesign until Vikunja ships RFC 5545 RRULE so the schedule expressivity question is answered upstream. Rejected because (a) RRULE is months-not-years away with no committed date, (b) the schedule encoding is only one of ten design questions — completion model, history preservation, identity attribution, parser consolidation, and reconciliation are all independent of RRULE, and (c) interval-only recurrence covers every Kent pattern in scope today. When RRULE lands, only Q1 encodings need to change.

### JSONL only — drop the Vikunja comment mirror

Skip the comment write in `record_completion.py`'s three-write transaction. Simpler, fewer failure modes. Rejected because Vikunja is Kent's primary UI; without a comment trail he loses the in-UI audit of "what did Felix record today?" The marginal cost of the third write is small relative to the UX value.

### Single shared completion script across all agents

Combine `habits/record_completion.py`, `escalation/record_completion.py`, `enrichment/record_completion.py` into one. Rejected at this layer because each domain has different post-write side effects (escalation closes; habits triggers auto-advance; enrichment offers next-action prompts). The shared infrastructure lives one layer down in `scripts/common/state_log.py`; the per-domain wrappers stay separate.

### Per-user OAuth-style attribution

Mint a Vikunja personal-access token per Felix agent (one for habits, one for escalation, one for tasker) so the audit trail distinguishes them. Rejected as over-engineered for the current scale. `felix-bot` as a single bot identity is enough to distinguish human from agent; per-agent attribution can be added later if it becomes useful (it likely won't).

## Things out of scope

- **RRULE upstream contribution (Track B).** Tracked separately; see `vikunja-rrule-upstream-state.md`. Optional sponsorship initiative.
- **Webhook-based reconciliation.** Q4 explicitly deferred.
- **Vikunja saved views as canonical filter store.** Q9 explicitly deferred.
- **`felix-bot` accounts for systems other than Vikunja.** Out of scope; each integration handles its own identity attribution (GitHub already uses `kg-felix-bot`).

## References

- Research: [`vikunja-task-model-research.md`](<../../research/vikunja-task-model-research.md>) — Vikunja v0.24.6 capability survey, current-code audit, completion-record data model.
- Research: [`vikunja-rrule-upstream-state.md`](<../../research/vikunja-rrule-upstream-state.md>) — upstream RRULE feasibility (PR #2032, sponsorship path).
- Upstream PR: [`go-vikunja/vikunja#2032`](https://github.com/go-vikunja/vikunja/pull/2032) — RFC 5545 RRULE migration via `teambition/rrule-go`.
- Upstream issue: [`go-vikunja/vikunja#1369`](https://github.com/go-vikunja/vikunja/issues/1369) — original RRULE feature request.
- Governance: [Felix Constitution Directive 6](<../../../constitution/FELIX-CONSTITUTION.md>) — deterministic vs. stochastic work split; the design-time discipline this ADR operationalizes.
- Roadmap context: [Felix capability roadmap](<../../felix-capability-roadmap.md>).
- Format precedent: [ADR-0001](<./0001-google-workspace-via-gog.md>).
- Triggering incident: internal investigation 2026-05-16 (Saturday morning check-in surfaced 2/8 habits after parallel UI writes).
