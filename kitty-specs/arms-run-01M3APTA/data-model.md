# Data Model: 849 Lattice Arms and Decisive Run

Phase 1 output. Entities from spec.md §Key Entities, with the fields the rulings fixed. Nothing
here is a database schema — the only persistent stores are append-only JSONL ledgers and the
per-question FalkorDB graphs Graphiti owns.

## Ledger

An append-only JSONL file; line 1 is the **Header**, every later line is a **Row**. Bound to one
corpus, one prompt, one serving configuration.

| Field (Header) | Type | Source | Invariant |
|---|---|---|---|
| `record` | `"header"` | — | first line only |
| `started` | ISO-8601 UTC | harness | explicit UTC (never bare `astimezone()`) |
| `registration_commit` | str | loader `REGISTRATION` | `c0b35cd1` |
| `corpus` | {file: sha256} | fingerprinted at open | must equal `REGISTRATION.files`; a resume with different values is refused |
| `prompt_hash` | sha256 | `arms849.prompt` | over the registered §3.2 text with the slot empty; refused if it differs |
| `serving` | ServingConfiguration | `arms849.serving` | equal across every row; the secondary differs in exactly `rope_scaling, rope_scale, yarn_orig_ctx, n_ctx` |
| `model_context_tokens` | int | serving | 262,144 primary; 393,216 secondary |
| `run_env_commit` | str | harness | commit the run environment was exported from |
| `run_env_manifest_sha` | sha256 | harness | sha over the **contents** of every exported file, in path order (D-16) |
| `code_hashes` | {path: sha256} | harness | every file under `scripts/research/arms849/` + harness + loader; compared on resume (D-16) |
| `question_manifest_sha` | sha256 | `arms849.questions` | id + ask_time + text of the eight questions (D-14) |
| `preflight_sha` | sha256 | preflight | digest of `preflight.json` (gate results from the full checkout, IC-07) |
| `blinding_seed` | int | harness | seed for per-cell blinded ids |
| `recovery_log` | [str] | reader | e.g. `recovered_torn_tail@<ts>` (D-12) |
| `plan` | int | harness | 72 primary / 24 secondary |

Note: the header is immutable after write. R's calibration is a **`calibration` record line**
(below), never a header mutation.

Record kinds after the header: `attempt_start`, `run`, `calibration`, `event`.

| `attempt_start` | `arm, question, repeat, attempt, ts` — appended BEFORE every attempt so a death mid-cell is counted (D-12) |
|---|---|
| `calibration` | `r_k, g_repeat1_medians{q}, r_medians_at_k{q}, ratio{q}, parity: ok|infeasible, ts` — written once, before the first R cell (D-10) |
| `event` | `kind: server_restart|cache_clear|gate|halt, detail, ts` (D-13) |

| Field (Row `run`) | Type | When | Notes |
|---|---|---|---|
| `record` | `"run"` | always | |
| `arm`, `question`, `repeat` | str, str, int | always | the Cell key |
| `attempt` | int (1–3) | always | NFR-008 / FR-007; an `error` row may be followed by another attempt for the same key; an `ok` row never is |
| `outcome` | Outcome | always | see below |
| `ask_time` | ISO-8601 | always | |
| `prompt_tokens` | int | `ok`, `exceeds_model_context`, `error` when known | total sent (prompt + assembled context + question), Qwen tokenizer |
| `assembled_context_tokens` | int | `ok` | the slot's tokens only — the cost primitive |
| `output_tokens` | int | `ok` | |
| `finish_reason` | `"stop"` \| `"length"` | `ok` | `length` sets `truncated: true` — scored with a flag |
| `cache_read_tokens` (= `cache_n`), `uncached_tokens` (= `prompt_n − cache_n`), `cache_write_tokens` (= uncached) | int | `ok` | explicit llama.cpp `timings` mapping (D-13); row refused if absent |
| `cache_state`, `cache_fraction` | `cold`\|`warm`, float | `ok` | classified from observation, never from repeat index (D-13) |
| `prefill_s` (= `prompt_ms`/1000), `generation_s` (= `predicted_ms`/1000), `generation_tok_s` | float | `ok` | from `timings`; row refused if absent |
| `peak_gtt_gib` | float | `ok`, `error` | serving-process peak, 1 Hz beside the request |
| `falkordb_rss_peak_mib` | float | G `ok` | per-question build+retrieval window (D-13) |
| `assembled_context_sha256` | sha256 | `ok` | asserted equal across repeats and resumes (NFR-005, D-15) |
| `r_g_ratio` | float \| `"unavailable:<reason>"` | R `ok` | R assembled ÷ G repeat-1 median for the question (D-10) |
| `context_limit_applied` | `trained`\|`permitted` | D rows | which limit the gate used (D-11) |
| `seed` | int | `ok` | `1000 + repeat` |
| `text` | str | `ok` | the answer; never shown to the grader from here (GradingView) |
| `plan` | PlanRecord | `ok` | per arm, below |
| `error` | str | `error` | `TypeName: message`, or `timeout` |
| `elapsed_s` | float | all | wall-clock of the attempt |
| `events_loaded`, `nodes_loaded`, `edges_loaded`, `links_loaded` | int | `ok` | from the ArmView |

**Invariants**: (I1) exactly one Header, first line; (I2) at most one `ok` row per Cell key;
(I3) `attempt` increases by 1 per row for a key and never exceeds 3; (I4) `prompt_tokens` present
on every `exceeds_model_context` row and > `model_context_tokens`; (I5) every row parses — the
writer flushes and fsyncs before returning; (I6) one writer: a lock file beside the ledger, held
for the session, refused to a second process.

## Cell

`(arm ∈ {G, D, R}, question ∈ {C1, A, F1, B1, E2, E1, F2, B2}, repeat ∈ {1, 2, 3})`. Execution
order: arm-major G → D → R; within an arm, repeat-major; within a repeat, questions in
`ask_time` ascending order (protocol, C-008). 72 cells primary; the secondary is D only, 24 cells.

## Outcome

| Value | Meaning | Scored | Averaged | Counts as failure |
|---|---|---|---|---|
| `ok` | answer returned | yes | yes | no |
| `exceeds_model_context` | prompt measured > model context before sending (D only) | no | never | no |
| `error` | attempted, failed (infrastructure, timeout, tripwire fired) | no | never | yes |
| `not_implemented` | arm not registered | no | never | no (blocks a real run: SC-001 requires zero) |

State transitions for a Cell key: `(none) → error → error → error` (terminal, 3 attempts) or
`(none) → [error →]* ok` (terminal). `exceeds_model_context` is terminal on first attempt.

## ArmView

What one arm may read for one question at its `ask_time` — produced by `replay()` and narrowed
by `arm_view()` (existing). `events`, `entities`, `edges` for all; `links` (episode→entity) for G
only; D and R receive `links = []`. Every event `at ≤ ask_time`; every Decision `decided_at ≤
ask_time`; every edge's effective time `≤ ask_time` with both endpoints present.

## ServingConfiguration

| Field | Primary | Secondary |
|---|---|---|
| `model` | `Qwen3-Next-80B-A3B-Instruct UD-Q4_K_XL` | same |
| `gguf_sha256` | from `SHA256SUMS` | same |
| `image_digest` | `sha256:063e88ae…` | same |
| `n_ctx` | 262144 | 393216 |
| `rope_scaling`, `rope_scale`, `yarn_orig_ctx` | none, —, — | `yarn`, 2, 262144 |
| `parallel` | 1 | 1 |
| `cache_prompt` | true | true |
| `sampling` | `{temperature: 0.7, top_p: 0.8, top_k: 20, repeat_penalty: 1.05, min_p: 0}` | same |
| `seed_policy` | `1000 + repeat` | same |
| `max_tokens` | 2048 | same |
| `embedder` | `fastembed BAAI/bge-small-en-v1.5` (+ model sha) | same |
| `reranker` | `cosine (#974)` | same |
| `tokenizer` | `Qwen/Qwen3-Next-80B-A3B-Instruct` (+ files sha) | same |

Equality across all rows of a ledger is asserted at every append.

## PlanRecord (per arm, on `ok` rows)

- **G**: `anchors_resolved: [entity ids]`, `anchor_resolution_paths: {alias: [...], commitment_desc: [...], outcome_desc: [...]}`,
  `ambiguous_mentions: [...]`, `path: "anchored" | "search_only"`, `plan_steps: [typed pulls…, search…, expansions…]`,
  `items_assembled: int (≤ 60)`, `items_by_kind`, `llm_calls: 0`, `group_id` (D-15).
- **D**: `layout: "events_entities_edges"` (asserted), `events_in_dump`, `entities_in_dump`, `edges_in_dump`.
- **R**: `k`, `retrieved_refs_by_rank: [ref…]` (rank order — recorded, not shown to the model),
  `assembled_order: "ask_time"`, `entities_in_records`, `edges_in_records`, `availability_capped: bool`.

## GradingView, AdminReport and Seal

- **GradingView** (`build/849-runs/views/<ledger>-grading.json`): per question, **every scored
  (`ok`) cell** as an entry under a blinded id — `q<Q>-<6 hex>` drawn from
  `Random(f"{blinding_seed}:{question}:{arm}:{repeat}")`, ordered by id — carrying
  `question_text`, `ask_time`, `text`, `truncated`. Nine entries for a fully scored question,
  fewer where cells are non-scored. Contains **no** arm name, repeat index, timing, token count,
  plan record, seed or ledger path. Blinded ids encode neither arm nor repeat.
- **AdminReport** (`build/849-runs/admin/<ledger>-admin.json`): the non-scored cells
  (`exceeds_model_context`, `error`) with arm, question, repeat and token counts — for the
  reader of the run, **never** for the grader; the view carries no trace of them.
- **Seal** (`build/849-runs/seals/<ledger>-seal.json`): `{blinded_id: {arm, question, repeat}}`,
  the seed, and the header hash; reproducible from the seed; opened only after scores are in.
  Views, admin reports and seals live in three separate directories.

## Gate

Two phases (IC-07). **Preflight, from the full checkout**: `check_849_seed`, `check_849_oracle`,
`check_849_freeze`, `check_849_loader` (these load the oracle and would pass vacuously in the
export) → `preflight.json` with results, corpus fingerprints and the export's content manifest
sha. **In-container, before the header**: `preflight_present_and_matching`, `prompt_digest`,
`question_manifest_digest`, `oracle_absent` (path + static scan), `boundary` (denied-access test:
original checkout, oracle, seeds, narrative files unreachable), `env_clean` (no `OPENAI_API_KEY`,
FastEmbed and tokenizer caches present, no `torch`), `tokenizer_equivalence` (100 lines vs the
server's `/tokenize`), `substrate_health` (FalkorDB `GRAPH.LIST`; llama-server `/health` + `/props`
n_ctx, model file, rope settings). All must pass before the Header is written.
