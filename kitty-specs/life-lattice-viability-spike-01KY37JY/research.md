# Research: Life Lattice Viability Spike (Phase 0)

Consolidated decisions resolving the plan's open unknowns. Format: Decision / Rationale / Alternatives.

## R-01 — Q2 reasoning methodology: A/B (graph-retrieval vs flat-dump)

- **Decision**: Reason over the seeded data twice on identical content — (A) Graphiti graph/temporal retrieval feeds Claude a structured subgraph; (B) a flat full-context dump of the same nodes feeds Claude directly. Compare the traversal answer and surfaced conflict across both arms. "Go" evidence = the graph arm at least matches the flat arm's quality (no signal lost) AND offers the scale path the flat arm cannot sustain.
- **Rationale**: At spike scale everything fits in context, so a flat dump *will* work; without the A/B, a "go" would only prove Claude can read structured text, not that the temporal substrate adds value. The A/B isolates the substrate's contribution and forces honesty about the scale caveat. (Decision `graph_value_isolation`, resolved with Kent.)
- **Alternatives considered**: Graph-retrieval only (no baseline → can't attribute value); flat-dump only (fastest but proves nothing about the graph). Both rejected.

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

## R-06 — Open research tasks to resolve during the mission (not blockers)

- **R-06a**: Confirm Graphiti's LLM/embedder config supports an all-Claude/non-OpenAI path; pick the embedder. (Feeds IC-01/IC-03.)
- **R-06b**: Confirm an Anthropic API key is available to the sandbox on office2 (env/secret), isolated from prod credentials. (Feeds IC-01.)
- **R-06c**: Confirm office2 headroom for the added containers before stand-up (Tier-1 connectivity / Tier-2 snapshot posture check, even though throwaway). (Feeds IC-01/IC-05.)

These are surfaced as mission tasks; none blocks planning.
