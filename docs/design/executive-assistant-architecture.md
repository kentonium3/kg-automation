---
title: "Executive Assistant Architecture — Design Brief"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-07-20'
audience: agents_and_humans
---

# Executive Assistant Architecture — Design Brief

**Status:** Draft (captured from the 2026-07-20 design conversations; expect iteration)
**Author:** Kent Gale
**Location:** `docs/design/executive-assistant-architecture.md`
**Tracked by:** Theme [#366](https://github.com/kentonium3/kg-automation/issues/366) (Felix as life-steering substrate — this brief is its architecture doc) · Epic [#820](https://github.com/kentonium3/kg-automation/issues/820) (the net-new decision-router — §7/§10 forward work)
**Related:** Epic [#692](https://github.com/kentonium3/kg-automation/issues/692) (Second Brain Graph Layer / world-model) · [`second-brain-graph-layer.md`](second-brain-graph-layer.md) · [`felix-capability-roadmap.md`](felix-capability-roadmap.md) · [`felix-openclaw-boundary.md`](felix-openclaw-boundary.md) · [`engineering-principles.md`](engineering-principles.md) · #271 (mirror/back-chaining behavior) · #165 (mail intake) · #164 (calendar executor) · #698 (life-coach, deferred) · #679 (delegation broke) · #643 (doctrine-substrate parallel) · #817 (deploy-integrity)

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

**The sharpest point — structure is what makes "represent the whole life" pay off.** Users dump everything into flat second brains (meetings, recordings, walking rambles, journals, health, financials) believing *more life = better service*. That is backwards *without* structure — more data becomes more noise, priorities blur, nothing connects. The Purpose→…→Task backbone plus the "every node connects upward to a Purpose" invariant is exactly what turns a whole life from noise into navigable signal. Their thesis is right, but **only on our architecture.** (We still capture freely: raw content enters as **episodes**; structure is *extracted and linked over time* across the membrane, §6 — so "everything in" and "structured" don't conflict.)

## 4. Layered architecture

```
  INTAKE MODALITIES          →  normalize to a canonical INTENT
  email(#165) · voice-in(Wispr) · WhatsApp · manual capture · inbound calendar
        │
        ▼
  EA DECISION-ROUTER  (the gatekeeper)  ─────────────  ← reads WORLD-MODEL (§6):
  match intent-pattern library (cheap-first) →              Purposes/Outcomes (direction)
  per intent: handle / surface / defer / drop               + Principles (constraint)
  unmatched / low-confidence → escalate ↑ then surface
        │  (for "handle": delegate; per-sub-action autonomy, §10)
        ▼
  NARROW EXECUTOR AGENTS   tasker · calendar · habits · …  (via pluggable adapters, §11)
        │
        ▼
  OUTPUTS   alert bus (#701, built) · WhatsApp to Kent
```

- **Email is an *input*, not a peer capability** (all intake modalities normalize raw input into intents). This is the **intake→intent normalization** primitive.
- **The EA decision-router is the genuinely net-new design** — it exists in no current doc. Per [Directive 6](engineering-principles.md) it is **hybrid**: an intent-pattern library and deterministic routes for the clear cases + escalation to LLM judgment only for the ambiguous tail (§10). The **output** side (alert bus) is already built; **intake** and **router** are the gaps.

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

The router is only as good as the context it scores against. That context — the **world-model** — is largely designed already in [`second-brain-graph-layer.md`](second-brain-graph-layer.md) (Epic #692; seed #695), with the **first-class Principle addition below** (now landed in that doc's ontology).

> **Naming (Kent, 2026-07-20).** The world-model structure — the second brain + the Purpose→Outcome→Project→Task hierarchy as a vectorized *temporal* graph — is named the **Life Lattice** (short: **Lattice**): it binds the **why** (Purpose), the **what** (Outcome→…→Task), and the **when** (bi-temporal edges) into one queryable whole. Its raw input units are **episodes** (Graphiti's ingest primitive; a data-lake of unstructured capture); the curated **second brain** vault is a warehouse-like reference pool; the Lattice itself is *canon* (structured to the ontology's patterns). Between them sits the **membrane** (the promotion gate, §7). Full vocabulary + the rollout/validation plan: [`second-brain-graph-layer.md`](second-brain-graph-layer.md) → "Vocabulary & role" and "Rollout & validation".

**Goal hierarchy (direction):** `Purpose → Domain → Outcome → Objective → Project → Task`, plus **Commitment** (a cross-cutting hard-temporal node). **Bi-temporal** — tracks how priorities/commitments evolve over time. Outcomes carry `priority_rank` + target dates. **Structural invariant:** *every node must connect upward to a Purpose — no floating tasks.* That rule is the enforcement mechanism for prioritization (a top-down invariant made executable).

**Principles axis (constraint) — first-class (Kent, 2026-07-20).** A **Principle** is a distinct, cross-cutting node type at the *definitional* tier (slow-changing, foundational, like Purpose). Where **Purposes/Outcomes *direct*** decisions (what/why you pursue), **Principles *constrain*** them — your values, standards, and non-negotiables (how you decide; what the boss will or won't accept). Many-to-many: a Principle may attach to specific Purposes/Domains (`SCOPED_TO`) or apply globally. Principles are **seeded explicitly** (a #695-style Kent-authored content exercise, alongside Purposes/Outcomes) and are stable. *Now folded into the #692 ontology — see [`second-brain-graph-layer.md`](second-brain-graph-layer.md) (Guiding Principle 6, the PRINCIPLE tier, the `Principle` entity model with `hard`/`soft` strictness, and the `SCOPED_TO`/`GOVERNED_BY`/`VIOLATES` edges).*

- **The principal-model = Principles (declared, explicit) + tendencies (learned, observed via write-back).** Principles are its stable, authored half; tendencies compound over time.
- Principles are the **most non-duplicable element in the whole system** — the deepest moat.

**The membrane — a named design element.** Between raw capture and structured world-model sits a **curation step**: unstructured episodes are *interpreted and intentionally extracted* into existing structure, **or** genuinely *emergent* structure is recognized and thoughtfully added to the structured side. This is a judgment operation (LLM proposes; structural changes are reviewed before they land — see the promotion gate, §7). "Capture freely, structure deliberately" is the membrane's whole point.

**Graph vs. vector vs. RAG — already decided: all three, one store.** The goal hierarchy and the second brain both carry relationships flat files cannot serve, and the router's reasoning is too complex for keyword retrieval. #692's tool selection already resolves this: **Graphiti is a hybrid** — vector similarity + BM25 full-text + graph traversal **in a single query** (this is why it was chosen over LightRAG, which cannot do the temporal/graph half). So: the **goal hierarchy** lives as **graph structure** (traversal-primary — walk Task→Purpose, compare priority ranks); the **second brain** lives as **episodes with embeddings** (vector/RAG-primary), *plus* edges extracted across the membrane into the graph. **Same store, two access patterns — do not build a separate graph, vector DB, and RAG pipeline.** The remaining research is narrower and more valuable than "which architecture" (answered): *is one hybrid store enough, at our scale, for the trade-off queries the router demands?* — stress-test Graphiti's hybrid retrieval against real queries **before** committing the ingest pipeline (#696).

**Reconciliation:** the "second brain" is under-utilized today only because it is flat Markdown — no traversal, no priority-over-time, no task→purpose links. #692 turns it into a traversable bi-temporal graph, and *that graph is the world-model the EA reasons against.* They were never two separate things. #692 also **absorbs** two primitives that first looked separate: **write-back/compounding** (its bi-temporal fact tracking) and **provenance/decision-ledger** (its durable trade-off records). **Privacy:** `~/second-brain/notes/04-Growth/_private/` is never ingested; the #696 gate governs what the knowledge tier absorbs — load-bearing as sensitive life-data (health, financials) flows in.

## 7. The promotion gate — one mechanism, three growths (keystone)

The sharpest insight from the 2026-07-20 conversations: **three things that looked like separate problems are one mechanism.** In every case, the system encounters something it doesn't yet have structure for, a judgment step *proposes* a structural addition, and that addition only becomes load-bearing after **human approval**:

| Growth | Trigger | Proposed by | Becomes structure |
|---|---|---|---|
| **New intent pattern** | An input the intent library doesn't recognize (§10) | LLM (or Kent's resolution) | A new entry in the pattern library with a defined route |
| **New world-model structure** | An episode carrying emergent structure the ontology doesn't hold (the membrane, §6) | LLM extraction | New/updated nodes + edges in the graph |
| **New autonomy grant** | A sub-action currently preview-gated that has earned trust (§10) | The write-back confirm/override log | Promotion of that sub-action from preview → autonomous |

**The unifying pattern is `propose → human-approve → structure grows`**, and it is desirably a **learning loop**: every human resolution is training signal, recorded as a write-back episode, so the proposals get better and the unmatched/uncertain tail shrinks over time. Build this gate **once** and all three ride on it. It is also the natural home for **human-in-the-middle as a principle** (§8.7): the gate *is* the middle — the point where a proposed structural change waits for a human before it takes effect. What sits behind the gate (auto) vs. in front of it (needs approval) is exactly the autonomy-boundary question, and it is tunable per growth-type and per action-class.

**Parallel to watch — spec-kitty's doctrine hierarchy (Kent, 2026-07-20).** Spec-kitty is wrestling with the same shape from a different domain: how to *capture, populate, and leverage a hierarchy of doctrine decisions* (charter → directives → tactics → procedures) across the spec→plan→tasks→merge cycle. That is structurally Felix's problem — a decision-hierarchy captured once, the **relevant slice injected at each decision-point**, and coherence checked against it. The **charter-injection mechanism** is the sharpest analog: at plan-time it surfaces *only* the activated directive IDs + section anchors, not the whole doctrine — precisely how the router should read *only* the applicable Principles/Outcomes for a given intent, not the whole graph. As spec-kitty's implementation lands (RFC [#643](https://github.com/kentonium3/kg-automation/issues/643); the doctrine substrate / decision-point injection / coherence-scan work), harvest its design and implementation wisdom for the router and the world-model — capture/populate/inject/coherence is a solved-in-parallel problem worth mining rather than re-deriving.

## 8. Settled decisions (Kent, 2026-07-20)

1. **WRITE-BACK.** The world-model grows through use (compounds) — a property of #692's bi-temporal graph. *Rationale:* gatekeeping improves over time instead of requiring perpetual hand-curation.
2. **FEDERATED, not consolidated.** Graph (#692) = world-model (hierarchy + knowledge + Principles); **Vikunja = operational task execution**; the Obsidian vault = knowledge substrate ingested into the graph. Connected by one-way **Vikunja → Graphiti** sync (open-Q). *Corroboration:* deleting the Vikunja "Goals" project (#734/#724) was correct — hierarchy belongs in the graph.
3. **PRINCIPLES ARE FIRST-CLASS** (§6) — a distinct axis constraining decisions, and the explicit half of the principal-model. Landed in the #692 ontology.
4. **COACHING DEFERRED.** The life-coach agent (#698) is an *overlay* that needs the outcome/task/principle machinery working first. Defer #698 and the *learned* half of the principal-model; the router needs only the **declared Principles + a thin tendencies model** now.
5. **VOICE: input now, two-way deferred.** Voice *input* (Wispr, already in the capture path) is fine and stays. Two-way voice carries a financial cost that isn't justified yet — defer.
6. **ROUTER IS A CHEAP-FIRST CASCADE, not powerful-first** (§10). The intent-pattern library matches first (cheap / deterministic / embedding); only the *unmatched or low-confidence* tail escalates to a more powerful model. Powerful-first would spend the expensive token cost on every input and forfeit moat #4 — the economics wedge only pays off if the common case is cheap.
7. **AUTONOMY = PRINCIPLE NODES, PER SUB-ACTION, PROMOTION VIA WRITE-BACK** (§10). The autonomy boundary is authored as `hard`/`soft` **Principle** nodes, not hardcoded — so moving the line is a data change. The unit is the **sub-action**, not the request. Default posture (generalizing the working "let me view first" model): **deny-to-preview on external + irreversible; allow on reversible + internal.** Human-in-the-middle stays a principle; *where* the middle sits per sub-action is tuned from the confirm/override log. The final promotion *criteria* (how many clean confirms before a sub-action graduates) is intentionally left TBD — tuned with real data.
8. **ONE PROMOTION GATE** (§7) serves new intent patterns, new world-model structure, and new autonomy grants: `propose → human-approve → structure grows`. Build it once.

## 9. Primitive set (forward ∪ backward)

Build-now = demanded by ≥2 capabilities. Single-capability primitives are built *with* that capability; the rest are a watch-list — this filter keeps the forward pass from becoming its own hydra.

| Primitive | Status / home |
|---|---|
| **P1 World-model** (Purpose→…→Task + **Principles**, bi-temporal, write-back, hybrid graph+vector store) | **≡ #692** (Principle refinement now landed in the ontology) — designed, awaiting build/seed |
| **P2 Intake → intent normalization** (+ the **intent-pattern library**) | New; email (#165) is the trigger modality; the library is the deterministic first pass of the router |
| **P3 Delegation / decision-router** (cheap-first cascade) | **The net-new design** (§4/§10), tracked in **#820**; #679 is the negative evidence |
| **P4 Identity / consent / scope** | Partial: #715 two-token, #696 privacy gate |
| **P5 Temporal / scheduler** | Fragmented today (heartbeat gate, escalator, crons, calendar); coaching-cadence part defers |
| **P6 Provenance / decision-ledger** | **Absorbed into #692** (durable trade-off records) |
| **P7 Promotion gate** (`propose → human-approve → structure grows`) | **New keystone (§7)** — shared by intents (P2), world-model (P1), autonomy (P3); demanded by ≥3, build early |
| *Backward infra (mostly guarded already):* | resource-identity **seams** (#811, #748); **deploy-integrity canary** (#817 + #818, the last named gap); **alert bus** (#701, done) |

## 10. The decision-router (the forward design work) — Epic #820

The CEO-EA framing **is** the router's spec:

- **Input:** a normalized intent from any modality.
- **Decision:** `handle` / `surface-to-Kent` / `defer` / `drop`, from a **two-part judgment** — **direction** (does this advance a Purpose/Outcome, and at what priority rank?) × **constraint** (does this respect Kent's Principles?). A high-value action that violates a `hard` Principle is *not* auto-handled — it surfaces.
- **Routing mechanism — a cheap-first cascade over an intent-pattern library:**
  - The input is matched (embedding similarity + rules) against a **library of recognized intent patterns**, each with a **defined route** and an **autonomy class**. A route may itself be fully deterministic, "hand to a cheap LLM," or "hand to a powerful LLM" — the route encodes the power required.
  - **Known pattern, high confidence → its predefined route** (cheap; the common case).
  - **No match / low confidence → escalate** to a more powerful model for open-ended reasoning; if it still can't resolve, **surface for intervention.** This is the deliberate inverse of powerful-first: reasoning-heavy tokens are spent only on the tail, which is *exactly* where you want them (moat #4).
  - **Learning loop:** an unrecognized input that a human (or the escalated LLM) resolves becomes a **candidate new intent pattern** → the **promotion gate** (§7) → approved → added to the library. The unmatched tail shrinks over time.
- **On `handle`:** delegate to the right **executor** via a reliable contract (the #679 fix), through the adapter boundary (§11). **Autonomy is evaluated per sub-action, not per request** (§8.7): e.g. "negotiate a meeting time" decomposes into read-email (auto) → check-calendar (auto) → draft-reply (auto) → propose-time-internally (auto) → **send-to-external-party** (preview-gated until the write-back log supports promotion). The human-in-the-middle sits at the last irreversible/external step; everything upstream is already autonomous.
- **On `surface`:** route through `felix-admin-escalation` to Kent.
- **Implementation:** hybrid (Directive 6) — intent-library / deterministic routes first, LLM only for the ambiguous tail. Every decision is a **write-back** episode so the model learns which calls Kent confirms or overrides (compounding the *tendencies* half of the principal-model, and feeding the promotion gate).

## 11. Extensibility — ports-and-adapters (someday, but design the boundary now)

Long-term framing (not a near-term goal): Felix as an **opinionated OpenClaw add-on** that could work over a *choice* of email / calendar / task / channel backends. This is **ports-and-adapters (hexagonal) architecture**, and the key realization is that **the plugin boundary *is* the OpenClaw/Felix boundary:**

- **Core (Felix, system-agnostic):** the world-model + reasoning + the Purpose/Principle/Outcome/Project/Task logic. Never leaves Felix.
- **Ports:** the contracts — "what does the core need from *a* task system / calendar / mailbox / channel?"
- **Adapters (pluggable):** Vikunja / Todoist / Asana; Google Calendar / Outlook; Gmail / Fastmail; **WhatsApp / Signal**. OpenClaw's connectors *are* adapters.

**Design the channel port first.** A channel is the cleanest port — the *same* intent contract in, a different transport out. Kent is already contemplating replacing WhatsApp with **Signal** (not now). If the channel port is designed first, that swap is an adapter change, not a refactor — the lowest-risk place to prove the whole pattern before tackling the harder task/calendar/mailbox ports.

**Value even with zero product intent:** clean separation of Felix-judgment from tool-specifics (mock the adapter → testable), and insulation from tool churn (swap Vikunja without touching reasoning). **Discipline:** *design the ports now, build exactly one adapter each (channel, task=Vikunja, calendar=Google), defer additional adapters* — the same cross-cutting-and-near-term filter as everywhere else. Realizing advanced capabilities on different tools *will* require this refactoring quest; the boundary design is what makes it incremental rather than a rewrite.

## 12. When is substrate-hardening "enough"?

- **The "hydra" is two things.** (a) *Discovery debt* — building observability turns the lights on (#816 was dead 6 weeks until #811's verify ran it). **Finite and converging** — watch *new-findings-per-fix* trend toward zero. (b) A few *structural patterns* (seams, deploy/source divergence, monitoring blind spots) — **most now have executable guards.**
- **Why docs didn't prevent bottom-up drift:** docs capture *state*; they cannot *enforce invariants*. The fix is **executable invariants** — seams + guard tests + canaries + buses (the alert bus is the model). Target posture: **bottom-up construction with top-down invariants**, checked at spec/merge/CI gates.
- **Verdict: basically there.** Substrate = the *floor* (nearly laid; #817/#818 are the last named gaps). #692 = the *foundation* (designed and waiting — elevate from "P2 someday" to foundational). The **router (§10) = the net-new forward work.** The next move is *forward*, not more hydra. And note: the observability substrate is **moat #3** (§3), not sunk cost.

## 13. Sequencing (proposed)

1. **Seed the world-model** — #695 (Kent-authored **Purposes / Principles / Domains / Outcomes**) + stand up the #692 graph substrate (#693/#694, with the Principle node type).
2. **Design + build the decision-router** (§10, Epic #820) on top, grounded in this brief — including the intent-pattern library and the promotion gate (§7).
3. **Wire email intake** (#165) as the first intake modality feeding the router.
4. **Thin principal-model** (declared Principles + light tendencies) + `Vikunja → Graphiti` sync as connective tissue.
5. **Defer:** coaching (#698), full vault ingest, learned-tendencies model, two-way voice, additional adapters.

Optionally bank the independent, low-risk substrate wins first (autopilot queue: #808 → #805 → #807 → #819).

## 14. Open questions

**Resolved in the 2026-07-20 conversations** (now in §8): voice (input now, two-way deferred); the "intent" contract (an intent-pattern library with defined routes); deterministic-vs-LLM shape (cheap-first cascade); autonomy boundary (Principle nodes, per sub-action, promotion via write-back).

**Still open:**
- **Promotion criteria** — how many clean confirm/override observations before a sub-action graduates from preview to autonomous, and how is that threshold expressed (per action-class? per Principle strictness)? Tuned with real write-back data.
- **Is one hybrid store enough?** — stress-test Graphiti's hybrid retrieval (vector + BM25 + traversal) against real trade-off queries at our scale before committing the ingest pipeline (#696). (Reframes the old "which architecture" question, which #692 already answered.)
- **Router home** — a capability *inside* `main`, or a dedicated inspectable **router agent**? (Cf. epic #692 open-Q for the life-coach agent.)
- **Deterministic-vs-LLM share** — what fraction of triage is library/rule-expressible before LLM fallback? (Shapes moat #4 economics + reliability; measured, not guessed.)
- **Sync semantics** — is one-way `Vikunja → Graphiti` enough, or does task completion/state flow back to Outcomes?

---

*Captured from live design conversations (2026-07-20); see project memory `project_ea_architecture_synthesis.md` for the same synthesis in brief.*
