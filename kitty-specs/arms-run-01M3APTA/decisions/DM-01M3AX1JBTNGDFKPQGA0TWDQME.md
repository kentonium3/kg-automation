# Decision Moment `01M3AX1JBTNGDFKPQGA0TWDQME`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `plan`
- **Slot key:** `plan.arm-g.embedder-and-reranker`
- **Input key:** `arm_g_embedder_and_reranker`
- **Status:** `resolved`
- **Created:** `2026-09-24T23:47:05.210562+00:00`
- **Resolved:** `2026-09-24T23:48:32.419653+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Arm G's hybrid retrieval needs node/edge embeddings and optionally a reranker. Which embedder (FastEmbed bge-small local, the same as R, or something else) and is a cross-encoder reranker used at all?

## Options

_(none)_

## Final answer

Per design lead 23:43Z ruling 2: embedder = FastEmbed bge-small local, ONE definition shared with arm R; cross-encoder = the local cosine reranker from #974; LLM client = tripwire that raises on any call, G rows record llm_calls: 0 and a non-zero count fails the cell as error

## Rationale

_(none)_

## Change log

- `2026-09-24T23:47:05.210562+00:00` — opened
- `2026-09-24T23:48:32.419653+00:00` — resolved (final_answer="Per design lead 23:43Z ruling 2: embedder = FastEmbed bge-small local, ONE definition shared with arm R; cross-encoder = the local cosine reranker from #974; LLM client = tripwire that raises on any call, G rows record llm_calls: 0 and a non-zero count fails the cell as error")
