---
title: "#849 rubric — pre-registration"
doc_type: research
status: draft
owner: claude-macbook (design lead); reviewed by claude-office4; registered 2026-09-24
last_updated: 2026-09-24
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
| **G** — tuned graph | Graphiti + FalkorDB over the typed ontology, seeded by structured writes (no LLM) | node + edge hybrid retrieval; typed constraint pull, one query per label (`Capacity`, `Commitment`, `Principle`, `Interest`); anchored history expansion (entity → its episodes via `MENTIONS`); **no BFS by default**; `group_id` in `[A-Za-z0-9_]`; retrieval budget recorded per question |
| **D** — full dump | the entire corpus (rendered seed + full stream) in the prompt | prompt caching **on**; hit rate logged |
| **R** — vector-RAG + records | embedding retrieval over the stream and rendered records, top-k | ONE global k, chosen so R's median assembled context is within ±20 % of G's median; the per-question ratio R_context / G_context is a reported column so a parity breach is visible, never silent; caching on for any stable prefix |

Common to all arms: the **same reasoning model**, the **same fixed prompt**, the **same question
wording**; the arm assembles context, the model answers; nothing else differs. The model and its
provider are recorded, not prescribed (per-function seam, §Tool Selection). **Assembled context**
= the input tokens of the assembled block, excluding the fixed prompt and the question; that is
what the cost axis counts.

**Question order is protocol.** Questions are asked in `ask_time` ascending order (C1, A, F1, B1,
E2, E1, F2, B2). Under the time-cut each D prompt is then a prefix of the next, so D's cache hit
rate is a property of this protocol and is reported as such; a random order would collapse it and
the number would be an artifact of an unstated choice.

**Prompt layout is protocol (A1).** The event stream comes first and the entity block after it.
Entities change at A, F1 and E1 as Decisions become visible under the replay rules, so
entities-first collapses the cache prefix to ~0 % for those three questions; events-first keeps
every step a token-level prefix extension (measured with the Qwen3-Next tokenizer: A 35.3 %,
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

The served model's context window must exceed the B2 prefix and is recorded in the registration;
the pre-freeze figure of ~178k tokens is superseded. Feasibility on office4 is arithmetic until
the (b) gate measures it (12 of 48 Qwen3-Next layers carry KV, GQA with 2 KV heads: weights +
KV ≈ 51–53 GiB of 62.5 GiB GTT); the gate records n_ctx, peak GTT and tok/s at full B2 length.

**Time-cut rule.** Every question is asked at its stream timestamp. An arm may only see material
with `created_at ≤ ask time`. For D this means the dumped prefix differs per question — that is
realistic, and the caching hit rate it produces is a finding, not a nuisance. **State as of, not
filtered:** G is built for each question by *replaying* primitives up to `ask_time`, never by
filtering a final-state graph — otherwise every current-state attribute (`Interest.status`,
`Task.scheduled_date`, `Outcome.status`) leaks the future. D and R likewise consume only rendered
material with `created_at ≤ ask_time`.

## 3. Questions

Eight, from the worksheet (`docs/design/research/849-lattice-scenario-arcs.md@f3076643`):

| id | arc | ask time | question (verbatim from the worksheet) |
|---|---|---|---|
| A | A | Tue 2026-06-09, on the calendar move | the collision + the travel-time absence |
| B1 | B | Mon 2026-08-17 | "Am I on track for the October 5K?" |
| B2 | B | after 2026-10-15 | "Why did I miss sub-10?" |
| C | C | Tue 04-28 on receipt | "Fred just sent this. What is he referring to, and what do I owe him?" |
| E1 | E | wk 24 | "What recurring manual work am I doing that should be automated?" |
| E2 | E | one sample week | "Which of this week's emails should reach me / become to-dos / be digested / filed / dropped?" |
| F1 | F | Mon 2026-08-10 | "Am I keeping my non-negotiables?" |
| F2 | F | wk 25 | "When should this have been caught?" |

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
  random 25 % of the rest. Disagreements resolve to Kent.

## 5. Axis 2 — cost

Per question, per run, per arm — recorded, never estimated:

- **input tokens per correct answer** = total input tokens ÷ points hit (the primitive), with
  sub-columns **cache-write / cache-read / uncached**;
- output tokens; wall-clock latency from question to answer;
- **peak memory**, two labelled columns: *per question* for D and R inference (the KV cache
  scales with the prefix, ~7× across questions), sampled from the serving process during the
  question; *per run* for G's graph store, which is dominated by the loaded graph and near
  constant per question. A number, not a pass/fail;
- D and R: prompt-cache **hit rate** under the time-cut arrival pattern.

Dollar conversions are derived afterwards from the token columns for any provider; they are not
what is scored.

## 6. Repeats and variance

**3 runs per arm per question** (72 runs). Report mean and range. Two arms are *indistinguishable*
on a question when their ranges overlap. #844's single-run fragility (Threats §3) is what this
fixes.

## 7. Decision rule (confirmed by Kent, 2026-09-24)

Read on the 8 questions, using recall as the primary and precision as the tie-break:

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

## Amendment log

| # | date (UTC) | what changed | why | frozen commit |
|---|---|---|---|---|
| — | 2026-09-24 17:03 | Registration | freeze verdict PASS | `b203907e` |
| A1 | 2026-09-24 18:15 | Entity allowlist (`arcs` stripped); `loader_links.jsonl` written, G-only; loader gate added; §2 replay rules, prompt layout, measured prefix tokens (B2 = 362,772) | loader-side structural pass found L12 and L13; prefix figure was a prose-ratio estimate | `c0b35cd1` |
