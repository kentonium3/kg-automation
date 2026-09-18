---
title: "#849 Life Lattice scenario arcs — authoring worksheet"
status: draft
owner: Kent
last_updated: 2026-09-18
---

# #849 scenario arcs — authoring worksheet

**This is the thing to edit.** It is the blocking input for
[#849](https://github.com/kentonium3/kg-automation/issues/849), the decisive test that earns or
kills [#693](https://github.com/kentonium3/kg-automation/issues/693).

Each arc below is a **candidate, pre-filled** so you edit rather than author from a blank page.
Change anything. The parts marked **`TODO(kent)`** are the ones only you can write.

## How to use this

1. Set **Keep / Cut / Rewrite** on each arc. Four strong arcs beat six thin ones.
2. Fix the **cast, channels and timeline** so they look like your actual life. Mine are placeholders.
3. Fill the **Oracle** block. This is the irreplaceable part — it is the ground truth the run is
   scored against, and a wrong oracle silently invalidates the whole test.
4. Fill the **Near-misses**. The same-shape wrong answers only you know about.

Then hand it back. I synthesise the timestamped multi-channel stream and the evolving Lattice
around it, and **split this file into a seed and a hidden oracle** — the oracle is never loaded
into either arm ([#844](https://github.com/kentonium3/kg-automation/issues/844)'s hidden-oracle
rule). Keeping the story and its answer together here is an authoring convenience only.

## Settled context (don't re-litigate while editing)

- **Corpus** = work realm + communication stream. Reference/vault material is out.
  Content is synthetic but authored from real life, so no privacy gate applies.
- **What makes an arc hard** is *near-miss density and multi-hop aggregation*, not corpus size.
  Every arc must stay hard **even when the baseline is handed the entire corpus**.
- **Ontology** is `docs/design/second-brain-graph-layer.md` — `Person` is ratified (Kent,
  2026-09-18), so people are nodes with an alias list.
- **Seeds assert primitives only.** No conflict, drift or pattern is ever written as an edge;
  all of it must be inferable. Ground truth lives in the Oracle blocks below.

## Per-arc scorecard (fill as you go)

| Arc | Hard case | Keep/Cut/Rewrite | Oracle done | Near-misses done |
|---|---|---|---|---|
| A | cross-time collision | `TODO(kent)` | ☐ | ☐ |
| B | quiet drift | `TODO(kent)` | ☐ | ☐ |
| C | dropped ball | `TODO(kent)` | ☐ | ☐ |
| D | cross-channel identity | `TODO(kent)` | ☐ | ☐ |
| E | stakeholder pattern | `TODO(kent)` | ☐ | ☐ |
| F | principle erosion | `TODO(kent)` | ☐ | ☐ |

---

## Arc A — Cross-time collision

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate — edit freely).** You make a commitment to a client in email. About six
weeks later, in Slack, you commit to something else with a collaborator. Neither conversation
mentions the other. Both land in the same week, roughly three months out. Neither has become a
scheduled task yet, so nothing is late and nothing is flagged.

**Cast** — `TODO(kent)`: replace with real shapes (fictional names, real dynamics).

| handle | who they are to you | relationship | channels |
|---|---|---|---|
| *candidate* | client principal | client | email, calendar |
| *candidate* | internal collaborator | collaborator | Slack, calendar |

**Timeline** — `TODO(kent)`: fix dates/effort so the collision is real against your true capacity.

| when | channel | what happened |
|---|---|---|
| T+0 | email | commit to a client deliverable for week W |
| T+6wk | Slack | commit to a second piece of work, also landing in week W |
| T+12wk | — | week W arrives; combined effort exceeds capacity |

**The tension to catch.** The collision exists only if you project both commitments forward
against weekly capacity. At the moment it is detectable, nothing looks wrong.

**ORACLE — the right answer.** `TODO(kent)`
- [ ] both commitments land in the same week — which week?
- [ ] projected effort vs your capacity that week — the actual numbers
- [ ] which is **external** (fixed) and which **internal** (movable)?
- [ ] which Principle resolves it, and therefore which one gives?

**Near-misses** (5–15 same-shape wrong answers). `TODO(kent)`
- *e.g. another commitment in a nearby week that does NOT collide*
- *e.g. a busy week that looks worse but has slack*

---

## Arc B — Quiet drift

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate).** An Outcome with a real measure and date. Over ~4 months its supporting
Objectives get re-scoped five times. Every individual re-scope is locally reasonable. The
aggregate effect is that the Outcome can no longer reach its measure by its date.

**The Outcome** — `TODO(kent)`: state it with **a date and a measure** (that's what makes it an
Outcome and not a Purpose).

**Timeline** — `TODO(kent)`: five re-scopes, each with a reason that sounded fine at the time.

| when | what was re-scoped | the reason at the time |
|---|---|---|
| ×5 | `TODO(kent)` | `TODO(kent)` |

**The tension to catch.** The drift is the *delta across five events*. No single event is a defect.

**ORACLE.** `TODO(kent)`
- [ ] all five re-scope events, in order, with dates
- [ ] the gap between current trajectory and the stated measure
- [ ] **which re-scope made the measure unreachable**
- [ ] that no individual decision was unreasonable — the failure is aggregate

**Near-misses.** `TODO(kent)` — *other things that were re-scoped and were genuinely fine.*

> Why this arc matters technically: node attributes are **overwritten**, and the graph's
> bi-temporal history covers edges only — so this drift is recoverable *only* from the episode
> log. It is the sharpest test of the state-vs-history rule.

---

## Arc C — Dropped ball

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate).** You promise someone something in a Slack thread. It never becomes a
task anywhere. About three months later they follow up **obliquely, in a different channel**,
without naming it — "did you ever get anywhere with that?"

**Two variants — build both** (design lead, 2026-09-18):
- **C1 structural:** the promise *was* captured as a Commitment, but no Task or Project ever
  attached to it. Findable as a pattern: a commitment with a counterparty and nothing downstream.
- **C2 episode-only:** it never entered the Lattice at all. Recoverable only from the message log.
  This is the realistic case today; C1 is what you'd get once a router exists.

**Cast & timeline** — `TODO(kent)`

**ORACLE.** `TODO(kent)`
- [ ] the original promise, its date, its channel, and its exact wording
- [ ] that **nothing was ever created against it** — a gap, not a delay
- [ ] that the later oblique message refers to it — and what makes that inferable
- [ ] elapsed time and the relational cost

**Near-misses.** `TODO(kent)` — *promises you DID keep, and follow-ups about something else.*

---

## Arc D — Cross-channel identity

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate).** One person appears under three handles — an email address, a Slack
display name, and a calendar invitee under a third spelling. Commitments to and from them
accumulate across all three over months.

**The question put to both arms:** *"What have I committed to <person>, and is any of it overdue?"*

**The cast** — `TODO(kent)`. The alias list is the point of this arc:

| the person | handle 1 (email) | handle 2 (Slack) | handle 3 (calendar) |
|---|---|---|---|
| `TODO(kent)` | | | |

**The trap** — `TODO(kent)`: **a different person with a confusingly similar handle**, who must
*not* be merged. Without this the arc measures nothing.

**ORACLE.** `TODO(kent)`
- [ ] the complete commitment set across all three handles
- [ ] that the three handles are one person — and the evidence a reader could use
- [ ] which single commitment is overdue
- [ ] that the near-miss person is **separate**

> Authoring rule: the stream carries the **raw handles**; the Person node carries the **alias
> list**. Don't pre-resolve them in the stream, or the arc is solved before it starts.

---

## Arc E — Stakeholder pattern

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate).** One client or collaborator requests scope additions ~6 times over ~5
months. Each is small, each is individually reasonable, each was accepted.

**Timeline** — `TODO(kent)`: the ~6 asks, with dates and the hours each quietly added.

**The tension to catch.** The *pattern* is a boundary problem and its cumulative cost is material
against capacity. No single instance justifies raising it.

**ORACLE.** `TODO(kent)`
- [ ] all the scope-addition events with dates
- [ ] cumulative hours, set against your capacity
- [ ] that each instance alone is trivial — the pattern is the finding
- [ ] framed as a relationship conversation, not a task problem

**Near-misses.** `TODO(kent)` — **important here**: other people who asked once or twice and are
genuinely fine. Without them, "flag the person with the most asks" wins by accident.

---

## Arc F — Principle erosion at scale

**Keep / Cut / Rewrite:** `TODO(kent)`

**The story (candidate).** A **hard** Principle — say, protecting deep-work mornings. Over ~3
months about eleven exceptions are granted, each justified in the moment. **Some have a recorded
reason; some are silent** — the meeting simply appears. Current state: mornings are routinely
booked, and it reads as "that's just my schedule now."

**The Principle** — `TODO(kent)`: state it, and confirm it is **hard**, not soft.

**Timeline** — `TODO(kent)`: the exceptions, and critically **which were decided with a reason and
which just happened**.

**ORACLE.** `TODO(kent)`
- [ ] the Principle, and that it is hard
- [ ] the exception count and its trajectory
- [ ] **the split between decided-with-reason and silent** — a bare event with no decision behind
      it is itself the coaching signal
- [ ] the downstream consequence (capacity, or another Principle also in scope)

**Near-misses.** `TODO(kent)` — *exceptions that were genuinely correct calls.*

> Why this arc is hard: it requires noticing an **absence** — that a decision was never recorded.
> Nothing in a dump of everything says "this wasn't decided."

---

## Still open (not yours to fill — tracking only)

- **Rubric**: score correctness under near-misses *and* input-tokens-per-correct-answer, against
  two baselines (dump-everything as the honest upper bound, vector-RAG as the realistic
  deployment). Awaiting your confirmation — it multiplies the run matrix.
- **Repeat runs**: #844 ran once per arm and could not measure variance. Fix before running.
