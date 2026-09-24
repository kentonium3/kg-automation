# Decision Moment `01M3AWRBB7D5N1D4GTA5QNPG7C`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `plan`
- **Slot key:** `plan.arm-g.graph-write-path`
- **Input key:** `arm_g_graph_write_path`
- **Status:** `resolved`
- **Created:** `2026-09-24T23:42:03.111309+00:00`
- **Resolved:** `2026-09-24T23:48:11.463365+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Arm G must be seeded by structured writes with no LLM (rubric §2), but Graphiti's native ingestion extracts entities with an LLM. How should G's graph be written: through Graphiti's typed-entity APIs with extraction disabled, by direct FalkorDB writes in Graphiti's schema so Graphiti's hybrid retrieval still runs, or by direct FalkorDB writes with our own hybrid retrieval and no Graphiti at all?

## Options

- Graphiti typed-entity APIs, LLM extraction disabled; Graphiti retrieval
- Direct FalkorDB writes in Graphiti schema; Graphiti retrieval
- Direct FalkorDB writes; our own node+edge hybrid retrieval, no Graphiti
- Design lead decides — it is the ontology owner

## Final answer

(a) per design lead 23:43Z, as #974 measured: graphiti-core typed EntityNode/EntityEdge/EpisodicNode saved DIRECTLY in Graphiti's own schema; tripwire LLM client that raises on any call; Graphiti hybrid search on top. Not raw Cypher, not our own retrieval.

## Rationale

_(none)_

## Change log

- `2026-09-24T23:42:03.111309+00:00` — opened
- `2026-09-24T23:48:11.463365+00:00` — resolved (final_answer="(a) per design lead 23:43Z, as #974 measured: graphiti-core typed EntityNode/EntityEdge/EpisodicNode saved DIRECTLY in Graphiti's own schema; tripwire LLM client that raises on any call; Graphiti hybrid search on top. Not raw Cypher, not our own retrieval.")
