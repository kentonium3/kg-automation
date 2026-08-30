# Data Model: Backup Pointer Key Ledger

**v2** — revised after the post-plan review. v1's key counts were wrong, its type invariant covered
one direction of a two-directional collision, and its absence rule contradicted itself. Corrected below.

## Entities

### KeyLedger

The per-producer declaration at `health_check.key_ledger`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `adjudicated` | map: key → Predicate | no | Absent means no key decides canary health |
| `diagnostic_only` | map: key → `{reason}` | no | An **object with reasons**, not a bare array |
| `reconciliation_harness` | repo-relative path | **yes, when `key_ledger` present** | Must exist on disk |

**L1** — `adjudicated` and `diagnostic_only` are disjoint. Structural error, not a precedence rule.
**L2** — `adjudicated ∪ diagnostic_only` equals the producer's emitted key set exactly. Enforced by
test, not by the validator: the validator cannot know what a producer emits, which is why Obligation 2
exists.
**L3** — a declared ledger has a registered harness. Without this, a ledger is a hand-maintained list
and the mechanism is decorative (research R15).
**L4** — at most one key declares `freshness` with `anchor: true`. Several keys may carry a
`freshness` predicate with their own bound; only the *anchor* — the key answering "is this component
stale?" — must be unique. Conflating these two made the v2 contract self-contradicting, caught by
`/spec-kitty.analyze`.

### Predicate

| Form | Field | Healthy when |
|---|---|---|
| Membership | `good_values` | value in list, matched by type identity **and** value |
| Floor | `minimum` (+ optional `unmeasured_is_unknown`) | value is a real number and `>= minimum` |
| Freshness | `freshness` (+ optional `anchor`, `max_age_seconds`) | **this key** resolves, parses, is within bound, and is not >5 min future-dated |

**P1** — exactly one predicate field per key.
**P2** — membership is evaluated with **no type pre-filter**. A value of an unexpected type is not in
the good-set and is therefore unhealthy. Stated as an invariant because the surrounding module's style
does the opposite, and matching it would reintroduce the defect.
**P3 (corrected)** — type matching is **symmetric**. In the host language `False == 0` and `True == 1`,
so the collision runs both ways:

| value | good-set | naive result | required result |
|---|---|---|---|
| `1` | `[true, null]` | matches | **no match** |
| `0` | `[false]` | matches | **no match** |
| `false` | `[0, 3]` | matches | **no match** |
| `true` | `[1]` | matches | **no match** |

v1 stated only the first two rows. The third is the dangerous one: `restic_exit_code: false` — a
plausible shell-interpolation accident — would have read healthy.

**P4** — an adjudicated key **absent** from the document is unhealthy, whatever its predicate. `null`
in `good_values` licenses only a *present* null.
**P5** — for `minimum` with `unmeasured_is_unknown`, a present `null` yields **unknown**: "could not
measure" is neither good nor bad, and reporting it as bad is a false alarm on a healthy backup.

### StatePointer

The producer's output. **Modified by this mission** (C-001 reversed): four keys added, one output
guard fixed, schema bumped to 2.

| Key | Disposition | Predicate | Why |
|---|---|---|---|
| `schema_version` | adjudicated | `good_values: [2]` | The one key whose purpose is to announce the contract changed; pinning it forces a deliberate ledger review on a bump |
| `restic_exit_code` | adjudicated | `good_values: [0, 3]` | 3 = warnings but a snapshot was produced |
| `prune_exit_code` | adjudicated | `good_values: [0]` | `forget` exiting 3 gives no snapshot guarantee. **Never merge with the set above** |
| `snapshot_timestamp_utc` | adjudicated | `freshness` **anchor** (28 h) | The staleness anchor; parseable, in-budget, not future-dated |
| `integrity_check_passed` | adjudicated | `good_values: [true, null]` | The reported defect. `null` = not run today = healthy |
| `snapshot_count` | adjudicated | `minimum: 2`, unmeasured→unknown | A wiped-and-reinitialised repo yields one snapshot and otherwise reads all-green |
| **`last_integrity_check_utc`** | adjudicated | `freshness` (9 d, **not** anchor) | **NEW.** Detects the check *silently stopping* — invisible in v1. Bounded for its own recency; the component's staleness is still measured from the backup timestamp |
| **`files_processed`** | adjudicated | `minimum: 1` | **NEW.** An empty capture otherwise reads healthy |
| **`source_roots_present`** | adjudicated | `good_values: [true]` | **NEW.** A partial capture otherwise reads healthy |
| **`repo_fs_free_bytes`** | adjudicated | `minimum: 50 GiB` | **NEW.** The approach to a full volume otherwise has no signal |
| `snapshot_id` | diagnostic_only | — | Identifier for investigation |
| `repo_size_bytes` | diagnostic_only | — | Trend data; measures the repo, not the filesystem that fills |
| `script_finished_at_utc` | diagnostic_only | — | Separate witness; deliberately **not** a freshness fallback (#902) |
| `integrity_check_run` | diagnostic_only | — | Recency is adjudicated via `last_integrity_check_utc` |

Ten adjudicated, four diagnostic, fourteen total.

**Baseline correction.** v1 said "six of ten inert, four effectively adjudicated". Wrong: it
double-counted `snapshot_timestamp_utc` (once "by freshness", once "by the timestamp-fallback guard" —
the same key). `script_finished_at_utc` cannot act as this component's fallback, because
`_explicit_error` returns before timestamp resolution whenever the snapshot timestamp is unusable. The
true prior state is **three adjudicated, seven inert**. #934's issue body carries the same undercount.

### HealthVerdict

Existing entity, unchanged in shape (`ok`, `stale`, `evaluable`, `evidence`, `signal`). Ledger failures
must populate `evidence` with the key and value (NFR-004).

## State transitions

```mermaid
stateDiagram-v2
    [*] --> Read
    Read --> Unknown: document unreadable / not an object
    Read --> Iterate: document is an object
    Iterate --> Unhealthy: adjudicated key fails its predicate
    Iterate --> Unhealthy: adjudicated key ABSENT (any predicate)
    Iterate --> Unknown: minimum key present-null with unmeasured_is_unknown
    Iterate --> Stale: declared freshness key out of bound or future-dated
    Iterate --> Healthy: all adjudicated keys satisfied
    Unhealthy --> [*]: alert, evidence names key + value
    Stale --> [*]: alert
    Healthy --> [*]: no alert
    Unknown --> [*]: recorded; FIRST-SEEN unknown does NOT alert
```

**The `Unknown` terminal is the mission's own hazard.** A first-seen `unknown` is ledgered without
paging. So an evaluator that raises on a document carrying `integrity_check_passed: false` produces
*silence* — converting the bug being fixed into a differently-shaped one. Hence NFR-006 (totality) and
the hostile-value tests.

## What changes for office2 today

Evaluated against the live document (2026-08-30 02:51 UTC): `restic_exit_code: 0`, `prune_exit_code: 0`,
`snapshot_count: 14`, `integrity_check_passed: null`, fresh timestamp — all satisfied, component
continues to read healthy. The four new keys do not exist yet and appear only after the producer is
installed; until then the reconciliation binds the repo copy (R-002).

Introducing the contract must not change the reported health of a healthy system, and that is itself a
test.

## Consumers

Two, not one — v1's "the only interface between the backup and everything that judges it" was false.

| Consumer | Reads | Governed by this ledger? |
|---|---|---|
| `felix-canary` via `probes.py` | the document, for component health | **Yes** |
| `scripts/deploy/lib/snapshot.py` | the same document, for the Tier-2 deploy pre-flight gate | **No** — its own rules, deliberately divergent (a prune failure must not block a deploy) |

Therefore `diagnostic_only` means "does not decide **canary health**", never "unused". A key marked
diagnostic here may still be load-bearing in the deploy gate, and deleting one on that basis would
break it.

## Externally visible events

None added. Failures flow through the existing canary → alert-bus path with an unchanged payload shape.
The only observable difference is that conditions which previously produced silence now produce an
alert whose evidence names the responsible key.
