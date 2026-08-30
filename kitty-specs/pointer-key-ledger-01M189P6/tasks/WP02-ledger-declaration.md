---
work_package_id: WP02
title: Ledger declaration and structural validation
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-009
- FR-017
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: Generated from plan v2 IC-01.
agent_profile: python-pedro
authoritative_surface: tooling/scripts/
create_intent:
- tests/architecture/test_key_ledger_rules.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- docs/design/architecture/data/service-inventory.json
- tooling/scripts/validate_architecture_data.py
- tests/canary/test_inventory_health_checks.py
- tests/architecture/test_key_ledger_rules.py
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Load it before reading further.

## Objective

Turn the key ledger from an idea into **validated data**: define the `key_ledger` structure, declare
`restic-backup`'s, and make a malformed, self-contradictory, or unreconciled ledger impossible to
merge.

Read `contracts/key-ledger.md` in full before starting. It is the authority for this WP; this prompt
tells you how to land it, not what it says.

## Context you need

`docs/design/architecture/data/service-inventory.json` is the authoritative machine-readable record of
every service. Each component carries a `health_check` object. The `restic-backup` entry's
`health_check.expected` already states — **in English** — three real rules, and `probes.py` enforces
all three. What no rule covers, anywhere, is the other seven emitted keys.

You are adding a machine-readable `key_ledger` to that `health_check`, and teaching the
architecture-data validator to police its structure.

### ⚠️ The validator is a blocking Docs-CI gate

`tooling/scripts/validate_architecture_data.py` runs in CI **and** in the repo's pre-commit hook. A
rule that is too broad blocks unrelated work across the whole repository. Two specific traps:

1. **Gate on `entry.get("health_check")`, never on `"key_ledger" in entry`.** The validator walks
   *every nested dict* via its object iterator, so your per-key predicate objects
   (`{"good_values": [0, 3]}`) will each be yielded as an "entry" in their own right. A loosely-gated
   rule will fire on those fragments and produce nonsense findings.
2. **Absence must stay legal.** 16 of the 17 pointer-emitting components have no ledger and must
   remain valid. `key_ledger` is optional; only its *contents* are constrained.

## Subtasks

### T007 — Tests for the structural rules

**Purpose**: Red-first. Each of the eight rules in the contract gets a test that fails before the rule
exists.

**Steps**:
1. Create `tests/architecture/test_key_ledger_rules.py`. Follow the conventions of the existing
   architecture-data tests — check how they import and invoke the validator before writing yours.
2. Write one failing case per rule from `contracts/key-ledger.md` § *Structural rules*:
   unknown member key; `adjudicated` not an object; `diagnostic_only` entry missing a non-empty
   `reason`; a key in **both** lists; zero predicates on an adjudicated key; two predicates on one
   key; malformed `good_values` (empty array) and malformed `minimum` (non-numeric); a ledger on a
   non-pointer `health_check` method; two keys carrying `freshness`; and a `key_ledger` whose
   `reconciliation_harness` is missing or names a path that does not exist.
3. Write the **negative** cases too, and treat them as equally important: a component with no
   `key_ledger` validates clean, and a well-formed ledger validates clean. These are what stop an
   over-broad rule from reddening the repo.

**Validation**: every new test fails for the right reason before T008.

### T008 — Implement the structural rules

**Steps**:
1. Read the validator's existing structure first. It is a "rules-as-code" module — a set of check
   functions over iterated objects, with findings accumulated. Match that shape exactly; do not
   introduce a JSON-Schema dependency.
2. Add one check function covering the contract's eight rules, gated on `entry.get("health_check")`.
3. For the `reconciliation_harness` existence check, resolve the path **relative to the repo root**,
   not the current working directory — the validator runs from CI, from the hook, and by hand.
4. Findings must name the component and the offending key. A finding that says only "invalid ledger"
   is not actionable.

**Validation**: T007's tests all pass. `--strict` over the real repo reports **0 findings** before you
add the ledger in T009.

### T009 — Author `restic-backup`'s ledger

**Purpose**: Declare all fourteen keys WP01 emits.

**Steps**:
1. Add `key_ledger` to `restic-backup`'s `health_check`, exactly as laid out in
   `contracts/key-ledger.md` § *Shape* — ten adjudicated, four diagnostic-only with reasons, plus
   `reconciliation_harness` pointing at `tests/office2/restic_backup/test_ledger_reconciliation.py`
   (WP05 creates that file; the path is agreed now so the two WPs cannot disagree).
2. Take the good-sets and their **rationale** from the contract. Two carry hard-won history and must
   keep it in their reasons or nearby prose:
   - `restic_exit_code: [0, 3]` vs `prune_exit_code: [0]` — deliberately different. A *backup*
     exiting 3 produced a snapshot; a *forget* exiting 3 did not. **Never merge them**; merging is a
     named prior regression (#902).
   - `script_finished_at_utc` is diagnostic-only *and must never become a freshness fallback* — it was
     one, and a run producing no snapshot read fresh through it (#902/FR-009).
3. Update `last_updated` and `updated_by` on the document per the file's existing convention.

**Validation**: `validate_architecture_data.py --strict` reports 0 findings with the ledger present.

### T010 — Reduce the `expected` prose to point at the ledger

**Purpose**: Stop two authoritative descriptions of the same rules from coexisting.

**Steps**:
1. `health_check.expected` currently restates the three enforced rules in prose. Rewrite it to name
   the ledger as authoritative and describe only what the ledger cannot express — the *why* behind
   the good-sets, which is genuinely valuable and belongs in prose.
2. Do **not** delete the reasoning. The `{0,3}` vs `{0}` distinction, the `127` sentinel, and the
   #902 fallback hazard are the kind of context that stops a future reader "simplifying" the ledger.
3. Do the same for the `note` field where it enumerates schema-v1 fields — that list is now stale
   (fourteen keys, schema 2) and a stale enumeration is exactly the rot this mission is about.

### T011 — Rewrite the prose-binding test

**Purpose**: Keep a guard that exists for good reason, without letting it block T010.

**Context**: `tests/canary/test_inventory_health_checks.py::test_restic_expected_prose_describes_the_prune_rule`
asserts by **substring** that the `expected` prose mentions `prune_exit_code` and
`snapshot_timestamp_utc`. Its docstring says it was written because this mission's predecessor "fixes
two unenforced couplings and would otherwise have created a third".

T010 will break it. There are three ways out and only one is acceptable:
- ❌ Keep the prose unchanged → two authoritative descriptions, the problem T010 exists to fix.
- ❌ Delete or weaken the test → removes a guard against this exact defect class.
- ✅ **Rewrite it to bind prose → ledger → behaviour**, which is strictly stronger than a substring
  check and preserves the original intent.

**Steps**:
1. Rewrite the test to assert the ledger is the binding: that `restic-backup` declares a
   `key_ledger`; that `prune_exit_code`'s declared good-set is exactly `[0]`; that
   `script_finished_at_utc` is declared `diagnostic_only`; and that `expected` names the ledger as
   authoritative.
2. Update the docstring to explain the new binding and why it replaced the substring form. The next
   reader needs to know this was a deliberate strengthening, not an erosion.

**Do not** assert equality between the ledger's good-sets and `probes.py`'s module constants. That was
considered and rejected: once the ledger is authoritative those constants no longer govern this
component, so such a test would make editing a dead constant silently mutate live adjudication. See
`research.md` R3.

## Branch Strategy

- **Planning branch / merge target**: `feat/934-pointer-key-ledger`, `single_branch`.
- Work in the lane workspace the implement command gives you.

## Test Strategy

Required. New tests in `tests/architecture/test_key_ledger_rules.py`; modified test in
`tests/canary/test_inventory_health_checks.py`. All offline and deterministic. Build fixture
inventories inline rather than mutating the real one.

## Definition of Done

- [ ] All eight structural rules enforced, each with a failing-first test.
- [ ] A ledger-free component still validates clean (the over-broad-rule guard).
- [ ] `restic-backup` declares all fourteen keys with the contract's predicates and reasons.
- [ ] `reconciliation_harness` is present and its existence is validated.
- [ ] `expected` and `note` point at the ledger and no longer restate or stale-enumerate it.
- [ ] The prose-binding test is *stronger* than before, not removed.
- [ ] `validate_architecture_data.py --strict` → 0 findings; `make test` ≥ 6324 passing.

## Risks and Review Guidance

1. **Over-broad validator gating** — confirm the rule is gated on `entry.get("health_check")`. Ask the
   implementer to show a test proving a nested predicate object does not trigger a finding.
2. **A key in both lists must be a hard error**, not resolved by precedence. Precedence silently picks
   a winner; the whole point is that placement is a stated decision.
3. **Reasons must be substantive.** `"reason": "n/a"` satisfies a non-empty check and defeats the
   purpose. Each of the four should say something a reader could disagree with.
4. **T011 is where corners get cut.** If the test was deleted, weakened, or the prose left unchanged,
   reject — those are the two failure modes named above.
5. Verify the fourteen declared keys match what WP01 actually emits. Do not take the count on trust;
   run the producer.
