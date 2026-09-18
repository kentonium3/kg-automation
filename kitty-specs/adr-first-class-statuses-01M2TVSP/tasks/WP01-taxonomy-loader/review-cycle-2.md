---
affected_files: []
cycle_number: 2
mission_slug: adr-first-class-statuses-01M2TVSP
reproduction_command:
reviewed_at: '2026-09-18T22:24:11Z'
reviewer_agent: user
wp_id: WP01
---

# WP01 review feedback #2 — REQUEST CHANGES

**Reviewer**: Codex (read-only, advisory) · **Diff**: `8ba83264` · **Date**: 2026-09-18

Five findings closed. Three not closed, and they share **one root cause I introduced while fixing F7**:
the mixed-type `level` vocabulary is exposed but never validated.

`_MIXED_KEYS` short-circuits `_require_vocabulary` and does `tuple(raw)` with no checks. So `level`
accepts whitespace-bearing strings (reopening F5), arbitrary nested containers which stay mutable
through `allowed("level")` (reopening F6), and duplicates. Fixing one finding opened a hole in two
others — exactly what a verification pass is for.

## Accepted

**F5 / F6 / NEW DEFECT — validate the mixed vocabulary instead of waving it through.**
`level` legitimately holds both `"1"` and `1`, which is why it was exempted; that is an argument for a
*different* validator, not for none. Fix: entries must be `str` or `int` (rejecting `bool`, which is an
`int` subclass and would compare equal to `1`); string entries follow the same canonical-token rule as
everywhere else; duplicates are rejected comparing type and value together so `"1"` and `1` both remain
legal. Rejecting containers by type removes F6's deep-freeze problem **by construction** — there is
nothing nested left to mutate.

## Rejected, with reasoning

**F9 — "no regression test distinguishes the one-pass duplicate detection from the old O(n²)."**
Correct, and it should stay that way. The change is **behaviour-preserving by design**: both
implementations reject exactly the same inputs with the same message, which is why the existing
duplicate tests pass against either. The only test that could distinguish them is a timing assertion,
and a flaky timing test in a pre-commit hook is worse than the O(n²) it would be guarding. Recorded
rather than papered over.
