---
work_package_id: WP04
title: 'Probe integration, freshness binding, and the #902 trap'
dependencies:
- WP03
requirement_refs:
- FR-008
- FR-018
- NFR-003
- NFR-006
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
- T020
- T021
- T022
- T023
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: "Generated from plan v2 IC-02/IC-04. Highest-risk WP: the post-plan review found v1's design would have deleted the #902 guard here."
agent_profile: python-pedro
authoritative_surface: scripts/canary/probes.py
create_intent:
- tests/canary/test_probes_ledger.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/canary/probes.py
- tests/canary/test_probes.py
- tests/canary/test_probes_prune.py
- tests/canary/test_probes_ledger.py
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Wire WP03's evaluator into the freshness probe, make the declared freshness key genuinely
authoritative, and add the future-skew bound — **without deleting the #902 snapshot-timestamp guard.**

## ⚠️ Read this before touching `probes.py`

**This is the most dangerous edit in the mission, and the plan's first draft got it wrong.** The
post-plan review caught it; you are working from the corrected design.

The legacy chain is organised **per rule-block, not per key**:

```python
if "restic_exit_code" in pointer:
    code = pointer["restic_exit_code"]
    if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES:
        return f"restic_exit_code={code}"
    # ↓ a SECOND, unrelated rule living inside the first rule's presence test
    snapshot_ts = pointer.get("snapshot_timestamp_utc")
    if _parse_iso(snapshot_ts) is None:
        return "restic pointer has no usable snapshot_timestamp_utc"
```

The obvious integration — "the ledger is authoritative for keys it declares, so skip
`_explicit_error` for those keys" — **deletes the snapshot-timestamp guard along with the exit-code
check**, because the guard lives inside the exit-code branch. That reopens #902/FR-009 verbatim: a run
producing no snapshot, with `restic_exit_code: 0` and a fresh `script_finished_at_utc`, reads
**healthy**.

**And CI would not catch it.** Every existing FR-009 regression test builds its `health_check` dict
*without* a `key_ledger`, so they all exercise the legacy path and stay green forever while the one
component that carries a ledger regresses. T019 defuses this; T023 proves it stayed defused. Neither
is optional.

## Subtasks

### T017 — Tests: the declared freshness key is the anchor

**Purpose**: `_resolve_timestamp` walks the module-level `TIMESTAMP_KEYS` tuple in fixed order and
takes the first present, parseable key. It takes no `health_check` argument and **cannot see a
ledger**. So a ledger declaring "key X is the anchor" is currently a claim the mechanism does not
implement.

For restic today the two agree *by accident* of list order. They will not agree for a producer
emitting a higher-priority candidate — which office4 plausibly will.

**Steps**:
1. Create `tests/canary/test_probes_ledger.py`.
2. Assert: a document containing both `completed_at_utc` (fresh) and `snapshot_timestamp_utc` (stale),
   with a ledger declaring `freshness` on `snapshot_timestamp_utc`, reads **stale**. Without the
   binding it reads fresh, because `completed_at_utc` sorts first.
3. Assert a ledger-free component still resolves via `TIMESTAMP_KEYS` exactly as today.
4. Assert the evidence names the key actually judged.

### T018 — Tests: the future-dating boundary

**Steps**:
1. Boundary cases against the 5-minute tolerance: `T − 1s` in the future → fresh; `T + 1s` in the
   future → **not** fresh. State in the test which side of `>` the boundary sits on.
2. Timestamp forms: `Z`-suffixed, explicit-offset, and **naive** (no offset). A naive value makes
   `now - ts` raise `TypeError`, which upstream becomes `unknown` — assert the guard does not widen
   that surface, and that a naive value is handled deliberately rather than by accident.
3. Assert a normal recent-past timestamp is unaffected.

### T019 — Lift the snapshot-timestamp rule out of the exit-code branch

**Purpose**: Defuse the trap above. Do this **first**, before any ledger wiring, and keep it a pure
refactor.

**Steps**:
1. Extract the `snapshot_timestamp_utc` parseability rule from inside the `if "restic_exit_code" in
   pointer:` block into its own top-level clause in `_explicit_error`, guarded on its own condition.
2. Preserve the existing behaviour **exactly** — same evidence string, same trigger conditions. This
   subtask must be a no-op for every existing test. Run the suite and confirm zero diffs in outcomes
   before proceeding.
3. Leave a comment explaining that the rule was nested and why it now stands alone: a rule that lives
   inside another rule's presence test cannot be reasoned about per-key, and the mission's precedence
   model is per-key.

**Validation**: `make test` passes with no changes to any test file in this subtask. If a test needed
changing, the refactor was not behaviour-preserving — back it out and try again.

### T020 — Wire the evaluator in; ledger authoritative for declared keys

**Steps**:
1. In `_probe_freshness`, read `health_check.get("key_ledger")`. This mirrors how
   `success_status_values` is already read and passed down — follow that established pattern.
2. When a ledger is present: run WP03's evaluator over the document. Its verdict is authoritative for
   **every key it declares**. Apply the legacy `_explicit_error` conventions only to keys the ledger
   does **not** declare.
3. When no ledger is present: behaviour is byte-for-byte unchanged. 16 components depend on this.
4. Map the evaluator's outcomes onto `ProbeResult`: unhealthy → `ok=False, evaluable=True` with
   evidence; unknown → `evaluable=False` (which the caller maps to `unknown`); healthy → continue to
   freshness resolution.
5. **Never let the evaluator's result raise or bypass.** WP03 guarantees totality, but the wiring must
   not reintroduce a raise — no `[...]` indexing into predicate dicts, no assumed shapes.

### T021 — Bind freshness resolution to the declared key

**Steps**:
1. When the ledger declares a `freshness` predicate on key K, resolve **K** specifically: parse it,
   apply its bound (the predicate's own `max_age_seconds` if present, else the `health_check`'s), and
   do **not** fall through `TIMESTAMP_KEYS`.
2. If K is absent or unparseable, that is unhealthy per WP03's absence rule — it must **not** fall
   through to another candidate key. This is the #902 hazard in its general form.
3. `TIMESTAMP_KEYS` remains the resolution path for ledger-free components, untouched.

### T022 — The future-skew guard

**Steps**:
1. Add a module constant of **5 minutes** with a comment explaining it is deliberately the same value
   as `scripts/deploy/lib/snapshot.py`'s `_FUTURE_SKEW_TOLERANCE`, because that module guards **this
   same field on this same document** for the Tier-2 deploy gate, and two consumers of one file must
   not disagree. Reference it by name so a future reader can find its sibling.
2. Apply it to freshness resolution: `instant > now + tolerance` → not fresh, with evidence naming the
   future-dated value. Strict `>`, matching the sibling.
3. Applies to **all** freshness-probed components, not just ledgered ones — a skewed clock pins any of
   them fresh forever. Note in the comment that the tightest `max_age_seconds` in the inventory is
   600 s, so the tolerance must stay well below it or the guard is defeated for that component.

### T023 — Re-assert the #902 scenarios *with the ledger attached* (SC-007)

**Purpose**: This is the subtask that makes the whole WP trustworthy. Without it, the regression tests
prove nothing about the configuration that actually ships.

**Steps**:
1. In `tests/canary/test_probes_prune.py` (and `test_probes.py` where relevant), the `judge` fixture
   builds a `health_check` dict inline with **no ledger**. Parameterise it so each FR-009 scenario runs
   **twice**: once ledger-free, and once with `restic-backup`'s **real ledger loaded from
   `service-inventory.json`**. The pattern for loading the real inventory already exists in
   `tests/canary/test_inventory_health_checks.py` — follow it.
2. The scenarios that must pass in **both** configurations:
   - `snapshot_timestamp_utc: null` + `restic_exit_code: 0` + fresh `script_finished_at_utc` → unhealthy
   - `snapshot_timestamp_utc: "not-a-date"` (truthy but unparseable) → unhealthy
   - a numeric `snapshot_timestamp_utc` → unhealthy
   - `prune_exit_code: 127` → unhealthy; `prune_exit_code: 3` → unhealthy
   - `restic_exit_code: 3` → healthy (warnings, but a snapshot was produced)
3. Add the case the review specifically named: with the ledger attached, `restic_exit_code: 0` +
   `snapshot_timestamp_utc: null` + fresh `script_finished_at_utc` reads **unhealthy**. This is the
   exact regression v1's design would have shipped.

## Branch Strategy

`feat/934-pointer-key-ledger`, `single_branch`. Work in the lane workspace provided.

## Test Strategy

Required, and the ordering matters: **T019 before T020.** Refactor the trap away while the suite is a
reliable oracle, confirm it is a no-op, and only then change behaviour. Doing them together makes it
impossible to tell a refactor bug from an integration bug.

All tests offline and deterministic with an injected `now` (NFR-002) — never `datetime.now()`.

## Definition of Done

- [ ] The snapshot-timestamp rule stands alone; T019 was proven behaviour-preserving.
- [ ] Evaluator wired; ledger authoritative for declared keys, legacy for the rest.
- [ ] Ledger-free components behave identically to before — asserted, not assumed.
- [ ] The declared `freshness` key is the anchor; no fall-through when it is absent or unparseable.
- [ ] 5-minute future-skew guard, boundary-tested, matching the deploy gate's value.
- [ ] **Every FR-009 scenario passes with the real ledger attached** (SC-007).
- [ ] `make test` ≥ 6324 passing.

## Risks and Review Guidance

**This WP gets the most reviewer attention in the mission.**

1. **Verify T019 landed first and was a no-op.** Check the commit sequence. If ledger wiring and the
   refactor arrived in one change, ask for evidence the extraction preserved behaviour — this is where
   a silent regression hides.
2. **Try to construct the #902 regression by hand.** Take the shipped code, attach the real ledger,
   feed `restic_exit_code: 0` + `snapshot_timestamp_utc: null` + fresh `script_finished_at_utc`. If it
   reads healthy, reject: that is the exact defect the review caught in the plan.
3. **Confirm the ledgered path is actually exercised.** A test that passes because the ledger was never
   loaded proves nothing. Check the parameterisation genuinely reaches the real inventory.
4. **Ledger-free regression.** Confirm a component with no ledger is byte-for-byte unchanged — 16
   components ride that path.
5. **Fall-through.** Confirm an absent or unparseable declared freshness key does **not** reach another
   `TIMESTAMP_KEYS` candidate. That fall-through is #902's general form.
6. **Skew value.** Confirm 5 minutes and strict `>`, and that the comment points at the sibling in
   `scripts/deploy/lib/snapshot.py`. A different value here means the two readers of one document
   disagree about when it is trustworthy.
