---
affected_files: []
cycle_number: 8
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T18:35:49Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/litscan.py:37 — `X="{}{}".format("or","acle")` produces no scan hits and the isolation gate passes — why: literal format calls bypass the required forbidden-material scan — fix: evaluate allowlisted literal formatting calls in the resource-limited child and add a failing gate regression.
[MAJOR] scripts/research/arms849/litscan.py:47 — an unclassified AST expression returns `_UNKNOWN` and the scan returns `[]`; the grammar-partition test also derives its expected coverage from the same automatic complement — why: unknown syntax silently passes instead of failing closed — fix: explicitly enumerate supported nodes and reject unclassified expressions, with an injected-unknown regression.
[MAJOR] scripts/research/arms849/gates.py:203 — `excluded_prefixes=()` passes with excluded material present; a missing package directory also passes as "0 modules scanned" — why: empty scan inputs can certify isolation without checking it — fix: require the canonical exclusion list and a nonempty package file inventory.
[MINOR] kitty-specs/arms-run-01M3APTA/contracts/gates.md:7 — carried-forward contract mismatch: the lane's copy lacks the dated two-phase amendment and still places boundary and substrate health inside the container — why: the binding contract omits current-stack identity, timezone refusal, and the inclusive freshness window implemented by c7 — fix: bring lane-d level with the mission branch's contracts (the amendment IS on feat/849-arms-run; lane-d branched before it landed).
[MINOR] tests/research/test_arms849_gates.py:107 — the reference-directory test creates and removes `REPO_ROOT/build/_guard_probe_*`, causing three read-only failures despite `/dev/shm` basetemp — why: the prescribed review cannot execute these guard regressions — fix: construct the reference fixtures under `tmp_path` and inject the corresponding root.

Source: Codex read-only review (gpt-6-astra), WP04 cycle 8 on lane-d @657b643d, 2026-09-25. All three c7 folds confirmed by direct checks (both inclusive timestamp boundaries, previous-stack replay refusal, naive-timestamp refusal); calibration probes (tie, jump-over, cap, halt) passed; litscan's memory-limit probe fails closed. VERDICT: REJECT.
