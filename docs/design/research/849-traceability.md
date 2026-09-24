---
title: "#849 traceability — oracle points → seed primitives"
doc_type: research
status: draft
owner: claude-macbook (design lead); rows verified against seeds by claude-office4 at freeze
last_updated: 2026-09-24
---

# #849 traceability — every oracle point has a primitive, or is a GAP

Rubric §8 closure of #844 Threats §1 (an oracle point with nothing in the seed behind it).
Built from the worksheet oracles (`849-lattice-scenario-arcs.md@f3076643`) and the seeds at
`2994bab7` / `a489039d` / `938cd847`. **Legend:** OK = inferable from the named primitives; OK-ABS = inferable from an
absence the seed constructs; GAP = no primitive yet, with the primitive that would close it;
GRADE = a note for the grader, not a seed change. Arcs B and E are added when their seeds land.

## Arc A — cross-time, cross-context collision (`seed/arc-a.yaml`)

| # | oracle point | primitives | status |
|---|---|---|---|
| A1 | Thu overlap: 1:1 14:00–15:00 vs PT 14:30–15:15; whole meeting vs true footprint 14:00–15:45 | `EP_A_MOVE`, `calendar_events_after_move`, `COM_PT_THU` + its calendar event; footprint from the 30-min travel blocks on Mon/Wed/Fri | OK |
| A2 | Tue/Thu PT sessions are missing travel time | travel events present for MWF, absent for Tue/Thu; no field says so | OK-ABS |
| A3 | PT is fixed (paid, hard to reschedule); the 1:1 is movable (moved unilaterally) | `EP_A_PT_BOOKING` ($95, 24-h cancellation, forfeiture, limited availability); `EP_A_MOVE` organiser `mvale@…`, no consultation | OK (gap closed 2994bab7) |
| A4 | The governing Principle, verbatim, hard, global | `PRIN_PERSONAL_PRIORITY` + companions `PRIN_ONE_TO_ONE_MOVABLE`, `PRIN_STANDING_WORK_FIXED`, `PRIN_SELF_INFLICTED_YIELDS` | OK |
| A5 | Exception test: not very high importance; notice exactly two working days | `EP_A_MOVE` carries no reason (absence); `reference_time` Tue 09:12 vs event Thu 14:00; no holiday in the window | OK-ABS |
| A6 | Resolution: counter-offer Wed 06-10 14:00–15:00; any Thu counter ≥ 15:45 | Wed calendar shows only 11:30–13:30 workout+travel; seed constraint keeps Wed 14:00–15:00 free corpus-wide; `PRIN_ONE_TO_ONE_MOVABLE` ("within the week") | OK — constraint must survive Arc E's generator (freeze check) |
| A7 | Should have been caught Tue 06-09 at the move | `EP_A_MOVE.reference_time` | OK |
| A-NM | Near-misses 1–7 need their own primitives (a 45-min travel block for NM1; a stated high-importance reason in NM4 and NM7a episodes; a self-called multi-person meeting for NM7b) | `arc-a-near-misses.yaml` not yet written | PENDING |

## Arc C — dropped ball, captured-and-deferred (`seed/arc-c.yaml`)

| # | oracle point | primitives | status |
|---|---|---|---|
| C1 | The promise: 04-14, Slack, outbound, exact wording | `EP_C_PROMISE` | OK |
| C2 | Captured and deferred with no date/timeframe; nothing ever created against it | `EP_C_INTAKE`; `COM_DESIGN_REVIEW` with `datetime: null` + `trigger`; no inbound `DUE_BY`/`GATES`/`BLOCKS` (absence) | OK-ABS (`DEC_C_DEFER` removed a489039d) |
| C3 | The condition has been met (launch shipped ~04-23), inferable only indirectly | `OUT_LAUNCH.target_date` 04-23 with no status advance; 04-24 email "Quarterly report … how the launch went" | OK — **GRADE:** accept "shipped on or before 04-24, target 04-23"; the exact day is not in the corpus by design |
| C4 | Fred's message refers to the design review, not the launch; evidence: he already knows how the launch went | Fred drafted the launch section (04-24); "See you at the exec review" (04-27 outbound) | OK — inferable; the worksheet's "co-presents" is implied, not stated |
| C5 | The quarterly-report thread is the wrong binding | same thread; `GATED_ON` → `OUT_LAUNCH` gives the arm what to check | OK |
| C6 | Elapsed two weeks; cost rising — Fred's integration is waiting | timestamps 04-14 → 04-28; `OUT_INTEGRATION` "Fred owns on his side"; promise text "so we can start working on the integration" | OK |
| C7 | Response: propose the review with dates; coaching — a dateless commitment needs a trigger, which intake could have asked for | `EP_C_INTAKE` shows intake asked "when", not "what would tell us" | OK-ABS |
| C-NM | Near-misses 3–6 | `arc-c-near-misses.yaml` not yet written; NM3 (Dana, pricing page) already present as 04-27 traffic | PENDING |

## Arc F — principle erosion (`seed/arc-f.yaml`)

| # | oracle point | primitives | status |
|---|---|---|---|
| F1 | The Principle, verbatim, hard, global | `PRIN_SELF_INVESTMENT` | OK |
| F2 | Five-phase trajectory; the signal is the slope | ~180 generated check-in completions + ~110 journal marks (jittered inside bands; bands never rendered) | OK — `meta.non_rendered` declares it and the detector rejects undeclared blocks (a489039d); the renderer test is still owed |
| F3 | Journaling drops below 3/week at wk 14 | generated journal marks | OK (the "3/week" marker is oracle-only) |
| F4 | ~4 of ~60 misses decided; the wk-11 APAC sync simply appeared with no Decision | four `DEC_F_*` + their source episodes (ruling: add provenance episodes for TZ_CALL, TRAVEL, ILLNESS); wk-11 `slot_fillers` entry with `recurrence_rule` and no decision | OK (provenance episodes + dispositions a489039d) |
| F5 | What filled the slot: early calls, **email-first mornings**, sleep after late nights | early calls: `slot_fillers` wk 6, 11; late nights: `shared_late_nights` generator; **email-first mornings: no primitive** | **GAP** — generator must emit sent-email events at 06:00–07:00 on the mornings the worksheet marks "early start on email" (wk 8) and "email-first mornings are the default" (wk 14–18) |
| F6 | Root cause shared with Arc B's missed runs | `shared_late_nights` (single event set, consumed by arc-b and arc-f) | OK — contingent on Arc B referencing the same ids |
| F7 | Response in the Principle's own terms; reward/badge/public commitment are wrong answers | Principle text ("no fanfare, no celebration, no external view") | OK |
| F8 | The wk-25 return is scored positive | `EP_F_RESTART`, `DEC_F_RESTART`, phase-7 generation | OK — F1 is asked wk 19, before this; the time-cut rule must hold |
| F9 | Should have been caught wk 9–10 | generated data (two consecutive phases of decline + a repeated cause) | OK |
| F-NM | Near-misses 1–7 (illness wk 16, travel wk 12, one-off TZ call wk 6, journaling dip wk 9, Arc B link, lighter weekends, late-evening check-in) | wk 6/12/16 present; **lighter-weekend convention and the wk-9 journaling dip need generator rules; the late-evening check-in needs a completion event at ~20:30 on a lost morning** | PARTIAL — 3 generator rules to add |
| F-REP | Missed mornings are represented by absence of a completion, not by an explicit "not done" | generator emits completions only | CHOICE — adapter fidelity decides (asked on the bus); record in the seed header |

## Arc B — quiet drift (`seed/arc-b.yaml` @938cd847) — PROVISIONAL until R3 is confirmed

| # | oracle point | primitives | status |
|---|---|---|---|
| B1 | The Outcome with date and measure; the date is a hard Commitment | `OUT_5K` (target_date, success_criteria — seeded as `measure`, see R4), `COM_RACE`, `DUE_BY`, `EP_B_REGISTER` (non-refundable, $35) | OK after R4 |
| B2 | Every counted deferral, in order, with dates and the reason at the time | generator must emit one primitive per row: the Thu 07:30 series as a real recurring calendar event (wk 6→) whose acceptance is a Decision; a favour-request message + block (wk 5, 11); Vikunja reschedule-to-evening episodes with no completion (wk 7, 13); silent misses as absence against the plan; holiday/away calendar entries (wk 3, 12) | GAP until R3 — reasons currently exist only as generator strings |
| B3 | Which reasons repeat; the 07:30 series agreed to three times into a known quality slot | the series' three occurrences + three acceptance Decisions; the plan marks Thu as the quality run | OK after R3 |
| B4 | Decided vs silent split (5 silent, 5 decided-then-silent) | Decisions + provenance episodes for the meetings and the evening moves; none for the runs themselves | OK after R2/R3 — classification lives in the oracle only |
| B5 | Point of no return = CP2, Sun 08-09, by the halfway rule; not wk 10 calf, not wk 15 cold | `EP_B_PLAN` (milestones: Phase-2 45–50 min long run, wk-7 "quicker 5 min" ~10:30), `EP_B_CONDITIONING_RULE` (halfway rule, *without* the coaching clause — R1); wk 6/7 Sat misses + wk 8 40-min cutback as events; wk 7 pace 11:10 as a completion note | OK after R1/R3 |
| B6 | No individual deferral was unreasonable | the reasons as primitives (R3) | OK after R3 |
| B7 | Should have been caught end of wk 7 (08-02) | events through wk 7 (two 1/3 weeks, one repeated reason) | OK after R3 |
| B8 | Retrospective framed as coaching: scheduling, commitment management, delegation, mindset; reset-not-quit | reasoning over B2–B7; **no primitive may state the coaching move** (R1) | OK — judgement, graded |
| B9 | Race result 32:50 → 10:35/mi (for B2, asked after 10-15) | results email / completion note after 10-15 | GAP until R3 |
| B-NM | Near-misses: wk 10 calf (red-flag rule in the plan), wk 15 cold, wk 2 reschedule-within-week, wk 3/12 holidays, wk 9 full week, Arc A's PT sessions not drifting, strength sessions never core | plan red-flag list (`EP_B_PLAN`); note episodes + Decisions (wk 10, 15); calendar (wk 3, 12); PT sessions rendered weekly Jun–Oct from Arc A's recurrence (`non_drifting_control`); Mon/Wed/Sun strength as Vikunja completions | PARTIAL — PT must render across B's window; strength sessions need a generator rule |

## Arc E

Rows are added when the Arc E generator lands. Known in advance from the worksheet: E1 needs the
13 marathon sessions as calendar blocks with no "triage" label, the six consequential misses as
ordinary mail with their consequences as later ordinary events, and the wk-10 WhatsApp
interest-list change as an episode; E2 needs the Interest nodes with add/drop episodes and the
contacts as `Person.is_contact`.
