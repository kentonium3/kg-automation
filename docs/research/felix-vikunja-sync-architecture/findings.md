---
title: "Felix ↔ Vikunja Sync Architecture Research — Findings"
status: operator-review-pending
research_mission: felix-vikunja-sync-architecture-research-01KT7Q15
source_issue: "508"
parent_epic: "507"
last_updated: "2026-06-04"
tags: [507, 508, 516]
---

# Felix ↔ Vikunja Sync Architecture — Findings

This is the entry point for the research deliverables of mission [`felix-vikunja-sync-architecture-research-01KT7Q15`](https://github.com/kentonium3/kg-automation/issues/508). Each section below summarises one research question; follow the link in each section to the per-RQ file for full evidence.

## Summary

Felix should sync with Vikunja using a **polling-only, three-layer (status / task / project) reconciliation cycle** on a 3–5 minute cadence. The architecture **extends** [ADR-0002](<../../design/architecture/adr/0002-felix-vikunja-task-model.md>) (preserves the `done=true` model, `felix-bot` identity, and JSONL history pattern) and adds a centralized reconciliation driver, a conflict-event log, and WhatsApp routing for unsafe conflicts. All seven Epic [#507](https://github.com/kentonium3/kg-automation/issues/507) operator use cases are covered within a 5-minute ceiling, with one documented gap: task deletion is detected within 15 minutes (3-cycle confirmation), because Vikunja's `updated_since` parameter does not surface deletions. The conflict-event log shape is forward-compatible with each of [#516](https://github.com/kentonium3/kg-automation/issues/516)'s three possible framework outcomes.

For the operator-facing architectural proposal, read [`recommendation.md`](<./recommendation.md>). For the canonical record, read [`ADR-0003`](<../../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>).

## Sub-Question Findings

### RQ-1 — Vikunja API surface

**Question**: What capabilities does the live Vikunja API expose for read access (REST CRUD, batch ops, filtering, subscribe), and which fields are suitable as stable identifiers for sync re-identification across reconciliation cycles?

**Answer**: Vikunja v0.24.6 at `https://office2.tail0f5f56.ts.net/api/v1` exposes a REST surface with per-task `GET /tasks/{id}` + per-project `GET /projects` + a critical `GET /tasks/all?updated_since=<ts>` incremental-delta endpoint. Batch read is unavailable; the G6/G7 server-side filter rejection class memorialised in `reference_vikunja_filter_gotchas` is real and forces client-side filtering. The integer `id` field is globally unique and stable across edits, suitable as the canonical sync identifier. Webhooks are available but unconfigured — confirms the operator's polling-only decision (C-001).

[`findings/rq-1-vikunja-api.md`](<./findings/rq-1-vikunja-api.md>) · [`findings/probe-transcripts.md`](<./findings/probe-transcripts.md>)

### RQ-2 — Felix touchpoint inventory

**Question**: Which Felix code callsites currently read from or write to Vikunja, and what state-freshness assumptions does each make?

**Answer**: Exhaustive grep enumerated **18 touchpoints** across 23 files (TP-01 through TP-18, with one explicit exclusion for `scripts/escalation/hard_fail.py` — comment-only URL in docstring, no HTTP client). All write paths use Python `urllib.request`; the sweeper, escalation, capture, and tasker domains all touch Vikunja directly. Two findings of note: (a) **two URL bases are in concurrent use** — Tailscale HTTPS (`office2.tail0f5f56.ts.net`) and direct IP HTTP (`192.168.x.x`) — a latent fragility worth surfacing; (b) **no touchpoint implements a freshness pointer today**, so the sync architecture must add one as a first-class component. In-prompt agent callsites (escalation/tasker) are not grep-discoverable from the Mac-side codebase; the inventory is exhaustive only for static call paths.

[`findings/rq-2-touchpoints.md`](<./findings/rq-2-touchpoints.md>)

### RQ-3 — Conflict policy + log shape

**Question**: When Felix's computed state diverges from Vikunja's actual state, how is the conflict detected, classified, logged, and surfaced — and what log shape is forward-compatible with #516's three possible framework outcomes?

**Answer**: Conflict detection runs as the `diff` phase of a 6-phase reconciliation cycle. Four unsafe-class criteria — `kent_edit_after_felix_write` (UC-1), `operator_authored_field` (UC-2), `downstream_behavior_depends` (UC-3), `manual_override_signal` (UC-4) — partition each conflict into `auto_resolved` or `unsafe_to_auto_resolve`; each criterion is testable from log fields alone (no out-of-band lookup) with worked examples drawn from RQ-2 touchpoints. The proposed WhatsApp ping format is a structured three-line shape (class + entity + diff summary). Volume math: 15 tasks × 3 writes/day × 5% Kent-edit probability × 75% unsafe fraction ≈ 1.69/day raw → three guards (24-hour dedup, 30-minute post-write suppression, hard daily cap) reduce volume to ≤ 1/day under steady state (NFR-003 passes).

The 15-field conflict-event schema uses a deterministic `event_id = sha256(layer | vikunja_entity_id | diff_field | ts_observed_utc | canonical(value))[:16]` for idempotency, and the forward-compat analysis confirms compatibility with each of #516's outcomes: under outcome (a) the load-bearing field is `schema_version`; under (b) it is `event_id`; under (c) it is `router_route_set`.

[`findings/rq-3-conflict-policy.md`](<./findings/rq-3-conflict-policy.md>) · [`findings/conflict-event-log.sketch.md`](<./findings/conflict-event-log.sketch.md>)

### RQ-4 — Use-case → layer mapping

**Question**: Map each of Epic #507's seven operator use cases (a–g) to the proposed three-layer model (`status` / `task` / `project`), with detection mechanism, Felix-side response, and worst-case convergence latency under polling.

**Answer**: All seven use cases mapped. **Six of seven pass NFR-002 (≤ 5-min worst case)** at a 3–5 minute cycle cadence. Use case (b) **task deletion is a documented gap at 15 minutes** (3-cycle confirmation required because `updated_since` does not surface deleted tasks — instead, a task is presumed-deleted only after it fails to appear in three consecutive `/tasks/all` responses). The gap is surfaced (not silently shrunk) and offered to follow-on implementation missions as a recommendation tension with three resolution options (more frequent project-layer poll, soft-delete polling endpoint feature-request upstream, or accepting the 15-min latency as a project-domain trade-off). Project-layer polling uses a full `GET /projects` per cycle (Vikunja's `updated_since` is task-scoped); the project inventory is small enough (~14 projects observed) that this is not a cost concern.

[`findings/rq-4-use-case-mapping.md`](<./findings/rq-4-use-case-mapping.md>)

### RQ-5 — Existing-pattern fit

**Question**: For each existing Felix pattern (signal-driven monitoring pipeline #59/#490, felix-doc-auditor driver, `schedule_loader.py` reconciliation, `habits-history.jsonl` ledger), assess fit for the sync architecture.

**Answer**: **All four patterns get an `extend` verdict** — no new infrastructure primitives are required. The reconciliation cycle maps directly onto the signal-pipeline tick structure, the felix-doc-auditor driver pattern (scripts-first Python driver + last-tick pointer + hourly user timer) is the right shape for the reconciliation driver, the `schedule_loader.py` reconciliation flag generalises to per-layer cycle state, and the `habits-history.jsonl` ledger format + `scripts/common/state_log.py` is the correct base for the conflict-event log — with extensions for `event_id`, `conflict_class`, `schema_version`, and state snapshots. The architecture is an additive layer on Felix's existing observability + driver patterns, not a replacement.

[`findings/rq-5-pattern-fit.md`](<./findings/rq-5-pattern-fit.md>)

### RQ-6 — ADR-0003 scope (supersede vs extend ADR-0002)

**Question**: Does ADR-0003 supersede ADR-0002 entirely or extend it?

**Answer**: **ADR-0003 extends ADR-0002.** Per-decision tally across ADR-0002's Q1–Q10: 5 preserve (Q1, Q2, Q6, Q8, Q9), 4 extend (Q3, Q4, Q5, Q10), 1 override (Q7 — reconciliation policy, where the centralized cycle structurally subsumes ADR-0002's per-domain reconcilers without contradicting their domain-specific write semantics). Per plan.md § RQ-6's tally rule, `mostly preserve + extend → extend`. The override on Q7 is recorded as a structural subsuming, not a contradiction (the per-domain `source: vikunja-ui` backfill semantics from ADR-0002 are preserved inside the new cycle's `update` phase).

[`findings/rq-6-adr-scope.md`](<./findings/rq-6-adr-scope.md>)

## Cross-References

- [`recommendation.md`](<./recommendation.md>) — operator-readable architectural proposal (start here for the bottom line).
- [`ADR-0003`](<../../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>) — canonical record; extends [ADR-0002](<../../design/architecture/adr/0002-felix-vikunja-task-model.md>).
- [`findings/conflict-event-log.sketch.md`](<./findings/conflict-event-log.sketch.md>) — proposed log schema (FR-010 / SC-006).
- Source issue: [#508](https://github.com/kentonium3/kg-automation/issues/508).
- Parent epic: [#507](https://github.com/kentonium3/kg-automation/issues/507).
- Cross-referenced spike: [#516](https://github.com/kentonium3/kg-automation/issues/516).

## Evidence Trail

- `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/source-register.csv` — 53+ sources consulted (API endpoints, code paths, memory entries, ADRs, issues, docs).
- `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/evidence-log.csv` — 45+ load-bearing findings with confidence levels and citations.
- `findings/probe-transcripts.md` — 12 raw HTTP probe transcripts for reproducibility.

Every load-bearing claim in this synthesis cites the per-RQ file, which in turn cites a row in evidence-log.csv (NFR-001). API claims are tagged `observed (probe transcript)` or `documented (URL)` per NFR-006.

## Mission Status

| Item | State |
|---|---|
| Six per-RQ findings files | ✅ Delivered |
| `findings.md` synthesis index | ✅ Delivered (this file) |
| `recommendation.md` | ✅ Delivered |
| Draft `ADR-0003` | ✅ Delivered |
| Conflict-event log shape sketch | ✅ Delivered |
| Follow-on implementation missions filed as sub-issues under #507 | 🕐 Filing in progress — see footer |
| Operator review on #508 (SC-007) | ⏳ Pending operator action |

### Follow-on Implementation Missions (filed under Epic #507)

Three follow-on missions are scoped from the recommendation, in dependency order:

1. **Mission A — [Feature: Felix-Vikunja sync reconciliation driver foundation (#518)](https://github.com/kentonium3/kg-automation/issues/518)**. Build the central reconciliation driver (scripts-first Python + systemd user timer) that runs the 6-phase cycle for the status + task layers. Implements the conflict-event log JSONL and the WhatsApp-router integration for unsafe-class conflicts. Does NOT include project-layer reconciliation or migration of existing touchpoints. No predecessors.

2. **Mission B — [Feature: Migrate Felix touchpoints to sync cache (#519)](https://github.com/kentonium3/kg-automation/issues/519)**. Migrate the existing habits/escalation/tasker touchpoints (TP-01..TP-15E, TP-16A-E, TP-18) from direct Vikunja API calls to consulting the sync cache where appropriate. Removes the duplicate-poll pattern (each script polling Vikunja independently). Depends on #518.

3. **Mission C — [Feature: Project-layer sync + deletion handling + URL normalization (#520)](https://github.com/kentonium3/kg-automation/issues/520)**. Adds project-layer polling, the 3-cycle deletion-confirmation algorithm for use case (b), and resolves the two-URL-base fragility surfaced in RQ-2 (Tailscale HTTPS vs direct IP HTTP). Depends on #518.

All three filed under `kg-felix-bot` identity, linked as sub-issues of [Epic #507](https://github.com/kentonium3/kg-automation/issues/507) via the GraphQL `addSubIssue` mutation, added to the Felix Roadmap project, labeled `area/task-intel`, `P1-feature`, `spec: brief` (operator formalizes to `spec: ready` before `/spec-kitty.specify` runs on them per C-008).

## Next Step (Operator Action)

**Operator review pending on issue [#508](https://github.com/kentonium3/kg-automation/issues/508).** Per spec.md SC-007, the operator records `accept` or `reject + feedback` as a comment on #508 with the mission merge commit hash. This research mission's `done` state is gated by that comment, NOT by the spec-kitty merge of these artifacts to `main`.

- **If accepted**: the three follow-on missions filed under #507 are cleared to start. They need their `spec: brief` label flipped to `spec: ready` before `/spec-kitty.specify` runs on them.
- **If rejected**: this research re-enters work with the feedback as input.
