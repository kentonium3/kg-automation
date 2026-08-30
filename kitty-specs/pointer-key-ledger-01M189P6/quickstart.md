# Quickstart: Backup Pointer Key Ledger

**v2** — revised after the post-plan review. v1's "prove the contract bites" section proved two of the
three cases and missed the one that actually recurs; and it described the reconciliation as executing
"the real producer", which it does not.

## Run the tests

```bash
make test
```

That is `pytest -q --ignore=docs/archive`. Baseline before this mission: **6324 tests**.

Narrower loops:

```bash
.venv/bin/python -m pytest tests/office2/restic_backup/ -q
```

```bash
.venv/bin/python -m pytest tests/canary/ -q
```

The reconciliation executes the **repo copy** of the producer with `restic`, `mountpoint`, `du` and
`df` stubbed on `PATH`. No network, no office2 access, no restic install.

## Prove the contract bites

Run all three by hand once. A contract nobody has watched fail is a contract nobody has verified.

**1. An undeclared key must fail the suite.**

```bash
sed -i 's/  "schema_version": 2,/  "schema_version": 2,\n  "unclaimed_field": 42,/' \
  scripts/office2/restic-backup.sh
```

```bash
.venv/bin/python -m pytest tests/office2/restic_backup/ -q
```

Expect a failure naming `unclaimed_field`, then `git checkout -- scripts/office2/restic-backup.sh`.

**2. A stale declaration must fail the suite.** Add a key to `diagnostic_only` in
`service-inventory.json` that the producer does not emit; re-run; expect a failure naming it; revert.

**3. Deleting the ledger must fail the suite.** Remove the whole `key_ledger` block from
`restic-backup`'s `health_check`; re-run; expect a failure. Revert.

Check 3 is the one v1 missed, and it is the failure that actually recurs: absence is legal for the 16
unledgered components, so without an explicit pin, `git rm`-ing the contract passes every gate and
silently returns the component to its pre-mission behaviour.

If any of the three passes silently, the contract is decorative and the mission has not been delivered.

## Validate the declaration

```bash
.venv/bin/python tooling/scripts/validate_architecture_data.py --strict
```

A **blocking** Docs-CI gate, also run by the pre-commit hook. It checks ledger *structure* — disjoint
lists, one predicate per key, non-empty reasons, at most one `freshness`, and that
`reconciliation_harness` exists on disk. It cannot check whether the ledger matches the producer; that
is the test's job. Neither substitutes for the other.

> **office4 note:** the pre-commit hook resolves `PY="${PYTHON:-python3}"` and office4's system
> `python3` has no `pyyaml`, so commits fail there until kentonium3/kg-automation#935 lands. Prefix
> with `PYTHON=/home/kgale/repos/kg-automation/.venv/bin/python` meanwhile.

## Install the producer on office2 (operator step — Kent only)

The repo change does **not** reach the live backup by itself. `/data/services/backup/scripts/` is
`root:root drwxr-xr-x`, felix-deployer runs as `claude`, and `claude` has no passwordless sudo. So
after merge, run this yourself:

```bash
ssh office2-kgale
```

```bash
sudo install -m 755 -o root -g root ~/kg-automation/scripts/office2/restic-backup.sh /data/services/backup/scripts/backup.sh
```

Tier 2 — confirm a Restic snapshot ≤24 h old before installing. Then verify convergence:

```bash
ssh office2-claude 'cat /data/services/backup/drift/script-drift-last-tick.json'
```

**The mission is not complete until this is done and the drift comparator reports the copies
converged.** Until then the ledger describes the repo copy, not the producer.

## Read the live signal

```bash
ssh office2-claude 'cat /data/services/backup/state/last-backup.json'
```

Six days in seven this shows `integrity_check_run: false` / `integrity_check_passed: null` — **healthy**,
the check simply did not run. `last_integrity_check_utc` is the key that distinguishes that from the
check having stopped altogether.

```bash
ssh office2-claude 'cat /data/services/felix-canary/state/last-tick.json'
```

The canary evaluates every 15 minutes. If this stops advancing, the evaluator made the runner throw —
which is caught and mapped to `unknown` rather than crashing. **Watch for a silent degradation to
`unknown`, not for a stack trace**, because a first-seen `unknown` is recorded without alerting.

## Adopt the contract for a new producer

The #913 path. It requires **no change to the evaluator or the reconciliation helper**.

1. Add `key_ledger` to the component's `health_check`, declaring every key its producer emits as either
   `adjudicated` (one predicate) or `diagnostic_only` (with a written reason).
2. Write an execution harness that runs the producer under stubbed effects and returns the emitted
   document. `tests/office2/restic_backup/test_pointer_emission.py` is the worked example.
3. Set `reconciliation_harness` to that harness's path. The shared helper in
   `tests/canary/ledger_reconcile.py` does the rest — you do not write reconciliation logic.

If step 3 requires editing the shared helper or the evaluator, something is wrong: neither may contain
a component name, host name, or producer-specific key. That property is itself tested by driving a
fictitious producer through both.

Note the honest cost: a second producer supplies a ledger **and a harness**. Only the adjudication and
reconciliation logic is free.

## Deliberate non-obvious choices

Six things that look simplifiable and must not be:

- **`restic_exit_code` accepts `{0, 3}`; `prune_exit_code` accepts `{0}` only.** A *backup* exiting 3
  produced a snapshot; a *forget* exiting 3 did not. Merging them is a named prior regression (#902).
- **Good-sets match by type identity in both directions.** `false` must not satisfy `[0, 3]` and `1`
  must not satisfy `[true, null]` — the host language says both do.
- **An absent adjudicated key is unhealthy, always** — never healthy because `null` happens to be in
  its good-set. Absence is the producer no longer speaking; `null` is a value it deliberately wrote.
- **`script_finished_at_utc` must never become a freshness fallback.** It was one, and a run producing
  no snapshot read fresh through it (#902/FR-009).
- **The declared `freshness` key is the anchor**, not whichever candidate key sorts first. Otherwise a
  producer emitting a higher-priority timestamp silently reopens the above.
- **`diagnostic_only` means "does not decide canary health", not "unused".** The Tier-2 deploy gate
  reads this same document with its own rules; deleting a key because the ledger calls it diagnostic
  would break it.
