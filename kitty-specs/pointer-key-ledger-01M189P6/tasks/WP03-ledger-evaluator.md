---
work_package_id: WP03
title: Pure ledger evaluator
dependencies:
- WP02
requirement_refs:
- FR-001
- FR-002
- FR-007
- FR-016
- FR-019
- NFR-002
- NFR-004
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
- T015
- T016
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: Generated from plan v2 IC-02. Split from probe wiring (WP04) so the evaluator is unit-testable in isolation — NFR-006 totality requires it.
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- scripts/canary/ledger.py
- tests/canary/test_ledger_eval.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/canary/ledger.py
- tests/canary/test_ledger_eval.py
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Write `scripts/canary/ledger.py`: a **pure, total** function that adjudicates a state document against
a declared ledger. No I/O, no component names, no host names, no producer-specific key names.

This module is the mechanism the whole mission rests on, and it is deliberately small enough to reason
about exhaustively. WP04 wires it into the probe; you do not touch `probes.py`.

## Context you need

Read `contracts/key-ledger.md` § *Adjudication predicates* and `data-model.md` § *Predicate* first —
they are the authority. The invariants there (P1–P5) are the specification.

### The three ways to get this wrong

Every one of them reintroduces the exact defect this mission exists to close. They are the reason this
WP is separate and unit-tested in isolation.

**1. A type guard that skips.** The neighbouring module does this:

```python
if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES:
```

A value of an unexpected type is *skipped* and reads healthy. Do not copy that shape. A value not in
the good-set is **unhealthy regardless of type**. (Those existing guards stay where they are for
unrelated historical reasons; they are not your template.)

**2. Bool/number equality, in both directions.** Python:

```python
False in [0, 3]        # True   -> restic_exit_code: false would read HEALTHY
True  in [0, 3]        # False
1     in [True, None]  # True   -> a numeric 1 satisfies the integrity good-set
0     in [False]       # True
```

The producer builds its JSON by **shell interpolation**, so a value arriving as the wrong type is a
realistic drift, not a hypothetical. Matching must require type identity, with `bool` and `int`
treated as distinct in both directions.

**3. Raising.** Upstream, `run_probe` catches every exception and converts it to `unknown` — and a
**first-seen `unknown` is recorded without alerting** (see
`tests/canary/test_run.py::test_first_seen_unknown_is_ledgered_not_paged`). So an evaluator that
throws on a document carrying `integrity_check_passed: false` produces **silence**, converting the bug
being fixed into a differently-shaped one. Totality is a correctness requirement (NFR-006), not
hygiene.

## Subtasks

### T012 — Tests: membership semantics, all four collision directions

**Steps**:
1. Create `tests/canary/test_ledger_eval.py`.
2. Assert the four bool/number cases resolve as the contract requires: `1` vs `[true, null]` → no
   match; `0` vs `[false]` → no match; `false` vs `[0, 3]` → no match; `true` vs `[1]` → no match.
   Test all four explicitly — the third is the dangerous one and it is the one a partial fix misses.
3. Assert the ordinary cases still work: `0` vs `[0, 3]` matches; `true` vs `[true, null]` matches;
   a present JSON `null` vs `[true, null]` matches.
4. Assert a value outside the good-set is unhealthy **whatever its type** — a string `"false"`, a
   float, a list — and that the evidence names the key and the offending value.

### T013 — Tests: absence, and the unmeasured case

**Steps**:
1. Assert an adjudicated key **absent** from the document is unhealthy for *every* predicate form —
   `good_values`, `minimum`, and `freshness` — including when `null` is in its `good_values`. Absence
   and present-`null` are different conditions; the contract's rule is unconditional.
2. Assert a present `null` for a `minimum` predicate carrying `unmeasured_is_unknown: true` yields
   **unknown** — not unhealthy, not healthy.
3. Assert a present `null` for a `minimum` predicate *without* that flag is unhealthy.
4. Assert `diagnostic_only` keys never influence the verdict, whatever their values.

### T014 — Tests: totality

**Steps**:
1. Drive the evaluator with hostile inputs and assert **no exception escapes**, in every case: a
   document that is not a dict; nested structures where scalars are expected; a `minimum` compared
   against a string; `good_values` containing unhashable values; a malformed predicate that survived
   validation; unicode and very long strings; a `freshness` key holding a non-string.
2. Assert each returns a *decided* result with evidence rather than raising.
3. Prefer a table-driven or property-style test here — this is the one place breadth matters more than
   depth.

### T015 — Implement the evaluator

**Steps**:
1. Create `scripts/canary/ledger.py`. Match the neighbouring module's conventions: `from __future__
   import annotations`, module docstring explaining *why* the module exists, typed signatures, no
   third-party imports. Target **Python 3.11** — CI pins 3.11 while local interpreters are newer.
2. Public surface, roughly:
   - a small result type carrying outcome (`ok` / `unhealthy` / `unknown`) and `evidence`;
   - `evaluate(document: dict, ledger: dict) -> Result` which **iterates the declaration**, not the
     document. Iterating the document is how absent keys go unnoticed.
3. Implement membership with a type-identity helper — `bool` matches only `bool`, numbers match
   numbers, `None` matches `None`. Write it once and use it everywhere.
4. Wrap the whole evaluation so no exception escapes; an internal failure returns `unknown` with
   evidence naming what could not be evaluated. **`unknown` must be distinguishable from healthy** in
   the return type — that distinction is the mission in miniature.
5. Document the three traps above as comments where the code addresses them, in the style of the
   `_PRUNE_OK_EXIT_CODES` comment (which explains *why* a duplication must not be tidied). A future
   reader must be able to see why the obvious simplification is wrong.

**Do not** implement freshness here beyond recognising the predicate and deferring — WP04 owns
timestamp resolution, which needs probe context. Return a marker the probe layer resolves.

### T016 — First-run suppression for `snapshot_count` (FR-019)

**Purpose**: A brand-new repository legitimately reports one snapshot on its first night. Under a bare
`minimum: 2` that alerts for a full day on a correctly functioning backup — arriving exactly when the
operator is standing the thing up and is most primed to dismiss its alerts. #913 creates a new
repository imminently, so this is not hypothetical.

**Steps**:
1. The clause is **already defined** — `suppress_until_utc`, a `minimum` modifier in the contract's
   *Predicate modifiers* table. You are consuming a settled vocabulary, not inventing one. (This was
   changed after `/spec-kitty.analyze`: the original prompt asked you to invent the clause, but the
   validator that must accept it is owned by WP02 and runs first, so an invented field would have
   been rejected and you could not have fixed it without editing another WP's files.)
2. Implement it generically: when the predicate carries `suppress_until_utc` and the evaluation
   instant is before it, the predicate is **not evaluated** and contributes nothing to the verdict.
   No key names in code.
3. Note *why* the contract chose an explicit dated exemption over inferring "new repository" from
   other keys: every signal a new repository produces, a **wiped** repository can also produce, and
   conflating them defeats the very rule `snapshot_count` exists to enforce.
4. Test both directions: suppressed on a genuine first run, and **not** suppressed on an established
   repository reporting 1 (which is the wipe case the rule exists to catch). Getting this backwards
   would silently disable the wipe detection.

## Branch Strategy

`feat/934-pointer-key-ledger`, `single_branch`. Work in the lane workspace provided.

## Test Strategy

Required, and this WP is *mostly* tests by design — the evaluator's value is that it is exhaustively
specified. Offline, deterministic, no filesystem, no network. Every test constructs its ledger and
document inline. Prefer many small explicit cases over a few broad ones; this module's failure modes
are all about specific value/type combinations.

## Definition of Done

- [ ] `scripts/canary/ledger.py` exists, pure and importable with no side effects.
- [ ] Membership requires type identity; all four bool/number directions asserted.
- [ ] A value outside a good-set is unhealthy regardless of type.
- [ ] An absent adjudicated key is unhealthy for every predicate form.
- [ ] `unmeasured_is_unknown` yields `unknown`, distinguishable from healthy in the return type.
- [ ] No input causes an exception to escape; proven by hostile-value tests.
- [ ] First-run suppression is declarative and correct in both directions.
- [ ] No component name, host name, or producer-specific key name appears anywhere in the module.
- [ ] `make test` ≥ 6324 passing.

## Risks and Review Guidance

1. **Grep the module for `restic`, `office2`, `office4`, `snapshot_`, `integrity_`.** Any hit is a
   reject — genericity is the requirement FR-010 and SC-006 rest on.
2. **Check for `isinstance` used as a skip.** Any guard whose *else* branch falls through to healthy is
   the fail-open shape. `isinstance` used to *reject* is fine; used to *skip* is not.
3. **Verify all four collision directions are tested.** A fix covering only `1 in [true]` is the
   half-fix the review caught in the spec.
4. **Totality is not a code-reading exercise.** Ask for the hostile-value test list and check it
   includes non-dict documents and malformed predicates.
5. **First-run suppression backwards** would disable wipe detection entirely, which is a silent
   regression on a P2 requirement. Confirm the established-repo-reporting-1 case still alerts.
