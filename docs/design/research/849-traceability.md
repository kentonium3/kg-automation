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
`2994bab7` / `a489039d` / `938cd847` / `c331e6f9` / `1be1cb23`. Ids in backticks are seed ids or
`meta.emits` declarations; the oracle checker resolves the same names. **Legend:** OK = inferable from the named primitives; OK-ABS = inferable from an
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
| F2 | Five-phase trajectory; the signal is the slope | `GEN_F_CHECKINS` (~180 completions) + `GEN_F_JOURNAL` (~110 marks), jittered inside bands; bands never rendered | OK — `meta.non_rendered` declares it and the detector rejects undeclared blocks (a489039d); the renderer test is still owed |
| F3 | Journaling drops below 3/week at wk 14 | generated journal marks | OK (the "3/week" marker is oracle-only) |
| F4 | ~4 of ~60 misses decided; the wk-11 APAC sync simply appeared with no Decision | four `DEC_F_*` + their source episodes (ruling: add provenance episodes for TZ_CALL, TRAVEL, ILLNESS); wk-11 `slot_fillers` entry with `recurrence_rule` and no decision | OK (provenance episodes + dispositions a489039d) |
| F5 | What filled the slot: early calls, **email-first mornings**, sleep after late nights | early calls: `slot_fillers` wk 6, 11; late nights: `SHARED_LATE_NIGHTS` (owned by arc-f); email-first mornings: `GEN_F_EMAIL_FIRST` | OK — bound by `meta.emits` (1be1cb23) |
| F6 | Root cause shared with Arc B's missed runs | `SHARED_LATE_NIGHTS`, declared by arc-f, referenced by arc-b (R5; detector enforces the week subset) | OK |
| F7 | Response in the Principle's own terms; reward/badge/public commitment are wrong answers | Principle text ("no fanfare, no celebration, no external view") | OK |
| F8 | The wk-25 return is scored positive | `EP_F_RESTART`, `DEC_F_RESTART`, phase-7 generation | OK — F1 is asked wk 19, before this; the time-cut rule must hold |
| F9 | Should have been caught wk 9–10 | generated data (two consecutive phases of decline + a repeated cause) | OK |
| F-NM | Near-misses 1–7 (illness wk 16, travel wk 12, one-off TZ call wk 6, journaling dip wk 9, Arc B link, lighter weekends, late-evening check-in) | wk 6/12/16 present; **lighter-weekend convention and the wk-9 journaling dip need generator rules; the late-evening check-in needs a completion event at ~20:30 on a lost morning** | OK — three generator rules added (lighter weekends from wk 1, wk-9 dip, wk-17 late-evening completion), c331e6f9 |
| F-REP | Missed mornings are represented by absence of a completion, not by an explicit "not done" | generator emits completions only | DECIDED — completions-only (a recurring Vikunja task emits nothing when not done); stated in the seed header |

## Arc B — quiet drift (`seed/arc-b.yaml` @938cd847, rulings applied @c331e6f9; R3 confirmed by the implementer 05:10Z)

| # | oracle point | primitives | status |
|---|---|---|---|
| B1 | The Outcome with date and measure; the date is a hard Commitment | `OUT_5K` (target_date, success_criteria — seeded as `measure`, see R4), `COM_RACE`, `DUE_BY`, `EP_B_REGISTER` (non-refundable, $35) | OK (`success_criteria`, c331e6f9) |
| B2 | Every counted deferral, in order, with dates and the reason at the time | declared emits: `GEN_B_WK5_TUE`, `GEN_B_WK6_THU`, `GEN_B_WK6_SAT`, `GEN_B_WK7_TUE`, `GEN_B_WK7_SAT`, `GEN_B_WK8_TUE`, `GEN_B_WK8_THU`, `GEN_B_WK10_THU`, `GEN_B_WK11_TUE`, `GEN_B_WK13_THU`; `GEN_B_SESSIONS` for the silent misses as absence | OK — bound by `meta.emits` (1be1cb23) |
| B3 | Which reasons repeat; the 07:30 series agreed to three times into a known quality slot | `GEN_B_WK6_THU`, `GEN_B_WK8_THU`, `GEN_B_WK10_THU` + `GEN_B_DECISIONS`; `EP_B_PLAN` marks Thu as the quality run | OK |
| B4 | Decided vs silent split (5 silent, 5 decided-then-silent) | `GEN_B_DECISIONS` (provenance episodes for the meetings and evening moves); none for the runs themselves | OK — classification in `oracle/arc-b-appendix.yaml` (1be1cb23) |
| B5 | Point of no return = CP2, Sun 08-09, by the halfway rule; not wk 10 calf, not wk 15 cold | `EP_B_PLAN` (milestones: Phase-2 45–50 min long run, wk-7 "quicker 5 min" ~10:30), `EP_B_CONDITIONING_RULE` (halfway rule, *without* the coaching clause — R1); `GEN_B_WK6_SAT`, `GEN_B_WK7_SAT`, `GEN_B_WK7_PROG` (11:10), wk-8 cutback in `GEN_B_SESSIONS` | OK — coaching clause stripped (c331e6f9) |
| B6 | No individual deferral was unreasonable | the reasons as primitives | OK |
| B7 | Should have been caught end of wk 7 (08-02) | events through wk 7 (two 1/3 weeks, one repeated reason) | OK |
| B8 | Retrospective framed as coaching: scheduling, commitment management, delegation, mindset; reset-not-quit | reasoning over B2–B7; **no primitive may state the coaching move** (R1) | OK — judgement, graded |
| B9 | Race result 32:50 → 10:35/mi (for B2, asked after 10-15) | `GEN_B_RACE` | OK |
| B-NM | Near-misses: wk 10 calf (red-flag rule in the plan), wk 15 cold, wk 2 reschedule-within-week, wk 3/12 holidays, wk 9 full week, Arc A's PT sessions not drifting, strength sessions never core | plan red-flag list (`EP_B_PLAN`); note episodes + Decisions (wk 10, 15); calendar (wk 3, 12); PT sessions rendered weekly Jun–Oct from Arc A's recurrence (`non_drifting_control`); Mon/Wed/Sun strength as Vikunja completions | PARTIAL — PT must render across B's window; strength sessions need a generator rule |

## Arc E — repeating pattern → automation (`seed/arc-e.yaml` @ad0e3e5c) — PROVISIONAL until E-1..E-3 land

| # | oracle point | primitives | status |
|---|---|---|---|
| E1-1 | ~200 mail/week across three accounts (~70/60/70); one pattern, three boxes | generator volume per account; sender domains as provenance | OK |
| E1-2 | 13 sessions, ~2 h each, the same five sub-activities in the same order | timestamped typed mail actions (read/dwell, move-to-folder by sender org, delete, star, reply) in the same order per session; span from timestamps; nothing names session/step/process | OK-ABS — **recoverability probe required at freeze** (rubric §9); adapter assumption recorded in the seed header |
| E1-3 | ~1.2 h/week ≈ 8 % of the 15 h Capacity, plus six consequential misses as the larger cost | session spans; `CAP_DEEP`; the six buried mails **and their consequences as later ordinary events** | GAP until E-2 (consequences currently generator strings) |
| E1-4 | No single session or miss justified automating | the same primitives; judgement | OK |
| E1-5 | Recognisable at the third session, wk 5 | sessions 1–3 as events + the wk-3 consequence event | OK after E-2 |
| E1-6 | The proposed automation (Kent's eight points) | **must not be seeded**; inferred from the sessions' action shape + the misses | OK-ABS — grader accepts substance, not wording |
| E1-7 | Framed as a process finding | judgement | OK |
| E2-1 | Mail from anyone on the contacts list surfaces, including a contact's newsletter | `Person.is_contact` on the eight cast members; E2_04 from PER_JOEL | OK |
| E2-2 | A contact's meeting request gets the Calendly reply, nothing else does | E2_03 from PER_CLIENT with meeting-request shape | OK |
| E2-3 | Bill, tax document, doctor's reminder become Vikunja to-dos with dates | E2_05/06/07 with `due` | OK once E-3 grounds them |
| E2-4 | Renewal notice → alert; the same vendor's weekly promo → digest/file | E2_08 (`renews`) vs E2_09, same sender | OK once E-3 grounds the subscription |
| E2-5 | Time-sensitivity grounded in something Kent has, not tone (E2_13 fake loan is NOT an alert) | **grounding primitives**: prior statements from billing_org; the clinic appointment on the personal calendar; an active subscription/prior renewal from vendor_org_a; accountant is a contact | GAP until E-3 |
| E2-6 | Interest list as of the sample week (typography dropped wk 10 → ordinary digest; k8s added wk 10 → current interest) | `EP_E_INT_ADD_TYPO`, `EP_E_INT_WK10`; replay to ask_time (rubric §2) | OK — plus the wk-1 baseline episode for the four standing Interests (E-1) |
| E-NM | E2 near-misses 1–3, 6, 7; E1 near-misses 4–5 | E2_10 (friendly spam), E2_11/E2_12 (cold calls off/on list), E2_13 (urgent spam), E2_04, E2_14; `already_automated` daily summary; `varying_recurrence` client prep | OK — verdicts move to `oracle/arc-e-oracle.yaml` (E-4) |
