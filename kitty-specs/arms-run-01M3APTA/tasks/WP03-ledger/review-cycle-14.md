---
affected_files: []
cycle_number: 14
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T18:35:28Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:326 — An fsync failure after flush leaves the row on disk but absent from `_rows`; probing a retry produced two `ok` rows for one attempt, both averaged after resume — why: duplicates distort scored-cell counts and token measurements — fix: invalidate the Ledger after any append I/O failure and require reopening before further writes; add fault-injection tests.
[MAJOR] scripts/research/arms849/ledger.py:687 — Resume accepts parsed rows without validating their invariants; probes admitted outcome `"banana"`, an R scored row without calibration, and a D row using `"permitted"` beneath a `"trained"` header — why: resume bypasses the protections enforced by `record()` and exposes invalid scored rows to grading and averaging — fix: validate persisted rows and their ordered transitions before returning the ledger or repairing its tail.
[MINOR] scripts/research/arms849/ledger.py:580 — A complete final `null\n` is treated as a torn JSON line and silently deleted, whereas other non-object JSON values raise `LedgerCorrupt` — why: the non-object fold still misclassifies valid JSON corruption as recoverable truncation — fix: distinguish JSON parsing failure from parsed `None` and reject every non-object value; add a final-null regression test.

Source: Codex read-only review (gpt-6-astra), WP03 cycle 14 on lane-c @4e6e8c84, 2026-09-25 (Codex back on the personal account). 134 tests passed; the seven Opus c11 MINOR folds and the ArmRefusal-terminal ruling were confirmed present; the three findings above came from adversarial probes beyond the folds. VERDICT: REJECT.
