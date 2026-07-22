# Research: Life Lattice Viability Spike (Phase 0)

Consolidated decisions resolving the plan's open unknowns. Format: Decision / Rationale / Alternatives.

## R-01 — Q2 reasoning methodology: A/B (graph-retrieval vs flat-dump)

- **Decision**: Reason over the seeded data twice on identical content — (A) Graphiti graph/temporal retrieval feeds Claude a structured subgraph; (B) a flat full-context dump of the same nodes feeds Claude directly. Compare the traversal answer and surfaced conflict across both arms.
- **Rationale**: At spike scale everything fits in context, so a flat dump *will* work; without the A/B, a "go" would only prove Claude can read structured text, not that the temporal substrate adds value. The A/B isolates the substrate's contribution and forces honesty about the scale caveat. (Decision `graph_value_isolation`, resolved with Kent.)
- **Alternatives considered**: Graph-retrieval only (no baseline → can't attribute value); flat-dump only (fastest but proves nothing about the graph). Both rejected.

### R-01a — Pre-registered Q2 go-rubric (Codex HIGH-1 — the bar was too weak)

"Graph arm matches flat + offers a scale path" is NOT sufficient to approve — it can pass without temporal reasoning ever paying off. **Before running the A/B, we pre-register this rubric:**

- **GO for Q2** requires the graph/temporal arm to produce a **materially better or more reliable** answer than the flat baseline on **at least one temporal stress case** (chronic-defer or week-conflict) — i.e., the graph surfaces something the flat arm misses, gets wrong, or answers less reliably — AND Kent judges that difference genuinely useful.
- If the two arms are indistinguishable in quality (flat does just as well), the honest verdict is **`inconclusive` / no-go-for-Q2 at this scale**, NOT a go. That is a valid, first-class outcome.
- The rubric and the per-case scoring dimensions are written into `findings.md` **before** the runs, not reverse-engineered after.

### R-01b — A/B validity controls (Codex HIGH-2 — remove confounds)

The make-or-break judgment is worthless if the comparison is confounded. Controls, applied to both arms:

- **Fixed prompts** — identical task instruction across arms; only the *context* (graph-retrieved subgraph vs flat dump) differs.
- **Nondeterminism** — temperature 0, and/or N repeated runs per arm to expose variance; record all runs.
- **Blinding** — arm labels are randomized/hidden when results are presented to Kent for the FR-005 judgment; he scores against the rubric without knowing which arm is graph-backed. De-blind only after scoring.
- **Captured raw contexts** — the exact context handed to each arm is saved as evidence (so a reviewer can see what the graph retrieval actually pulled vs the flat dump).
- **Order/position effects** — randomize arm presentation order; don't always show graph first.

### R-01c — Hidden oracle (Codex HIGH-3)

Expected conflicts/trade-offs live in `data/oracle.yaml`, never loaded into the graph and never shown to the reasoner (see data-model.md). Scoring compares each arm's surfaced conflicts against the oracle; a "hand-fed" surface (from a pre-loaded tension edge) does not count.

## R-02 — Graph engine: Graphiti + FalkorDB (as designed)

- **Decision**: Use Graphiti (Zep) over FalkorDB — the engine already selected in `docs/design/second-brain-graph-layer.md` — for the sandbox.
- **Rationale**: The spike must de-risk the *actual* build target, not a proxy. Graphiti gives bi-temporal edges + hybrid (vector + BM25 + graph) retrieval in one store and a native Anthropic path, matching the design.
- **Alternatives considered**: Neo4j/LightRAG/custom — rejected; testing a different engine wouldn't de-risk #693. A pure-vector store — rejected; wouldn't exercise temporal traversal, which is the whole point of Q2.

## R-03 — Extraction + reasoning LLM: Claude (native Anthropic API)

- **Decision**: Use Claude via the native Anthropic API for both Graphiti entity extraction and the reasoning arms.
- **Rationale**: Matches the #692 "Claude-native, no OpenAI dependency" design intent; keeps the spike representative. Content is synthetic, so no privacy gate applies (C-004).
- **Alternatives considered**: A local LLM — deferred; the post-#848 posture means the local-LLM question is no longer forced for the spike, so we don't pay that complexity now. OpenAI embeddings (Graphiti default) — rejected per the design's no-OpenAI stance; confirm Graphiti can be configured Claude/anthropic-only for extraction and pick a non-OpenAI embedder (research task R-06).

## R-04 — Sandbox isolation & reversibility

- **Decision**: Run Graphiti + FalkorDB via a dedicated `docker-compose` project on office2 with its own network, volume, and non-default ports; tear the whole project (containers + volume + network) down at spike end.
- **Rationale**: Satisfies NFR-001 (zero prod contact) and NFR-002 (zero residue). A compose project is the cleanest atomic up/down unit.
- **Alternatives considered**: Reusing existing infra — rejected (couples to prod). A local-Mac sandbox — rejected for Q1, which must measure office2 fit (though early Q2 harness dev can happen locally if convenient).

## R-05 — office2 execution constraints

- **Decision**: All office2 actions run as the `claude` user via `ssh office2-claude`, Docker through the `docker` group (`sg docker`). Any command needing sudo is surfaced to Kent for manual run via `ssh office2-kgale`.
- **Rationale**: Repo standing rule; `claude` has no sudo. Container ops via the docker group do not need sudo.
- **Alternatives considered**: none — this is fixed policy.

## R-06 — Pre-standup gates and research tasks

- **R-06a (PRE-STANDUP GATE — Codex HIGH-4)**: Confirm and **document** Graphiti's actual LLM + embedder + outbound-host configuration for an all-Claude / non-OpenAI path, and the failure mode if the intended provider path is unavailable. This is central to Q3 (privacy) and to whether the spike tests the *intended* architecture. **If the intended provider path cannot be achieved (e.g. Graphiti silently falls back to OpenAI embeddings), Q3 and the Q2 architecture-fit are marked `blocked` / `inconclusive` — we do NOT quietly run on default embeddings and report a green Q3.** Record actual LLM, embedder, and every outbound host. (Feeds IC-01/IC-03/IC-06.)
- **R-06b (credential hygiene — Codex LOW-13)**: Use a **spike-specific, narrowly-scoped** Anthropic key (not a prod credential); inject via env only; keep it out of compose files and shell history; disable secret logging; and **verify it is removed** from env, containers, compose, and history after teardown. (Feeds IC-01/teardown.)
- **R-06c**: Confirm office2 headroom for the added containers before stand-up (Tier-1 connectivity / Tier-2 snapshot posture check, even though throwaway). (Feeds IC-01/IC-05.)

R-06a is a gate that must pass before stand-up; R-06b/R-06c are pre-flight checks. None blocks *planning*.
