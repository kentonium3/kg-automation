# Findings: Life Lattice Viability Spike

**Mission**: life-lattice-viability-spike-01KY37JY (research) · **Date**: 2026-07-22 · **Issue**: #844
**Status**: complete · **Run**: live on office2 (isolated FalkorDB sandbox, torn down)

---

## Verdict (go / no-go)

Two separable questions, two different answers:

| Question | Verdict |
|---|---|
| **Does the temporal/priority REASONING pay off?** (Q2 core) | **GO** — Kent judged it *clearly valuable* (blinded). |
| **Does the GRAPH substrate (Graphiti+FalkorDB) pay off at this scale?** | **NO-GO / inconclusive** — the graph arm lost **4/4** blinded comparisons to a flat-context baseline. Its value is a *scale* argument this small slice structurally cannot test. |
| **Build direction for #692** | **OPEN** — Kent is deciding. The spike redirects the question from *"build the graph"* to *"build the reasoning; graph-vs-structured-context is unproven."* |

**Bottom line:** the *capability* (surface the quiet risk, resolve the conflict via Kent's principles) is worth building. Whether it needs a bi-temporal graph is **not established** — at Kent's scale a flat/assembled structured context + a strong model matched or beat the graph on every question. Do **not** greenlight the Graphiti+FalkorDB infrastructure build on the strength of this spike.

---

## Q2 — Temporal-reasoning payoff (the make-or-break)

### Pre-registered rubric (locked in research.md R-01a, commit `e533eee9`, before the run)
> GO requires the graph/temporal arm to be **materially better or more reliable** than the flat baseline on **≥1 temporal stress case**, AND judged genuinely useful. Indistinguishable arms → `inconclusive`/no-go.

### Method
A/B on identical seeded data, same fixed prompt + model (`claude-opus-4-8`), **blinded** arm labels re-randomized per question; conflicts inferred from primitives (no asserted edges; hidden oracle). Arm A = Graphiti hybrid/temporal retrieval → Claude. Arm B = flat full-context dump → Claude.

### Result — the graph arm lost every blinded comparison
Kent's blinded picks (revealed after judging):

| Question | Kent chose | Was |
|---|---|---|
| Q1 "why this task?" (upward) | Arm-1 | **flat** |
| Q2 "what's quietly a risk?" (chronic-defer) | Arm-2 | **flat** |
| Q3 "scheduling conflict that week?" | Arm-2 | **flat** |
| Q4 "genuine trade-off?" | Arm-2 | **flat** |

**Graph arm: 0/4.** Root cause: the graph arm's hybrid retrieval (top-20 facts) **missed load-bearing facts** — most damagingly the **15h/week capacity constraint** — so it produced weaker or wrong reasoning (pulled in the wrong "observability" collision on Q3/Q4; explicitly said "the context does not state a time budget" on Q4). The flat arm always had the complete context and correctly nailed the 18h-vs-15h collision resolved by the hard client-deadline principle.

Per the rubric: graph was better on **zero** cases → **Q2 graph-substrate = NO-GO / inconclusive.**

### The reasoning itself is valuable (Kent's judgment)
Independent of representation, the reasoning both arms produced when given the facts — catching that a *medium-priority, no-deadline task feeding a high-priority outcome had silently slipped 4× and was about to slip a 5th*, and resolving the week's conflict by protecting the committed client deadline and de-scoping the demo — Kent judged **"clearly valuable."** That is the capability worth building.

### Why the graph didn't win — and why that's honest, not damning
At this scale (~25 seeded facts) a **flat dump of everything is complete and unbeatable**; the graph can at best tie (perfect retrieval) or lose (retrieval gaps, which happened). The graph's genuine advantage is **scale** — when the world-model is too large to dump and you *must* retrieve — which a hand-seeded slice cannot exercise. **This was pre-registered as the likely outcome (the scale caveat), and it held.**

### What this spike could NOT test — the flat baseline's three expiry conditions (Kent, 2026-07-22)
The flat-dump arm won by *including everything*. That is only possible in the spike's small, static, single-shot regime. Three real-life factors each dissolve that advantage — and they are exactly the conditions under which the graph is *meant* to win:

1. **Volume** — many competing priorities, a full schedule, hundreds of commitments. Eventually the world-model can't be dumped (context limits) or dumping drowns the signal in noise. Retrieval becomes mandatory; the flat baseline ceases to exist and the only question is *which* retrieval is best.
2. **Dynamics** — constant multi-channel inbound (email, Slack), interruptions, urgent items, priority churn. A flat dump is a static snapshot with no story for continuously ingesting / deduping / reconciling / re-prioritizing a stream of new inputs. That ingest-and-reconcile loop is precisely a bi-temporal graph's purpose (and Graphiti's cross-episode entity resolution). The flat approach has no answer here.
3. **History depth** — a rich decision history ("why deferred 4×? what did we decide last time? the multi-month pattern"). A current-state dump loses it; bi-temporal edges keep it. Notably the graph's **one clear win** in this spike was exactly this: it captured and retrieved the 4-event defer history faithfully.

**Rigor caveat (keeps this OPEN, not a settled "build the graph"):** "scale needs retrieval" ≠ "scale needs a *graph*." At scale you need good retrieval + a temporal store, which could be **vector-RAG + an event log** without Graphiti's typed-graph complexity. The graph's specific bet — that *typed, traversable, bi-temporal structure* beats flat retrieval — is unproven, and this spike surfaced a real threat to it (Graphiti flattened the ontology to generic `Entity` nodes and fragmented the upward edges; see Q4).

### The decisive next test (what should actually gate #693)
Not "more nodes" — the **dynamic regime above**: a larger, evolving world-model with multi-channel inbound, interruptions, priority churn, and months of decision history, comparing **graph-mediated retrieval vs the best non-graph retrieval baseline (vector-RAG + structured records)** on realistic queries. That test earns #693 or kills it. This spike deliberately does not attempt it.

---

## Q1 — office2 fit — PASS
Graphiti-core + FalkorDB ran comfortably on office2 (Ubuntu 24.04). Footprint vs baseline (2568 MB host used):
- cold start: +86 MB host; container ~50 MiB
- idle after runs: +112 MB host; container ~82 MiB
- disk: FalkorDB image large (~part of 8.6 GB images pool) but the data **volume was ~22 B**; the graph is tiny.
No contention with the existing stack (28+ GiB free RAM throughout). **office2 can host the infra easily** — this de-risks #693 *if* the graph path is pursued.

## Q3 — Privacy / extraction posture (post-#848 "verify not present")
- **Extraction LLM = Claude** (Anthropic API, `claude-sonnet-5` for extraction, `claude-opus-4-8` for reasoning) — episode content **crosses the Tailscale boundary to Anthropic** during ingestion + reasoning.
- **Embedder = local FastEmbed** (BAAI/bge-small-en-v1.5, on-box ONNX) and **reranker = local** cosine — the vector half is fully on-box, no OpenAI, no external calls.
- This spike used **synthetic content only** (verified not present: no real vault/second-brain data), so no privacy gate applied.
- **For a real build:** episode *text* would reach Anthropic during extraction. Given #848 (private content physically excluded) the residual boundary is "opaque handles in, private content out." A fully-local extraction LLM would be required only if even opaque-handle episode text must not leave the box — a decision for the build, not the spike.

## Q4 — Ontology fit — significant friction (3-bucket split)
- **Ontology friction (real):** Graphiti stores everything as generic **`Episodic` + `Entity`** nodes (confirmed: those are the only node labels). The fixed **Purpose→Domain→Outcome→Objective→Project→Task** tiers and the **"every node connects upward to a Purpose"** invariant are **not natively represented** — they survive only as LLM-*extracted* edges, which fragmented (the graph arm hedged on whether a "goal" and an identically-named "outcome" were the same entity). Enforcing the #692 ontology would require custom `entity_types` + validation on top of Graphiti, and even then the hierarchy is reconstructed, not guaranteed.
- **Engine/API friction:** FalkorDB `v4.2.2` lacked relationship full-text search (needed a newer image); group-scoped search errored/returned empty (had to use a single unscoped group); newest Claude models deprecate `temperature` (graphiti sends it unconditionally → patched via `NOT_GIVEN`).
- **Seed-authoring friction:** minimal — the seed loaded cleanly and the bi-temporal defer history *was* faithfully captured and retrievable (the one clear graph strength: 4 discrete reschedule events at their historical timestamps).

---

## Incidental findings (useful for the build regardless of direction)
1. **Anthropic has no embeddings API** → "Claude-native" can't cover the vector half; the embedder is a separate choice (local FastEmbed worked well and keeps it on-box).
2. **Newest Claude models deprecate `temperature`** → determinism controls must rely on the model, not a temperature knob.
3. **Graphiti's default reranker is OpenAI**; the BGE local reranker needs torch. A small local cosine reranker avoids both.
4. **Bi-temporal capture works well** — the 4-event defer history was the graph's one clear win in retrieval; if a graph is built, this is its strongest justification.

## Rollout ladder / epic sequencing / membrane topology — DEFERRED
These were to be confirmed *on a go*. Since the graph-substrate verdict is no-go/inconclusive and the **build direction is open (Kent deciding)**, the shadow→advisory→gated→autonomous ladder, the #693→#698 sequencing, and the membrane-topology decision for #696 are **not confirmed here** — they are contingent on the build-direction decision. If Kent pursues structured-context-first, much of #693/#694 (graph infra + ontology) is deferred or reshaped.

## Recommended next step (Kent's call)
Either (a) **pivot to structured-context-first**: build the reasoning capability on assembled structured context (the approach that won), add a graph only when scale demands; or (b) **re-test the graph at scale** (hundreds+ of nodes, where flat-dump becomes infeasible) before committing to #693. The reasoning capability is validated either way.

## Reproducibility
Harness under `harness/` (embedder_local, reranker_local, graph_common, seed_lattice, reason_ab), seed under `data/`, isolated sandbox under `sandbox/`. Raw A/B contexts + answers + blinding map in `results/ab_reveal.json`; blinded presentation in `results/ab_results_blinded.md`. Sandbox torn down after the run (see teardown evidence).
