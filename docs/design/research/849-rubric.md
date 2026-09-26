---
title: "#849 rubric — pre-registration"
doc_type: research
status: draft
owner: claude-macbook (design lead); reviewed by claude-office4; registered 2026-09-24
last_updated: 2026-09-25
---

# #849 rubric — pre-registration (REGISTERED 2026-09-24)

**Status: REGISTERED.** Reviewed build-side by claude-office4 (measured answers folded at
`3f7213e8`); §7 confirmed by Kent 2026-09-24; posted to
[#849](https://github.com/kentonium3/kg-automation/issues/849) as the pre-registration on
2026-09-24 17:03Z, before any run; Kent confirmed it on the issue ("I agree with all as stated").

**Frozen corpus (Amendment A1, 2026-09-24 18:15Z): `c0b35cd1`** — rendered fingerprints
`stream.jsonl` sha256 `188b9bf1402645c5a015da01bd3241376a1914e25aacad8a529a84b10a290d4a`,
`entities.json` sha256 `22532e50297a8594f358376919ce38bde3db3bce3f015d9e2dd9fb5ce0c9a9df`,
`loader_links.jsonl` sha256 `826fa4544085055a689298b117b5c5ecb4a596cdfe132b6af8c85418cc1302ee`;
5,750 events / 66 entities / 22 loader links. A run that reproduces different fingerprints is not
running the frozen corpus. Changes to this document after registration are amendments, dated and
reasoned, never silent edits — see the amendment log at the end.

*Superseded registration:* `b203907e` (17:03Z) — `stream.jsonl` identical; `entities.json` was
`c1962d4d7ceb623c…` and carried `arcs` authoring metadata on Person nodes; `loader_links.jsonl`
did not exist. Reason for A1: the loader-side structural pass (owed at freeze) found both. Rulings it encodes: Kent 2026-09-24 (§7 decision rule confirmed first-hand), Kent 2026-09-18 ("run both": both axes, both baselines, cost is
not a constraint) and 2026-09-18 corpus scope; design-lead refinements of 2026-09-24 (caching on,
token primitive, memory reported). Ontology: `docs/design/second-brain-graph-layer.md` at the commit named in the registration (≥ ffb8834d).

## 1. The bet under test

> Typed, traversable, bi-temporal structure lets retrieval assemble a **small, correct, complete**
> context for a question whose answer is scattered across months and channels — more correctly
> than the best non-graph retrieval, and at a per-question cost that scales with the *answer*
> rather than with the *corpus*.

Two things it does **not** test: whether office2 can host any arm (settled by ADR-0009), and
whether free-prose extraction works (no extraction is used in this run; the seed is structured).

## 2. Arms

| arm | what it is | fixed configuration |
|---|---|---|
| **G** — tuned graph | Graphiti + FalkorDB over the typed ontology, seeded by structured writes (no LLM) | node + edge hybrid retrieval; typed constraint pull, one query per label (`Capacity`, `Commitment`, `Principle`, `Interest`); anchored history expansion (entity → its episodes via `MENTIONS`); **no BFS by default**; `group_id` in `[A-Za-z0-9_]`; retrieval budget recorded per question. **Query plan (A3):** anchors are derived **from the question text** by deterministic resolution against the loaded entities (names/aliases → Person; commitment and outcome descriptions by exact or normalised match; typed labels for the constraint pull) — never from a per-question list, which would be the oracle leaking through configuration. Per question: resolve anchors → hybrid search on the question text → typed constraint pull → anchored history expansion per anchor → assemble, under a fixed cap of **60 items** (nodes + edges + episodes), set once; the ledger records the anchors resolved, the plan, and the actual count. Zero anchors → search-only path, recorded |
| **D** — full dump | the entire corpus (rendered seed + full stream) in the prompt, in the ruled **native** configuration | prompt caching **on**; hit rate logged. **(A2)** Where the prompt exceeds the model's trained context (262,144 tokens on Qwen3-Next-80B: F1, B1, E2, E1, F2, B2) the cell is recorded as `exceeds_model_context` with the measured token count — never a zero, never a truncated run |
| **R** — vector-RAG + records | **(A4)** the replay-visible **records** (entities and edges, as of ask_time) are always present as R's structured half, placed after events like D; **top-k embedding retrieval over events only** | ONE global k; the per-question ratio R_context / G_context is a reported column (explicit `unavailable` when G's figure is missing) so a parity breach is visible, never silent; caching on for any stable prefix. **k procedure (A3, made deterministic in A4):** arm-major order G → D → R; after all eight G repeat-1 cells are `ok`, for each question build R's view and compute R_context(k) = tokens of the *exact assembled text* (records block + the k top-ranked events re-sorted chronologically — *chronologically* meaning by each event's **position in the replayed view** (stream order), never a literal (at, ref) sort, so R's events are always a subsequence of D's dump [clarified 2026-09-25 18:50Z: the A4 ordering ruling in words; the WP07 prompt's "(at, then ref)" wording is the dated side]), same tokenizer and bytes as the request; k = the **smallest** integer whose median over the eight questions lies within ±20 % of G's repeat-1 median; per-question availability caps recorded; if no k satisfies (the records block alone exceeds the band) the run records `parity: unattainable` with the closest k and continues; written once as a durable `calibration` record and recovered before any R cell; if any G repeat-1 cell ends `error` after three attempts the run halts for a registered disposition |

Common to all arms: the **same reasoning model**, the **same fixed prompt**, the **same question
wording**; the arm assembles context, the model answers; nothing else differs. The model and its
provider are recorded, not prescribed (per-function seam, §Tool Selection). **Assembled context**
= the input tokens of the assembled block, excluding the fixed prompt and the question; that is
what the cost axis counts.

**Question order is protocol.** Questions are asked in `ask_time` ascending order (C1, A, F1, B1,
E2, E1, F2, B2). Under the time-cut each D prompt's **event section** is then a prefix of the next's (the records block that follows it is re-emitted per question — clarified 2026-09-25 18:52Z), so D's cache hit
rate is a property of this protocol and is reported as such; a random order would collapse it and
the number would be an artifact of an unstated choice.

**Prompt layout is protocol (A1).** The event stream comes first and the entity block after it.
Entities change at A, F1 and E1 as Decisions become visible under the replay rules, so
entities-first collapses the cache prefix to ~0 % for those three questions; events-first keeps
every step a token-level prefix extension of the event section (measured with the Qwen3-Next tokenizer: A 35.3 %,
F1 50.5 %, B1 94.7 %, E2 87.3 %, E1 91.1 %, F2 99.9 %, B2 99.7 % of the prompt reused).

**Replay rules (A1, measured on the frozen corpus):** a Decision is visible only from its
`decided_at` (DEC_F_RESTART, decided 09-21, would otherwise answer F1 asked 08-10); a `DECIDED`
edge inherits its Decision's `decided_at` and is withheld with it — an edge naming a withheld
decision leaks its existence and disposition while pointing at an id the arm cannot resolve.

**Prefix sizes on the frozen corpus** (`c0b35cd1`, real tokenizer, 2.32 chars/token for
JSON-dense text — a prose ratio under-counts by ~40 %):

| Q | events | tokens |
|---|---|---|
| C1 | 772 | 51,398 |
| A | 2,184 | 139,451 |
| F1 | 4,313 | 272,863 |
| B1 | 4,558 | 288,041 |
| E2 | 5,216 | 329,415 |
| E1 | 5,720 | 361,170 |
| F2 | 5,730 | 361,659 |
| B2 | 5,750 | **362,772** |

**Arm D and the model's context (Amendment A2, Kent 2026-09-24).** The ruled model's trained
context is 262,144 tokens (`max_position_embeddings`, no RoPE scaling). Six of the eight D
prompts exceed it, the largest by 100,628 tokens; memory is not the limit (weights + KV ≈ 51 GiB
of 62.5 GiB GTT — 12 of 48 layers carry KV), the wall is positional, and output past it would be
silently degraded. The ruling:

- **Primary run:** all three arms in the native configuration. D runs on C1 and A. On F1, B1,
  E2, E1, F2, B2 the D cell is `exceeds_model_context` (could-not-check, Engineering Principle
  14), reported with the token count and excluded from every average.
- **Pre-registered expected result:** *on this life-sized corpus (~363k tokens at the last
  question) the full-context approach hits a positional wall that the graph and RAG arms do
  not.* This is a finding about where flat context stops scaling, stated in tokens, and it counts
  whichever way the scored cells come out. It is registered here, before the run, so it cannot
  be read as post-hoc.
- **Secondary run, after the primary and never interleaved:** **D-YaRN** — the same weights
  served with Qwen's documented YaRN/RoPE scaling to cover 362,772 tokens, on all eight
  questions, reported in its own table as a *different serving configuration*. It answers "what
  would a full dump have given"; it is excluded from the §7 decision rule; its cache, memory and
  tok/s are recorded so the cost of making D runnable is itself visible.
- Rejected: a truncated D (no longer an upper bound on recall); re-scoping the frozen corpus;
  YaRN for all three arms (moves G and R off the ruled model for a benefit only D needs).

The empirical gate runs at n_ctx 262,144 (the largest valid configuration) and records
configured n_ctx, peak GTT and tok/s at the longest prompt that fits.

**Three context limits (A4):** *trained* (262,144 — the model's `max_position_embeddings`),
*configured* (the served `n_ctx`), and *permitted* (what a cell may send). Primary: permitted =
trained. Secondary (D-YaRN): permitted = configured = 393,216, so all eight D cells run; the
secondary's own gate demonstrates all eight before its first cell. A cell exceeding its permitted
limit is `exceeds_model_context`; server acceptance beyond the trained limit is never relied on.

**Time-cut rule.** Every question is asked at its stream timestamp. An arm may only see material
with `created_at ≤ ask time`. For D this means the dumped prefix differs per question — that is
realistic, and the caching hit rate it produces is a finding, not a nuisance. **State as of, not
filtered:** G is built for each question by *replaying* primitives up to `ask_time`, never by
filtering a final-state graph — otherwise every current-state attribute (`Interest.status`,
`Task.scheduled_date`, `Outcome.status`) leaks the future. D and R likewise consume only rendered
material with `created_at ≤ ask_time`.

## 3. Questions

Eight, from the worksheet (`docs/design/research/849-lattice-scenario-arcs.md@f3076643`):

| id | arc | ask_time (ISO, America/New_York) | question_text (verbatim; the registered manifest) |
|---|---|---|---|
| C1 | C | 2026-04-28T09:06:00-04:00 | Fred just sent this. What is he referring to, and what do I owe him? |
| A | A | 2026-06-09T09:15:00-04:00 | Marcus just moved our Friday 1:1 to Thursday. Is that a problem, and what should I do? |
| F1 | F | 2026-08-10T09:00:00-04:00 | Am I keeping my non-negotiables? |
| B1 | B | 2026-08-17T09:00:00-04:00 | Am I on track for the October 5K? |
| E2 | E | 2026-09-04T17:00:00-04:00 | For this week's email across all three accounts: which should reach me, which become to-dos, which are digested, which are filed, and which are dropped? |
| E1 | E | 2026-09-21T09:00:00-04:00 | What recurring manual work am I doing that should be automated? |
| F2 | F | 2026-09-25T09:00:00-04:00 | When should this have been caught? |
| B2 | B | 2026-10-16T09:00:00-04:00 | Why did I miss sub-10? |

**Question manifest (A4; serialisation made explicit and digest re-registered 2026-09-25
00:22Z).** The eight rows above, in this order, are the oracle-free registry the harness reads.
Serialisation rule: for each row, the object `{"question": <id>, "ask_time": <the "T"-form ISO
string exactly as printed in the table>, "question_text": <verbatim>}`, rendered with
`json.dumps(row, sort_keys=True, ensure_ascii=False)`; the eight lines joined with `\n` plus one
trailing `\n`; sha256 of the UTF-8 bytes =
`fe17beef263777261e5d623ed8362ebaaada60ffbb0fd20b10b1f4d7a820c462`. (The earlier value
`4864c31c…` was computed on the oracle files' space-form timestamps and is withdrawn.) The
harness refuses if its manifest digest differs; the oracle files' `question_text`/`ask_time`
must equal these rows (checked by `check_849_oracle`, in the full checkout, never in the run
environment).

Each question's oracle block is the worksheet's `must_identify` list plus its explicit wrong
answers, held in the hidden oracle artifact and **never loaded into any arm**.

### 3.1 The hidden-oracle artifact — contract

One file, `docs/design/research/849-synthesis/oracle/<question-id>.yaml`, per question. The
grader and the traceability check consume it; no arm, renderer, or loader may import it.

```yaml
question: A                      # id from §3
ask_time: 2026-06-09T09:12:00-04:00   # the time-cut instant; arms see created_at <= this
question_text: "…"               # verbatim, as put to every arm
must_identify:                   # one entry per oracle point; each is binary at grading
  - id: A1
    statement: "the moved 1:1 (Thu 14:00–15:00) overlaps the PT session (14:30–15:15)"
    required_values: ["2026-06-11", "14:00", "14:30"]   # any of these missing = not hit
    traceability: [EP_A_MOVE, COM_PT_THU]               # rows in 849-traceability.md
wrong_answers:                   # asserting any of these = hard fail for the run
  - "a Thursday counter-offer earlier than 15:45"
near_misses: [NM_A_1, NM_A_2, …] # ids of the seeded decoys for precision scoring
grader_notes: "accept 'on or before 04-24' for the launch date (C3)"   # optional
```

Rules: `required_values` are the literal tokens a hit must contain — reserve them for dates
(ISO), times (HH:MM), counts and names, where a literal is the honest test; for verdict-shaped
points use `[]` and let the grader judge the statement, or list every acceptable token.
`traceability` must name existing **seed ids or declared emits** (below), nothing else; the
oracle checker (`scripts/research/check_849_oracle.py`) fails on an undeclared id or an empty
list. Per-miss classifications (counted / decided-then-silent, Arc B) and phase bands (Arc F)
live here, never in a seed; the artifact is committed under `oracle/` and the harness asserts
that directory is absent from every arm's input path before a run starts.

**Two-way emits contract (implementer, 2026-09-24; accepted).** Every seed declares
`meta.emits`: the rendered-event ids its generator **must** produce. This makes oracle
traceability checkable before the renderer exists, and binds the renderer: a generator that
drops a declared event fails the renderer test instead of leaving an oracle point silently
unverifiable. Shared sets (e.g. `SHARED_LATE_NIGHTS`) are declared by their owning seed and
referenced by dependants, which must not re-declare them. **Families:** an entry ending in `*`
declares a family (`GEN_B_WK*`); every emitted id must be a declared literal, a family member,
or a resolvable seed id, and a declared family with no members fails exactly as an unproduced
literal does (implementer, 2026-09-24; accepted).

### 3.2 The fixed prompt (registered text, A3)

Identical for G, D and R; the arm inserts its assembled context at the single slot and nothing
else varies. Authored by the design lead; wired in verbatim by the implementer; the harness
asserts the text's digest per run. **Registered digest (A4):** normalise as UTF-8, LF line
endings, trailing whitespace stripped per line, exactly one trailing newline, the two slots left
as the literal tokens `{assembled_context}` and `{question_text}`; sha256 =
`0aa7ee77560b1f5cbbb04a6c3dfa90749dfd79305b4207134c62d9fdd733af45`. The digest covers the
template; the exact serialised request is what token counts are measured on.

**Chat template (A4 clarification, 2026-09-25 00:46Z).** The ruled model is an instruct model
trained on its chat format, so the registered text is sent as the **single user turn** of the
model's own chat template (no system turn), with the template applied **client-side** through the
same Qwen tokenizer that counts tokens, and the resulting string sent as the raw `prompt` of the
native completion endpoint. This keeps the counted bytes equal to the sent bytes and leaves the
telemetry mapping untouched. The serving configuration records `chat_template_applied: true` and
the template's sha256; primary and secondary share it. Gate (b)'s memory and throughput figures
stand (the template adds a constant of a few dozen tokens); the §2 table is re-measured on the
templated request at code freeze.

```text
You are the assistant of the person whose records follow. You are reviewing their own
calendar, tasks, messages and notes to answer one question they have asked.

Use only the material provided below. Do not rely on outside knowledge about them, and do
not invent events, dates or people that the material does not contain.

Answer the question directly. State each finding as a specific claim, with the dates, times,
counts and names the material supports. Where the material does not establish something,
say "the material does not establish this" rather than guessing. Then say what you would
do next, and why, in their terms.

=== MATERIAL ===
{assembled_context}
=== END MATERIAL ===

Question: {question_text}
```

The prompt never mentions arcs, oracles, scoring, near-misses, or any question's
`must_identify` vocabulary. Grader notes in the oracle map answers *to* this shape; the prompt
does not map the shape to the oracle.

## 4. Axis 1 — correctness

Per question, per run:

- **Recall** = must_identify points hit ÷ points in the oracle. A point is hit only if the answer
  states it, with the specific value the oracle requires (a date, a count, a name). Partial credit
  is not given per point.
- **Decoys asserted** = the raw count of seeded near-misses the answer asserts *as the finding*
  (an integer; expected 0 — most such assertions are also hard fails below). A normalised
  precision ratio is **not** used: seeded-decoy counts range 2–6 per question (measured), so one
  assertion would cost 0.17 on B1 and 0.50 on C1, and the ratio is not comparable across
  questions or averageable.
- **Decoys seen and rejected** = the count of seeded near-misses the answer mentions and
  correctly rules out. This is the better signal: it separates an arm that retrieved the trap
  and reasoned past it from one that never saw it. Never penalised.
- **Hard fails**: any answer that proposes something the oracle names as a *wrong answer* (Arc F:
  a reward, badge, or public commitment; Arc A: a Thursday counter before 15:45; Arc C: binding
  Fred's message to the report thread) scores 0 for that run regardless of hits.
- Grading is **blind to arm**: answers are re-labelled per question; the grader holds the oracle.
  First pass by an LLM grader with the oracle in context; Kent spot-checks every hard fail and a
  random 25 % of the rest. **Grader independence (added 2026-09-25 23:06Z, design-lead coherence
  pass):** the grader MUST NOT be the model that produced the answers — all three arms share one
  reasoning model (§2), so that model may not also grade, and the grader's identity and version are
  recorded in the run record beside the arms'. A grader indistinguishable from the answering model
  is not a blind grade, whatever the labels say; Kent's spot-check is the backstop, not the control.
  Disagreements resolve to Kent.

## 5. Axis 2 — cost

Per question, per run, per arm — recorded, never estimated:

- **input tokens per correct answer** = total input tokens ÷ points hit (the primitive), with
  sub-columns **cache-write / cache-read / uncached**. *Clarification (2026-09-25, D-13 corrected):*
  from llama.cpp `/completion` `timings`, `prompt_n` counts tokens **processed** this request and already
  excludes cache hits, so total input = `prompt_n + cache_n`; cache-read = `cache_n`; uncached = cache-write
  = `prompt_n`; hit rate = `cache_n / (prompt_n + cache_n)`. No quantity is derived by subtracting the cache;
- output tokens; wall-clock latency from question to answer, **reported at the context length the question ran at** (A3: prefill throughput fell 630 → 154 tok/s cumulative and generation 43 → 20 tok/s between 16k and 256k on the ruled model, measured in `849-synthesis/gate-b-context-window.md`), never as one figure per arm;
- **peak memory**, two labelled columns: *per question* for D and R inference (the KV cache
  scales with the prefix, ~7× across questions), sampled from the serving process during the
  question; *per run* for G's graph store, which is dominated by the loaded graph and near
  constant per question. A number, not a pass/fail;
- D and R: prompt-cache **hit rate** under the time-cut arrival pattern — **load-bearing** for D (A3): with ask_time ordering and events-first layout, later questions reuse 87–99.9 % of their prefix (the reusable prefix is the **event section**: the records block follows the events and is re-emitted per question as entities and edges appear, so the cacheable prefix ends where the events end — clarified 2026-09-25 18:50Z after Codex's WP06 c4 note; the modules and tests already said so, the rubric's whole-prompt wording was the inaccurate side); the hit rate is the difference between a ~30-minute cold question and a seconds-long warm one. `cache_prompt` ON is the only valid D configuration. **(A4)** *cold* and *warm* are classified from **observed reuse** (`cache_read_tokens` from the server's timings), never inferred from the repeat index; every server restart and cache reset is a ledger event. **Telemetry mapping (A4):** the cost columns come from the pinned server's `timings` object (prompt token count, tokens served from cache, predicted token count, prompt and generation milliseconds), validated once against the pinned image at setup; a scored row is **refused** when a required measurement is absent, never filled with a plausible value. Client-side token counts are validated against the pinned server's `/tokenize` at setup (tokenizer equivalence) and count the exact serialised request including the chat template; the configured output allowance is reserved inside the permitted limit.
- **Memory (A4), two measures with defined windows:** *inference* — peak memory attributed to the serving process, sampled at 1 Hz from request start to response end, per cell (D and R); *graph store* — peak memory attributed to the graph-database process from the question's load through its last query, per question (G). Neither is a pass/fail; both are columns. **Clarified 2026-09-25 22:07Z (design lead):** where this section earlier frames the graph-store figure as *per run*, that line describes its expected VARIANCE (dominated by the loaded graph, near constant across questions), not a second measure — the per-question definition here governs, and a 1 Hz series sampled across the whole run satisfies both readings. Both columns are PROCESS-level measures: an allocator-reported figure (e.g. the graph database's own `INFO memory`) is not interchangeable with process RSS and may not be recorded under an RSS column name; substituting it requires renaming the column and a dated amendment here. **Ceiling guard and its residual (added 2026-09-25 22:41Z, design-lead ruling on the WP08 cycle-3 finding):** the 57.5 GiB ceiling (NFR-004: a 62.5 GiB budget with at least 5 GiB headroom, so exactly 57.5 is compliant and a breach is strictly above it) is checked immediately before a request is sent — after the request has been serialised and counted, at the last point the protocol controls — and again across the cell's sampling window. A residual window remains between that final check and the socket write; it is not zero, and no guard placed in the client can make it zero. Therefore the **recorded per-cell peak is the authoritative figure** for NFR-004 and for the memory column; a passing pre-send reading is a precondition for sending, never evidence that the cell stayed within budget. An unreadable sampler is could-not-check and refuses the cell; it is never recorded as a pass or as zero. **Window reconstruction (added 2026-09-26 02:25Z, design-lead ruling):** both sampled memory columns are reconstructed from a 1 Hz series by SAMPLE-AND-HOLD. The window is CLOSED at both ends, [start, end]: its readings are every reading in [start, end], plus a HOLD — the last reading STRICTLY BEFORE the start, of which there is at most one (clarified 2026-09-26 02:28Z; the earlier phrasing "at or before" made a reading exactly at the start satisfy both clauses, which under-reported a tie). The alternative (in-window readings only, `None` when there are none) would refuse a cell for a sampling artifact rather than for anything about the run, since an unreadable required sampler stops the cell. Sample-and-hold can over-attribute memory observed just before a window to that window; that bias inflates the graph arm's reported cost and so runs AGAINST the hypothesis under test, which is the direction to choose when a choice must be made. The held reading must be fresh at BOTH ends — no more than the registered gap tolerance before the window start, and the series no staler than the registered tolerance at its end — otherwise it is a gap and the sampler fails closed. Each reported peak records its support: the number of in-window samples, the window bounds, and whether the peak came from a held pre-window reading or from a sample inside the window.

Dollar conversions are derived afterwards from the token columns for any provider; they are not
what is scored.

## 6. Repeats and variance

**3 runs per arm per question** (72 runs). Report mean and range. Two arms are *indistinguishable*
on a question when their ranges overlap. #844's single-run fragility (Threats §3) is what this
fixes.

## 7. Decision rule (confirmed by Kent, 2026-09-24)

Read on the 8 questions, using recall as the primary and the decoy counts as the tie-break.
**(A2)** G vs R is read on all eight; G vs D only on the questions where D exists in the native
configuration (C1, A); the six `exceeds_model_context` cells are reported, not scored; D-YaRN is
reported separately and never enters this rule.

- **EARNS #693** — G beats R on a majority of questions, is not worse than D on any question
  beyond the repeat range, and G's uncached input tokens per correct answer are ≤ 20 % of D's on
  every question.
- **KILLS #693** — G loses to R on a majority of questions.
- **INCONCLUSIVE** — anything else; report which condition failed.

Reading rule for a non-EARNS result (Kent, 2026-09-18): a cost gap measured now is a **lower
bound**; the corpus only grows once the chain is in use. A "does not pay off yet" reading is
regime-bound the way #844's was, and the findings say so up front.

## 8. Threats from #844, and what closes each

| #844 threat | closure here |
|---|---|
| §1 under-seeded question | **traceability table before the run**: every oracle point maps to ≥ 1 seed primitive or episode. A point with no source is a corpus gap — fixed or dropped before freeze |
| §2 untuned graph arm | G configured per #974 RQ-5 (§2 above) |
| §3 no repeats | 3 per arm per question (§6) |
| §4 typed entities untested | typed ontology @0957c8f4, adapters-as-writers, validator not needed (no extraction) |
| §5 partial history | anchored expansion is a fixed part of G |

## 9. Seed and oracle invariants (checked at freeze)

- Seeds assert **primitives only**: no conflict, drift, pattern, cause, or target rate is ever an
  edge or a sentence. Late nights are single timestamped content-free episodes (Q3 ruling).
- Stream carries **raw handles**; `Person.aliases` holds the list; nothing is pre-resolved.
- `OUT_LAUNCH` status is never flipped to completed by a primitive (Arc C leak flag).
- Standing practices carry `EMBODIES`, no Outcome, no seeded rate (Q1 ruling).
- The oracle is a physically separate artifact; the harness cannot load it into an arm.
- **Freeze check, mechanical** (`scripts/research/check_849_seed.py`, 7a02e25d, extended per
  the design lead's 2026-09-24 review): (a) the vocabulary and structural-absence checks run
  over the **rendered corpus** the arms consume (D/R text, G's loaded nodes and edges), not only
  over seed YAML — loader-emitted edges are in scope; (b) in a sandbox that never touches an
  arm, the rendered corpus is grepped for every oracle `must_identify` phrase, every explicit
  wrong-answer phrase, and every seed comment line; each hit is adjudicated by hand as *leak*
  or *legitimately inferable primitive* and logged; (c) per-arc structural checks cover A, B, C,
  E and F as ruled on the bus; (d) every timestamp in seed data is tz-aware ISO (the time-cut
  rule depends on it). A non-empty unadjudicated hit list blocks freeze.
- **Recoverability probe** for every oracle point that is an *inferred pattern* (Arc A's missing
  travel blocks, Arc B's drift, Arc E's session shape, Arc F's slope): a deterministic, non-LLM
  script recovers the claimed structure from the **rendered** events (for E1: cluster mail actions
  by inter-event gap, order action types per session, ≥ 11 of 13 sessions share the shape with span
  ≈ 2 h). Recovered → the signal is present and an arm that misses it failed on merit. Not
  recovered → the corpus is too thin; add signal **before** any run. #844's seed-retrievability
  check, generalised. Probe results are attached to the registration.
- **Emits realised:** every id in every seed's `meta.emits` is present in the rendered corpus
  (renderer test), and every oracle `traceability` id resolves to a seed id or a declared emit
  (oracle checker). Both gate freeze.
- **Absence evidence cites the stream.** An oracle point whose evidence is an *absence* (a
  silent miss under completions-only, a missing travel block) cites the stream the absence is
  visible in (`GEN_B_SESSIONS`, `GEN_A_CALENDAR`), never a per-instance id — a per-instance id
  for an absent thing is a contradiction the emits contract will catch (implementer, 2026-09-24).
- **Prose is commentary, not seed.** Every id an oracle or the traceability table names must
  resolve in a *loadable* seed file (`seed/*.yaml`) or a declared emit. The narrative files
  (`00-context-chains.md`, `01-cast.md`) are the record of reasoning; nothing may trace to them.
- **Hint fields and generator strings are leaks too** (freeze gate, 2026-09-24): the vocabulary
  check is necessary, not sufficient. No rendered event may carry a generator instruction, a
  reason-for-the-miss sentence, a role tag (`emit`), a programme-relative `week`, or a field that
  encodes the test condition (`over_travel_block_min`). The freeze gate reads the rendered events
  by eye for this class as well as by grep.
- **Recoverability probes are code:** `scripts/research/probe_849_recoverability.py`, one probe
  per inferred-pattern arc, each with a can-fail test; results attached to the registration.
  `check_849_freeze.py` imports these; there is one implementation per probe.
- **Required-value presence** (the inverse of the leak grep): every oracle `required_values`
  literal appears in the rendered corpus. A leak makes a point too easy; a missing required
  value makes it unhittable, and nothing else would notice until an arm scored zero on it.
- **Emitted-id traceability:** an id the renderer produced that no oracle point can trace fails.
- **Rendered-view contract:** the stream is built from a **default-deny field allowlist** — a
  field not on it is stripped and reported; event ids are **opaque refs** (the id → ref mapping
  lives in the manifest, so a name like `EP_C_PROMISE` never tells an arm what an event is);
  loader wiring (`mentions`) is **not** in the stream — G links episodes to entities through the
  loader, and D/R are not handed that traversal. **(A1)** Entities are built from a per-kind
  default-deny allowlist owned by the renderer (L12: `arcs` was the first field through the
  gap); the loader wiring is written as `loader_links.jsonl`, registered by fingerprint, and is
  **arm G's input only** — D and R receive a view with links emptied, asserted by the harness.
- **Loader-side structural pass (A1):** `check_849_loader` verifies the three fingerprints,
  refuses any other corpus, replays to every `ask_time`, and checks the loaded graph for
  forbidden vocabulary, unregistered edge pairs and the arc-specific absences. **Four gates**
  (`check_849_seed`, `check_849_oracle`, `check_849_freeze`, `check_849_loader`) run in-process
  before any run; a failing gate raises and no ledger is created; a ledger is bound to the
  fingerprints and refuses to resume against different ones.
- Corpus frozen at a commit hash before the first run; the hash is in the registration.

## 10. Artifacts

`docs/design/research/849-synthesis/` — `00-context-chains.md`, `01-cast.md`, `seed/*.yaml`,
`stream/` (deterministic RNG for Arc E's mass, hand-authored scored events), `oracle/` (hidden),
harness code, `results/<run>.json`, grading sheet. Findings are written against this rubric.

### Preconditions for the run (added 2026-09-25 23:08Z, design lead)

Registered here rather than left in a working note, so the list outlives any one session. The
run's **first live cell of any arm** may not start until all four hold, and each is verified by a
test, not by assertion:

- **C4 — the isolation gate's inventory is complete.** `REQUIRED_MODULES` names every module of
  the run package, the three arms included, with a two-way test (every module in the package is
  registered, and every registered module is present). Without it a truncated export certifies
  isolation by scanning a smaller set than it should.
- **C8 — a live-style resume succeeds end to end.** A ledger created with timestamp-bearing gate
  records, closed mid-run, reopened by a fresh session that re-runs both gate phases, writes its
  own `session_gates`, and completes with the earlier rows intact and no double-recording. With
  the two negatives: a failing fresh gate stops and records; a session that skips the gate phase
  cannot write a row. Timestamp-stable fakes do not satisfy this — they are what hid the defect.
- **C9 — the graph-store memory series is wired end to end.** The host-side 1 Hz writer, the
  runner-side reader and the harness reading a G cell's peak from real samples, with the
  fail-closed conditions (absent, stale, gapped, wrong container) driven through the real path.
  Until it lands the G arm cannot run: its required sampler is unreadable and the harness refuses
  the cell, which is the correct failure and should not be mistaken for a bug at run time.
- **C11 — the ceiling guard runs at the last point the protocol controls.** A `before_send`
  callback invoked after the permitted-limit count and immediately before the request is sent,
  for every live cell, its exception propagating unwrapped with nothing sent.

One further item gates the **post-merge review** rather than the run: **C10** — every contract
sentence prescribed by an in-mission ruling must have landed before the review runs, because that
review works by checking merged code against those sentences. A review against a contract known
to be stale is not a check.


## Amendment log

| # | date (UTC) | what changed | why | frozen commit |
|---|---|---|---|---|
| — | 2026-09-24 17:03 | Registration | freeze verdict PASS | `b203907e` |
| A1 | 2026-09-24 18:15 | Entity allowlist (`arcs` stripped); `loader_links.jsonl` written, G-only; loader gate added; §2 replay rules, prompt layout, measured prefix tokens (B2 = 362,772) | loader-side structural pass found L12 and L13; prefix figure was a prose-ratio estimate | `c0b35cd1` |
| A2 | 2026-09-24 18:20 | Arm D: native config, `exceeds_model_context` outcome on six questions, pre-registered expected result; D-YaRN secondary; §7 reading | ruled model's trained context is 262,144 tokens; six D prompts exceed it (Kent ruled the design lead's recommendation) | `c0b35cd1` (no corpus change) |
| A3 | 2026-09-24 19:20 | §3.2 the fixed prompt (registered text); §2 G query plan (anchors from question text, 60-item cap) and R k procedure (once, from G repeat-1 medians); §5 reporting at context length, cache hit rate load-bearing | the arms cannot be built without these registered; gate (b) measured non-linear prefill | `c0b35cd1` (no corpus change) |
| A4 | 2026-09-25 00:05 (manifest digest re-registered 00:22 on the T-form timestamps: `fe17beef…`) | §2 R = records always + top-k events, deterministic k, calibration record, halt rule; three context limits; §3 canonical question manifest + digest; §3.2 prompt digest + normalisation; §5 cache labelling by observed reuse, telemetry mapping, tokenizer equivalence, two memory windows | Codex post-plan checkpoint (7 blockers / 17 majors on arms-run-01M3APTA plan): three contested rubric readings and four contract gaps were on the rubric side | `c0b35cd1` (no corpus change) |
