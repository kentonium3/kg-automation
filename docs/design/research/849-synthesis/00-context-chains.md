---
title: "#849 synthesis — the four context chains (Purpose → Domain → Outcome)"
doc_type: research
status: draft
owner: claude-office4
last_updated: 2026-09-24
---

# #849 synthesis — step 0: the upward chains

The authored worksheet seeds **no Purposes**. Guiding principle 2 requires every work node to
connect upward to one, so these chains are written *before* any arc node, per the design lead's
synthesis requirement (`felix-graph-692`, 2026-09-24T03:04Z).

This file is **seed material**, not oracle. Everything here is a primitive the arms may see.

> **The governing constraint for every line below.** Seeds assert primitives only. No conflict,
> no drift, no pattern, and no *target rate* is ever written — all of that must be inferable.
> Where honouring principle 2 would require asserting something the oracle expects the arm to
> infer, that tension is flagged rather than resolved. See §Open questions.

---

## Purposes — 3, deliberately not 4

A Purpose has **no date, no measure, no status** (§Tier Definitions discriminator).

There is deliberately **not one Purpose per context**. The ontology has no `Domain → Purpose`
edge by design, and purpose-affinity is *derived* through `Outcome -SERVES-> Purpose`
(@a92db54b, reaffirmed by Kent). Minting one Purpose per Domain would smuggle that rejected 1:1
mapping back in through the seed. So `PUR_LIVELIHOOD` is served by Outcomes in **three**
different work Domains — which is what makes the derived affinity non-trivial and gives Arc A's
cross-context collision a single contended Capacity to bite against.

| id | statement | no date | no measure | no status |
|---|---|---|---|---|
| `PUR_TRANSFORM` | Transform my mind and character through persistent, consistent work, because that is where power comes from | ☑ | ☑ | ☑ |
| `PUR_VITALITY` | Sustain the physical vitality and capability that the rest of the life depends on | ☑ | ☑ | ☑ |
| `PUR_LIVELIHOOD` | Build a durable, independent livelihood that does not depend on any single venture | ☑ | ☑ | ☑ |

`PUR_TRANSFORM` is Kent's own framing, drawn from Arc F's Principle rationale (the 1%-a-day
compounding) — not invented.

## Domains — the four operating contexts

A Domain is **never dated, never measured, no status** — a container. Kent's four operating
contexts ARE Domains on the work side (Kent 2026-09-18; doc @ea1c3941 §Tier Definitions → DOMAIN).

| id | context | note |
|---|---|---|
| `DOM_PERSONAL` | personal | Arcs A (PT/workouts), B (5K), F (morning practice) |
| `DOM_INTENTIONAL` | Intentional | Arc E mailbox; own Outcome below |
| `DOM_SPECKITTY` | spec-kitty | Arcs A (1:1 with Marcus), C (launch/integration), E mailbox |
| `DOM_POINTERHEALTH` | PointerHealth | **no arc exercises this context** — see §Open questions Q2 |

The originating account or system of a message is **episode provenance** (`source_description`),
never a node. One **global `Capacity`** (no `CONSTRAINS` edge) is what all four contend for —
that is the mechanism Arc A's cross-context collision and Arc E's cost-against-capacity both read.

## Capacity — one, global

| id | description | hours_per_week |
|---|---|---|
| `CAP_DEEP` | Deep-work availability across all contexts | 15 |

Global by construction: **no `CONSTRAINS` edge**, so it is discovered by typed-label lookup
(§Tier Definitions → CAPACITY discovery contract) and is contended by every Domain. Arc E's
oracle scores the marathon sessions against this figure (~1.2 h/wk ≈ 8%).

## Outcomes — dated, measured, status-tracked

| id | outcome | date | measure | Domain | SERVES |
|---|---|---|---|---|---|
| `OUT_5K` | Run the 5K at a sub-10-minute-mile average for the full distance | 2026-10-15 | < 31:00 for 3.1 mi | `DOM_PERSONAL` | `PUR_VITALITY` |
| `OUT_LAUNCH` | Ship the spec-kitty launch | 2026-04-23 | shipped / not | `DOM_SPECKITTY` | `PUR_LIVELIHOOD` |
| `OUT_INTEGRATION` | Land the integration Fred owns on his side | 2026-Q3 | delivered / not | `DOM_SPECKITTY` | `PUR_LIVELIHOOD` |
| `OUT_INTENTIONAL_*` | *(to be drafted — see Q2)* | | | `DOM_INTENTIONAL` | `PUR_LIVELIHOOD` |
| `OUT_POINTERHEALTH_*` | *(to be drafted — see Q2)* | | | `DOM_POINTERHEALTH` | `PUR_LIVELIHOOD` |

`OUT_5K` carries a hard external `Commitment` (registered, $35 paid, 2026-10-15) via
`DUE_BY` — the endpoint extension landed at @ee1311a5 specifically for this.

Arc F has **no Outcome** in this table. That is deliberate and is Q1 below.

---

## Open questions for the design lead

These are the three places where synthesis could quietly invalidate its own test. I am not
resolving them unilaterally.

### Q1 — Arc F: principle 2 vs. answer leakage (the sharpest one)

Arc F's Vikunja meditation and personal-investment tasks are **work nodes**, so principle 2 wants
them to reach a Purpose through `Project → Objective → Outcome → Purpose`.

But an Outcome **requires a measure**. Any Outcome I write for the morning practice — "sustain
≥5 check-ins/week through 2026" — **asserts the expected rate**, and Arc F's entire finding is
the *slope of decline* inferred from the check-in stream. With a target in the seed, detecting
erosion collapses to a threshold comparison the arm reads off one node. The oracle explicitly
scores "the signal is the slope, not any one miss"; a seeded rate hands that over.

Three options, none obviously right:

- **(a) No upward chain for the practice tasks.** The recurring tasks hang off the `Principle`
  (hard, global) and nothing else. Honest to the arc — Kent's framing is that *nothing external
  defends it* — but it violates principle 2 as written.
- **(b) An Outcome with a date but a non-numeric measure**, e.g. "the practice is still running
  at year end / it isn't". Satisfies the discriminator's "measure required" without stating a
  rate. Weaker leak, not zero.
- **(c) Principle 2 is scoped to exclude practice-type recurring tasks**, the way it already
  excludes `Person` ("a Person has no upward edge" — your 04:23Z ruling). That would be a doc
  change and is yours, not mine.

My lean is **(c)**, because the same argument that exempts `Person` seems to apply: a practice
defended only by a Principle is not work *toward* an Outcome, it is a standing commitment to a
value. But this is an ontology ruling and I would rather have it from you than assume it.

### Q2 — PointerHealth has no arc

`DOM_POINTERHEALTH` appears in the ratified four-context enum, but **no authored arc exercises
it**. Arc E's three mailboxes are personal + Intentional + spec-kitty; A and C are personal and
spec-kitty; B and F are personal.

Options: seed it with real-but-unexercised Outcomes so that the Domain-partitioned read over one
global Capacity is genuinely 4-way (my lean — a context that exists only as an empty container
makes the partition easier than reality); or leave it out of the seed and record that #849 tests
three of four contexts.

Either way it is a **corpus-honesty** decision rather than an ontology one, so it may be Kent's
rather than yours. Same question for `OUT_INTENTIONAL_*`: Intentional appears only as a mailbox
in Arc E, with no Outcome of its own.

### Q3 — the arcs are causally coupled, and the seed has to preserve that

Not a blocker, but it changes the synthesis shape and I want it on the record before I build:

- Arc F's oracle requires that the late nights working which eroded the morning practice are
  **the same** late nights that broke Arc B's training *in the same weeks* — "one cause, two
  Principles eroding", and naming the shared cause is scored as the coaching finding.
- Arc B near-miss 5 requires Arc A's PT sessions to be present and **not** drifting across B's
  window, so "count deferrals per commitment" cannot win by accident.
- Arc E's ~5,000 emails are the distractor mass the other arcs' near-misses are embedded in.

So this is **one corpus on one timeline** (≈2026-04-06 → 2026-10-15), not five independent
fixtures — and the late-night events must be single events that both B and F read, not two
parallel fabrications that happen to agree. I will build it that way unless you say otherwise.

---

## What comes next (not started)

1. Resolve Q1–Q3.
2. Cast + `Person` nodes with alias lists; stream carries **raw handles**, never pre-resolved.
3. The primitive seed per arc — entities and edges only, no asserted conflict/drift/pattern.
4. The timestamped multi-channel stream, generated deterministically (seeded RNG) for Arc E's
   ~5,000-email distractor mass; hand-authored for the scored events.
5. The **hidden oracle** as a physically separate artifact, one block per question
   (A, B1, B2, C, E1, E2, F1, F2) — never loaded into either arm.
