# WP01 Review — Cycle 1 — REJECT

Reviewer: codex (advisory, read-only). Verdict recorded by the orchestrator, which independently
verified all three findings against the source before rejecting.

The implementation is close and the structure is right: `SOURCE_ROOTS` is defined once and used for
both the backup invocation and the presence check, the guards emit the JSON literal `null`, the EXIT
trap is unmoved, scope is exactly the two owned files, and the 14-key set was genuinely verified by
executing the script. Three defects must be fixed.

Two of them are instances of the very defect class this mission exists to close, which is why they
block rather than being noted.

---

## 1. The carry-forward builds JSON with shell quoting, so a corrupt prior document can emit invalid JSON

`scripts/office2/restic-backup.sh:121`

```bash
LAST_INTEGRITY_CHECK_UTC="\"$PRIOR_INTEGRITY_CHECK_UTC\""
```

`jq -r '.last_integrity_check_utc // empty'` is accepted whenever it is non-empty, with no check that
it is a string or a plausible timestamp, and the value is then wrapped in quotes by hand.

**Failure scenario.** A prior document whose `last_integrity_check_utc` contains a double quote — say
`x"y` — produces `"last_integrity_check_utc": "x"y"`. The whole state document is now unparseable.
`read_state` raises, the probe maps it to `unknown`, and **a first-seen `unknown` does not alert**
(`tests/canary/test_run.py::test_first_seen_unknown_is_ledgered_not_paged`). The result is silence,
not a loud failure.

This matters more than a generic robustness nit because the guard's stated purpose — in its own
comment — is "a missing **or corrupt** prior document must leave the null default and must not abort
the run". A corrupt document is exactly the input it claims to handle, and it is the input that breaks
it.

**Required fix.** Validate that the retained value is a JSON *string* and matches the timestamp shape
the script itself emits, and let `jq` do the JSON encoding rather than constructing it with shell
quotes. Anything that fails validation falls back to the `null` default.

**Required tests.** A prior document containing a quote-bearing value; a prior document whose
`last_integrity_check_utc` is a non-string (number, object, array). Both must yield a document that
`json.loads` parses, with the field defaulted.

---

## 2. `source_roots_present` reports `false` when the comparison could not be performed

`scripts/office2/restic-backup.sh:154`

```bash
if ! echo "$snapshot_json" | jq -e --arg r "$root" '(.[0].paths // []) | index($r) != null' >/dev/null 2>&1; then
    missing_root=1
```

`jq -e` exits non-zero in **two different situations**: the filter evaluated to `false`/`null`, and jq
itself failed (malformed JSON, unexpected shape, jq missing). The code treats both as "a root is
missing".

**Failure scenario.** The snapshot JSON is malformed or has an unexpected shape. Nothing is known
about whether the roots were captured — but the document asserts `source_roots_present: false`, a
positive claim that a configured root was proven absent.

**Why this blocks.** This is the mission's central distinction, violated inside the mission. Spec
C-004 requires adjudication to distinguish "ran and failed" from "could not be measured", and WP01's
own prompt states the rule explicitly: *"Emit `true` when every configured root appears, `false` when
any is missing, `null` when the comparison could not be performed."* The sibling key `snapshot_count`
gets this right via `unmeasured_is_unknown`; this one does not.

**Required fix.** Separate evaluation failure from a true negative. Perform the comparison once,
distinguish jq's error exit from a legitimate `false`, and emit `null` on any failure to evaluate.

**Required tests.** Malformed snapshot JSON → `null`; a snapshot whose `paths` is the wrong shape →
`null`; a genuinely missing root → `false`; all roots present → `true`.

---

## 3. The fourteen-key shape is asserted only on the happy path

`tests/office2/restic_backup/test_pointer_emission.py:215` is the only assertion of the exact key set.
The early-exit tests (`test_mount_failure_records_prune_never_attempted:153`,
`test_repo_inaccessible_records_prune_never_attempted:161`,
`test_backup_failure_records_prune_never_attempted:167`) assert selected fields only.

The Definition of Done requires "exactly fourteen keys **on every path**, asserted by executing it".
The early exits are where this component's historical defects have lived — #906 survived review in
exactly those branches, which is why the executing harness exists at all.

**Required fix.** Parameterise the exact-key-set assertion and a `json.loads` parseability assertion
across every execution path, including the early exits.

---

## Note on review coverage

The reviewer did **not** execute the test suite: the review instructions prohibited creating any
files, and pytest necessarily writes temporary stub, log, and state files. That was an
over-constraint in the dispatch prompt, not a reviewer failure, and it has been corrected for
subsequent reviews. The three findings above are from source inspection and were independently
verified by the orchestrator. Re-review will include a test run.
