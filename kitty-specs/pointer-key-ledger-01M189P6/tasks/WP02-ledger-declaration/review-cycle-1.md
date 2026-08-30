---
affected_files: []
cycle_number: 1
mission_slug: pointer-key-ledger-01M189P6
reproduction_command:
reviewed_at: '2026-08-30T05:16:28Z'
reviewer_agent: user
wp_id: WP02
---

# WP02 Review — Cycle 1 — REJECT

Reviewer: codex (advisory, read-only). Verdict recorded by the orchestrator, which independently
confirmed the finding by reading the source.

**Almost everything passed.** Verified by the reviewer: 34 focused tests green; `--strict` on the real
tree reports 0 findings; rule 8's missing / empty / non-string / absolute / **nonexistent** cases all
behave as the revised contract requires; the ledger declares 10 adjudicated + 4 diagnostic keys; the
prose-binding test was genuinely strengthened and does **not** bind to `probes.py` constants. The
rule-8 relaxation landed correctly and did not over-relax.

One defect.

---

## `key_ledger: null` validates clean

`tooling/scripts/validate_architecture_data.py:348`

```python
ledger = hc.get("key_ledger")
if ledger is None:
    return
```

`hc.get("key_ledger")` returns `None` for **two different conditions**: the field is absent (legal —
16 components have no ledger), and the field is present but `null` (malformed). The early `return`
then skips every structural rule.

The `key-ledger-shape` rule immediately below would catch a non-dict — it is simply unreachable for
`null`.

**Failure scenario.** Someone writes `"key_ledger": null` into a component's `health_check`. The
validator passes it, the pre-commit hook passes it, CI passes it — and the component silently has no
adjudication at all. A declaration that is present and means nothing is precisely the shape this
mission exists to retire, so it should not be possible to write one.

**Required fix.** Distinguish absence from present-null:

```python
if "key_ledger" not in hc:
    return
ledger = hc["key_ledger"]
```

The existing `isinstance(ledger, dict)` check then catches `null`, a string, a list, and a number
without further change.

**Required tests** in `tests/architecture/test_key_ledger_rules.py`:
- `"key_ledger": null` → `key-ledger-shape` finding
- `"key_ledger": "some string"` → finding
- `"key_ledger": []` → finding
- `key_ledger` **absent** → still **no** finding (the guard that must not regress — 16 components
  depend on it)

---

## Note on review coverage, not a defect in your work

The reviewer could not execute the producer-execution check: the read-only sandbox gave it no
writable temp directory, so `tmp_path` setup failed before the producer ran. The ledger-vs-producer
key-set match is therefore **unverified by the reviewer** this cycle, though you verified it yourself
by executing the producer and the count (10 + 4 = 14) is consistent. The next review dispatch will
point the sandbox at a writable location so this is checked independently.
