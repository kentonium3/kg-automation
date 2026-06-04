---
title: "Felix ↔ Vikunja Sync Architecture — Recommendation"
status: operator-review-pending
source_issue: "508"
parent_epic: "507"
research_mission: felix-vikunja-sync-architecture-research-01KT7Q15
---

# Felix ↔ Vikunja Sync Architecture — Recommendation

**Operator review pending on [#508](https://github.com/kentonium3/kg-automation/issues/508).**
Record accept or reject as a comment on #508 to close this research mission (SC-007).

---

## Summary

Felix should sync with Vikunja using a three-layer, polling-only reconciliation cycle that
runs on a 3–5 minute cadence. The architecture extends ADR-0002 (preserves the `done=true`
completion model, `felix-bot` identity, and JSONL history stores) and adds a centralized
reconciliation driver that replaces today's ad-hoc per-script polling with a structured
6-phase cycle. When Felix's cached state diverges from Vikunja's actual state, the cycle
detects the conflict, accepts Vikunja's value (Vikunja wins, always), emits a structured
log record, and routes unsafe conflicts to Kent via WhatsApp. This covers all seven operator
use cases from Epic #507 within a 5-minute latency ceiling, with one documented gap:
task deletion takes up to 15 minutes to confirm (see Deferred section below).

---

## Sync Layers

The sync architecture organizes Vikunja's state surface into three layers, each with its
own detection mechanism and reconciliation cadence:

| Layer | Vikunja resources | Detection | Cadence |
| --- | --- | --- | --- |
| **status** | `task.done`, `task.done_at` | `GET /tasks/all?updated_since=<ts>` returns changed tasks | Same as task layer — single poll covers both |
| **task** | All task fields (`title`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, etc.) | `GET /tasks/all?updated_since=<ts>` delta poll | 3–5 min |
| **project** | `project.id`, `project.title`, `project.is_archived` | `GET /projects` full fetch per cycle (14 projects; lightweight) | Same cycle as task layer |

The three layers share one reconciliation cycle. Status-layer divergences are detected as
part of the task-layer `updated_since` poll — no separate status poll is needed. Project-layer
uses a full `GET /projects` per cycle because `updated_since` is task-scoped and does not
surface project changes.

---

## Polling Cadence

**Recommended range**: 3–5 minutes per cycle, with 5 minutes as the default starting point.

**Rationale**: NFR-002 requires convergence within 5 minutes for all use cases. A 5-minute
cadence satisfies this with zero headroom for processing delay; a 3-minute cadence provides
a 2-minute margin. Felix's current scale (~15 active habit tasks, 14 projects) makes each
cycle a handful of HTTP GETs — sub-second execution time. The cadence is a systemd user timer
configuration value, tunable after initial deployment.

**Do not start below 3 minutes.** At sub-3-minute cadence, the `updated_since` delta polling
places non-trivial load on the Vikunja instance and may produce false-positive conflicts if
clock-skew between Felix's system clock and Vikunja's write timestamps is not handled. Start
at 5 minutes and reduce only if NFR-002 latency becomes a real operational issue.

---

## Conflict Resolution

**Policy (locked, C-002)**: Vikunja wins all conflicts.

When the `diff` phase detects a divergence between Vikunja's current state and Felix's cached
state, Vikunja's value is accepted unconditionally. Felix updates its cache to match. No
operator decision is required for conflict resolution itself.

**Unsafe-class criteria** (from RQ-3): four criteria determine whether a conflict is
`unsafe_to_auto_resolve` (triggers WhatsApp ping) vs `auto_resolved` (log only):

- **UC-1 `kent_edit_after_felix_write`**: Vikunja's `updated` timestamp is newer than
  Felix's last write timestamp for that field. Operator edited after Felix wrote.
- **UC-2 `operator_authored_field`**: The conflicting field's current Vikunja value was
  written by the `kent` user (not `felix-bot`).
- **UC-3 `downstream_behavior_depends`**: The conflicting field is one Felix agents act on
  to produce externally-visible effects (`done`, `done_at`, `due_date`, `repeat_after`,
  `repeat_mode`, `title`).
- **UC-4 `manual_override_signal`**: Felix's cache contains a "do not overwrite" marker for
  this field (prospective — requires override-flags mechanism not yet built).

**Volume**: Back-of-envelope estimate yields ~1.69 unsafe-class pings/day without guards.
Three guards (24h per-field dedup, 30-min post-write suppression, hard daily cap) reduce this
to ≤1/day — below the existing 4× daily inbox-cron IDLE WhatsApp noise floor. Details in
[rq-3-conflict-policy.md](<./findings/rq-3-conflict-policy.md>).

---

## Conflict-Event Log

Every conflict event (both `auto_resolved` and `unsafe_to_auto_resolve`) is written to a
JSONL log at `/data/services/openclaw/state/sync-conflict-history.jsonl` before any router
is called. The log uses the same append-only semantics and `state_log.py` shared library as
the existing domain history files (`habits-history.jsonl`, etc.). Each event record carries
a deterministic `event_id` (SHA-256 of layer + entity ID + field + timestamp + Vikunja value,
truncated to 16 hex chars) for dedup at the WhatsApp router. The record also carries
`schema_version: 1` as a forward-compat anchor for the eventual #516 observability framework.

Full schema and worked examples: [findings/conflict-event-log.sketch.md](<./findings/conflict-event-log.sketch.md>).

---

## Identifier Choice

**Stable identifier**: `task.id` (integer, globally unique, immutable for the task's lifetime).
Do not use `identifier` (e.g., `#1`) as the sync primary key — it is project-scoped and can
be reassigned on delete-recreate. Use `identifier` only for human-readable display in
WhatsApp conflict pings.

**Project stable identifier**: `project.id` (integer, same stability model as task `id`).

Evidence: RQ-1 confirmed `id` immutability from live API probes; memory
`reference_vikunja_id_vs_identifier` documents the UI vs API distinction.

---

## What This Changes

Each Felix component named in the RQ-2 touchpoint inventory (see
[findings/rq-2-touchpoints.md](<./findings/rq-2-touchpoints.md>)) changes as follows:

| Component | Before (today) | After (with sync architecture) |
| --- | --- | --- |
| **habits-agent** (`record_completion.py`, `reconcile_completions.py`, `query_active_habits_v2.py`, `set_due_dates.py`, `sweeper.py`, `morning_checkin_list.py`) | Each script polls Vikunja independently, no freshness pointer, no cross-script conflict coordination | Reads from Felix's sync cache (populated by reconciliation driver); writes still go direct to Vikunja but are registered with the reconciliation cycle so the driver knows Felix's last-write timestamp per field |
| **escalation-agent** (`escalation/record_completion.py`, `escalation/reconcile_completions.py`) | Same pattern as habits-agent — independent polling | Same migration path as habits-agent |
| **tasker-agent** (`enrichment/record_completion.py`, `enrichment/reconcile_completions.py`) | Same pattern | Same migration path |
| **Reconciliation driver** (new component) | Does not exist | Central systemd user timer (~5 min); runs 6-phase cycle per tick; writes conflict-event log; routes unsafe events to WhatsApp router; updates `last_polled_utc` freshness pointer per layer |
| **Two URL bases** (`https://office2.tail0f5f56.ts.net/api/v1` vs `http://100.92.197.90:3456/api/v1`) | Inconsistency across scripts — latent fragility | Normalized to single config point in the reconciliation driver; all scripts read base URL from shared config |

This table describes the architectural direction, not implementation steps. Each component
migration is a separate work item in the follow-on missions.

---

## What This Defers

The following gaps and open questions are explicitly deferred to implementation missions:

1. **Task deletion latency gap (use case b)**: Deletion is not surfaced by `updated_since`.
   Worst-case detection latency is 15 minutes (3-cycle confirmation via `GET /tasks/{id}` →
   404). This exceeds NFR-002's 5-minute ceiling. Accepted as a design exception: deletion
   is infrequent and the 15-minute exposure window carries low risk of incorrect downstream
   behavior. Implementation must verify Vikunja's deletion behavior (hard-delete vs
   soft-delete) and tune the N-cycle confirmation window.

2. **Project-layer polling cost**: At 14 projects, full `GET /projects` per cycle is a single
   lightweight request. If the instance grows to hundreds of projects, this becomes expensive.
   Not a concern at current scale; revisit at 100+ projects.

3. **UC-4 `override_flags` mechanism**: The `manual_override_signal` criterion requires
   Felix's cache to support per-field override markers. This is a new cache schema requirement
   not present in any current JSONL format. Implementation mission must design and build this.

4. **Two URL bases**: Normalization to a single config point is described above as
   architectural direction. The actual migration of per-script `DEFAULT_BASE_URL` constants
   is implementation work.

5. **In-prompt agent callsites**: The escalation and tasker agents issue Vikunja API calls
   in-prompt (not via Python helpers). These are not grep-discoverable from the codebase.
   Their integration with the reconciliation cycle requires reading live AGENTS.md and
   SKILL.md files on office2.

6. **`updated_since` clock-skew handling**: Implementation must validate that `updated_since`
   returns tasks consistently under clock-skew conditions between Felix's system clock and
   Vikunja's write timestamps.

7. **#516 framework**: ADR-0003 references #516 for forward-compat but does not implement
   the framework. If #516 produces a sender contract, the conflict-event log's `schema_version`
   and `event_id` fields are the adoption hooks.

---

## Follow-On Missions

The implementation roadmap is scoped into 2–3 follow-on missions filed as sub-issues under
Epic #507. Back-fill issue numbers below after filing:

- **Mission 1**: Reconciliation driver foundation (polling core + conflict detection + log)
  → [#TBD]
- **Mission 2**: Agent migration (habits + escalation + tasker touchpoints updated to use sync
  cache) → [#TBD] — Depends on Mission 1
- **Mission 3** (if needed): Project-layer and deletion handling → [#TBD] — Depends on
  Mission 1

See [findings.md](<./findings.md>) for the filed issue numbers once available.
