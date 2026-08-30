---
work_package_id: WP05
title: Shared reconciliation and its floors
dependencies:
- WP02
- WP03
requirement_refs:
- FR-004
- FR-005
- FR-006
- FR-010
- NFR-001
- NFR-002
- NFR-005
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
subtasks:
- T024
- T025
- T026
- T027
- T028
- T029
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: 'Generated from plan v2 IC-03. The shared helper exists because v1 told #913 to reuse a reconciliation it never planned.'
agent_profile: python-pedro
authoritative_surface: tests/canary/ledger_reconcile.py
create_intent:
- tests/canary/ledger_reconcile.py
- tests/canary/test_ledger_reuse.py
- tests/office2/restic_backup/test_ledger_reconciliation.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- tests/canary/ledger_reconcile.py
- tests/canary/test_ledger_reuse.py
- tests/office2/restic_backup/test_ledger_reconciliation.py
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Build the mechanism's **teeth**: derive a producer's emitted key set by executing it, reconcile that
set against the declared ledger in both directions, and make it impossible for the contract to pass
while enforcing nothing.

This is the work package that decides whether this mission is structural or decorative.

## Context you need

The generative rule is: *a test enumerates the keys the producer **actually emits** and fails if any
key is in neither list*. Everything else in the mission is downstream of that sentence being true.

A weak version of this WP is **worse than none** — it would certify the contract while enforcing
nothing, and the certification would be trusted. The specific weak versions to refuse:

- Comparing against a key list written in the test file → that is the defect, relocated.
- Asserting only one direction → the ledger rots in the other.
- Treating a missing document as `{}` → reconciles vacuously against anything.
- Parametrising over "components with a ledger" without asserting the selection is non-empty → **a
  green suite with zero assertions executed.** This repo has five documented instances of that shape
  in a single day.
- Nothing failing when a ledger is **deleted** → absence is legal for 16 components, so `git rm`-ing
  the contract would pass every gate and silently restore the old behaviour.

## Subtasks

### T024 — Tests: both reconciliation directions

**Steps**:
1. Create `tests/canary/ledger_reconcile.py` as an importable helper module (not a test module — no
   `test_` prefix, so pytest does not collect it as tests).
2. Create `tests/office2/restic_backup/test_ledger_reconciliation.py`. **This path is already
   referenced** by `restic-backup`'s `reconciliation_harness` in the inventory (WP02) — keep it exactly.
3. Assert: a producer emitting a key in neither `adjudicated` nor `diagnostic_only` fails, and the
   failure message **names the undeclared key**.
4. Assert: a ledger declaring a key the producer does not emit fails, naming the stale declaration.
5. Drive both with synthetic ledgers and synthetic emitted sets first — the helper's logic is what is
   under test here, not restic.

### T025 — Tests: the empty-selection and deleted-ledger floors

**Steps**:
1. Assert the reconciliation's component selection is **non-empty**, and that the assertion itself
   fails when the selection is empty. The simplest form is one line —
   `assert components, "no ledgers found — the reconciliation is not running"` — and it is the
   difference between this mission and a decorative one.
2. Assert the selection **equals** the set of ledger-declaring components in the inventory. Not a
   subset: equal. A component that grows a ledger and is silently not reconciled is the #913 failure
   mode.
3. Add a hardcoded pin: `restic-backup` must declare a ledger. Yes, this is a hand-maintained list —
   of **producers** (2, changing yearly), not of **keys** (14, changing per commit). Accepting one
   while refusing the other is deliberate; say so in a comment, because the next reader will
   reasonably ask.
4. Assert that removing the ledger fails the suite (simulate with a fixture inventory, not by editing
   the real one).

### T026 — Tests: the harness must prove it produced something

**Steps**:
1. Define what a harness must return: process outcome, whether the document exists, whether it parsed
   as an object, and the key set.
2. Assert reconciliation **fails** when: the producer exited non-zero unexpectedly; the document is
   absent; the document is not a JSON object; or the key set is empty.
3. Each must fail *distinctly* — the evidence should say which floor was hit. "Reconciliation failed"
   with no cause sends the reader to the wrong place.

### T027 — Implement the shared helper

**Steps**:
1. In `tests/canary/ledger_reconcile.py`, implement roughly:
   - `load_ledgers(inventory) -> dict[str, dict]` — every component declaring a `key_ledger`.
   - `declared_keys(ledger) -> set[str]` — the union of both lists.
   - `assert_reconciles(emitted: EmissionResult, ledger: dict, component: str) -> None` — both
     directions plus the T026 floors, raising `AssertionError` with actionable messages.
2. **No component names, no host names, no producer-specific keys.** This module is what #913 reuses;
   a single `restic` reference in it defeats FR-010.
3. Give it a module docstring stating what it guarantees and — importantly — what it does **not**:
   it binds a ledger to *the repo copy* of a producer. See the drift caveat in `research.md` R4.
4. Type-annotate the public surface. Target Python 3.11.

### T028 — Reconcile `restic-backup`, and assert the early-exit verdicts

**Steps**:
1. In `test_ledger_reconciliation.py`, execute the real producer through the WP01 harness pattern
   (stubbed `restic` / `mountpoint` / `du` / `df` on `PATH`), collect the emitted document, and run it
   through `assert_reconciles` against the real ledger from `service-inventory.json`.
2. Then assert **evaluator verdicts** on each early-exit path — mount failure, repo inaccessible,
   backup failure. Feed each emitted document to WP03's evaluator and assert the verdict.

   **Why verdicts and not reconciliation here**: the producer writes a *static heredoc*, so its key
   set is invariant across paths by construction — reconciling every early exit re-checks the same
   names and can never fail. What those paths actually pin is the **values** the predicates must
   survive: `restic_exit_code: 127`, `snapshot_count: null`, `last_integrity_check_utc` carried or
   `null`. That is where the real risk lives, and it is where a false-positive would come from.
3. Assert explicitly that the **happy-path document reads healthy** — introducing the contract must not
   change the reported health of a healthy system.

### T029 — The reuse test (SC-006)

**Purpose**: Prove a second producer needs no change to shared logic. This is the acceptance test for
the mission's stated reason for existing, and v1's version tested only half of it.

**Steps**:
1. In `tests/canary/test_ledger_reuse.py`, create a **fictitious producer** — a tiny shell script in
   `tmp_path` emitting a JSON document with an entirely different key set and different good-sets.
2. Declare a ledger for it inline, with a different shape from restic's (different predicates,
   different diagnostic keys).
3. Run it through **both** shared pieces: `assert_reconciles` and WP03's evaluator.
4. Assert both behave correctly with **zero changes** to either module — that is the property SC-006
   claims. v1's version exercised the evaluator only and would have been cited as satisfying SC-006
   while the reconciliation half was untested.
5. Assert the failure modes too: an undeclared key in the fictitious producer fails, and a bad value
   against its good-set is unhealthy.

## Branch Strategy

`feat/934-pointer-key-ledger`, `single_branch`. Work in the lane workspace provided.

## Test Strategy

Required — this WP *is* the test strategy for the mission. Offline, deterministic, no network, no
office2 access, no restic install. The fictitious producer must be created in `tmp_path`, never
committed as a fixture script that could drift.

## Definition of Done

- [ ] `tests/canary/ledger_reconcile.py` exists, generic, with no component or host name in it.
- [ ] Both reconciliation directions fail with messages naming the specific key.
- [ ] Empty selection fails; selection equals the ledger-declaring set; `restic-backup` is pinned.
- [ ] A deleted ledger fails the suite.
- [ ] Harness floors enforced distinctly: exit status, document present, parses as object, non-empty.
- [ ] `restic-backup` reconciles against its real ledger by executing the producer.
- [ ] Early-exit **verdicts** asserted; happy path still reads healthy.
- [ ] The fictitious-producer test drives **both** shared modules unchanged.
- [ ] `make test` ≥ 6324 passing.

## Risks and Review Guidance

1. **Run the three sabotage checks from `quickstart.md` yourself.** Add an undeclared key to the
   producer; add a phantom key to the ledger; delete the ledger. Each must go red. If any passes
   silently, reject — the contract is decorative and the mission has not been delivered.
2. **Check the non-empty assertion exists** and that a test proves it fires. This is the single
   cheapest line in the mission and the one most likely to be omitted as obvious.
3. **Grep the helper for `restic` / `office2` / `office4` / `snapshot_`.** Any hit fails FR-010, and
   #913 is the immediate consumer.
4. **Confirm early exits assert verdicts, not key sets.** If the implementer reconciled every early
   exit, they have written guaranteed-pass work and missed the values that matter.
5. **Confirm the reuse test drives the reconciliation**, not just the evaluator. That was v1's gap and
   it would let SC-006 be marked satisfied on half the evidence.
