---
affected_files: []
cycle_number: 16
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T18:56:56Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:266 — Persisted `plan=72.9` and `blinding_seed=7.9` resume successfully as 72 and 7 because Header.from_dict applies int() — why: invalid header values silently satisfy configuration binding and change the recorded blinding seed's meaning — fix: validate exact integer types on creation and replay; remove coercion from header loading and resume comparisons.
[MINOR] scripts/research/arms849/ledger.py:414 — A scored row with serving `parallel=True` is accepted and resumes under a header with `parallel=1`; likewise persisted `model_context_tokens=262144.0` passes header comparison against integer 262144 — why: Python equality admits schema-invalid values despite the configuration binding contract — fix: validate persisted integer fields and compare serving configurations with type-aware equality.

Source: Codex read-only review (gpt-6-astra), WP03 cycle 16 on lane-c @39d6f3ed, 2026-09-25. 168 tests passed; all three c15 folds confirmed by probe, plus safe `with`-block cleanup after a write/fsync failure. The two findings are the same class as c15 (coercion / type-loose equality), now at the header. VERDICT: REJECT.
