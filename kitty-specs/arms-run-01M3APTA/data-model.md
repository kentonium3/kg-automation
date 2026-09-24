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
| `run_env_commit` | str | harness | commit the run environment was exported from; oracle path absent |
| `run_env_manifest_sha` | sha256 | harness | hash of the exported file list (adversarial A3) |
| `blinding_seed` | int | harness | seed for per-question label randomisation |
| `r_k` | int \| null | written when R starts | derived once from G repeat-1 medians; null until then |
| `r_k_derivation` | {question: g_median_context_tokens} | written with `r_k` | the medians used |
| `plan` | int | harness | 72 primary / 24 secondary |

| Field (Row) | Type | When | Notes |
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
| `cache_write_tokens`, `cache_read_tokens`, `uncached_tokens` | int | `ok` | from llama.cpp timings; `cache_hit_rate` derived = read / prompt_tokens |
| `prefill_s`, `generation_s`, `generation_tok_s` | float | `ok` | from llama.cpp timings |
| `peak_gtt_gib` | float | `ok`, `error` | sampled 1 Hz beside the request by the harness |
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

- **G**: `anchors_resolved: [entity ids]`, `anchor_resolution: "alias"`, `plan_steps: [label
  pulls..., anchored expansions...]`, `items_assembled: int (≤ 60)`, `items_by_kind`, `llm_calls:
  0`, `group_id`.
- **D**: `layout: "events_first"` (asserted), `events_in_dump`, `entities_in_dump`.
- **R**: `k`, `retrieved_refs_by_rank: [ref…]` (rank order — recorded, not shown to the model),
  `assembled_order: "ask_time"`, `entities_in_records`.

## GradingView and Seal

- **GradingView** (`build/849-runs/<ledger>-grading.json`): per question, the three `ok`
  answers under labels `X/Y/Z` re-randomised per question from `blinding_seed`; includes
  `question_text`, `ask_time`, the answer texts and `truncated` flags; contains **no** arm name,
  no timings, no tokens, no plan records. For a cell with no `ok` row the slot reads
  `{"outcome": "exceeds_model_context" | "error"}` under its label, so the grader knows an answer
  is absent without knowing whose.
- **Seal** (`build/849-runs/<ledger>-seal.json`, written to a **different directory** from the
  view): `{question: {label: arm}}` plus `blinding_seed` and the ledger's header hash. Reproducible
  from the seed; the grader opens it only after scores are in.

## Gate

`(name, passed: bool, detail)` for each of `check_849_seed`, `check_849_oracle`,
`check_849_freeze`, `check_849_loader`, `prompt_hash`, `oracle_absent`, `env_clean` (no
`OPENAI_API_KEY`; FastEmbed cache present; tokenizer cache present). All must pass before the
Header is written.
