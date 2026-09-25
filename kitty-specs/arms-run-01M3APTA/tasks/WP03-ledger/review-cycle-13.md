---
affected_files: []
cycle_number: 13
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T04:40:49Z'
reviewer_agent: claude
wp_id: WP03
---

REOPEN for cycle 12 (fix cycle on an approved WP; the approve @1aa59ced stands): Opus c11's seven MINORs plus the design-lead ruling (bus 20260925T043533517516Z003ce84a20) that an error row whose error begins 'ArmRefusal:' is terminal on the first attempt (no AttemptsExhausted path).
[MINOR] scripts/research/arms849/ledger.py:623 — the header missing-field guard covers only
[MINOR] scripts/research/arms849/ledger.py:363 — `pt = int(row.get("prompt_tokens", -1))` coerces before
[MINOR] scripts/research/arms849/ledger.py:362 — `exceeds_model_context` is accepted for a G or R key;
[MINOR] scripts/research/arms849/ledger.py:131-142 — `RunKey` validates nothing, and `record()` never
[MINOR] scripts/research/arms849/ledger.py:302 — `json.dumps(record, sort_keys=True, default=str)`
[MINOR] scripts/research/arms849/ledger.py:621 — `rows[0].get("record")` assumes line 1 parsed to a dict;
[MINOR] scripts/research/arms849/ledger.py:199 — `model_context_tokens=int(model_context_tokens or
