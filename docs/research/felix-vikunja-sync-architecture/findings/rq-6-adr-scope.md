---
rq_id: "RQ-6"
title: "ADR-0003 scope — supersede vs extend ADR-0002"
depends_on: ["RQ-1", "RQ-2", "RQ-3", "RQ-4", "RQ-5"]
wp: "WP03"
tags: [507, 508]
---

# RQ-6 — ADR-0003 Scope Decision

**Purpose**: Determine whether ADR-0003 supersedes ADR-0002 in full or extends specific
decisions, with rationale sourced to specific ADR-0002 decisions (SC-001).

**Method**: Enumerate each ADR-0002 architectural decision (Q1–Q10); classify the proposed
sync architecture's stance as `override` / `extend` / `preserve`; apply the plan.md § RQ-6
tally rule.

---

## 1. ADR-0002 Decision Enumeration and Classification

| Decision | Topic | Stance | Rationale |
|---|---|---|---|
| Q1 — Schedule expression | Native Vikunja recurrence; MWF as N tasks | **preserve** | Sync architecture does not change how schedules are expressed. Native recurrence is orthogonal to the reconciliation layer. |
| Q2 — Completion signal | `done=true` canonical; JSONL history; comment mirror | **preserve** | Sync architecture treats `done` as Vikunja-canonical (C-002: Vikunja wins), reinforcing Q2's hierarchy rather than changing it. |
| Q3 — History preservation | Three-write transaction (`done` + comment + JSONL) | **extend** | Sync adds a fourth persistent surface: the conflict-event log (`sync-conflict-history.jsonl`). The reconciler gains a new responsibility: reading and writing the conflict-event log during the `emit` and `update` phases. The three-write transaction itself is unchanged. |
| Q4 — Webhooks vs cron polling | Cron polling; webhooks deferred | **extend** | Sync architecture formalizes polling into a structured 6-phase reconciliation cycle (fetch → diff → classify → emit → update → complete) with explicit per-layer cadence, freshness pointer management, and `updated_since`-based delta detection. ADR-0002 Q4 was a directional choice; ADR-0003 operationalizes it into an architecture. The re-evaluation criteria for webhooks (sub-day reactivity) remain unchanged and are preserved as deferred scope. |
| Q5 — One parser or N | JSONL pattern extended to all agents; shared `state_log.py` | **extend** | Sync adds a new domain (`sync`) to the JSONL pattern and `state_log.py`. The existing per-domain files (`habits-history.jsonl`, `escalation-history.jsonl`, `enrichment-history.jsonl`) are unchanged. |
| Q6 — Identity attribution | `felix-bot` Vikunja user; API token rotation | **preserve** | Unchanged. The sync architecture uses the same `felix-bot` identity established in ADR-0002 Q6 (mission `felix-bot-vikunja-provisioning-01KRT3N4`). |
| Q7 — Parallel-write reconciliation policy | Silent backfill via per-script reconcilers; `source: vikunja-ui` | **override** | This is the one decision the sync architecture substantively replaces. ADR-0002 Q7 defined per-domain reconcilers that each implement ad-hoc backfill logic for their domain. The sync architecture centralizes this into one reconciliation cycle driver that covers all touchpoints across all three layers. The unsafe-class criteria (UC-1..UC-4) and conflict-event log add new semantics not present in ADR-0002's silent-backfill model. The per-domain `source: vikunja-ui` backfill semantics are preserved inside the `update` phase of the new cycle, but the coordination model is replaced. |
| Q8 — Frequency lexicon | Dissolved under Q1 | **preserve** | Unchanged. |
| Q9 — Filter scope | Code-canonical filters | **preserve** | Unchanged. The sync architecture does not change how filters are expressed in scripts. |
| Q10 — Failure-mode hardening | Domain-specific failure policy (habits soft-fail, escalation hard-fail, tasker soft-fail) | **extend** | Sync adds conflict classification and cross-domain routing on top of per-domain failure modes. The per-domain policies remain intact; the sync layer adds a new failure surface (conflict events that exceed the WhatsApp cap are logged but not routed). |

---

## 2. Tally

| Stance | Count | Decisions |
|---|---|---|
| preserve | 5 | Q1, Q2, Q6, Q8, Q9 |
| extend | 4 | Q3, Q4, Q5, Q10 |
| override | 1 | Q7 |

**Tally rule application** (plan.md § RQ-6): `>50% override → supersede; mostly preserve+extend → extend; split → document both, pick one with rationale.`

**Result**: 9/10 decisions are preserve or extend; only 1/10 is override. Clearly meets the "mostly preserve+extend" criterion.

---

## 3. Verdict: ADR-0003 **extends** ADR-0002

**ADR-0003 extends ADR-0002.** It does not supersede it.

### Rationale

ADR-0002 made correct foundational decisions. The data model (Q2), identity attribution (Q6), schedule encoding (Q1), JSONL history (Q3/Q5), and filter strategy (Q9) all hold without change. The sync architecture is an *additional layer* built on top of ADR-0002's foundation, not a replacement of it.

The single override (Q7) is a *structural subsuming*, not a contradiction. ADR-0002 Q7's per-domain reconcilers remain in place as domain-specific write logic; the sync architecture adds a coordination layer that routes conflict events consistently across all domains. The Q7 "silent backfill" semantics are preserved for `auto_resolved` conflicts; the new unsafe-class criteria add a signal where ADR-0002 was silent.

The most significant extension is Q4: ADR-0002 said "polling, not webhooks" without defining what polling means structurally. ADR-0003 defines the reconciliation cycle that makes that decision operational — per-layer cadence, freshness pointers, `updated_since` delta polling, 6 named phases.

### Consequences for ADR-0003 front matter

- Declare: `extends: 0002-felix-vikunja-task-model`
- Name the specific decisions extended: Q3 (history), Q4 (polling), Q5 (JSONL pattern), Q7 (reconciliation policy), Q10 (failure modes)
- Status: `Draft` until operator accepts on #508

---

## 4. Stop Conditions (not triggered)

- "If no new architectural decisions are required beyond ADR-0002, surface to operator (ADR-0003 unnecessary)." — **Not triggered.** ADR-0003 adds substantial new architecture: the 6-phase reconciliation cycle, three sync layers, unsafe-class criteria, conflict-event log, and WhatsApp router integration.
- "If ADR-0002 tension requires operator input." — **Not triggered.** The extend verdict is unambiguous; no operator decision required.
