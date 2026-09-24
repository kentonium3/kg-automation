---
title: "#849 rubric — pre-registration"
doc_type: research
status: draft
owner: claude-macbook (design lead); reviewer claude-office4
last_updated: 2026-09-24
---

# #849 rubric — pre-registration (DRAFT, not yet registered)

**Status:** draft by the design lead, parallel to synthesis. It becomes the pre-registration only
when (1) claude-office4 has reviewed it, (2) ~~Kent has confirmed §7~~ **§7 confirmed by Kent 2026-09-24**, and (3) it is posted to
[#849](https://github.com/kentonium3/kg-automation/issues/849) **before any run**. Until then it
binds nothing. Rulings it encodes: Kent 2026-09-24 (§7 decision rule confirmed first-hand), Kent 2026-09-18 ("run both": both axes, both baselines, cost is
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
| **R** — vector-RAG + records | embedding retrieval over the stream and rendered records, top-k | k chosen so the assembled context is within ±20 % of G's median assembled context; caching on for any stable prefix |

Common to all arms: the **same reasoning model**, the **same fixed prompt**, the **same question
wording**; the arm assembles context, the model answers; nothing else differs. The model and its
provider are recorded, not prescribed (per-function seam, §Tool Selection).

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

Rules: `required_values` are the literal tokens a hit must contain (dates ISO, times HH:MM,
counts as integers); `traceability` must name existing seed ids or rendered-event ids, and the
freeze check fails on an oracle point whose `traceability` is empty; per-miss classifications
(counted / decided-then-silent, Arc B) and phase bands (Arc F) live here, never in a seed;
the artifact is committed under `oracle/` and the harness asserts that directory is absent from
every arm's input path before a run starts.

## 4. Axis 1 — correctness

Per question, per run:

- **Recall** = must_identify points hit ÷ points in the oracle. A point is hit only if the answer
  states it, with the specific value the oracle requires (a date, a count, a name). Partial credit
  is not given per point.
- **Precision** = 1 − (near-misses the answer asserts *as the finding* ÷ near-misses seeded for
  that arc). Asserting a decoy is a wrong answer, not a missing one.
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
- **peak memory** of the arm's serving process during the question (KV / GTT on office4) — a
  number, not a pass/fail;
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
- Corpus frozen at a commit hash before the first run; the hash is in the registration.

## 10. Artifacts

`docs/design/research/849-synthesis/` — `00-context-chains.md`, `01-cast.md`, `seed/*.yaml`,
`stream/` (deterministic RNG for Arc E's mass, hand-authored scored events), `oracle/` (hidden),
harness code, `results/<run>.json`, grading sheet. Findings are written against this rubric.
