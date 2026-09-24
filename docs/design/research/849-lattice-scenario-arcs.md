---
title: "#849 Life Lattice scenario arcs — authoring worksheet"
status: authored — ready for synthesis
owner: Kent
last_updated: 2026-09-23
---

# #849 scenario arcs — authoring worksheet

**Authored 2026-09-23.** All six arcs decided: A, B, C, E, F authored with oracles and
near-misses; D cut. Next step is synthesis — the split into seed and hidden oracle.

**This was the thing to edit.** It is the blocking input for
[#849](https://github.com/kentonium3/kg-automation/issues/849), the decisive test that earns or
kills [#693](https://github.com/kentonium3/kg-automation/issues/693).

Each arc below is a **candidate, pre-filled** so you edit rather than author from a blank page.
Change anything. The parts that were marked `TODO(kent)` were the ones only Kent could write; all are now filled or ruled.

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
  for. Arc A is authored **cross-context** — that is what makes it bite. (Arc D, the other
  cross-context candidate, was cut 2026-09-23.)
- **Outbound channels are watched** (Kent, 2026-09-23). Intake reads what Kent *sends* — Slack
  replies, email, suggestions, commitments — not only what arrives. Outbound is where the
  machinery notices conflicts, over-commitments and scheduling opportunities, and surfaces
  trade-offs and reprioritisation needs. Consequence for the arcs: a promise made in writing
  **always enters the system**; the realistic dropped ball is *captured, deferred, never
  revisited*, not *never captured*. Only verbal and text-message promises stay outside (see
  Arc A's scope note).

## Per-arc scorecard (fill as you go)

| Arc | Hard case | Keep/Cut/Rewrite | Oracle done | Near-misses done |
|---|---|---|---|---|
| A | cross-time, **cross-context** collision | **Keep** | ☑ | ☑ (Kent's 4; 3 candidates stand) |
| B | quiet drift | **Keep** | ☑ | ☑ |
| C | dropped ball (captured-and-deferred) | **Keep** | ☑ | ☑ |
| D | cross-channel identity | **Cut** | — | — |
| E | repeating pattern → automation | **Rewrite** | ☑ | ☑ |
| F | principle erosion | **Keep** | ☑ | ☑ (accepted) |

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

**Cast** — fictional names, real dynamics (Kent, 2026-09-23).

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

**ORACLE — the right answer.** (Kent, 2026-09-23; complete)
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
      is **exactly two days** — borderline by construction, and **kept that way** (Kent,
      2026-09-23). Rider: *the system needs to be conscious of weekends and holidays* — "two
      days" is two working days, so a Friday move for a Monday event is short notice, and a
      Tuesday move for the Thursday after a Wednesday holiday is too
- [x] the resolution (Kent, 2026-09-23) — **counter the invite with an invite for a Wednesday
      meeting**: Wed 06-10 14:00–15:00, clear of the 11:30–13:30 workout-plus-travel block, and
      within the week as the 1:1 rule requires. Any Thursday counter must respect the *true*
      footprint — nothing before 15:45. Offering Thu 15:15 (the calendar's stated end) is a wrong
      answer that only the travel-time finding prevents
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

**Keep / Cut / Rewrite:** **Keep** (Kent, 2026-09-23).

**Context:** **personal**, solo. The pressure that causes the drift comes from every context;
the Outcome lives in this one.

**The story (Kent, 2026-09-23).** It's June. You sign up to run a 5K race on **15 October** and
pay the **$35 registration fee**. The training commitment is a progression of **3–5 runs a
week** at different distances and paces to get in condition for it. Work and personal
obligations start to pile up, and the commitment to run on a given day starts getting deferred
more than it should. Things that happen at random points on the journey, **some of them more
than once**:
- someone asks for a favor after work;
- you agree to schedule a meeting in the morning when you would normally run;
- you choose to run in the evening to accommodate an early meeting — then don't;
- you stay up too late working and don't get up early enough to fit the run in before or
  around other scheduled events.

The accumulated misses at some point reach a **point of no return**: you have run out of time
to safely condition yourself to get the performance you want on race day. In retrospect,
different choices could have been made and the deferrals avoided — with different scheduling,
better commitment management, better delegation, and a shift in mindset.

**The Outcome** (Kent, 2026-09-23) — *Run the 5K on 2026-10-15 at a **sub-10-minute-mile average
pace** for the full distance* (3.1 mi → under 31:00). The date is a hard external Commitment
(registered, $35 paid); the measure is the pace.

**The conditioning rule** (Kent, 2026-09-23 — this is what the oracle computes against).
- Conditioning is **cumulative** and cannot be accumulated all at once in a few weeks.
- **Consistent workouts, at least 3× a week**, are the only way to meet the targets.
- Working backwards from the race, there are **mid-month time/distance checkpoints** that say
  whether you're on track.
- **If the target training pace is not hit at the 50% point of the program, there is no path to
  recovery.**
- **If you cannot run at race pace two weeks before the race, you are unlikely to do it on race
  day.**

**The plan** (Kent's real conditioning plan, 2026-09-23) — full detail in
[`849-arc-b-training-plan.md`](849-arc-b-training-plan.md). Seventeen weeks, Mon 2026-06-15 →
race Thu 2026-10-15, four phases: rebuild the habit (wk 1–4), continuous running (wk 5–8),
5K-specific fitness (wk 9–12), sharpen (wk 13–16), taper (wk 17 + race week). Core runs
**Tue easy / Thu quality / Sat long**; strength Mon/Wed/Sun. The plan's own gate: *"if the 2 × 1
mile at 9:50–10:00 in week 16 feels controlled, you are in range."*

**Checkpoints**, derived from Kent's rule against the plan's own milestones:

| checkpoint | when | target | meaning |
|---|---|---|---|
| CP1 | wk 5 (07-13 → 19) | first continuous easy 25-min run | Phase 2 entered |
| **CP2 — the 50% point** | **end of wk 8, Sun 08-09** | a 45–50 min continuous long run completed in Phase 2, and the wk 7 progression's "quicker 5 min" at ~10:30/mi | **miss this → no path to recovery** |
| CP3 | wk 14, Thu 09-17 | 3 × 8 min at 10:00/mi | race pace sustainable in pieces |
| **CP4 — two weeks out** | **wk 16, Thu 10-01** | 2 × 1 mile at 9:50–10:00, controlled | the plan's own go / no-go |

**Timeline** (invented to Kent's spec: misses reach ~30% of core sessions — "that's trouble").
Miss rate is cumulative over core sessions; near-miss rows are marked and **not counted**.

| wk | Mon | core | what happened | reason at the time | decided / silent | miss rate |
|---|---|---|---|---|---|---|
| 1 | 06-15 | 3/3 | | | | 0% |
| 2 | 06-22 | 3/3 | Thu run/walk moved to Fri evening | friend's birthday dinner | decided — *near-miss, reschedule* | 0% |
| 3 | 06-29 | 2/3 | Sat 07-04 brisk walk skipped | July 4th weekend | decided — *near-miss, holiday* | 0% |
| 4 | 07-06 | 3/3 | first 20-min continuous run ✓ | | | 0% |
| 5 | 07-13 | 2/3 | Tue not run; **CP1 hit** Thu | someone asked a favor after work | silent | 7% |
| 6 | 07-20 | 1/3 | Thu quality slot taken by a 07:30 meeting; Sat long run not run | agreed to the morning meeting; up too late Fri working | decided (meeting) / silent (run); silent | 17% |
| 7 | 07-27 | 1/3 | Tue moved to evening, then not run; Thu progression done but the "quicker 5 min" at **11:10**; Sat 50-min long run not run | early meeting → "I'll run tonight"; up too late **again** | decided-then-silent; silent | **24%** |
| 8 | 08-03 | 1/3 | Tue not run; Thu slot taken by the 07:30 meeting **again**; Sat cutback 40 min ✓ | up too late; same meeting series | silent; decided/silent | **29%** |
| **8** | **08-09** | | **CP2 missed** — no 45+ min continuous long run completed in Phase 2 (wk 6 and wk 7 Saturdays both missed; wk 8 is the 40-min cutback), progression pace 11:10 vs ~10:30 | | | **← point of no return** |
| 9 | 08-10 | 3/3 | a full week — feels like recovery; 6 × 1 min run at ~10:40 effort | | | 26% |
| 10 | 08-17 | 1/3 | Thu slot taken by the 07:30 meeting, third time; Sat long run stopped at 25 min | same series; **calf tightness worsening — backed off per the plan's red-flag rule** | decided/silent; decided, with reason — *near-miss, legitimate* | 27% |
| 11 | 08-24 | 2/3 | Tue not run | favor after work, **again** | silent | 27% |
| 12 | 08-31 | 2/3 | Sat 09-05 long run skipped | Labor Day weekend away | decided — *near-miss, holiday* | 25% |
| 13 | 09-07 | 2/3 | Thu workout moved to evening, then not run | early meeting → "tonight", **again** | decided-then-silent | 26% |
| 14 | 09-14 | 3/3 | **CP3 missed** — 3 × 8 min at **10:35**, not 10:00 | | | 24% |
| 15 | 09-21 | 1/3 | head cold, three days off, plan adjusted | illness | decided, with reason — *near-miss, legitimate* | 22% |
| 16 | 09-28 | 3/3 | **CP4 failed** — 2 × 1 mile at **10:25 and 10:40**, not controlled | | | 21% |
| 17 | 10-05 | 3/3 | taper as written | | | 20% |
| race | 10-15 | | **32:50 → 10:35/mi.** Finished; sub-10 missed | | | |

Four reasons, and **every one repeats**: up too late working (×3: wk 6, 7, 8), the 07:30 meeting
series booked into the Thursday quality slot (×3: wk 6, 8, 10), "I'll run tonight" then not
(×2: wk 7, 13), a favor after work (×2: wk 5, 11). Ten counted misses over the programme; the
damage was done by week 8.

**The question put to both arms** — **build both** (Kent, 2026-09-23):
- **B1 mid-journey (coaching):** asked Mon 2026-08-17 — *"Am I on track for the October 5K?"*
  Right answer: no — CP2 was missed at the 50% point, so by the rule sub-10 is no longer
  reachable; the cause is a 29% miss rate driven by four repeating reasons, three of them
  scheduling choices; and the coaching move is **don't give up, but learn from this** — reset
  the outcome to *finish healthy*, and fix the 07:30 series and the late nights now.
- **B2 retrospective:** asked after the race — *"Why did I miss sub-10?"* Right answer: the same
  chain, plus the earliest week it was catchable. Accepting the lesser outcome is the
  "don't give up, learn from this" situation, not a failure to be hidden.

**ORACLE.** (Kent's rule + plan, invented timeline, accepted by Kent 2026-09-23)
- [x] the Outcome, with its date **and** its measure — 10-15, sub-10:00/mi — and that the date
      is a hard Commitment
- [x] every counted deferral, in order, with dates and the reason at the time — the table,
      **excluding** the five near-miss rows (wk 2, 3, 10-Sat, 12, 15)
- [x] **which reasons repeat** — all four; the 07:30 meeting series is the largest single cause
      and was **agreed to three times into a known quality-run slot**
- [x] the split between **decided** and **silent** — the meetings and the evening moves were
      decided (a Decision exists, on the meeting or the move); the runs themselves were never
      decided against — they just didn't happen. Five silent misses, five decided-then-silent
- [x] **the point of no return** — **CP2, Sun 08-09**, by the 50% rule. Not the last miss, not
      the first, **not** the wk 10 calf tightness and **not** the wk 15 cold — both tempting
      wrong answers, both legitimate back-offs the plan itself prescribes
- [x] that no individual deferral was unreasonable — the failure is aggregate
- [x] **when it should have been caught** — **end of wk 7, Sun 08-02**: two consecutive weeks at
      1/3, one reason already repeated, miss rate 24% and rising, and one week left before CP2
      in which a change could still have mattered
- [x] the retrospective, framed as coaching (Kent): different scheduling (don't book the 07:30
      series into the quality slot), commitment management (an evening move is a new commitment,
      not a deferral), delegation (the after-work favors), and a mindset shift

**Near-misses.** Kent's three (2026-09-23) first, each placed at a specific week; candidates follow.
1. **Illness or injury that alters the conditioning plan** — wk 10's calf tightness (the plan's
   own red-flag rule) and wk 15's cold. Legitimate re-plans with a reason. Not drift, and
   **not the cause**.
2. **A deferral with an acceptable reschedule** — wk 2, Thursday to Friday evening. Decided,
   within the week, no load lost. Must not be counted.
3. **Holidays** — wk 3 July 4th, wk 12 Labor Day. A few days off look bad on a coarse count but
   aren't a miss when you're mostly on track. A naive counter that includes them reads 33% at
   CP2 instead of 29% — still trouble, but for the wrong reason.
4. *(candidate)* **The wk 9 full week** — looks like recovery, is arithmetically irrelevant after
   CP2. Must not be read as "back on track".
5. *(candidate)* **A different recurring personal commitment** (the PT sessions from Arc A) that
   is *not* drifting, so "count deferrals per commitment" doesn't win by accident.
6. *(candidate)* **The strength sessions** — Mon/Wed/Sun lifting continues throughout and is
   never a core run; a miss there is not a miss here.

> Why this arc matters technically: a deferred run is a rewritten `scheduled_date`, and node
> attributes are **overwritten** — the graph's bi-temporal history covers edges only. So the
> whole trajectory is recoverable *only* from the episode log, one episode per deferral, with a
> `Decision` node where one was actually made and **none where it just didn't happen**. It is the
> sharpest test of the state-vs-history rule, and the decided-vs-silent split is the same
> absence-detection Arc F asks for.

---

## Arc C — Dropped ball

**Keep / Cut / Rewrite:** **Keep** (Kent, 2026-09-23).

**Context:** **spec-kitty** (Kent: "could be personal or business" — the launch, the integration
and the executive staff put this one at work; the shape transfers to personal unchanged).

**The story (Kent, 2026-09-23).** Mid-launch, you send a colleague a Slack message:

> *"Hey Fred, let's meet and do a design review once we're past this immediate launch craziness
> so we can start working on the integration."*

Intake flags it — *there's a meeting to schedule; when should it be?* You reply **"I don't know
yet"** and give no follow-up date or timeframe. It sits. In the two weeks that follow you and
Fred exchange many emails and Slack messages, all about other things with clear, immediate
relevance — including coordinating a **quarterly report to the executive staff on how the
launch went**. Then Fred writes:

> *"How are things going with the launch activity?"*

**Variants — reframed after the outbound ruling** (Kent + design discussion, 2026-09-23):
- **C1 captured-and-deferred — the scored arc.** This story. The promise was your own outbound
  Slack reply; intake caught it; you deferred it with no date; it became a Commitment with a
  counterparty and **nothing downstream** — no calendar hold, no Task, no revisit.
- **C2 never-entered — out of scope.** With outbound watched, a written promise cannot fail to
  enter. Only verbal and text-message promises stay outside, per Arc A's scope note. Not built.
- **Residual risk, noted not tested:** recognition precision. If intake over-flags, the
  dismissals become the dropped balls — C1 by another route.

**What makes this one hard — three things stacked:**
1. **The commitment has no date.** It is gated on a *condition* — "once we're past the launch" —
   not a time. Nothing can go overdue, so nothing is ever late.
2. **The condition has been met, and the evidence is indirect.** Nobody wrote "the launch is
   over." What exists is a thread coordinating a report on *how the launch went* — which can only
   be written after it.
3. **The follow-up is a probe on the condition, not the promise.** Fred is co-presenting the
   launch retrospective; he already knows how the launch went. So *"how are things going with
   the launch activity?"* cannot be a sincere question about the launch. It is asking whether the
   thing gated on the launch is coming. And the quarterly-report thread — Fred + launch — is the
   **lexically closest match** to his message, and the wrong binding.

**Cast** — fictional names, real dynamics.

| handle | who they are to you | relationship | context | channels |
|---|---|---|---|---|
| **Fred Okafor** (fictional) | spec-kitty colleague; owns the integration on his side; co-presents the launch retrospective with you | collaborator | spec-kitty | Slack, email, calendar |

**Timeline** (dates invented).

| when | channel | what happened |
|---|---|---|
| Tue 04-14 | Slack (outbound) | the promise, verbatim above |
| Tue 04-14 | intake | flagged: "meeting to schedule — when?" · Kent: "I don't know yet" · no date, no timeframe, no revisit set |
| Thu 04-23 | — | the launch ships |
| 04-15 → 04-27 | Slack + email | many Kent ↔ Fred exchanges on other, immediately relevant topics *(near-miss set)* |
| Fri 04-24, Mon 04-27 | email | coordinating the **quarterly report to the executive staff on how the launch went** *(the lexical near-miss)* |
| Tue 04-28 | Slack | Fred: *"How are things going with the launch activity?"* |

**The question put to both arms**, asked Tue 04-28 on receipt: *"Fred just sent this. What is he
referring to, and what do I owe him?"*

**ORACLE.** (Kent's story, invented dates; confirmed by Kent 2026-09-23)
- [x] the original promise — 04-14, Slack, outbound, and its exact wording
- [x] that it was **captured and deferred with no date or timeframe** — a condition-gated
      Commitment, "once we're past the launch" — and that **nothing was ever created against it**:
      no hold, no Task, no revisit. A gap, not a delay
- [x] that **the condition has been met** — the launch shipped 04-23, inferable from the
      quarterly-report thread about *how it went*, which can only exist afterwards. So the
      deferred commitment is **now due**, even though nothing is overdue
- [x] that Fred's message **refers to the design review, not the launch** — and the evidence: he
      is co-presenting the launch retrospective, so he already knows how the launch went; the
      question only makes sense as a probe on what was gated behind it
- [x] that the quarterly-report thread is the **wrong binding**, despite being the closest match
      on both person and topic
- [x] elapsed time and cost — two weeks; low but rising: Fred's integration work is waiting on a
      review that has no date, and he has had to ask sideways
- [x] the response — **propose the design review now, with dates**; and the coaching: a
      commitment deferred without a date needs a *trigger* ("ask me again the week after launch"),
      which intake could have asked for at 04-14

**Near-misses.** Kent's two (2026-09-23) first; candidates follow.
1. **The quarterly-report thread** — Fred, launch, recent, email. Everything a retrieval wants,
   and the wrong answer. Binding Fred's message to it makes the reply *"the report's on track"*,
   which answers a question he didn't ask.
2. **The other Fred traffic** — multiple Slack and email exchanges in the window, each with clear
   immediate relevance to something else. Recency and volume both point away from the promise.
3. *(candidate)* **A different deferred commitment gated on the same launch**, to someone else —
   "after launch let's revisit the pricing page with Dana." Same shape, wrong person.
4. *(candidate)* **A design review that did happen** in the window, with a third person. Lexical
   match on "design review"; the promise to Fred is not kept by it.
5. *(candidate)* **A meeting you did have with Fred** in the window — about the quarterly report.
   "We met, so the promise is kept" is a wrong answer: the meeting was about something else.
6. *(candidate)* **Fred's own earlier, sincere launch question**, sent before 04-23. Same words,
   different meaning, and the date is what separates them.

> **Ontology note for the design lead.** `Commitment.datetime` is required in the entity model.
> This arc's commitment has **no datetime** — it has a trigger condition. The realistic dropped
> ball is exactly the commitment the model cannot currently represent. Either `datetime` becomes
> optional with a `trigger` (free text, or a reference to the gating node), or intake must
> always convert a condition into a review date. Worth deciding before synthesis.

> **Why the flat arm can't just win it.** Person-and-topic retrieval lands on the report thread.
> The right answer needs the Person hub → the deferred Commitment with nothing downstream → the
> launch-ended inference from an unrelated thread → the reading of Fred's message as oblique. Four
> hops, two of them absences, one of them a date comparison.

---

## Arc D — Cross-channel identity — **CUT**

**Keep / Cut / Rewrite:** **Cut** (Kent, 2026-09-23) — *"not practical. Multiple IDs for a given
person are unique to that person."*

**Why it was cut.** The arc assumed identity resolution is a reasoning problem the arms must
solve at question time. It isn't: a person's handles are unique to that person, so the
`Person.aliases` list resolves handle → Person **deterministically, before writing, at $0** —
exactly as the design doc's identity-resolution rule already says. There is no inference for a
test to measure, and manufacturing a confusable second person would test a trap the real data
does not set. Person resolution is still *exercised* — Arc C binds through the Person hub — but
it is a precondition of the corpus, not a hard case.

**What survives.** The alias/handle authoring rule stands for the whole corpus: the stream
carries raw handles, the Person node carries the alias list, and synthesis must not pre-resolve
them in the stream. That remains the way every arc's cast is written.

---

## Arc E — Repeating pattern → automation

**Keep / Cut / Rewrite:** **Rewrite** (Kent, 2026-09-23) — reshaped from *stakeholder pattern*
to *noticing a repeating business or communication pattern that needs some form of automation.*

**Context:** **personal + Intentional + spec-kitty** — three mailboxes, one pattern. The
cross-context version by construction.

**The story (Kent, 2026-09-23).** Over a week your personal, Intentional and spec-kitty inboxes
receive roughly **200 emails** from newsletters, promotions and vendor product announcements.
Most are from organisations you *want* to stay informed about — the volume from each is just too
much. **A couple of times a week an important email in one of the accounts gets buried and
missed.** Periodically you end up in a **marathon session of a couple of hours** cleaning up all
three boxes. The session is the same every time:
1. look for the latest offers from vendors you're interested in;
2. skim the newsletters for the essence of the topics, and read perhaps 3–4 articles in depth;
3. file emails by organisation into folders;
4. purge old filed emails by organisation that you haven't starred to keep;
5. and, along the way, find the important ones you missed.

**The automation** (Kent's spec, 2026-09-23 — this is the oracle's "what should be proposed"):
- vendor offers **auto-filed by vendor organisation**; a **digest of just the latest offer** from
  each is sent to you;
- newsletters **condensed to a digest**; topics you've flagged as of interest *at the time* are
  highlighted, or sit in their own **"current interest"** section;
- you tell Felix — by **voice, journal, or text (WhatsApp today)** — which topics you want
  information on and which can be dropped;
- folders **auto-purged** of email older than 30 days;
- **email from contacts is surfaced** to you;
- contacts with a **meeting request** get a friendly reply with your **Calendly link**;
- anything **time-sensitive** is raised through an alert channel — **ntfy, or text (WhatsApp or
  Signal)**;
- items clearly indicating a **to-do** (review your taxes, pay a bill, schedule a doctor's
  appointment) are **added to Vikunja**, with suggested dates/times surfaced to you.

**Two layers, two questions — build both:**
- **E1 — notice the pattern.** Asked at some week N: *"What recurring manual work am I doing that
  should be automated?"* The right answer is the email marathon, with its numbers, its five
  identical sub-activities, the misses it exists to catch, and the automation above.
- **E2 — the automation's judgement.** Given the spec, over one sample week: *"Which of this
  week's emails should reach me, which become to-dos, which are digested, which are filed, which
  are dropped?"* This is where Kent's near-misses live, and it is the layer closest to the
  intake-router's job — score it, but read it as evidence about the router as much as the
  substrate.

**Corpus consequence.** This arc sets the stream's volume: ~200 promotional/newsletter emails a
week across three accounts for the ~6-month window is ~**5,000 emails**. That is not padding —
it is the distractor mass every other arc's near-misses are embedded in, and it is the volume
that makes the *cost-per-correct-answer* axis bite.

**Cast** — fictional; the organisations matter more than the people here.

| handle | who / what | relationship | context | channels |
|---|---|---|---|---|
| ~25 vendor orgs | tools, services, hardware — offers and product announcements | vendor | all three | email |
| ~15 newsletter orgs | industry, research, learning — topics Kent wants the essence of | other | all three | email |
| Kent's contacts list | the people whose mail must always surface | client / collaborator / family / peer | all three | email → Person nodes |
| 6 buried-and-missed senders (invented) | a client meeting request; a bill; a doctor's-appointment reminder; a spec-kitty vendor renewal notice; a tax document; a friend | mixed | mixed | email |

**Timeline** (invented to Kent's spec; ~6 months, Mon 2026-04-06 → Fri 2026-09-25).

| when | what happened |
|---|---|
| every week | ~200 newsletter / promo / vendor emails land across the three boxes (~70 / 60 / 70) |
| ~every 10–14 days | a **marathon triage session**, ~2 h, all five sub-activities, in this order — **13 sessions** over the window (~26 h) |
| ~2×/week | an important email is buried; **six** of them have a recorded consequence: the client meeting request answered four days late (wk 3); the bill paid after its due date (wk 6); the doctor's reminder found after the slot lapsed (wk 9); the vendor renewal auto-renewed at the old tier (wk 12); the tax document chased by the accountant (wk 17); the friend's message answered two weeks on (wk 21) |
| wk 5 | **third marathon session** — the same five steps, the same ~2 h, and the first miss with a consequence already behind it: **the pattern is recognisable here** |
| wk 10 | Kent tells Felix by WhatsApp two topics are now of interest and one newsletter can be dropped *(seeds the "current interest" mechanism)* |
| wk 24 | E1 asked |

**The tension to catch.** From inside any one session, this is just "doing email." From inside
any one miss, it is just "I missed one." The finding is that the *sessions are a process* — same
trigger (the boxes are full), same five steps, same output — and that the *misses are its cost*,
not separate accidents. Both are only visible as a shape across months. And the shape has to be
judged automatable: the steps are regular enough to specify, which Kent's spec demonstrates.

**ORACLE.**
*E1 — the pattern* (invented values to confirm):
- [x] the volume — ~200/week across three contexts, ~70 / 60 / 70 — and that it is **one pattern
      across three boxes**, not three problems
- [x] the sessions — 13 in the window, ~2 h each, ~26 h; and that each is **the same five
      sub-activities in the same order**
- [x] the cost against capacity — ~1.2 h/week of the 15 h deep-work Capacity (~8%), **plus** the
      six consequential misses, which are the larger cost and the reason the sessions exist
- [x] that no single session or miss justified automating — the pattern is the finding
- [x] **the session at which it was recognisable** — the third, wk 5: same steps, same duration,
      one consequential miss already behind it. Not the thirteenth
- [x] the proposed automation — Kent's spec above, in substance: auto-file by org, latest-offer
      digest, newsletter digest with current-interest section, contact surfacing, Calendly
      auto-reply on meeting requests, time-sensitive alerts, to-do extraction to Vikunja, 30-day purge
- [x] framed as a **process** finding — "this is a workflow to build," not "you have too much
      email" and not "you should be more disciplined"

*E2 — the judgement*, over one sample week (invented; ~200 items, of which ~20 are scored):
- [x] email from anyone on the contacts list **surfaces** — including a contact's newsletter
- [x] a contact's meeting request gets the **Calendly reply**, and nothing else does
- [x] the bill, the tax document and the doctor's reminder become **Vikunja to-dos** with
      suggested dates
- [x] the vendor renewal notice is **time-sensitive → alert**; the vendor's weekly promo is
      **digest → file**
- [x] the near-misses below are each classified **correctly** — every one is a plausible wrong
      answer to "surface it?"

**Near-misses.** Kent's three (2026-09-23) first; they are E2's traps. Candidates for E1 follow.
1. **Friendly-looking spam that is not from a contact.** First-name salutation, casual tone,
   "just checking in." Not on the contacts list → **not surfaced**. The contacts list is the
   test, not the tone.
2. **LinkedIn cold-call invitations** from someone in an area **not** on the interest list →
   dropped. **But some cold-call PMs are of interest** — one from an area *on* the list must
   surface. Same shape, opposite answer, decided by the current-interest list as it stood
   *that week*.
3. **Spam that looks urgent but isn't** — "the loan department is reviewing your application
   for a $60K loan" you never asked for. Urgency language → **not** an alert. Time-sensitivity
   has to be grounded in something Kent actually has (a bill, a renewal, an appointment), not in
   the sender's tone.
4. *(candidate, E1)* **A recurring activity that varies too much to automate** — the weekly
   client status call prep: same cadence, different content every time. "Automate it" is wrong.
5. *(candidate, E1)* **Something already automated** whose output still appears in the stream —
   the daily calendar-orchestrator summary — so it looks like manual recurrence but isn't.
6. *(candidate, E2)* **A newsletter from an org that is also a contact** — surfaces because of
   the sender, not the content; must not be digested away.
7. *(candidate, E2)* **A topic that *was* of interest in wk 4 and was dropped in wk 10** — a
   newsletter on it in wk 14 goes to the ordinary digest, not "current interest." Bi-temporal
   by construction.

> **Ontology note for the design lead.** Two things in Kent's spec have no home in the entity
> model: (a) the **current-interest list** — a set of topics Kent adds and drops over time by
> voice / journal / WhatsApp, which E2's near-miss 2 and 7 depend on and which is *bi-temporal by
> nature*; (b) the **contacts list** maps to `Person`, but "is on my contacts list" is a
> property the router needs at $0 and the model doesn't carry. Neither is a #849 build item;
> both are needed to *seed* E2 honestly.

> Why the flat arm can't just win it: E1's evidence is thirteen unremarkable two-hour blocks and
> six unrelated misses spread across six months and ~5,000 emails. Nothing links them except
> their shape. A dump contains them all and marks none of them; the arm has to cluster
> same-shaped events across months and then judge the cluster as a process. E2 is the reverse:
> ~200 items, ~20 decisions, and each decision needs a fact that lives *outside* the email —
> the contacts list, the interest list as of that week, Kent's actual bills and appointments.
> That is a typed-lookup problem, and it is where a structured substrate should be cheapest.

---

## Arc F — Principle erosion at scale

**Keep / Cut / Rewrite:** **Keep** (Kent, 2026-09-23).

**Context:** **personal**, solo. The pressure that erodes it comes from every context; the
practice lives in this one.

**The story (Kent, 2026-09-23).** Early-morning **meditation and personal growth time** —
probably the most important time spent consistently on any given day, and cumulatively through
the year. It is easy time to trade off to more urgent, less important tasks: it sits in the
*not urgent / important* category, and nothing external defends it. **It shows up by its
absence.** Journaling slows to less than three times a week, or stops. The daily Vikunja
check-ins for meditation and other personal-investment time start to sputter — the days missed
go from *one here and there*, to *a couple a week*, to *a few a week*, to *very sporadic or
missing*. Nothing marks the moment it stopped being a practice.

**The Principle (Kent, 2026-09-23 — verbatim, hard, global):**

> *Only I can make this investment in myself, and it must be a non-negotiable priority. There is
> no external force; no one is coming to tell me to do it. Personal transformation is necessary
> to achieve the vibrant, prosperous life I imagine, but it takes slowly transforming my mind
> through persistent, consistent work. This needs to be a near-daily practice done with no
> fanfare, no celebration, no external view, and for no one's fulfilment and satisfaction but my
> own. This is where power comes from if recognised as such — but if not, it is easy to trade
> away for trivial pursuits.*
>
> *Life will interfere at times, but the practice of returning to the habit in spite of
> interruptions and pressures to do otherwise is itself strengthening a mental muscle.*

Rationale, in Kent's framing: a 1%-a-day improvement in mindset, emotional intelligence,
consciousness and mindfulness, and interpersonal or professional skill compounds across a year.
The cost of a missed morning is never the hour; it is the compounding.

**Two things the Principle fixes about the right answer:**
- **The finding is the absence, and the response is *return*.** Not guilt, not a streak, not a
  celebration — the Principle forbids fanfare explicitly. The right coaching output is *"the
  practice has lapsed; return to it,"* with the evidence. Anything that proposes a reward, a
  badge, or a public commitment is a **wrong answer**.
- **Returning is the muscle.** A lapse followed by a return is not a failure to record; it is the
  practice working. So the oracle scores *trajectory*, not *misses*: the signal is the slope, and
  a return after interruption is a positive event.

**Evidence streams** (this is what the corpus carries — three, all metadata, no content):

| stream | what it shows | note |
|---|---|---|
| Vikunja | two recurring daily tasks — *meditation* and *personal-investment time* — with a check-in record per day (done / not done, time) | adapter-written events; the primary signal |
| journal | **entry timestamps only** — one opaque event per entry, no content | the vault is out of scope and journal content is private by construction; the *count per week* is all Arc F needs, which is the "structure without content" rule applied |
| calendar | what fills the **06:00–07:00** slot when the practice doesn't | the trade-off partner — early calls, email started early, sleep after late nights |

**Timeline** (invented to Kent's sputter; ~6 months, Mon 2026-04-06 → Fri 2026-09-25).
Check-ins are meditation-task completions per 7 days; journal is entries per 7 days.

| phase | weeks | check-ins /7 | journal /wk | what filled the slot | decided or silent |
|---|---|---|---|---|---|
| practice | wk 1–5 | 6–7 | 5–6 | — | — |
| one here and there | wk 6–8 | 5–6 | 4–5 | a 06:30 call with a colleague in another time zone (wk 6, **decided, reason recorded**); slept in after a late night working (wk 7, silent); an early start on email (wk 8, silent) | 1 decided / 2 silent |
| a couple a week | wk 9–13 | 4–5 | 3–4 | the late-night → sleep-in pattern, now weekly (silent); a second recurring early call appears on the calendar (wk 11, **silent — it simply appears**); travel day (wk 12, decided) | 1 decided / ~9 silent |
| a few a week | wk 14–18 | 2–4 | **<3 → 1–2** | the morning slot is booked 3×/wk; email-first mornings are the default; one illness week (wk 16, decided, legitimate) | 1 decided / ~14 silent |
| sporadic | wk 19–22 | 1–2 | 0–1 | "that's just my schedule now" | ~14 silent |
| missing | wk 23–24 | 0–1 | 0 | | |
| **return** | wk 25 | 5 | 3 | Kent restarts after a WhatsApp voice note to Felix: *"I've let the mornings go"* | **decided** |

Across the window roughly **60 missed mornings; 4 have a Decision behind them** (the time-zone
call, the travel day, the illness week, the restart). The rest are bare events.

**The question put to both arms** — build both:
- **F1 — the absence, mid-lapse.** Asked Mon 2026-08-10 (wk 19): *"Am I keeping my
  non-negotiables?"* Right answer: no — the morning practice has lapsed; here is the slope, the
  point it crossed the journaling threshold, what has been filling the slot, and that almost none
  of it was decided. Then: return.
- **F2 — the earliest catch.** Asked retrospectively at wk 25: *"When should this have been
  caught?"* Right answer: wk 9–10, when misses went from *one here and there* to *a couple a
  week* and the late-night cause had repeated — before the second early call was allowed to
  appear on the calendar.

**ORACLE.** (Kent's Principle; invented trajectory accepted by Kent 2026-09-23)
- [x] the Principle, verbatim in substance, and that it is **hard** and **global**
- [x] the trajectory — the five phases with their rates — and that the signal is the **slope**,
      not any one miss
- [x] **the threshold crossing** — journaling under 3/week at wk 14, the marker Kent named
- [x] **the decided-vs-silent split** — ~4 decided of ~60 missed; the second early call that
      *simply appeared* on the calendar at wk 11 is the sharpest single instance: a standing
      intrusion on a non-negotiable, with no Decision anywhere
- [x] **what filled the slot** — early calls, email-first mornings, sleep after late nights —
      and that these are *urgent-unimportant* trades, exactly what the Principle predicts
- [x] the **root cause link** — the late nights working that eroded this practice are the same
      late nights that broke Arc B's training in the same weeks. One cause, two Principles
      eroding. An arm that names the shared cause has found the coaching finding
- [x] **the response, in the Principle's own terms** — surface the absence, prompt the return, no
      fanfare. A streak, a reward, a public accountability partner, or "block the calendar and
      tell your team" are all **wrong answers** — the last one because the Principle says *no
      external view*
- [x] **the return is scored as positive** — wk 25 is the practice working, not a data point
      in the lapse
- [x] **when it should have been caught** — wk 9–10

**Near-misses** (candidates, accepted by Kent 2026-09-23):
1. **The illness week** (wk 16) — decided, legitimate, and *not* the cause. A tempting wrong
   answer for "when did it stop."
2. **The travel day** (wk 12) — the practice moved to the evening and the check-in was done at
   20:30. A reschedule, kept; must not count as a miss.
3. **The time-zone call** (wk 6) — one early call with a recorded reason. Decided, one-off,
   fine. Must be distinguished from the wk 11 call that *recurs* and was never decided.
4. **A journaling dip with meditation held** (wk 9: journal 3, check-ins 6). One signal down,
   one up — an early warning, not a lapse. Reading it as full erosion is wrong; ignoring it is
   also wrong.
5. **Arc B's running misses in the same weeks** — a *different* practice eroding from the same
   cause. Must be linked as shared cause, not merged as one practice.
6. **A "lighter weekend" convention** — Saturday and Sunday practice is shorter by design and
   the journal entry is often skipped. Plan-absorbed; a naive 7-day count reads it as misses.
7. **A late-evening meditation check-in** on a day the morning was lost — the practice was kept,
   at the wrong time. Counts as done for the slope; counts as a *morning* miss for the calendar
   question. The two readings must not be confused.

> Why this arc is hard: it requires noticing an **absence** across three metadata streams, and
> then noticing a *second* absence — that almost none of the intrusions were decided. Nothing in
> a dump of everything says "this wasn't decided" or "this stopped." And the right response is
> constrained by the Principle itself in a way a task-list read cannot see: the obvious fixes
> (block it, tell people, reward yourself) are the ones the Principle forbids.

---

## Still open (not yours to fill — tracking only)

- **Rubric — RULED (Kent, 2026-09-18):** score **both** correctness under near-misses *and*
  input-tokens-per-correct-answer, against **both** baselines (dump-everything as the honest
  upper bound, vector-RAG + structured records as the realistic deployment); 3 repeats per arm
  per arc. Run matrix = 3 arms × surviving arcs × 3 repeats. Pre-register on #849 before any run.
- **Repeat runs**: #844 ran once per arm and could not measure variance. Fix before running.
