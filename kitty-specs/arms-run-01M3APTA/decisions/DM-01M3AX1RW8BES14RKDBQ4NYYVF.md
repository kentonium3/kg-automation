# Decision Moment `01M3AX1RW8BES14RKDBQ4NYYVF`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `plan`
- **Slot key:** `plan.secondary.yarn-configuration`
- **Input key:** `secondary_yarn_configuration`
- **Status:** `resolved`
- **Created:** `2026-09-24T23:47:11.880583+00:00`
- **Resolved:** `2026-09-24T23:49:30.178265+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

For the D-YaRN secondary, what exact scaled-context serving configuration is registered: rope scaling type and factor, original context, target n_ctx (must cover 362,772), and whether anything else changes from the primary?

## Options

_(none)_

## Final answer

Per design lead 23:48Z Q6: llama.cpp --rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 262144 --ctx-size 393216 (factor 2 is the smallest covering B2, less perturbing than factor 4); everything else identical to the primary (GGUF sha, image digest, sampling, seeds, prompt hash, layout, cache on, embedder/reranker); header fields that differ: rope_scaling=yarn, rope_scale=2, yarn_orig_ctx=262144, n_ctx=393216 — SC-006 asserts exactly these; the secondary runs its own context-window gate at that config before its first cell

## Rationale

_(none)_

## Change log

- `2026-09-24T23:47:11.880583+00:00` — opened
- `2026-09-24T23:49:30.178265+00:00` — resolved (final_answer="Per design lead 23:48Z Q6: llama.cpp --rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 262144 --ctx-size 393216 (factor 2 is the smallest covering B2, less perturbing than factor 4); everything else identical to the primary (GGUF sha, image digest, sampling, seeds, prompt hash, layout, cache on, embedder/reranker); header fields that differ: rope_scaling=yarn, rope_scale=2, yarn_orig_ctx=262144, n_ctx=393216 — SC-006 asserts exactly these; the secondary runs its own context-window gate at that config before its first cell")
