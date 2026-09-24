# Decision Moment `01M3AX1M4PE2XQWZT4Y63KSCS0`

- **Mission:** `arms-run-01M3APTA`
- **Origin flow:** `plan`
- **Slot key:** `plan.arm-g.per-question-rebuild`
- **Input key:** `arm_g_per_question_rebuild`
- **Status:** `resolved`
- **Created:** `2026-09-24T23:47:07.030603+00:00`
- **Resolved:** `2026-09-24T23:48:34.007625+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Rubric section 2 says G is built per question by REPLAY, never by filtering a final-state graph. Mechanism: a fresh graph per question (separate group_id per question, e.g. q_C1) rebuilt from the loader's replayed view, or one graph with validity timestamps filtered at query time (forbidden?) — confirm the former and name the group_id convention.

## Options

_(none)_

## Final answer

Per design lead 23:43Z ruling 3: one FalkorDB graph per question, group_id = arms_<question> in [A-Za-z0-9_] (hyphen bug #976/RQ-6a), built by replaying primitives to ask_time from the loader's view, dropped after the three repeats; repeats reuse the loaded graph (NFR-005); ledger records nodes/edges/episodes loaded per question; search(group_ids=[...]) always explicit; query-time validity filtering forbidden

## Rationale

_(none)_

## Change log

- `2026-09-24T23:47:07.030603+00:00` — opened
- `2026-09-24T23:48:34.007625+00:00` — resolved (final_answer="Per design lead 23:43Z ruling 3: one FalkorDB graph per question, group_id = arms_<question> in [A-Za-z0-9_] (hyphen bug #976/RQ-6a), built by replaying primitives to ask_time from the loader's view, dropped after the three repeats; repeats reuse the loaded graph (NFR-005); ledger records nodes/edges/episodes loaded per question; search(group_ids=[...]) always explicit; query-time validity filtering forbidden")
