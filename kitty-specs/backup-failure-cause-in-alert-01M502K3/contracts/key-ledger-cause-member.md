# Contract amendment: `key_ledger.cause` (rule 9)

**Amends**: `kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`, rule 1, and adds rule 9.
**Mission**: `backup-failure-cause-in-alert-01M502K3` (kentonium3/kg-automation#1067), 2026-10-15.

## Change to rule 1

`key_ledger` may contain only `adjudicated`, `diagnostic_only`, `reconciliation_harness`, and, optionally, `cause`.

## Rule 9 — `cause`

An optional declaration naming the pointer key that carries a **failure cause**, plus the plain-words text for each code.

```json
"cause": { "key": "<pointer key>", "codes": { "<code>": "<text>" } }
```

1. The member must be an object with exactly the members `key` and `codes`.
2. `key` must be a non-empty string that is a member of `diagnostic_only`. A cause key may never be adjudicated, so it can never decide health.
3. `codes` must be a non-empty object whose names match `^[a-z][a-z0-9_]{0,63}$`. Each value must be a non-empty string of at most 120 characters with no control characters (U+0000–U+001F, U+007F).

## Semantics (consumer obligations)

- **Decoration only.** A consumer may append the declared text for the pointer's code to the evidence of a verdict that is **already** non-ok and evaluable. It must not change the verdict, the staleness, the evaluability, or any dedup signal.
- **Declared text only.** For a string value that is not in `codes`, a consumer emits a fixed marker. It never emits the raw value.
- **Total.** If the member is absent or malformed at runtime, the consumer ignores it and does not raise. The validator is a merge gate, not the runtime's only defence.
