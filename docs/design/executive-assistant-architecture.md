---
title: "Executive Assistant Architecture — Design Brief"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-07-20'
audience: agents_and_humans
---

# Executive Assistant Architecture — Design Brief

**Status:** Draft (captured from the 2026-07-20 design conversation; expect iteration)
**Author:** Kent Gale
**Location:** `docs/design/executive-assistant-architecture.md`
**Related:** Epic [#692](https://github.com/kentonium3/kg-automation/issues/692) (Second Brain Graph Layer) · [`second-brain-graph-layer.md`](second-brain-graph-layer.md) · [`felix-capability-roadmap.md`](felix-capability-roadmap.md) · [`felix-openclaw-boundary.md`](felix-openclaw-boundary.md) · #165 (mail) · #698 (life-coach, deferred) · #679 (delegation broke) · #817 (deploy-integrity)

> **Confidentiality:** ties to #692 material. Internal to `kentonium3/kg-automation` — do not republish externally.

---

## 1. Purpose of this brief

Give Felix a **top-down architectural frame** so future EA (executive-assistant) capabilities are built *onto a named foundation* rather than accreted bottom-up. It captures the organizing model, the layered design, the settled decisions, and the forward primitive set — and it answers the standing question *"when is substrate-hardening enough?"* The brief is a **map, not a spec**; each capability gets its own spec when picked up.

## 2. The organizing frame — a CEO's Executive Assistant

Design Felix as a **CEO's executive assistant**. The EA holds two powers plus a discipline:

- **Gatekeeper** — decides what information and which people reach the CEO. The power comes from *knowing what matters to the CEO both long-term and right now*; that context is what confers decision authority over what the CEO sees.
- **Executor** — expert at marshalling every available tool, skill, and resource to fulfil requests, backed by the authority of the CEO's office.
- **Managing-up** — continuously adapts to the boss's tendencies, preferences, habits, foibles, strengths, and weaknesses.

**The core reframe:** every input from every source is a **decision** the EA must either make or pass up — *handle / surface-to-Kent / defer / drop* — judged by relevance to the CEO's outcomes, goals, projects, and tasks *at that moment*. Those decisions drive what gets surfaced to whom, and what action is required. **Filtering what reaches the CEO, and knowing what to execute personally vs. pass through, is the job.**

## 3. Layered architecture (settled)

```
  INTAKE MODALITIES          →  normalize to a canonical INTENT
  email(#165) · voice(Wispr) · WhatsApp · manual capture · inbound calendar
        │
        ▼
  EA DECISION-ROUTER  (the gatekeeper)  ──────────────  ← reads WORLD-MODEL (§5)
  per intent: handle / surface-to-Kent / defer / drop        + thin principal-model
        │  (for "handle": delegate)
        ▼
  NARROW EXECUTOR AGENTS   tasker · calendar · habits · …
        │
        ▼
  OUTPUTS   alert bus (#701, built) · WhatsApp to Kent
```

- **Email is an *input*, not a peer capability** (Kent's key correction). It generalizes: all intake modalities normalize raw input into intents. This is the **intake→intent normalization** primitive.
- **The EA decision-router is the genuinely net-new design** — it exists in no current doc. Per [Engineering Directive 6](engineering-principles.md), it is a **hybrid**: a deterministic routing table for the clear cases (this sender always surfaces; this shape is always a task) + LLM judgment only for the ambiguous — the same split proven in capture and the deterministic crons.
- The **output** side (alert bus) is already built. The **intake** and **router** sides are the gaps.

## 4. Named-agent fleet today — the shape is ~70% right; the *brain* is missing

The #167 workspace series already produced named narrow agents that map onto the EA model:

| Agent | EA role | State |
|---|---|---|
| **main** | EA / orchestrator ("chief of staff") | Exists but **thin** — no real decision-router (#583 gave it "EA-orchestrator framing") |
| **felix-admin-escalation** | Surfacing / managing-up — *half the gatekeeper* | Exists |
| **felix-admin-capture** | Intake worker (one modality) | Exists |
| **felix-admin-tasker** | Executor — task ops | Exists |
| **felix-admin-calendar** | Executor — scheduling | Exists (feature #635 pending) |
| **felix-admin-habits** | Executor — habit tracking | Exists |

**We have the nouns (named agents); we lack the verbs (reliable routing + delegation).** #679 is the evidence — inbox→calendar delegation broke because the small model wouldn't hand off (see [`felix-openclaw-boundary.md`](felix-openclaw-boundary.md), #675). Gaps:

1. A reliable **decision-router** inside `main`.
2. A reliable **delegation contract** (main → executor) — #679's fix.
3. An **email-intake** worker (#165).
4. A **thin principal-model** (managing-up thresholds) as a first-class artifact — today it is implicit in prompts.

## 5. The keystone: the world-model **is** the Second Brain Graph Layer (#692)

The router is only as good as the context it scores against. That context — the **world-model** — is **already fully designed** in [`second-brain-graph-layer.md`](second-brain-graph-layer.md) (Epic #692; seed #695). It is not a sketch.

**Ontology:** `Purpose → Domain → Outcome → Objective → Project → Task`, plus **Constraint** (a cross-cutting hard-temporal node). **Bi-temporal** — it tracks how priorities and commitments evolve over time ("what were my active goals in March"). Outcomes carry `priority_rank` + target dates. **Structural invariant, already designed:** *every node must connect upward to a Purpose — no floating tasks, no projects without an Objective.* That rule **is** the enforcement mechanism for prioritization (a top-down invariant made executable).

**The reconciliation:** the "second brain" is under-utilized today only because it is flat Markdown — no traversal, no priority-over-time, no task→purpose links. #692 turns it into a traversable bi-temporal graph, and *that graph is the world-model the EA reasons against.* **They were never two separate things.** #692 also **absorbs** two primitives that first looked separate:

- **write-back / compounding** = its bi-temporal fact tracking (the model grows richer through use, like a tenured EA);
- **provenance / decision-ledger** = its "record trade-off decisions durably."

**Privacy:** `~/second-brain/notes/04-Growth/_private/` is never ingested; the #696 privacy gate governs what the knowledge tier absorbs.

## 6. Settled decisions (Kent, 2026-07-20)

1. **WRITE-BACK.** The world-model grows through use (compounds). Already a property of #692's bi-temporal graph — the EA writes context back (people, projects, preferences, decisions) as it operates. *Rationale:* this is what makes gatekeeping improve over time instead of requiring perpetual hand-curation.
2. **FEDERATED, not consolidated.** The stores serve different purposes and stay separate:
   - **Graph (#692)** = world-model: the hierarchy + knowledge tier.
   - **Vikunja** = operational task execution.
   - **Second brain (Obsidian vault)** = knowledge substrate (ingested into the graph).
   - Connected by the epic's **one-way `Vikunja → Graphiti` sync** (open-Q2). *Corroboration:* deleting the Vikunja "Goals" project (#734/#724) was correct — the hierarchy belongs in the graph, not Vikunja.
3. **COACHING DEFERRED.** The life-coach agent (#698) is an **overlay** that needs the outcome/task machinery working first. Defer #698 and the *full* principal-model; the router needs only a **thin** principal-model now.

## 7. Primitive set (forward ∪ backward)

Build-now = demanded by ≥2 capabilities. Single-capability primitives are built *with* that capability; the rest are a watch-list — this filter is what keeps the forward pass from becoming its own hydra.

| Primitive | Status / home |
|---|---|
| **P1 World-model** (Purpose→…→Task, bi-temporal, write-back) | **≡ #692** — designed, awaiting build/seed |
| **P2 Intake → intent normalization** | New; email (#165) is the trigger modality |
| **P3 Delegation / decision-router** | **The net-new design** (this brief §3/§8); #679 is the negative evidence |
| **P4 Identity / consent / scope** | Partial: #715 two-token, #696 privacy gate |
| **P5 Temporal / scheduler** | Fragmented today (heartbeat gate, escalator, crons, calendar); coaching-cadence part defers |
| **P6 Provenance / decision-ledger** | **Absorbed into #692** (durable trade-off records) |
| *Backward infra (mostly guarded already):* | resource-identity **seams** (#811, #748); **deploy-integrity canary** (#817 + #818, the last named gap); **alert bus** (#701, done) |

## 8. The router / orchestration primitive (the forward design work)

The CEO-EA framing **is** the router's spec:

- **Input:** a normalized intent from any modality.
- **Decision:** `handle` / `surface-to-Kent` / `defer` / `drop`, scored against the **world-model** (§5) + the **thin principal-model** (managing-up thresholds: what Kent wants to see vs. what annoys him).
- **On `handle`:** delegate to the right **executor** via a reliable contract (the #679 fix — deterministic hand-off, not a small-model judgment call).
- **On `surface`:** route through the escalation/surfacing path (`felix-admin-escalation`) to Kent.
- **Implementation:** hybrid (Directive 6) — deterministic routing rules first, LLM only for genuinely ambiguous intents. Every decision is a **write-back** episode (§6.1) so the model learns which calls Kent confirms or overrides.

## 9. When is substrate-hardening "enough"?

Kent's worry: the last several days of infra gap-fixing feel like a hydra, with no clear stopping rule. The answer:

- **The hydra is two things.** (a) *Discovery debt* — building observability turns the lights on and surfaces latent defects (#816 was dead 6 weeks until #811's verify ran it). This class is **finite and converging** — watch *new-findings-per-fix* trend toward zero. (b) A few *structural patterns* — scattered resource identity (seams), deploy/source divergence (#816/#817), monitoring blind spots (#818) — most of which **now have executable guards.**
- **Why docs didn't prevent bottom-up drift:** docs capture *state*; they cannot *enforce invariants*. A doc saying "openclaw lives at X" can't stop 9 files hardcoding X. The fix is **executable invariants** — seams + guard tests + canaries + buses. The alert bus is the model; the #811 guard, the vikunja SC-001 gate, and the no-bare-astimezone guard are the pattern working. Target posture: **bottom-up construction with top-down invariants**, checked at spec/merge/CI gates.
- **The verdict: you are basically there.**
  - **Substrate = the floor** — nearly laid (#817/#818 are the last named gaps).
  - **#692 = the foundation** — designed and waiting; elevate it from "P2 someday" to foundational.
  - **The router (§8) = the net-new forward work.**
  - The next move is *forward*, not more hydra.

## 10. Sequencing (proposed)

1. **Seed the world-model** — #695 (Kent-authored Purposes/Domains/Outcomes) + stand up the #692 graph substrate.
2. **Design + build the decision-router** (§8) on top, grounded in this brief.
3. **Wire email intake** (#165) as the first intake modality feeding the router.
4. **Thin principal-model** + `Vikunja → Graphiti` sync as connective tissue.
5. **Defer:** coaching (#698), full vault ingest, full principal-model.

Optionally bank the independent, low-risk substrate wins first (autopilot queue: #808 → #805 → #807 → #819).

## 11. Open questions

- Router as a capability *inside* `main`, or a dedicated inspectable **router agent**? (Epic #692 open-Q4 asks the analogous question for the life-coach agent.)
- Principal-model: explicit config, learned from the journal, or both — and where does it live (graph node vs. separate artifact)?
- Deterministic-vs-LLM boundary in the router: what share of triage is rule-expressible before LLM fallback?
- Sync semantics: is one-way `Vikunja → Graphiti` sufficient, or does task *completion/state* need to flow back to Outcomes?

---

*Captured from a live design conversation; see project memory `project_ea_architecture_synthesis.md` for the same synthesis in brief.*
