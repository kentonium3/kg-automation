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
- **Registered (A4 @c980e812, closing Codex blocker A-2)**: the replay-visible records (entities
  AND edges) are always present as the structured half; top-k is over events only; §2's earlier
  wording is superseded, dated.

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

## D-7 — The shared text form, enforced at final assembly (implementer's call; design lead reviews)

- **Decision (as corrected by the design lead's re-review, 00:05Z)**: one module, `arms849.text`,
  returns **frozen bytes, never a re-dump**: an event's line is the exact line from
  `stream.jsonl` for its ref; entities and edges get ONE canonical line each, produced once by
  the loader from `entities.json` at load time (the only re-serialisation), digest recorded in
  preflight; `render_block` only concatenates, at the **point of insertion into the prompt slot**,
  and the harness counts the exact assembled bytes/tokens of what was inserted. D's dump is the whole replayed
  view: events, then entities, **then edges** (Codex blocker H-1: edges were omitted, so D was not
  the full dump and the flat arms lost relationships G received). R's records block is the same
  entity+edge block. G's `EpisodicNode.content` is the event's rendered line.
- **Rationale**: the renderer produces no natural-language rendering; the JSON line is what was
  frozen and measured. Enforcing at assembly (not at storage) is what makes the byte-identity test
  meaningful (Codex major H-2).
- **Alternatives considered**: NL rendering (deferred — a §2 re-measurement, design lead's call);
  storage-time equality only (rejected — the test could pass while prompt text diverged).
- **Consequence for §2 (A4 ruling)**: the §2 token table is re-measured on the final assembled
  bytes (exact serialised request) at code freeze, before the primary run; I post the table, the
  design lead registers it as a dated amendment-log line. The six-of-eight finding cannot flip
  (edges only add tokens).

## D-8 — Oracle-isolated execution boundary (implementer's call; FR-013)

- **Decision**: the arms execute **inside a runner container** (the repo's Python image built
  from the pinned base, with the venv) whose **only** bind mount is the export directory —
  `~/.cache/arms849/run-env/` by default (`ARMS849_RUN_ENV`), **outside the repo tree**, because
  the export is a full repo copy and the pre-commit secret scan walks even gitignored `build/`
  (learned live in WP02: an export under `build/` aborted every commit on the test fixtures'
  fake secrets) — a
  `git archive` export of the mission branch at the run commit with
  `docs/design/research/849-synthesis/oracle/`, `seed/`, the two narrative files
  (`00-context-chains.md`, `01-cast.md`), `849-lattice-scenario-arcs.md`, `849-traceability.md`
  and the oracle's appendix **excluded** — plus the corpus directory read-only and the ledger
  directory read-write. The container is on the compose network with the two services and has no
  other network. A **denied-access test** run from inside the container asserts that the original
  checkout path, the oracle, the seeds and the narrative files do not exist and that the
  filesystem outside the mounts is the image's own. The static scan of `arms849/` for the strings
  `oracle`, `seed/`, `traceability` and the export's **content** manifest sha (not filenames)
  are recorded in the header.
- **Rationale**: Codex blocker D-1 — an export beneath the full checkout is not a boundary: the
  parent checkout stays reachable, and seeds and commentary carry answer-bearing material. A
  container with an allowlisted mount is a boundary the test can prove.
- **Alternatives considered**: export under the checkout (rejected as above); a worktree
  (rejected — a tracked directory cannot be absent); chroot/user separation (viable but the
  container already exists for the services and is the simpler proof).

**Dated note (2026-09-25, design-lead ruling on the WP02 review loop):** the static scan
under FR-013 is *defense in depth* — its scope is **literal structure only**: every expression
built from literals and operators is evaluated by Python itself, in a child process under
memory/CPU/time limits that fail closed, with the pure/opaque split computed over
`ast.expr.__subclasses__()` and asserted by test. A module that assembles a forbidden path at
runtime through names, calls, attributes or comprehensions is outside the scan's scope **and
still cannot read anything**: the **runtime boundary is load-bearing** — the export physically
lacks the excluded material and the in-container self-test proves every excluded path absent
under every data mount, every mount's type/source/content, and the host checkout unreachable.
A review finding of a further evaluator construction is recorded as out of scope; a finding
against the runtime boundary is folded (as c10's docker `/etc` bind identity was).

**Dated closure 2026-09-25 (design-lead ruling, bus msg 20260925T192614559952Z2743cd9757, landed with the WP04
cycle-10 fold):** "literal structure" for the static scan = literals, operators, f-strings, containers,
subscripts/slices over them, PLUS, by construction: (i) a call whose func is a Name in a CLOSED pure-builtin
allowlist (str, bytes, bytearray, int, float, bool, complex, len, repr, chr, ord, tuple, list, dict, set,
frozenset, sorted, reversed, min, max, sum, abs, round, divmod, pow, hex, oct, bin, format, slice, range,
enumerate, zip, map, filter, any, all — never hash or id, which are process-salted) with every argument pure,
evaluated in the resource-limited child; (ii) a call whose func is an attribute on a pure receiver (any method
name, receiver purity recursive through evaluated calls) with pure arguments, evaluated in the child — a method
that raises or is absent is `ScanRefused`. Everything else is OPAQUE: a literal-only call to any other name
(`RuntimeError("…")`, `ArmRefusal("…")`, a decorator) is code and belongs to the runtime boundary; its pure
arguments are still scanned. The scan REFUSES a module that rebinds any allowlisted builtin name at any scope
(assignment, def/class, import alias, global/nonlocal, comprehension/with/except/for target). **Cycle-class
closure:** a further finding is folded only if it is a construction built from literals + operators + this
allowlist + methods of literals that the scan misclassifies (an implementation bug of this ruling). A finding
that needs a name binding, an import, or attribute access on a module is runtime-boundary territory, recorded
against D-8 as out of scope, and not folded (as ruled 2026-09-25 02:39Z).

## D-9 — Sandbox envelope on office4 (implementer's call; FR-018 — recorded BEFORE any container runs)

- **Compose project**: `arms849`. **Network**: `arms849-net` (bridge, internal). **Volumes**:
  `arms849-falkor` (FalkorDB data; dropped at teardown). **Ports** (all bound to `127.0.0.1`
  only — never a tailnet interface): FalkorDB `16379`, llama-server `18080`. **Images**: FalkorDB
  `falkordb/falkordb@sha256:9042fdc4…` (the prefix #974 recorded; **dated correction 2026-09-25:**
  `setup` pins the `v4.20.1` tag's resolved digest `sha256:1ec88626…` — the prefix does NOT match,
  the mismatch is recorded in `setup.json` (`falkordb_digest_note`), and the resolved digest is
  the one that runs; the original line is kept as history); llama.cpp `ghcr.io/ggml-org/llama.cpp@sha256:063e88aef1c168cf4a0a4b3a7983604561f96870a3c4953bd1fad908b4e41716`.
  **Model**: `~/models/gguf/unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF/…UD-Q4_K_XL.gguf` mounted
  read-only. **Resource ceiling**: peak GTT ≤ 57.5 GiB (NFR-004; measured 51.33 at n_ctx
  262,144); `--parallel 1`; `/dev/dri` with render gid 992. **Duration**: the primary and
  secondary runs; the model may stay resident between cells and between sessions (DM1).
  **Teardown**: `docker compose -p arms849 down -v --rmi all` then verify no containers, volumes,
  networks or images matching `arms849|falkor|llama` remain and GTT is back under 2 GiB; the GGUF
  is kept. **Touches**: no production state, no credential, nothing on office2.
- **Rationale**: the deploy discipline's carve-out is conjunctive and self-certified; this note is
  the certification, and it exists before the first `docker run`.

## D-10 — R's k calibration: population, procedure, durability (Codex F-1, F-2, E-1, B-3)

- **Decision**: calibration requires **all eight** G repeat-1 cells `ok`. If any G repeat-1 cell
  ends `error` after three attempts, the run **halts** before any R cell with
  `blocked: calibration_population_incomplete`, posts `blocked` to the bus, and waits for a
  registered disposition — never a partial or substituted population. Procedure, deterministic:
  for each question build R's replayed view; for candidate k = 1, 2, … compute R's assembled
  tokens (records block + top-k events, exact assembled bytes, availability-capped); choose the
  smallest k whose median over the eight questions lies **within the two-sided band 0.8×–1.2×**
  of G's repeat-1 median of `assembled_context_tokens` (A4 reconciliation); ties to the smaller
  k; if no k reaches 0.8× within availability, record `k = max available` and
  `parity: infeasible`; if the records block alone already exceeds 1.2×, record
  `parity: unattainable` — never silently accepted. Written once as a **`calibration` record**
  (a ledger line, not a header mutation) carrying k, the eight G medians, the eight R medians at k,
  and the ratio per question; every R cell must find it before running; a resume reads it back.
  Every R `ok` row carries `r_g_ratio` = R's assembled tokens ÷ G's repeat-1 median for that
  question, or `"unavailable"` with a reason (never 0, never null).
- **Rationale**: A3 fixes the population as G repeat-1 medians; the rest was unspecified and two
  implementations could pick different k while both claiming compliance.

## D-11 — Context limits and token counting (Codex G-1, A-5)

- **Decision**: three limits, distinct: **trained** (262,144, primary gate), **configured**
  (`n_ctx`: 262,144 primary, 393,216 secondary), **permitted** = configured − `max_tokens`
  (2,048). The arm counts the **exact serialized request** (chat-templated, special tokens
  included) with a tokenizer whose equivalence to the served GGUF is **validated at setup**: 100
  corpus lines tokenized client-side and via the pinned server's `/tokenize`, identical or the
  setup refuses. Primary: refuse (`exceeds_model_context`) when the count exceeds the trained
  limit; secondary: when it exceeds the permitted limit. All eight secondary cells are asserted
  to fit under 393,216 − 2,048 by test before the secondary runs.
- **Rationale**: server acceptance proves nothing; an upstream tokenizer is only usable once shown
  equal to the served one; the secondary would otherwise refuse the six cells it exists to run.

## D-12 — Attempt durability and torn-tail recovery (Codex E-3, C-4)

- **Decision**: an `attempt_start` row is appended **before** every attempt (key + attempt + ts);
  a death mid-attempt therefore leaves evidence and counts toward FR-007's three. On open under the
  lock, the reader accepts exactly one malformed **final** line (a torn append), truncates it,
  records `recovered_torn_tail` in the header's recovery log, and rejects any interior malformed
  line as corruption. A test kills the writer mid-line and resumes.

## D-13 — Telemetry mapping, cache state, memory attribution (Codex I-1, C-3, B-2)

- **Decision (corrected 2026-09-25 after Codex WP01 cycle 2)**: llama.cpp `/completion`
  `timings` map: `prompt_n` = prompt tokens **processed** this request — it already **excludes**
  cache hits; `cache_n` = tokens reused from the prompt cache; `prompt_ms`/`predicted_ms`/
  `predicted_n` → prefill_s / generation_s / output tokens. So **total prompt = `prompt_n +
  cache_n`**, `uncached = cache_write = prompt_n`, `cache_read = cache_n`, `cache_fraction =
  cache_n / total`. (The first text said `uncached = prompt_n − cache_n`, which subtracts the
  cache twice and goes negative on any warm request; the code carried the same error until
  the review caught it with the fixture `prompt_n=1, cache_n=236`.)
  A scored row is **refused** if any of these is absent. `cache_state` per cell is classified
  from observation: `cold` if `cache_n == 0`, `warm` otherwise, with `cache_fraction` recorded;
  "repeat 1 = cold" is a prediction, never a label. Server restarts and `/slots` cache clears are
  recorded as `event` rows in the ledger. Memory: `peak_gtt_gib` sampled at 1 Hz during the
  attempt (serving process) **and**, for G, `falkordb_rss_peak_mib` sampled over the per-question
  build+retrieval window — the two labelled §5 measures.

## D-14 — Prompt digest and question manifest (Codex B-4)

- **Decision (per A4 @c980e812)**: `arms849.prompt.REGISTERED_TEXT` is the §3.2 text as it
  stands, with the literal slots `{assembled_context}` and `{question_text}`; digest = sha256 over
  UTF-8 bytes after normalisation (CRLF→LF, per-line trailing whitespace stripped, exactly one
  trailing newline) = `0aa7ee77560b1f5cbbb04a6c3dfa90749dfd79305b4207134c62d9fdd733af45`,
  registered in §3.2 by the design lead; the gate compares to that **constant**. Question texts
  live in `scripts/research/arms849/questions.py` (id, `ask_time`, text) and must digest to the
  §3 constant `fe17beef263777261e5d623ed8362ebaaada60ffbb0fd20b10b1f4d7a820c462`; neither digest
  is ever computed-then-stored.

## D-15 — Deterministic G assembly (Codex C-5)

- **Decision**: assembly order: typed constraint pulls (label order Capacity, Commitment,
  Principle, Interest), then hybrid-search hits, then anchored expansions per anchor (anchors in
  resolution order); within each group ordered by (score desc, uuid asc); de-duplicated by uuid;
  cut at 60. The assembled-context sha256 is recorded per cell and asserted equal across the three
  repeats and across a resume (NFR-005). Zero anchors → the search-only path (§2 A3), recorded.

## D-16 — Ledger binding includes code and questions (Codex E-2)

- **Decision**: the header records sha256 of every file under `scripts/research/arms849/` plus
  `run_849_harness.py` and `load_849_corpus.py` (content, not names), the question-manifest
  digest, and the export's content manifest; a resume compares all of them and refuses on any
  difference — changed retrieval code or question wording can never append to an existing ledger.

## Codex post-plan checkpoint — dispositions (2026-09-24 23:58Z; 7 blockers, 17 majors)

| Codex finding | Disposition |
|---|---|
| H-1 edges omitted from D/R | **changed** — D-7 |
| A-2 R population vs §2 | **changed** — registered by A4 @c980e812 (records always + top-k events); D-4 |
| A-3 zero anchors | **changed** — spec edge case now A3 verbatim; D-15 |
| A-4 resolution paths | **changed** — IC-03 names all A3 paths + ambiguity rule |
| D-1 export not a boundary | **changed** — D-8 container with allowlisted mounts + denied-access test |
| D-2 freeze gate vacuous in export | **changed** — IC-07 preflight from the full checkout, results bound |
| C-1 grading view has no repeat dimension | **changed** — contracts/grading-view.md per-cell blinded ids |
| C-2 classifications identify D | **changed** — admin report separate from the view |
| F-1 calibration population incomplete | **changed** — D-10 halt rule |
| F-2 k derivation unspecified | **changed** — D-10 procedure |
| E-1 header mutation for r_k | **changed** — D-10 calibration record |
| E-2 resume binding lacks code/questions | **changed** — D-16 |
| E-3 torn tail | **changed** — D-12 |
| C-4 attempt starts not durable | **changed** — D-12 |
| G-1 tokenizer equivalence / exact request | **changed** — D-11 |
| A-5 trained vs configured limit | **changed** — D-11 |
| C-3 cold/warm by repeat index | **changed** — D-13 observed classification |
| I-1 telemetry mapping | **changed** — D-13 |
| B-2 memory measures | **changed** — D-13 |
| H-2 text form at assembly | **changed** — D-7 |
| B-4 prompt digest / question manifest | **changed** — D-14 |
| C-5 G assembly determinism | **changed** — D-15 |
| J-1 IC-07/IC-08 cycle | **changed** — IC-08 (code) / IC-09 (execution) split |
| B-3 R/G ratio field | **changed** — D-10 row field with explicit unavailable state |

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
| A6 | "The JSON text form (D-7) leaks field names that hint at structure" | **ruled out of scope by the design lead (A4)** — identical for every arm, so not a between-arm confound; JSON-vs-prose absolute effect is unmeasurable without a prose arm and goes to the findings' Threats section as a stated limitation. |

No contested finding was dropped.
