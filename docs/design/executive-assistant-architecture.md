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
**Related:** Epic [#692](https://github.com/kentonium3/kg-automation/issues/692) (Second Brain Graph Layer) · [`second-brain-graph-layer.md`](second-brain-graph-layer.md) · [`felix-capability-roadmap.md`](felix-capability-roadmap.md) · [`felix-openclaw-boundary.md`](felix-openclaw-boundary.md) · [`engineering-principles.md`](engineering-principles.md) · #165 (mail) · #698 (life-coach, deferred) · #679 (delegation broke) · #817 (deploy-integrity)

> **Confidentiality:** ties to #692 material. Internal to `kentonium3/kg-automation` — do not republish externally.

---

## 1. Purpose of this brief

Give Felix a **top-down architectural frame** so future EA (executive-assistant) capabilities are built *onto a named foundation* rather than accreted bottom-up. It captures the organizing model, the differentiation thesis, the settled decisions, and the forward primitive set — and it answers the standing question *"when is substrate-hardening enough?"* The brief is a **map, not a spec**; each capability gets its own spec when picked up.

## 2. The organizing frame — a CEO's Executive Assistant

Design Felix as a **CEO's executive assistant**. The EA holds two powers plus a discipline:

- **Gatekeeper** — decides what information and which people reach the CEO. The power comes from *knowing what matters to the CEO both long-term and right now*; that context is what confers decision authority over what the CEO sees.
- **Executor** — expert at marshalling every available tool, skill, and resource to fulfil requests, backed by the authority of the CEO's office.
- **Managing-up** — continuously adapts to the boss's tendencies, preferences, habits, foibles, strengths, weaknesses.

**The core reframe:** every input from every source is a **decision** the EA must either make or pass up — *handle / surface-to-Kent / defer / drop* — judged by relevance to the CEO's outcomes and goals, *and consistency with the CEO's principles*, at that moment. Those decisions drive what gets surfaced to whom, and what action is required. **Filtering what reaches the CEO, and knowing what to execute personally vs. pass through, is the job.**

## 3. Differentiation — what makes this unique vs. OpenClaw

OpenClaw is a **runtime / orchestration engine**: agents that run, use tools/skills, talk to channels (WhatsApp/voice), schedule (cron), delegate, and hold session memory — plus a broad connector ecosystem (CRM, email, calendar, Canva, site builders). People use it to orchestrate business tools by voice ("build a landing page," "compose this email and read it back"). That breadth is real; **we consume it, we do not out-connector it.**

Felix is an **application on that runtime**, and its moat is four mutually-reinforcing advantages OpenClaw users conspicuously lack:

1. **Structure** — an organized, traversable, prioritized world-model (§6) vs. flat, unorganized second brains.
2. **Judgment / gatekeeping** — *proactive* relevance-filtering ("here's what matters; I handled the rest") vs. *reactive* command-execution ("do X").
3. **Reliability** — the observability / monitoring / alerting substrate almost no user builds (the "substrate hardening" work is **moat #3**, not overhead).
4. **Economics** — deterministic-first (scripts do the mechanical work, LLM only judges — [Directive 6](engineering-principles.md)) vs. LLM-for-everything. Anthropic's move to paid API access turns this from a preference into a **wedge**: rivals' cost curves break as usage scales; ours doesn't.

**The sharpest point — structure is what makes "represent the whole life" pay off.** Users dump everything into flat second brains (meetings, recordings, walking rambles, journals, health, financials) believing *more life = better service*. That is backwards *without* structure — more data becomes more noise, priorities blur, nothing connects. The Purpose→…→Task backbone plus the "every node connects upward to a Purpose" invariant is exactly what turns a whole life from noise into navigable signal. Their thesis is right, but **only on our architecture.** (We still capture freely: raw content enters as **episodes**; structure is *extracted and linked over time*, so "everything in" and "structured" don't conflict — see §6.)

## 4. Layered architecture

```
  INTAKE MODALITIES          →  normalize to a canonical INTENT
  email(#165) · voice(Wispr) · WhatsApp · manual capture · inbound calendar
        │
        ▼
  EA DECISION-ROUTER  (the gatekeeper)  ─────────────  ← reads WORLD-MODEL (§6):
  per intent: handle / surface / defer / drop              Purposes/Outcomes (direction)
        │  (for "handle": delegate)                        + Principles (constraint)
        ▼
  NARROW EXECUTOR AGENTS   tasker · calendar · habits · …  (via pluggable adapters, §10)
        │
        ▼
  OUTPUTS   alert bus (#701, built) · WhatsApp to Kent
```

- **Email is an *input*, not a peer capability** (all intake modalities normalize raw input into intents). This is the **intake→intent normalization** primitive.
- **The EA decision-router is the genuinely net-new design** — it exists in no current doc. Per [Directive 6](engineering-principles.md) it is **hybrid**: a deterministic routing table for the clear cases + LLM judgment only for the ambiguous. The **output** side (alert bus) is already built; **intake** and **router** are the gaps.

## 5. Named-agent fleet today — the shape is ~70% right; the *brain* is missing

The #167 workspace series already produced named narrow agents that map onto the EA model:

| Agent | EA role | State |
|---|---|---|
| **main** | EA / orchestrator ("chief of staff") | Exists but **thin** — no real decision-router (#583 gave it "EA-orchestrator framing") |
| **felix-admin-escalation** | Surfacing / managing-up — *half the gatekeeper* | Exists |
| **felix-admin-capture** | Intake worker (one modality) | Exists |
| **felix-admin-tasker** | Executor — task ops | Exists |
| **felix-admin-calendar** | Executor — scheduling | Exists (feature #635 pending) |
| **felix-admin-habits** | Executor — habit tracking | Exists |

**We have the nouns (named agents); we lack the verbs (reliable routing + delegation).** #679 is the evidence — inbox→calendar delegation broke because the small model wouldn't hand off (see [`felix-openclaw-boundary.md`](felix-openclaw-boundary.md), #675). Gaps: (1) a reliable **decision-router** inside `main`; (2) a reliable **delegation contract** (likely "use OpenClaw's delegation correctly," not build our own); (3) an **email-intake** worker (#165); (4) a **principal-model** — see §6.

## 6. The keystone: the world-model — Purpose/Principle backbone ≡ the Graph Layer (#692)

The router is only as good as the context it scores against. That context — the **world-model** — is largely designed already in [`second-brain-graph-layer.md`](second-brain-graph-layer.md) (Epic #692; seed #695), with **one first-class addition below (Principles)**.

**Goal hierarchy (direction):** `Purpose → Domain → Outcome → Objective → Project → Task`, plus **Constraint** (a cross-cutting hard-temporal node). **Bi-temporal** — tracks how priorities/commitments evolve over time. Outcomes carry `priority_rank` + target dates. **Structural invariant:** *every node must connect upward to a Purpose — no floating tasks.* That rule is the enforcement mechanism for prioritization (a top-down invariant made executable).

**Principles axis (constraint) — now first-class (Kent, 2026-07-20).** A **Principle** is a distinct, cross-cutting node type at the *definitional* tier (slow-changing, foundational, like Purpose). Where **Purposes/Outcomes *direct*** decisions (what/why you pursue), **Principles *constrain*** them — your values, standards, and non-negotiables (how you decide; what the boss will or won't accept). Many-to-many: a Principle may attach to specific Purposes or apply globally. Principles are **seeded explicitly** (a #695-style Kent-authored content exercise, alongside Purposes/Outcomes) and are stable. *Now folded into the #692 ontology — see [`second-brain-graph-layer.md`](second-brain-graph-layer.md) (Guiding Principle 6, the PRINCIPLE tier, the `Principle` entity model, and the `SCOPED_TO`/`GOVERNED_BY`/`VIOLATES` edges).*

- **The principal-model = Principles (declared, explicit) + tendencies (learned, observed via write-back).** Principles are its stable, authored half; tendencies compound over time.
- Principles are the **most non-duplicable element in the whole system** — the deepest moat.

**Reconciliation:** the "second brain" is under-utilized today only because it is flat Markdown — no traversal, no priority-over-time, no task→purpose links. #692 turns it into a traversable bi-temporal graph, and *that graph is the world-model the EA reasons against.* They were never two separate things. #692 also **absorbs** two primitives that first looked separate: **write-back/compounding** (its bi-temporal fact tracking) and **provenance/decision-ledger** (its durable trade-off records). **Privacy:** `~/second-brain/notes/04-Growth/_private/` is never ingested; the #696 gate governs what the knowledge tier absorbs — load-bearing as sensitive life-data (health, financials) flows in.

## 7. Settled decisions (Kent, 2026-07-20)

1. **WRITE-BACK.** The world-model grows through use (compounds) — a property of #692's bi-temporal graph. *Rationale:* gatekeeping improves over time instead of requiring perpetual hand-curation.
2. **FEDERATED, not consolidated.** Graph (#692) = world-model (hierarchy + knowledge + Principles); **Vikunja = operational task execution**; the Obsidian vault = knowledge substrate ingested into the graph. Connected by one-way **Vikunja → Graphiti** sync (epic open-Q2). *Corroboration:* deleting the Vikunja "Goals" project (#734/#724) was correct — hierarchy belongs in the graph.
3. **PRINCIPLES ARE FIRST-CLASS** (§6) — a distinct axis constraining decisions, and the explicit half of the principal-model.
4. **COACHING DEFERRED.** The life-coach agent (#698) is an *overlay* that needs the outcome/task/principle machinery working first. Defer #698 and the *learned* half of the principal-model; the router needs only the **declared Principles + a thin tendencies model** now.

## 8. Primitive set (forward ∪ backward)

Build-now = demanded by ≥2 capabilities. Single-capability primitives are built *with* that capability; the rest are a watch-list — this filter keeps the forward pass from becoming its own hydra.

| Primitive | Status / home |
|---|---|
| **P1 World-model** (Purpose→…→Task + **Principles**, bi-temporal, write-back) | **≡ #692** (+ the Principle refinement) — designed, awaiting build/seed |
| **P2 Intake → intent normalization** | New; email (#165) is the trigger modality |
| **P3 Delegation / decision-router** | **The net-new design** (§4/§9); #679 is the negative evidence |
| **P4 Identity / consent / scope** | Partial: #715 two-token, #696 privacy gate |
| **P5 Temporal / scheduler** | Fragmented today (heartbeat gate, escalator, crons, calendar); coaching-cadence part defers |
| **P6 Provenance / decision-ledger** | **Absorbed into #692** (durable trade-off records) |
| *Backward infra (mostly guarded already):* | resource-identity **seams** (#811, #748); **deploy-integrity canary** (#817 + #818, the last named gap); **alert bus** (#701, done) |

## 9. The decision-router (the forward design work)

The CEO-EA framing **is** the router's spec:

- **Input:** a normalized intent from any modality.
- **Decision:** `handle` / `surface-to-Kent` / `defer` / `drop`, from a **two-part judgment** — **direction** (does this advance a Purpose/Outcome, and at what priority rank?) × **constraint** (does this respect Kent's Principles?). A high-value action that violates a Principle is *not* auto-handled — it surfaces.
- **On `handle`:** delegate to the right **executor** via a reliable contract (the #679 fix), through the adapter boundary (§10).
- **On `surface`:** route through `felix-admin-escalation` to Kent.
- **Implementation:** hybrid (Directive 6) — deterministic rules first, LLM only for ambiguous intents. Every decision is a **write-back** episode so the model learns which calls Kent confirms or overrides (compounding the *tendencies* half of the principal-model).

## 10. Extensibility — ports-and-adapters (someday, but design the boundary now)

Long-term framing (not a near-term goal): Felix as an **opinionated OpenClaw add-on** that could work over a *choice* of email / calendar / task backends. This is **ports-and-adapters (hexagonal) architecture**, and the key realization is that **the plugin boundary *is* the OpenClaw/Felix boundary:**

- **Core (Felix, system-agnostic):** the world-model + reasoning + the Purpose/Principle/Outcome/Project/Task logic. Never leaves Felix.
- **Ports:** the contracts — "what does the core need from *a* task system / calendar / mailbox?"
- **Adapters (pluggable):** Vikunja / Todoist / Asana; Google Calendar / Outlook; Gmail / Fastmail. OpenClaw's connectors *are* adapters.

**Value even with zero product intent:** clean separation of Felix-judgment from tool-specifics (mock the adapter → testable), and insulation from tool churn (swap Vikunja without touching reasoning). **Discipline:** *design the ports now, build exactly one adapter each (Vikunja, Google), defer additional adapters* — the same cross-cutting-and-near-term filter as everywhere else.

## 11. When is substrate-hardening "enough"?

- **The "hydra" is two things.** (a) *Discovery debt* — building observability turns the lights on (#816 was dead 6 weeks until #811's verify ran it). **Finite and converging** — watch *new-findings-per-fix* trend toward zero. (b) A few *structural patterns* (seams, deploy/source divergence, monitoring blind spots) — **most now have executable guards.**
- **Why docs didn't prevent bottom-up drift:** docs capture *state*; they cannot *enforce invariants*. The fix is **executable invariants** — seams + guard tests + canaries + buses (the alert bus is the model). Target posture: **bottom-up construction with top-down invariants**, checked at spec/merge/CI gates.
- **Verdict: basically there.** Substrate = the *floor* (nearly laid; #817/#818 are the last named gaps). #692 = the *foundation* (designed and waiting — elevate from "P2 someday" to foundational). The **router (§9) = the net-new forward work.** The next move is *forward*, not more hydra. And note: the observability substrate is **moat #3** (§3), not sunk cost.

## 12. Sequencing (proposed)

1. **Seed the world-model** — #695 (Kent-authored **Purposes / Principles / Domains / Outcomes**) + stand up the #692 graph substrate (add the Principle node type).
2. **Design + build the decision-router** (§9) on top, grounded in this brief.
3. **Wire email intake** (#165) as the first intake modality feeding the router.
4. **Thin principal-model** (declared Principles + light tendencies) + `Vikunja → Graphiti` sync as connective tissue.
5. **Defer:** coaching (#698), full vault ingest, learned-tendencies model, additional adapters.

Optionally bank the independent, low-risk substrate wins first (autopilot queue: #808 → #805 → #807 → #819).

## 13. Open questions

- **Autonomy boundary** — proposed default (from Kent's "compose the email and read it back before sending"): **act-with-preview for outbound / irreversible; autonomous for reversible internal actions.** Confirm as the handle-vs-surface rule?
- **Router home** — a capability *inside* `main`, or a dedicated inspectable **router agent**? (Cf. epic #692 open-Q4 for the life-coach agent.)
- **Deterministic-vs-LLM share** in the router — what fraction of triage is rule-expressible before LLM fallback? (Shapes moat #4 economics + reliability.)
- **The "intent" contract** — the normalized shape passed intake→router is the interface everything hinges on.
- **Voice** — near-path intake modality (Wispr is already in the capture path), or later?
- **Sync semantics** — is one-way `Vikunja → Graphiti` enough, or does task completion/state flow back to Outcomes?

---

*Captured from a live design conversation; see project memory `project_ea_architecture_synthesis.md` for the same synthesis in brief.*
