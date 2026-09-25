---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T22:10:00Z'
reviewer_agent: claude
wp_id: WP08
---

[MAJOR] scripts/research/run_849_harness.py:838 — Two live_binding calls with identical successful gate inputs produce different timestamp-bearing gate digests; reopening the ledger raises LedgerBoundToAnotherConfig — why: ordinary live resume is impossible despite passing fake-resume tests — fix: preserve immutable bound gate evidence and record fresh session revalidation separately instead of rebinding the header.
[MAJOR] scripts/research/run_849_harness.py:884 — With FakeGtt(58.0), the secondary context probe sends its request and returns passed=True — why: the full-size secondary request bypasses the registered 57.5 GiB ceiling — fix: refuse before sending when telemetry is unreadable or breached, and fail the gate on an invalid or breached measurement window.
[MAJOR] scripts/research/run_849_harness.py:901 — --host-gates --secondary still supplies expect_n_ctx=262144 and expect_rope="none", confirmed through the CLI — why: WP08’s host-phase adapter rejects the intended 393216/YaRN stack, blocking secondary execution — fix: pass the selected configuration into host_phase and derive its expectations from that configuration.
[MINOR] scripts/research/arms849/sampler.py:166 — Carried-forward dependency gap confirmed: RSS sampling requires docker stats inside a runner without Docker access — why: live G execution stops at sampler_unreadable; WP08 correctly refuses to fabricate telemetry — fix: provide the approved sampler with a readable host-backed RSS source.
[MINOR] scripts/research/arms849/substrate.py:697 — Carried-forward dependency gap confirmed: run launches the runner without executing the host phase or supplying the current stack’s up_ts — why: the default launch path cannot satisfy the two-phase gate contract — fix: invoke the host phase after health and pass the same up_ts into the runner.
[MINOR] scripts/research/run_849_harness.py:347 — An unrelated transport ConnectionError subclass named ArmRefusal becomes terminal after one attempt with zero health checks — why: class-name matching misclassifies infrastructure failures and suppresses their retry ladder — fix: register concrete refusal exception types and use isinstance; retain the existing ordinary-ConnectionError retry test.
[MINOR] scripts/research/run_849_harness.py:715 — A complete primary carrying SKIP_GATES_SHA successfully opens a secondary ledger — why: this contradicts the CLI’s explicit claim that development ledgers cannot be used as primaries — fix: reject skipped-gate bindings in require_complete_primary.
[MAJOR] scripts/research/run_849_harness.py:346 — (design lead W8-1, bus 20260925T220551226384Z4831c24f84) terminal-refusal detection by class NAME; a rename silently sends a permanent defect through two 90-min retries and an unrelated same-named class becomes terminal — fix: required `refusal: type[BaseException]` on ArmRegistration, `isinstance(exc, reg.refusal)`, refuse a registration without it; can-fail tests (renamed class still terminal; unrelated same-named class not).
[MINOR] scripts/research/run_849_harness.py (_calibration_obj) — (design lead W8-2) a record missing a field raises a bare KeyError from a dict comprehension — fix: explicit error naming the field and the ledger path.

Source: Codex read-only review (gpt-6-astra), WP08 cycle 1 on lane-h @0be1e7f1, 2026-09-25 + design-lead direct read (APPROVE with W8-1/W8-2). The two carried-forward dependency gaps (substrate.run host phase; RssSampler docker socket) are NOT WP08 defects — they are reopens of WP02 and WP04 per the design lead's rulings (bus 20260925T220551226384Z4831c24f84, 20260925T220651378865Z5316e3fceb), sequenced after WP08 c2. VERDICT: REJECT.
