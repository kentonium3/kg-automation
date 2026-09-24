# Research: 849 Lattice Arms and Decisive Run

Phase 0 output. Every decision below is either a design-lead ruling (D-1..D-6, recorded on the
agent bus 2026-09-24 23:43Z and 23:48Z, `stability: accepted`, and resolved into the mission's
Decision Moments verbatim) or an implementer's call the design lead reviews at the post-plan
checkpoint (D-7..D-9). No `[NEEDS CLARIFICATION]` markers remain.

## D-1 — How arm G's graph is written (Decision Moment 01M3AWRBB7D5N1D4GTA5QNPG7C)

- **Decision**: graphiti-core 0.30.2 typed `EntityNode` / `EntityEdge` / `EpisodicNode` /
  `EpisodicEdge` objects saved **directly** in Graphiti's own schema; Graphiti's hybrid `search()`
  on top; `add_episode` is **never called** (a static test greps the arm module for it); the LLM
  client handed to Graphiti is a **tripwire** that raises on any call, and each G cell records
  `llm_calls: 0` — a non-zero count fails the cell as `error`. Entity types are the ontology's
  Pydantic models passed as labels/attributes as #974 did; edges are `EntityEdge` with `name` =
  the ontology edge type; episodes are `EpisodicNode` with `reference_time` = the event's `at` and
  `source_description` from the event; `MENTIONS` come from `loader_links.jsonl` as `EpisodicEdge`.
  Edge `valid_at` / `created_at` are set from the event's `at` so Graphiti's bi-temporal fields are
  honest. Graphiti **is** a runtime dependency — a G result must be a statement about
  Graphiti+FalkorDB.
- **Rationale**: settled empirically in #974 (2026-09-15): the typed seed loaded through the node
  and edge classes with `llm_calls_attempted: []`, and `search()` ran over it with local
  embeddings. This is what §2's "seeded by structured writes (no LLM)" means.
- **Alternatives considered**: (b) raw Cypher into Graphiti's schema — breaks the moment 0.30.x
  moves a property; (c) our own retrieval — makes G a substrate the design never selected.
- **Reference implementation**: the #974 harness, preserved in the issue's comments
  (`rq1_validate.py`, `rq6_engine.py`, the RQ-4/RQ-5 retrieval scripts).

## D-2 — G's embedder and reranker (01M3AX1JBTNGDFKPQGA0TWDQME)

- **Decision**: embedder = FastEmbed `BAAI/bge-small-en-v1.5`, local, **one definition shared by
  G and R** (`scripts/research/arms849/embed.py`); Graphiti's `cross_encoder` slot filled by the
  local cosine reranker from #974 (embedding similarity, no external call). Both recorded in the
  serving-configuration block as `embedder` and `reranker`.
- **Rationale**: the arms' only difference must be retrieval structure; a learned cross-encoder
  would be a second model whose quality the arms do not share.
- **Alternatives considered**: a cross-encoder reranker (rejected as above); a different embedder
  per arm (rejected — confounds the comparison).

## D-3 — Per-question rebuild and group naming (01M3AX1M4PE2XQWZT4Y63KSCS0)

- **Decision**: one FalkorDB graph per question, `group_id = arms_<Q>` — `arms_C1, arms_A,
  arms_F1, arms_B1, arms_E2, arms_E1, arms_F2, arms_B2` — `[A-Za-z0-9_]` only; built once per
  question by replaying the loader's view to `ask_time`, reused across the three repeats
  (NFR-005), dropped after the third; the ledger records nodes/edges/episodes/links loaded per
  question; `search(group_ids=[...])` always explicit; **validity-timestamp filtering at query
  time is forbidden** (a static test greps the G module for `valid_at`-based filters).
- **Rationale**: rubric §2 — state as of, never filtered. RQ-6a: a hyphenated `group_id`
  silently zeroes BM25 on FalkorDB (#976); RQ-6b: unscoped search does not span groups.
- **Alternatives considered**: one graph with validity filtering (forbidden by §2).

## D-4 — R's retrieval unit and assembly (01M3AX1NPS0QW9VGAQYQ0H4J09)

- **Decision**: R = the **full entity set** as of `ask_time` as records (structured half, always
  present, placed after events like D) + **top-k vector retrieval over events**, one event per
  chunk, embedded from the same text form every arm uses (D-7); k counts events only. Retrieved
  events are **re-sorted into `ask_time` order** before insertion (chronological, then entities),
  so R's layout matches D's and R's cache prefix is meaningful; the retrieval rank order is
  recorded per cell in the ledger, not shown to the model.
- **Rationale**: "vector-RAG + structured records" (§2); layout parity with D keeps the two flat
  arms comparable and keeps R's cache measurable.
- **Alternatives considered**: rank-order assembly (rejected — destroys the prefix property and
  makes R's layout differ from D's for no retrieval reason).

## D-5 — Sampling and output limit (01M3AX1QA44C6VMP2VFGPHTYF0)

- **Decision**: Qwen3 non-thinking recommended settings, fixed for every cell of a ledger and
  recorded in its header: `temperature 0.7, top_p 0.8, top_k 20, repeat_penalty 1.05, min_p 0`.
  Seed policy: **fixed seed per repeat index**, `seed = 1000 + repeat` (1001/1002/1003), identical
  across arms and questions. `max_tokens 2048`; `finish_reason` recorded per cell and a `length`
  finish **flagged** — a scored answer with a flag, not an error.
- **Rationale**: three repeats measure variance only if sampling is fixed; matched seeds per
  repeat make the variance across repeats the same sampling variance across arms; an unbounded
  output makes a truncated answer indistinguishable from a short one (R2).
- **Alternatives considered**: greedy decoding (rejected — the rubric wants repeat variance);
  per-cell random seeds (rejected — unmatched across arms).

## D-6 — D-YaRN secondary configuration (01M3AX1RW8BES14RKDBQ4NYYVF)

- **Decision**: llama.cpp `--rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 262144
  --ctx-size 393216`. Everything else identical to the primary (GGUF sha, image digest, sampling,
  seeds, prompt hash, layout, cache on, embedder/reranker). Header fields that differ:
  `rope_scaling=yarn, rope_scale=2, yarn_orig_ctx=262144, n_ctx=393216` — SC-006 asserts exactly
  these. The secondary runs its **own context-window gate** at that configuration before its
  first cell (peak GTT, prefill and generation rates at ~363k), as gate (b) did for the primary.
- **Rationale**: factor 2 is the smallest that covers B2 (362,772 < 524,288) and perturbs less
  than factor 4; 393,216 gives headroom over B2 without paying for 524k.
- **Alternatives considered**: factor 4 / 1M (rejected — more perturbation than needed).

## D-7 — The shared text form (implementer's call; design lead reviews at post-plan)

- **Decision**: the **rendered JSON line** of an event (`json.dumps(event, sort_keys=True)`) is the
  single text form for every arm — D's dump line, R's chunk, G's `EpisodicNode.content`. Entities
  likewise as their JSON records. One function, `arms849.text.render_event_text`, used by all
  three, with a test asserting the three arms' texts for any `ref` are byte-identical.
- **Rationale**: D-4 says "the same natural-language rendering the renderer produces for D's
  dump" — but the renderer produces **no** natural-language rendering; D's dump, gate (b) and the
  362,772-token measurement were all JSON lines. Adopting an NL rendering now would change what
  §5 counts and re-measure §2 for every question. The JSON line is what was frozen and measured.
- **Alternatives considered**: a natural-language rendering per channel (deferred — a §2
  re-measurement, not a corpus change; the design lead can rule it in at post-plan and IC-01
  absorbs it as one function change).
- **Disposition**: flagged to the design lead on the bus at 23:49Z; open until post-plan.

## D-8 — Oracle-isolated execution environment (implementer's call; FR-013)

- **Decision**: the run executes from `build/849-run-env/`, a `git archive` export of the mission
  branch at the run commit with `docs/design/research/849-synthesis/oracle/` **excluded**. The
  harness locates its own repo root and refuses to start if that path exists. Separately, a
  static test scans every module under `scripts/research/arms849/` for the string `oracle` and the
  oracle path, and the harness runs the same scan at start. Both refusals print what they found.
- **Rationale**: "enforced twice" (DM4): an arm cannot read what is not there, and a module that
  names the path is refused before it could run. An export beats a worktree because a worktree
  cannot have a tracked directory absent without a commit.
- **Alternatives considered**: a worktree with the directory deleted (rejected — dirty tree, and
  `git checkout` restores it); trusting review (rejected by DM4).

## D-9 — Sandbox envelope on office4 (implementer's call; FR-018 — recorded BEFORE any container runs)

- **Compose project**: `arms849`. **Network**: `arms849-net` (bridge, internal). **Volumes**:
  `arms849-falkor` (FalkorDB data; dropped at teardown). **Ports** (all bound to `127.0.0.1`
  only — never a tailnet interface): FalkorDB `16379`, llama-server `18080`. **Images**: FalkorDB
  `falkordb/falkordb@sha256:9042fdc4…` (the #974/#976 digest, full value verified at setup and
  recorded in the run record); llama.cpp `ghcr.io/ggml-org/llama.cpp@sha256:063e88aef1c168cf4a0a4b3a7983604561f96870a3c4953bd1fad908b4e41716`.
  **Model**: `~/models/gguf/unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF/…UD-Q4_K_XL.gguf` mounted
  read-only. **Resource ceiling**: peak GTT ≤ 57.5 GiB (NFR-004; measured 51.33 at n_ctx
  262,144); `--parallel 1`; `/dev/dri` with render gid 992. **Duration**: the primary and
  secondary runs; the model may stay resident between cells and between sessions (DM1).
  **Teardown**: `docker compose -p arms849 down -v --rmi all` then verify no containers, volumes,
  networks or images matching `arms849|falkor|llama` remain and GTT is back under 2 GiB; the GGUF
  is kept. **Touches**: no production state, no credential, nothing on office2.
- **Rationale**: the deploy discipline's carve-out is conjunctive and self-certified; this note is
  the certification, and it exists before the first `docker run`.

## Supply chain (DIRECTIVE 051 — advisory, recorded)

| Dependency | Source / authenticity | Pin | Lifecycle scripts | Disposition |
|---|---|---|---|---|
| `graphiti-core` | PyPI (getzep) | `==0.30.2` — the version #974 measured; RQ-6 defects known and mitigated | none (pure Python) | accepted |
| `falkordb` | PyPI (FalkorDB) | `==1.7.1` — as #974 | none | accepted |
| `fastembed` | PyPI (Qdrant) | `==0.8.1`; model `BAAI/bge-small-en-v1.5` fetched once from HF at setup, sha recorded in the run record | none; downloads a model file at first use — done at setup, not at run time | accepted |
| `openai` | PyPI | `==3.19.2`; used only as a client to `127.0.0.1:18080`; no API key set, and the harness asserts none is present in the environment | none | accepted |
| `transformers` | PyPI (HF) | tokenizer classes only, no torch; the Qwen tokenizer files fetched once at setup from `Qwen/Qwen3-Next-80B-A3B-Instruct`, sha recorded | none | accepted — needed for client-side token counts (FR-006) |
| `falkordb/falkordb` image | Docker Hub | by digest (#974/#976), verified at setup | n/a | accepted |
| `ghcr.io/ggml-org/llama.cpp` | GHCR | by digest, already re-pulled and verified on office4 | n/a | accepted |

All installs go through `uv pip install --python .venv/bin/python` with exact pins; no
`preinstall`/`postinstall` hooks apply (Python ecosystem); nothing runs with network access after
setup except the two local containers.

## Adversarial evidence (contracts/adversarial-evidence-contract.md)

Challenge pass run by the implementer against the dependency and isolation decisions before
claiming plan readiness; each contested finding's disposition:

| # | Contested finding | Disposition |
|---|---|---|
| A1 | "graphiti-core 0.30.2 is a known-defective version (RQ-6); why not a newer one?" | **accepted as is** — it is the version #974 measured and the design lead ruled; the three defects have local mitigations (no hyphens; one query per label; loader-side pair validation) and a newer version would invalidate #974 as the reference. Recorded in D-1/D-3. |
| A2 | "`transformers` pulls a large dependency tree for a tokenizer" | **changed** — install with `--no-deps` plus `tokenizers`/`huggingface-hub` only; assert no `torch` in the venv. |
| A3 | "An export-based run environment can drift from the committed code" | **changed** — the harness records the export's source commit and refuses if the working tree at that commit differs from the export (hash of the exported file list). |
| A4 | "The `openai` client could read `OPENAI_API_KEY` from the environment and call out" | **changed** — the harness asserts the variable is unset and the client base URL is `127.0.0.1`; a set key is a refusal, not a warning. |
| A5 | "FastEmbed fetches a model at first use — a run-time network call" | **changed** — model fetched at setup, cached, sha recorded; the run asserts the cache is present and never fetches. |
| A6 | "The JSON text form (D-7) leaks field names that hint at structure" | **deferred_with_rationale** — every arm sees the same text, so it is not a between-arm leak; whether it flatters all arms equally is a §2 question for the design lead at post-plan, noted in D-7. |

No contested finding was dropped.
