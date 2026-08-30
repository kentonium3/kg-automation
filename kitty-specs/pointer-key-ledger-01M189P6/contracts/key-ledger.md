# Contract: `health_check.key_ledger`

**v2** — revised after the post-plan review. v1 contained a self-contradiction on absent keys, left
absence undefined for two of three predicates, specified type matching in one direction only, made the
`freshness` predicate decorative, and bound its central obligation with prose that nothing enforced.
Each is fixed below.

## Placement

A `key_ledger` object is an optional member of a component's `health_check` in
`docs/design/architecture/data/service-inventory.json`.

**Optional is deliberate.** 16 of the 17 pointer-emitting components have no ledger and must remain
valid; a required field would block every unrelated inventory change. Absence means "not yet adopted"
(tracked as #937), never "no keys".

## Shape

```json
"health_check": {
  "method": "state-file",
  "state_path": "/data/services/backup/state/last-backup.json",
  "max_age_seconds": 100800,
  "key_ledger": {
    "reconciliation_harness": "tests/office2/restic_backup/test_ledger_reconciliation.py",
    "adjudicated": {
      "schema_version":           { "good_values": [2] },
      "restic_exit_code":         { "good_values": [0, 3] },
      "prune_exit_code":          { "good_values": [0] },
      "integrity_check_passed":   { "good_values": [true, null] },
      "snapshot_timestamp_utc":   { "freshness": true, "anchor": true },
      "last_integrity_check_utc": { "freshness": true, "max_age_seconds": 777600 },
      "snapshot_count":           { "minimum": 2, "unmeasured_is_unknown": true },
      "files_processed":          { "minimum": 1 },
      "source_roots_present":     { "good_values": [true] },
      "repo_fs_free_bytes":       { "minimum": 53687091200 }
    },
    "diagnostic_only": {
      "snapshot_id":            { "reason": "Identifier for investigation; carries no health meaning." },
      "repo_size_bytes":        { "reason": "Trend data. repo_fs_free_bytes is the capacity signal — this measures the repository, not the filesystem that fills." },
      "script_finished_at_utc": { "reason": "Separate cron-finished witness. Deliberately NOT a freshness fallback: a run producing no snapshot once read fresh through it (#902/FR-009)." },
      "integrity_check_run":    { "reason": "Whether the check executed today. Recency is adjudicated via last_integrity_check_utc, which is what detects the check silently stopping." }
    }
  }
}
```

`diagnostic_only` is an **object with reasons**, not a bare array (v1's form). A one-word escape hatch
and a considered decision were indistinguishable in the data — which is how `integrity_check_run`
became the silent answer to a question nobody had written down.

## Adjudication predicates

Exactly one predicate field per adjudicated key, plus any modifiers from that predicate's allow-list
(see *Predicate modifiers* below).

| Predicate | Meaning | Healthy when |
|---|---|---|
| `good_values` | Explicit membership | value is in the list, matched by **type identity and value** |
| `minimum` | Numeric floor | value is a real number and `>= minimum` |
| `freshness` | Recency of a timestamp | resolves, parses, is within its bound, and is not future-dated |

### Membership matching (both directions)

Membership is **never** evaluated through a type guard, and **never** by bare equality. The host
language treats booleans and numbers as equal in both directions:

```
False in [0, 3]       -> True     # would read HEALTHY
1     in [True, None] -> True
```

So matching requires that a boolean matches only a boolean and a number only a number. A value outside
the good-set is unhealthy **regardless of its type** — a type-guarded implementation reads healthy for
an unexpected type, which is the fail-open shape that produced this mission. The producer builds this
document by shell interpolation, so type drift is realistic, not hypothetical.

### Absence (unconditional — v1 was self-contradictory here)

**An adjudicated key absent from the document is unhealthy, whatever its predicate.** Evidence:
`adjudicated key <k> not emitted`.

`null` in `good_values` licenses only a **present** JSON null. Absence and present-null are different
conditions — `null` is a value the producer deliberately wrote; absence is the producer no longer
speaking — and collapsing them is the category error this whole mission diagnoses.

v1 said both "evaluates every key **present in the pointer**" and, four paragraphs later, that absent
keys are adjudicated; and it defined absence only for `good_values`, leaving `minimum` and `freshness`
undecided. The rule above replaces all of it: **iterate the declaration, not the document.**

### Unmeasured values

`minimum` may carry `"unmeasured_is_unknown": true`. A `null` for such a key then yields **unknown**,
not unhealthy — the producer is saying "I could not measure this", which is neither "measured and
good" nor "measured and bad". Without this, a transient failure of the producer's count query raises a
false alarm on a healthy backup (research R16).

### Predicate modifiers (the allow-list)

A predicate object carries **exactly one predicate field** — that is what rule 4 constrains — plus
zero or more **modifier** fields drawn from that predicate's allow-list. Modifiers are not predicates
and do not violate rule 4. Anything outside the allow-list is a structural error, so the vocabulary
cannot be extended by a downstream implementer inventing a field.

| Predicate | Permitted modifiers | Meaning |
|---|---|---|
| `good_values` | *(none)* | — |
| `minimum` | `unmeasured_is_unknown` | a present `null` yields **unknown** rather than unhealthy |
| | `suppress_until_utc` | an ISO-8601 instant; the predicate is **not evaluated** before it |
| `freshness` | `anchor` | this key is the component's staleness anchor (see below) |
| | `max_age_seconds` | a bound for this key, overriding the `health_check`'s |

**`suppress_until_utc` is how FR-019's first-run exemption is expressed** — declaratively, with an
explicit expiry, set by whoever stands up a new backup.

It was tempting to infer "this repository is new" from the other emitted keys instead. That was
rejected: every available signal a new repository produces, a **wiped** repository can also produce,
and conflating those two is precisely the failure `snapshot_count` exists to catch. An operator
setting a dated exemption cannot be mimicked by a failure, and it expires on its own. office2 does not
need one (14 snapshots); #913 sets one when standing up office4.

### Freshness: the anchor, and other bounded keys

**Two different things are being expressed and v1 conflated them**, which made the contract
self-contradicting: its Shape declared `freshness` on two keys while its own structural rule 7
forbade more than one.

- **The anchor** — the key that answers "is this component stale?". Exactly one, marked
  `"anchor": true`, and it feeds the component's staleness verdict.
- **Other recency-bounded keys** — keys with their own `max_age_seconds` that are adjudicated for
  their own recency but are *not* the component's staleness anchor.
  `last_integrity_check_utc` is one: a stale verification makes the component unhealthy, but the
  component's *freshness* is still measured from the backup timestamp.

So `snapshot_timestamp_utc` carries `anchor: true`; `last_integrity_check_utc` carries a
`max_age_seconds` and no anchor. Both are legal, and rule 7 now constrains only the anchor.

### The anchor binds to its key (v1 made this decorative)

When a ledger declares `freshness` with `anchor: true` on key K, **K is the anchor**. The probe must resolve K
specifically and must not fall through the module's ordered candidate list, which is the fallback for
ledger-free components only.

v1 declared `snapshot_timestamp_utc` with `freshness` purely so reconciliation would see a complete key
set, while the actual anchor was still chosen by a module constant that cannot see ledgers. For restic
the two agree by accident of list order. They will not agree for a producer emitting a
higher-priority candidate key — the declaration would be a false statement that reconciliation,
validation, and runtime all pass.

**At most one anchor per ledger** (rule 7). A non-anchor `freshness` key is adjudicated against its
own `max_age_seconds` but never becomes the staleness anchor.

`freshness` uses the `health_check`'s `max_age_seconds` unless the predicate carries its own — which
`last_integrity_check_utc` does (777600 s = 9 days: a weekly cadence tolerating one late or skipped run
but not a second silent miss).

### Future-dating

A timestamp more than **5 minutes** in the future (strict `>`) is not fresh. Ported rather than
invented: `scripts/deploy/lib/snapshot.py` already guards this exact field on this exact document with
`_FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)`, and two consumers of one file must not disagree. It is
independently sound — the tightest freshness budget in the inventory is 600 s, so a larger tolerance
would defeat the guard there entirely.

Without the bound, `age = now - ts` is negative, never exceeds any budget, and a skewed clock pins the
component fresh forever.

## Structural rules (enforced by `validate_architecture_data.py`)

1. `key_ledger`, when present, contains only `adjudicated`, `diagnostic_only`, and
   `reconciliation_harness`.
2. `adjudicated` maps key name → predicate object. `diagnostic_only` maps key name → `{"reason": …}`
   with a non-empty reason.
3. **No key appears in both.** A hard error, never a precedence rule — a precedence rule silently picks
   a winner, and the point of the contract is that placement is a stated decision.
4. Exactly one recognised **predicate** field per adjudicated key — zero is undecidable, two is
   ambiguous. **Modifier** fields are permitted alongside it, but only those on that predicate's
   allow-list (see *Predicate modifiers*); an unrecognised field is a structural error.
5. `good_values` is a non-empty array of JSON scalars or `null`; `minimum` is a number.
6. A ledger may only appear on a `health_check` whose method reads a JSON document
   (`state-file`, `tick-signal-file`, `signal-file`).
7. **At most one key declares `freshness` with `anchor: true`.** Any number of keys may carry a
   `freshness` predicate with their own `max_age_seconds`; only the *anchor* must be unique, because
   only the anchor answers "is this component stale?". v1 forbade more than one `freshness` key
   outright, which contradicted its own ledger — see *Freshness: the anchor, and other bounded keys*.
8. **`reconciliation_harness` is required when `key_ledger` is present**, and the path must exist on
   disk. This is what makes Obligation 2 a gate rather than a wish.

These constrain only the new structure; every existing ledger-free component stays valid. **Implementation
note**: the validator walks *every nested dict*, so per-key predicate objects will each be yielded as an
entry — gate the rule on `entry.get("health_check")`, never on `"key_ledger" in entry`.

## Obligation 1 — Runtime

For a component declaring a ledger, the freshness probe:

1. **Iterates the declaration**, evaluating every adjudicated key against its predicate. Absent keys
   are unhealthy (above). First failure wins, with evidence naming key and value.
2. Ignores `diagnostic_only` keys **for canary health**. This does not mean "unused" — see *Scope* below.
3. Applies legacy field-convention checks only where no ledger is declared. **Not per key** — see the
   warning below.
4. Never raises. A raised exception is caught upstream and mapped to `unknown`, and a first-seen
   `unknown` is recorded **without alerting** — so a throwing evaluator converts a detected corruption
   into silence. Totality is a correctness requirement, not hygiene (NFR-006).

> ⚠ **The per-key suppression trap.** The legacy chain is organised per *rule-block*, not per key: the
> `snapshot_timestamp_utc` parseability guard is nested inside `if "restic_exit_code" in pointer:`.
> Suppressing that branch because the ledger declares `restic_exit_code` **deletes the timestamp guard
> too**, reopening #902/FR-009. And every existing regression test for that guard builds its config
> without a ledger, so all of them stay green while the ledgered component regresses. Lift the
> timestamp rule into its own predicate rather than suppressing branches, and re-assert the #902
> scenarios with the real ledger attached (SC-007).

## Obligation 2 — Test

For every component declaring a ledger:

1. Determine the emitted key set by **executing the producer** under controlled effects — never by
   parsing source, never against a key list written in the test.
2. Fail on a key the producer emits that the ledger does not declare, naming it.
3. Fail on a key the ledger declares that the producer does not emit, naming it.
4. **Fail if the set of components being reconciled is empty**, or does not equal the set of
   ledger-declaring components in the inventory. An empty selection is a green suite with zero
   assertions executed.
5. **Fail if a ledger is deleted.** One hardcoded pin asserts `restic-backup` declares a ledger. That is
   a hand-maintained list — of *producers* (2, changing yearly), not of *keys* (14, changing per
   commit). The asymmetry is deliberate and is why it is acceptable here and refused there.
6. Prove the harness actually produced a document: process outcome, document exists, parses as an
   object, non-empty key set. A harness that treats a missing document as `{}` reconciles vacuously
   against anything.

**Reconciliation is a key-set property.** The producer writes a static heredoc, so its key set is
invariant across execution paths by construction — running reconciliation on every early-exit branch
cannot fail and proves nothing. The early-exit paths earn their place under **Obligation 1**: run the
*evaluator* over each early-exit document and assert the verdict, which is where the `127` sentinel and
the `null` count actually live.

## Scope: this contract governs one reader

`scripts/deploy/lib/snapshot.py`, the Tier-2 deploy pre-flight gate, reads the same document with its
own independent rules — deliberately, since a prune failure makes the component unhealthy but must not
block a deploy.

So `diagnostic_only` means **"does not decide canary health"**, never "unused by anything". A key
marked diagnostic here may still be load-bearing in the deploy gate. Unifying the two readers is out of
scope; the duplication is now documented rather than accidental.

## Reuse by a second producer

A second producer adopts the contract by declaring its own ledger **and registering its own
reconciliation harness**. It supplies no adjudication and no reconciliation logic — those come from the
shared evaluator and the shared reconciliation helper.

The mechanism must contain no component name, no host name, and no producer-specific key name. If
adopting a second backup requires editing the evaluator or the reconciliation helper, the contract has
failed its purpose. That property is itself tested, by driving a fictitious producer *script* with a
different key set through both shared helpers and asserting neither needed a change.
