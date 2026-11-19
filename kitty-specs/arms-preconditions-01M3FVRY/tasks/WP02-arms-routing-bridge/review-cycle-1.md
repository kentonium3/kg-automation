---
affected_files: []
cycle_number: 1
mission_slug: arms-preconditions-01M3FVRY
reproduction_command:
reviewed_at: '2026-09-27T06:15:43Z'
reviewer_agent: codex-gpt-6-astra
wp_id: WP02
---

# WP02 review cycle 1 — REVISE

Reviewer: Codex (gpt-6-astra, OpenAI Codex CLI), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope 5dc9f553..b20243c2; properties Q1–Q10.

## Findings
[MAJOR] scripts/research/arms849/arm_g.py:782 — Cancellation discards terminal exceptions — a real GraphArm probe detected a cross-group leak during grace, but the caller received `TimeoutError` instead of `PremiseViolated`; cancelling the concurrent future loses the coroutine’s eventual exception — preserve the coroutine’s outcome separately and propagate terminal exceptions after acknowledgement.
[MAJOR] scripts/research/arms849/arm_g.py:785 — Poisoning leaves the loop running — after `GCancellationUnacknowledged`, releasing the stalled transport caused the existing GraphArm retrieval to issue **eight additional queries** — prevent further transport operations and stop the loop before returning the fatal signal.
[MAJOR] scripts/research/arms849/arm_g.py:739 — Quiescence checks only one task snapshot — a task that spawns another task during cancellation cleanup leaves that descendant pending after acknowledgement; reproduced — track and drain descendants until all work has finished before setting acknowledgement.
[MAJOR] scripts/research/arms849/arm_g.py:720 — `close()` runs concurrently with active submissions — its `_guarded` cleanup and the active operation’s cleanup cancel and await each other; reproduced two `RecursionError`s and two remaining tasks — coordinate shutdown through one cancellation owner and prevent competing quiescence passes.
[MAJOR] scripts/research/arms849/arm_g.py:507 — Known UUIDs bypass group validation — a locally mapped UUID explicitly carrying another question’s `group_id` is accepted without recording a leak; reproduced — check reported group membership before accepting any UUID and add this regression.
[MINOR] tests/research/test_arms849_arm_g.py:1039 — The live routing test initializes the root driver inside a running loop — installed FalkorDriver schedules index writes against `default_db`, so this test does not demonstrate complete root isolation — construct the root outside the loop or exercise `make_bridge`, and assert absence of root queries.

VERDICT: REVISE
