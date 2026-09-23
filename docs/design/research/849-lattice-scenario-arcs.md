---
title: "#849 Life Lattice scenario arcs — authoring worksheet"
status: draft
owner: Kent
last_updated: 2026-09-23
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
- **Every arc carries a `context`** — personal / Intentional / spec-kitty / PointerHealth (Kent,
  2026-09-18). At synthesis a context is a **Domain**; the account or system a message arrived
  through is **episode provenance**, not a node; one **global Capacity** is what all four contend
  for. Arcs A and D are authored **cross-context** — that is what makes them bite.

## Per-arc scorecard (fill as you go)

| Arc | Hard case | Keep/Cut/Rewrite | Oracle done | Near-misses done |
|---|---|---|---|---|
| A | cross-time, **cross-context** collision | **Keep** | ☑ (notice edge open) | ◐ (4 of Kent's, 3 candidates) |
| B | quiet drift | `TODO(kent)` | ☐ | ☐ |
| C | dropped ball | `TODO(kent)` | ☐ | ☐ |
| D | cross-channel identity | `TODO(kent)` | ☐ | ☐ |
| E | stakeholder pattern | `TODO(kent)` | ☐ | ☐ |
| F | principle erosion | `TODO(kent)` | ☐ | ☐ |

---

## Arc A — Cross-time, cross-context collision

**Keep / Cut / Rewrite:** **Keep** (Kent, 2026-09-23).

**Context:** **personal ↔ spec-kitty** (Kent, 2026-09-23). Personal calendar on one side, the
spec-kitty calendar on the other, one body in one place at a time. Your personal calendar's
**availability is shared** into the work calendar — so the information to avoid the collision
was technically visible, and the colleague did not look.

**The story (Kent, 2026-09-23).** You have standing workout sessions three days a week — Monday,
Wednesday, Friday — at fixed but different times, on your personal calendar. Both the sessions
and the travel time are on the calendar. You also have 45-minute PT sessions on Tuesdays and
Thursdays at irregular times. You book those while at the studio and forget to add the travel
time, thinking you'll do it later. On Tuesday a colleague moves a regular Friday meeting to
Thursday, and it overlaps your PT session. The colleague is your boss, the CMO, who most likely
moves meetings agent-assisted on his end and doesn't always reference your calendar when he does.

**Two overlapping issues, not one:**
1. the **travel time** that was never added to the Tue/Thu PT sessions — the calendar understates
   the real block, so the true footprint of the session is not written anywhere;
2. the **conflict** between the moved meeting and the PT session, which has to be resolved.

**Cast** — `TODO(kent)`: fictional names, real dynamics.

| handle | who they are to you | relationship | context | channels |
|---|---|---|---|---|
| **Marcus Vale** (fictional) | your boss, the CMO — moves meetings agent-assisted, doesn't always check your shared availability | collaborator | spec-kitty | calendar (spec-kitty account), Slack |
| **Northside PT** (fictional) | the PT studio — paid sessions, hard to reschedule | vendor | personal | calendar (personal account) |

**Timeline** — times invented (Kent, 2026-09-23: "invent the time"). Week of Mon 2026-06-08.

| when | context / channel | what happened |
|---|---|---|
| standing | personal / calendar | Mon workout 07:00–08:00, Wed 12:00–13:00, Fri 16:00–17:00 — each with a 30-min travel block **on the calendar** either side |
| standing | personal / calendar | Tue PT 10:15–11:00, Thu PT 14:30–15:15 — booked at the studio, **no travel blocks** (true Thu footprint 14:00–15:45) |
| standing | spec-kitty / calendar | weekly 1:1 with Marcus, Fri 14:00–15:00 |
| Tue 06-09 | spec-kitty / calendar | Marcus moves the Friday 1:1 to **Thu 06-11 14:00–15:00** — overlaps the PT session 14:30–15:15 and sits entirely inside the unrecorded travel window |

**The tension to catch.** Two things, and the second is the harder one. The overlap between the
moved meeting and the PT session is visible in current state — but only if both calendars are
read together. The travel time is an **absence**: the Mon/Wed/Fri pattern shows the sessions
carry travel, the Tue/Thu ones don't, and nothing in either calendar says "this block is
understated." A right answer resolves the conflict *and* notices that the PT sessions are bigger
than they look.

**ORACLE — the right answer.** (Kent, 2026-09-23; open: the two-day notice edge only)
- [x] the Thursday overlap — moved 1:1 **Thu 14:00–15:00** vs PT **14:30–15:15**: 30 minutes of
      direct overlap; against the true footprint (14:00–15:45) the whole meeting collides
- [x] that the Tue/Thu PT sessions are **missing travel time** — the Mon/Wed/Fri sessions carry
      30-min travel blocks either side; the Tue/Thu ones don't, and nothing says so
- [x] which is **fixed** and which is **movable** — the PT session is fixed: **paid, and hard to
      schedule**. The 1:1 is movable: Marcus moved it unilaterally, so it can move again
- [x] which Principle resolves it (Kent, 2026-09-23) — **global**:
      > *Pre-scheduled, repeating, personal commitments take priority unless the competing
      > request is of very high importance **and** arrives at least two days before the event.
      > When they take priority, the response is a **counter-offer** on the competing request,
      > not a cancellation.*
      Rationale: repeating personal meetings for paid services are an obligation to yourself.
      A short-notice change usually means a cancellation for that week, and if it can be
      rescheduled it lands in a following week and adds pressure there. The counter-offer clause
      is in the Principle deliberately — it is the part that could conceivably be automated.
      Strictness: **hard** (Kent, 2026-09-23: "I'm going to call it a hard principle and we'll
      see how that works") — the exception clause is part of the Principle, not a reason to
      weigh it. A hard violation always surfaces; it is never auto-handled.
      Three companion rules the answer must also apply: **repeating 1:1s with colleagues may be
      rescheduled within the week**; **standing work meetings you do not own cannot be moved**;
      and **a collision you caused yourself with a multi-person meeting is resolved by moving the
      personal commitment**, because the cost now falls on other people (see near-miss 7).
- [x] the exception test, run explicitly — importance: a routine 1:1 moved for convenience is
      **not** very high importance, so the exception does not fire. Notice: Tuesday for Thursday
      is **exactly two days** — borderline by construction (`TODO(kent)`: keep the edge, or make
      it clearly short notice?)
- [x] the resolution — **counter-offer Marcus a new time within the same week** (1:1s may move
      within the week), and the counter-offer must respect the *true* footprint: nothing before
      15:45 on Thursday. Offering 15:15 (the calendar's end) is a wrong answer that only the
      travel-time finding prevents
- [x] when it should have been caught — **Tuesday 06-09**, the moment the move landed, not
      Thursday morning

**Scope note (Kent, 2026-09-23).** The other cross-time shape — two future commitments made in
channels that can't see each other, e.g. a climbing date agreed by text with a friend for a
Sunday weeks out and never put on the calendar, then a Friday spoken promise to your spouse for
the same Sunday morning — is **valid but out of scope**. Neither a text nor a spoken promise is
in any adapter's stream; the system can't be expected to solve it and this test does not try.
Arc A tests only what the calendars and the comms stream actually carry.

**Near-misses** (5–15 same-shape wrong answers). Kent's three (2026-09-23) first; the rest are
candidates in the same spirit — keep, cut, add.
1. **Phone meeting overlapping a travel block.** Sometimes feasible — but **only if the travel
   block is longer than 30 minutes**. Build the pair: one call over a 45-min travel block that
   *is* feasible, and one over a 30-min block that is not. "Take it in the car" is the wrong
   answer for the second.
2. **A social meeting or call with a friend** in the same slot shape as PT. Not a paid, repeating
   commitment — it yields, and must not be protected as if it were.
3. **A task with travel** — dropping off a package, a store purchase. Has a travel footprint like
   PT, but is movable; must not be treated as a fixed point.
4. *(candidate)* **The exception fires.** Marcus moves the 1:1 with three or more days' notice for
   something of very high importance. Same shape, opposite answer: the meeting wins and PT is the
   one rescheduled. Without this the arm can win by always protecting PT.
5. *(candidate)* **A clean move.** A week where Marcus moved the 1:1 and it landed clear. Nothing
   to flag.
6. *(candidate)* **A Mon/Wed/Fri workout** whose on-calendar travel block sits next to a work
   meeting and looks like an overlap on a coarse read, but isn't.
7. **A team meeting lands on an existing PT slot** (Kent, 2026-09-23 — the tricky one). The PT
   session existed first; a multi-person work meeting is scheduled over it. Same shape as the
   main arc, **opposite answer**, and for two different reasons:
   - **7a — the CEO calls it**, say for an announcement. An importance judgement: you need to be
     there, so **PT moves**. The exception clause fires on importance.
   - **7b — you called it yourself**, accidentally, over your own PT slot. **PT moves** — not on
     importance, but because you are now impacting a bunch of other people's schedules, and the
     cost of moving them outweighs the personal obligation.
   Both must be distinguished from the main arc, where a *one-person* meeting moved *onto* PT and
   PT holds. And 7b is the case Felix should **prevent at creation time** — the right answer
   there is the warning at the moment you book it, not the recovery afterwards.

---

## Arc B — Quiet drift

**Keep / Cut / Rewrite:** `TODO(kent)`

**Context:** `TODO(kent)` — personal / Intentional / spec-kitty / PointerHealth

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

**Context:** `TODO(kent)` — personal / Intentional / spec-kitty / PointerHealth

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

**Context:** `TODO(kent)` — personal / Intentional / spec-kitty / PointerHealth (author **cross-context**, per the 2026-09-18 ruling)

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

**Context:** `TODO(kent)` — personal / Intentional / spec-kitty / PointerHealth

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

**Context:** `TODO(kent)` — personal / Intentional / spec-kitty / PointerHealth

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

- **Rubric — RULED (Kent, 2026-09-18):** score **both** correctness under near-misses *and*
  input-tokens-per-correct-answer, against **both** baselines (dump-everything as the honest
  upper bound, vector-RAG + structured records as the realistic deployment); 3 repeats per arm
  per arc. Run matrix = 3 arms × surviving arcs × 3 repeats. Pre-register on #849 before any run.
- **Repeat runs**: #844 ran once per arm and could not measure variance. Fix before running.
