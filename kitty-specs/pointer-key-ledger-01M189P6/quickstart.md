# Quickstart: Backup Pointer Key Ledger

How to exercise, verify, and extend the contract. Written for whoever picks this up next — including
#913, whose job is to adopt the mechanism rather than rebuild it.

## Run the tests

```bash
make test
```

That is `pytest -q --ignore=docs/archive`. Baseline before this mission: **6324 tests**.

Narrower loops while working:

```bash
.venv/bin/python -m pytest tests/office2/restic_backup/ -q
```

```bash
.venv/bin/python -m pytest tests/canary/ -q
```

The reconciliation test executes the real `scripts/office2/restic-backup.sh` with `restic`,
`mountpoint` and `du` stubbed on `PATH`. It needs no network, no office2 access, and no restic
install.

## Prove the contract actually bites

Both checks should be run by hand once, because a contract nobody has seen fail is a contract nobody
has verified.

**1. An undeclared key must fail the suite.** Add a key to the producer's emitted document:

```bash
sed -i 's/  "schema_version": 1,/  "schema_version": 1,\n  "unclaimed_field": 42,/' \
  scripts/office2/restic-backup.sh
```

```bash
.venv/bin/python -m pytest tests/office2/restic_backup/ -q
```

Expect a failure naming `unclaimed_field`. Then revert:

```bash
git checkout -- scripts/office2/restic-backup.sh
```

**2. A stale declaration must fail the suite.** Add a key to the ledger's `diagnostic_only` list in
`docs/design/architecture/data/service-inventory.json` that the producer does not emit, re-run, and
expect a failure naming it. Revert.

If either check passes silently, the contract is decorative and the mission has not been delivered.

## Validate the declaration

```bash
.venv/bin/python tooling/scripts/validate_architecture_data.py --strict
```

This is a **blocking** Docs-CI gate and also runs in the repo's pre-commit hook. It checks the
ledger's structure — disjoint lists, exactly one predicate per adjudicated key, well-formed
`good_values` — but it cannot check whether the ledger matches the producer. That is the test's job.
The two are complementary and neither substitutes for the other.

> **office4 note:** the pre-commit hook resolves `PY="${PYTHON:-python3}"`, and office4's system
> `python3` has no `pyyaml`, so commits fail there until kentonium3/kg-automation#935 lands. Until
> then, prefix commands with `PYTHON=/home/kgale/repos/kg-automation/.venv/bin/python`.

## Read the live signal

```bash
ssh office2-claude 'cat /data/services/backup/state/last-backup.json'
```

Six days in seven this shows `integrity_check_run: false` and `integrity_check_passed: null`, which is
**healthy** — the check simply did not run. On Sunday it shows the real verdict, written at 04:00 UTC
and persisting until Monday 04:00 UTC overwrites it.

```bash
ssh office2-claude 'cat /data/services/felix-canary/state/last-tick.json'
```

The canary evaluates every 15 minutes. If this stops advancing, the evaluator made the runner throw —
which is caught and mapped to `unknown` rather than crashing, so watch for a silent degradation to
`unknown`, not for a stack trace.

## Adopt the contract for a new producer

This is the #913 path, and it should require **no change to the evaluator**.

1. Add `key_ledger` to the component's `health_check` in `service-inventory.json`, declaring every key
   its producer emits as either `adjudicated` (with one predicate) or `diagnostic_only`.
2. Give the producer an execution harness — a test that runs it under stubbed effects and captures the
   emitted document. `tests/office2/restic_backup/test_pointer_emission.py` is the worked example.
3. Point the shared reconciliation at that harness.

If step 3 requires editing the evaluator, something is wrong: the mechanism is meant to contain no
component name, host name, or producer-specific key name. That property is itself covered by a test
which declares a fictitious producer and asserts the same enforcement applies.

## Deliberate non-obvious choices

Three things look like they could be simplified and must not be:

- **`restic_exit_code` accepts `{0, 3}`; `prune_exit_code` accepts `{0}` only.** These are
  deliberately different. A *backup* exiting 3 completed with warnings but produced a snapshot; a
  *forget* exiting 3 carries no such guarantee. Merging them is a named prior regression (#902), and
  the code carries a "do not tidy up this duplication" comment saying so.
- **Good-sets are matched without a type guard.** A value of an unexpected type is unhealthy, not
  skipped. The surrounding module's existing `isinstance(...)` clauses do the opposite; that pattern
  is fail-open and must not be copied into new adjudication.
- **`script_finished_at_utc` is diagnostic-only and must never become a freshness fallback.** It was
  one, and a run that produced no snapshot at all read fresh through it (#902/FR-009).
