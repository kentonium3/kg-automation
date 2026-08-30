# Contract: `health_check.key_ledger`

The declaration format, its structural rules, and the two enforcement obligations that make it more
than documentation. This is the contract both hosts share; office4 supplies a different ledger, never
a different mechanism.

## Placement

A `key_ledger` object is an optional member of a component's `health_check` object in
`docs/design/architecture/data/service-inventory.json`.

**Optional is deliberate.** 15 of the 17 pointer-emitting components have no ledger and must remain
valid. Absence means "not yet adopted", never "no keys" — a validator that required the field would
block every unrelated change to the inventory.

## Shape

```json
"health_check": {
  "method": "state-file",
  "state_path": "/data/services/backup/state/last-backup.json",
  "max_age_seconds": 100800,
  "key_ledger": {
    "adjudicated": {
      "restic_exit_code":       { "good_values": [0, 3] },
      "prune_exit_code":        { "good_values": [0] },
      "integrity_check_passed": { "good_values": [true, null] },
      "snapshot_count":         { "minimum": 2 }
    },
    "diagnostic_only": [
      "schema_version",
      "snapshot_id",
      "repo_size_bytes",
      "script_finished_at_utc",
      "integrity_check_run"
    ]
  }
}
```

`snapshot_timestamp_utc` is adjudicated by the freshness path rather than by a good-set, and is
declared with an explicit marker rather than being omitted — see *Timestamp keys* below. Omission must
never be how a key escapes the ledger.

## Adjudication predicates

Exactly one predicate per adjudicated key. A key declaring none, or more than one, is a structural
error.

| Predicate | Meaning | Healthy when |
|---|---|---|
| `good_values` | Explicit membership against a literal list. `null` in the list means the JSON null is healthy. | The value is `in` the list, compared by value and type |
| `minimum` | Numeric floor | The value is a number and `>= minimum` |
| `freshness` | Delegated to the freshness probe and its `max_age_seconds` | The freshness probe judges it fresh and not future-dated |

**`good_values` is matched by explicit containment, never through a type guard.** A value that is not
in the list is unhealthy *regardless of its type*. This is the single most important rule in the
contract: a type-guarded implementation reads healthy for an unexpected type, which is the fail-open
shape that produced this mission (see research R2). `true` and `1` are distinct; boolean identity is
checked before numeric equality so `1` does not satisfy a `[true, null]` good-set.

## Structural rules (enforced by `validate_architecture_data.py`)

1. `key_ledger`, when present, is an object with at most the members `adjudicated` and
   `diagnostic_only`.
2. `adjudicated` is an object mapping key name → predicate object. `diagnostic_only` is an array of
   unique key-name strings.
3. **No key appears in both lists.** This is a hard error, not a precedence rule — a precedence rule
   would silently pick a winner, and the point of the contract is that placement is a stated decision.
4. Every adjudicated key declares exactly one recognised predicate.
5. `good_values` is a non-empty array of JSON scalars or `null`. `minimum` is a number.
6. A ledger may only be declared on a `health_check` whose `method` reads a JSON pointer document
   (`state-file`, `tick-signal-file`, `signal-file`). A ledger on an HTTP or systemd check is
   meaningless and is an error.

These rules constrain only the new structure. The validator is a **blocking** Docs-CI gate, so it must
treat every existing ledger-free component as valid.

## Obligation 1 — Runtime (the probe layer)

For a component declaring a ledger, the freshness probe:

1. Evaluates every key present in the pointer that the ledger marks `adjudicated`, against its
   predicate. The first failure makes the component unhealthy, with evidence naming the key and the
   offending value.
2. Ignores keys marked `diagnostic_only` for health purposes.
3. Applies the legacy `_explicit_error` conventions **only to keys the ledger does not name.** The
   ledger is authoritative for what it declares; running both over the same key would put its good-set
   in two places and let them drift.

An adjudicated key that is **absent** from the pointer is not silently healthy. Absence is reported as
unhealthy unless `null` is in the key's `good_values`, because "the producer stopped emitting a key we
adjudicate" is a real condition and reading it as healthy is the whole defect class.

## Obligation 2 — Test (the reconciliation)

For every producer whose component declares a ledger, a test must:

1. Determine the emitted key set by **executing the real producer** under stubbed effects — never by
   parsing its source, and never by comparing against a key list written in the test.
2. Fail when the producer emits a key that is in neither `adjudicated` nor `diagnostic_only`, naming
   the undeclared key.
3. Fail when the ledger declares a key the producer does not emit, naming the stale declaration.
4. Hold across the producer's early-exit paths, not only its success path.

Obligation 2 is what distinguishes this contract from a comment. Without it the ledger is a claim about
the producer that nothing checks; with it, the two cannot diverge without the suite going red.

## Reuse by a second producer

A second producer adopts the contract by declaring its own ledger and supplying its own execution
harness for Obligation 2. It supplies **no** evaluation logic. The mechanism must contain no
component name, no host name, and no key name specific to any one producer — if adopting a second
backup requires editing the evaluator, the contract has failed its purpose and the change is wrong.

## Timestamp keys

`snapshot_timestamp_utc` is judged by the existing freshness machinery (`TIMESTAMP_KEYS` +
`max_age_seconds`), extended by this mission with a future-dating bound: a timestamp beyond a small
tolerance in the future is not fresh. Without that bound, `age = now - ts` is negative, never exceeds
`max_age_seconds`, and a skewed clock pins the component fresh forever.

It is declared in the ledger with the `freshness` predicate so that the reconciliation in Obligation 2
sees a complete key set. A key must never be absent from the ledger merely because a different
subsystem adjudicates it — that would be an undeclared key by another name.
