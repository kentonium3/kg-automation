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
`2994bab7`. **Legend:** OK = inferable from the named primitives; OK-ABS = inferable from an
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
| C2 | Captured and deferred with no date/timeframe; nothing ever created against it | `EP_C_INTAKE`; `COM_DESIGN_REVIEW` with `datetime: null` + `trigger`; no inbound `DUE_BY`/`GATES`/`BLOCKS` (absence) | OK-ABS — after `DEC_C_DEFER` is removed per ruling; a Decision node here would over-state it |
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
| F2 | Five-phase trajectory; the signal is the slope | ~180 generated check-in completions + ~110 journal marks (jittered inside bands; bands never rendered) | OK — contingent on the render never emitting `generator_input` |
| F3 | Journaling drops below 3/week at wk 14 | generated journal marks | OK (the "3/week" marker is oracle-only) |
| F4 | ~4 of ~60 misses decided; the wk-11 APAC sync simply appeared with no Decision | four `DEC_F_*` + their source episodes (ruling: add provenance episodes for TZ_CALL, TRAVEL, ILLNESS); wk-11 `slot_fillers` entry with `recurrence_rule` and no decision | OK after provenance fix |
| F5 | What filled the slot: early calls, **email-first mornings**, sleep after late nights | early calls: `slot_fillers` wk 6, 11; late nights: `shared_late_nights` generator; **email-first mornings: no primitive** | **GAP** — generator must emit sent-email events at 06:00–07:00 on the mornings the worksheet marks "early start on email" (wk 8) and "email-first mornings are the default" (wk 14–18) |
| F6 | Root cause shared with Arc B's missed runs | `shared_late_nights` (single event set, consumed by arc-b and arc-f) | OK — contingent on Arc B referencing the same ids |
| F7 | Response in the Principle's own terms; reward/badge/public commitment are wrong answers | Principle text ("no fanfare, no celebration, no external view") | OK |
| F8 | The wk-25 return is scored positive | `EP_F_RESTART`, `DEC_F_RESTART`, phase-7 generation | OK — F1 is asked wk 19, before this; the time-cut rule must hold |
| F9 | Should have been caught wk 9–10 | generated data (two consecutive phases of decline + a repeated cause) | OK |
| F-NM | Near-misses 1–7 (illness wk 16, travel wk 12, one-off TZ call wk 6, journaling dip wk 9, Arc B link, lighter weekends, late-evening check-in) | wk 6/12/16 present; **lighter-weekend convention and the wk-9 journaling dip need generator rules; the late-evening check-in needs a completion event at ~20:30 on a lost morning** | PARTIAL — 3 generator rules to add |
| F-REP | Missed mornings are represented by absence of a completion, not by an explicit "not done" | generator emits completions only | CHOICE — adapter fidelity decides (asked on the bus); record in the seed header |

## Arcs B and E

Rows are added when `seed/arc-b.yaml` and the Arc E generator land. Known in advance from the
worksheet: B needs the training-plan checkpoints CP1–CP4 to be *derivable from the plan document
as a primitive*, not asserted; E1 needs the 13 marathon sessions as calendar blocks with no
"triage" label, and the six consequential misses as ordinary mail with their consequences as
later ordinary events.
