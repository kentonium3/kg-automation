---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:58:04Z'
reviewer_agent: claude
wp_id: WP04
---

[BLOCKER] scripts/research/arms849/preflight.py:46 — Registered checker module does not exist; invocation returns ModuleNotFoundError — every real preflight refuses — derive the actual check_849_oracle module name from exclusion data and test all four real imports.
[BLOCKER] scripts/research/arms849/gates.py:113 — Missing or empty checker results pass; confirmed with a re-signed fabricated record — required checker execution is not established — require exactly the four expected checker outcomes with strict successful values.
[MAJOR] scripts/research/arms849/gates.py:130 — Export hash is compared only against stored manifest metadata — a fictitious matching hash passes without checking exported bytes — recompute the content hash inside the gate, excluding the manifest itself.
[MAJOR] scripts/research/arms849/litscan.py:30 — Literal unpacking is omitted from supported AST nodes — `"%s%s" % (*("or", "acle"),)` evades this scanner despite WP02 detecting it — support unpacking and run WP02’s adversarial constructions against the production scanner.
[MAJOR] scripts/research/arms849/calibration.py:106 — Wall-clock timestamp makes identical inputs produce different records; as_record() also includes the ledger-reserved `ts` field — direct persistence through write_calibration rejects it — return a deterministic payload and let the ledger author its timestamp.
[MAJOR] scripts/research/arms849/sampler.py:61 — Failed readings retain the previous numeric peak, and subsequent success erases the failure reason — incomplete measurement can appear successful — invalidate the window with None and retain its failure reason.
[MAJOR] scripts/research/arms849/sampler.py:70 — Sampling waits one second after each read finishes — period becomes read duration plus one second, violating 1 Hz — schedule readings against monotonic deadlines and report missed intervals.
[MAJOR] tests/research/test_arms849_gates.py:105 — Claimed renamed-directory refusal test only invokes the seed checker — it never removes reference material or tests the real presence guard — exercise absent, empty, and incomplete reference directories and assert no checker runs.
[MAJOR] tests/research/test_arms849_gates.py:249 — Tokenizer-equivalence gate is skipped and has no injected-mismatch test — the required negative proof for every gate is missing — inject unequal client/server tokenization and assert refusal.

Source: Codex read-only review, WP04 cycle 1, 2026-09-25. VERDICT: REJECT (seven, all accepted).
