---
affected_files: []
cycle_number: 1
mission_slug: pointer-key-ledger-01M189P6
reproduction_command:
reviewed_at: '2026-08-30T05:36:07Z'
reviewer_agent: user
wp_id: WP03
---

# WP03 Review — Cycle 1 — REJECT

Reviewer: codex (advisory, read-only, module probed directly). Verdict recorded by the orchestrator.

**Nearly everything passed, including the hard parts.** Verified by the reviewer: genericity grep
clean; **totality holds** across non-dict documents, malformed predicates, unhashable values,
unicode/surrogates, million-character strings, recursive and deeply nested values — nothing escaped as
an exception; all four bool/int collision directions correct, with `2` matching `2` and float `2.0`
correctly *not* matching int `2`; absence unconditional and checked *before* suppression; `unknown`
structurally distinct from `ok`; the declaration iterated rather than the document; freshness deferred
but presence still enforced; `diagnostic_only` inert; both `unmeasured_is_unknown` directions correct;
suppression correct for valid timestamps including the exact boundary; `probes.py` untouched; 240
scoped tests pass.

One defect.

---

## A malformed `suppress_until_utc` returns `unknown` instead of declining to suppress

`scripts/canary/ledger.py:186`

Probed directly: value `1`, `minimum: 2`, and `suppress_until_utc` of either `"not-a-date"` or `123`
→ **`unknown`**. It should be **`unhealthy`** — the ordinary `minimum` verdict, with the malformed
modifier ignored.

**Why this blocks.** `unknown` is not a neutral outcome. Upstream, a *first-seen* `unknown` is
recorded **without alerting**
(`tests/canary/test_run.py::test_first_seen_unknown_is_ledgered_not_paged`). So a single typo in a
ledger's `suppress_until_utc` would silently switch off a live health rule, and the resulting silence
would be indistinguishable from health.

That is this mission's own defect class, reachable through the contract's own escape hatch — and it
is the fourth time this shape has appeared inside this mission. Suppression is an operator's
deliberate, dated exemption; anything that is not a valid one is not an exemption at all.

**Required fix.** Treat an absent, unparseable, or non-timestamp `suppress_until_utc` as "no
suppression" and evaluate the predicate normally. Never return `unknown` on the basis of malformed
suppression metadata alone.

**Required tests.** The reviewer notes the existing hostile-input tests
(`tests/canary/test_ledger_eval.py:183`) only assert that *some* valid outcome is returned, which
permits this defect. Add explicit assertions that malformed suppression falls through to the ordinary
predicate verdict:
- `suppress_until_utc: "not-a-date"` with a failing `minimum` → **unhealthy** (not unknown)
- `suppress_until_utc: 123` (non-string) with a failing `minimum` → **unhealthy**
- `suppress_until_utc: null` with a failing `minimum` → **unhealthy**
- and the passing counterparts → **ok**, confirming the modifier is ignored rather than inverted

Keep the valid-timestamp cases green: before the instant → not evaluated; after → evaluated; exact
boundary as already tested.

---

## Contract gap — my error, now fixed

The contract did not specify this case; it said only that `suppress_until_utc` is "an ISO-8601 instant
before which the predicate is not evaluated" and was silent on a malformed one. That silence is what
made `unknown` a defensible reading. `contracts/key-ledger.md` now states the rule and the reasoning
explicitly. Implement to the contract as updated.

## Note

The reviewer could not run `ruff` (unavailable in its sandbox). You ran it via `uvx` with exit 0; that
stands. Re-run it after this change.
