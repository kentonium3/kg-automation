# Research: Backup Pointer Key Ledger

Phase 0 output. Every finding below was verified against the live system or the actual source on
2026-08-30, not inferred. Where a prior document asserted something different, the correction is
stated explicitly.

## R1 — The contract already exists, as unenforceable prose

**Decision**: Treat `health_check.expected` as the *source text* for the ledger, and reduce it to a
pointer once the ledger is authoritative.

**Rationale**: `service-inventory.json`'s `restic-backup.health_check.expected` already states the
adjudication rules in English — `restic_exit_code` in `{0, 3}`, `prune_exit_code` must be `0`
("deliberately NARROWER"), the snapshot timestamp must be non-null and parseable, and `127` is the
never-attempted sentinel. Its `note` enumerates the schema-v1 fields, *including
`integrity_check_run` and `integrity_check_passed`*.

This is the finding that most shaped the plan. The system did not fail to describe its contract; it
described it in a medium with no enforcement. Two of the described rules were separately implemented
in `probes.py`; the rest were never wired to anything. So the work is not "invent a contract" but
"move an existing contract into a form that executes" — which also means the ledger's initial content
is a transcription exercise with a known-correct source, not a design guess.

**Alternatives considered**: Writing a fresh ledger from the office4 v0.2 table alone. Rejected —
office2's prose carries host-specific rationale (why `127` is the sentinel, why the prune set is
narrower, why the timestamp must not fall through to `script_finished_at_utc`) that the v0.2 table
compresses away. Losing it would discard the reasoning that justifies each good-set.

## R2 — The tri-state trap, and why the existing guards are the wrong pattern to copy

**Decision**: Good-set membership is tested by explicit containment including `None`; any value not
in the declared good-set is unhealthy. No `isinstance` pre-filter.

**Rationale**: `integrity_check_passed` is genuinely tri-state: `true` (checked, passed), `false`
(checked, failed), `null` (not checked — six days in seven). The two obvious implementations both
fail:

- **Truthiness** (`if not pointer["integrity_check_passed"]`) makes the component unhealthy on all six
  non-Sunday days. That is the alert-fatigue failure: a signal that cries wolf gets muted, and then the
  real Sunday failure is muted with it.
- **Type-guarded** (`if isinstance(v, bool) and v is False`) is what the existing code does for exit
  codes — `if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES`. It reads healthy for any
  value of an unexpected type. The producer writes this document with shell string interpolation, so a
  future change emitting `"false"` rather than `false` would be **skipped by the guard and read
  healthy** — the exact bug being fixed, reintroduced by copying the surrounding style.

The existing `isinstance` guards are load-bearing for a different reason (the `127` sentinel was made
an integer specifically *because* the guard skips non-integers — see the comment in
`restic-backup.sh`), so they are not being removed. But they are a fail-open pattern and must not be
the template for new adjudication.

**Alternatives considered**: A JSON-Schema-style type declaration per key. Rejected as more machinery
than the problem needs; an explicit good-set list already expresses type and value together, and
"anything not listed is unhealthy" is the fail-closed default we want.

## R3 — Precedence between the ledger and the existing `_explicit_error` chain

**Decision**: The ledger is authoritative for every key it declares. `_explicit_error` applies only to
keys the ledger does not name. The existing `_RESTIC_OK_EXIT_CODES` / `_PRUNE_OK_EXIT_CODES` constants
stay in the module for components with no ledger, and a test asserts the declared ledger sets equal
those constants.

**Rationale**: If both layers adjudicate `restic_exit_code`, its good-set exists in two places and can
drift — which is the coupling failure the mission exists to prevent, committed by the mission itself.
Making the ledger authoritative avoids that. But simply deleting the constants would be worse: they
still serve the 15 components with no ledger, and `_PRUNE_OK_EXIT_CODES` carries an explicit
"do not tidy up this duplication" comment naming its merger as the #902 regression. The equality test
between declaration and constant is the seam that keeps both honest while both exist.

**Alternatives considered**: (a) Ledger runs first, `_explicit_error` runs after on all keys —
rejected, double adjudication with two sources of truth. (b) Delete the constants and let the ledger
be the only home — rejected, it strands the 15 undeclared components and discards a comment written to
prevent a specific known regression.

## R4 — Deriving the emitted key set requires executing the producer

**Decision**: The reconciliation test runs `scripts/office2/restic-backup.sh` with `restic`,
`mountpoint` and `du` stubbed on `PATH`, parses the emitted JSON, and compares its key set against the
ledger in both directions.

**Rationale**: The producer is a bash script that writes its pointer from an `EXIT` trap using shell
interpolation. Its emitted key set is not statically derivable in any trustworthy way — and a test that
parsed the heredoc with a regex would be asserting against a second hand-maintained model. The
existing harness at `tests/office2/restic_backup/test_pointer_emission.py` already solves this: it was
built for #902 precisely because "reading the code tends to miss" the early-exit branches, and its
docstring says so. Reusing it costs nothing and inherits that reasoning.

**Both directions matter.** Undeclared-key detection catches the next `integrity_check_passed`.
Stale-declaration detection catches the opposite rot: a ledger that keeps describing a key the
producer stopped emitting, which would leave a good-set silently guarding nothing.

**Alternatives considered**: Asserting against a literal key list in the test file. Rejected — that is
the defect relocated from the code to the test, and it would pass forever while the producer changed.

## R5 — Early-exit paths emit a pointer too

**Decision**: Reconciliation must hold across the producer's early-exit branches, not only its happy
path.

**Rationale**: `write_state_pointer` is installed as `trap … EXIT`, so a run that aborts at the
mount check or the repo-access check still writes a complete pointer with sentinel values
(`BACKUP_RC=127`, `PRUNE_RC=127`, `INTEGRITY_PASSED=null`). Those runs emit the same ten keys, so the
ledger must reconcile there as well. The #902 mission added the executing harness specifically because
the sibling #906 defect hid in exactly these branches and survived code review.

**Alternatives considered**: Testing only the successful path. Rejected on the direct evidence that
this component's historical defects live in the early exits.

## R6 — Live pointer shape, used as the fixture source

**Decision**: Fixtures derive from the live document, read from office2 on 2026-08-30 02:51 UTC.

**Rationale**: The charter requires fixtures to mirror real inputs rather than being invented. The live
document (Saturday 2026-08-29 run) is:

```json
{"schema_version": 1,
 "snapshot_timestamp_utc": "2026-08-29T04:00:05Z",
 "snapshot_id": "6bf0ec80203a71c25f1d8ba159086229f6404e520a9106d5081d8795207cf4bf",
 "restic_exit_code": 0, "prune_exit_code": 0,
 "script_finished_at_utc": "2026-08-29T04:00:14Z",
 "repo_size_bytes": 3828853625, "snapshot_count": 14,
 "integrity_check_run": false, "integrity_check_passed": null}
```

Ten keys. Note `integrity_check_run: false` / `integrity_check_passed: null` — this is the
six-days-in-seven shape, and it must read **healthy**. `snapshot_count: 14` confirms the repository is
established, so the `>= 2` rule is satisfied today and its introduction changes nothing about current
reported health.

## R7 — Timing: the window is 25 hours, not 69 minutes

**Decision**: No rush-driven scope cuts. The full contract is built.

**Rationale**: The trigger for prioritising this work was "Sunday's `restic check` runs and nothing
reads it". Verified correction: `INTEGRITY_PASSED=null` and `INTEGRITY_RUN=false` are the script's
*defaults on the six non-Sunday days*, and the pointer is rewritten wholesale each run. So Sunday's
verdict is written at 04:00 UTC and **persists until Monday 04:00 UTC** overwrites it. The canary
re-reads the pointer every 15 minutes. A consumer landing any time before Mon 2026-08-31 04:00 UTC
therefore adjudicates *this* Sunday's real result.

## R8 — Delivery path carries no deploy manifest

**Decision**: No `deploys/queued/` manifest.

**Rationale**: `felix-canary` runs `scripts/canary/` from the `/home/claude/kg-automation` checkout
(confirmed in the inventory's `config_files` entry: repo source `scripts/canary/`, deployed path
`/home/claude/kg-automation/scripts/canary/`). The change is pure repo content consumed by a git
checkout, matching the #746 precedent recorded in the inventory ("No deploy manifest (pure helpers +
agent prompts via self-pull)"). The producer script is untouched, so nothing that *is* manifest-managed
changes.

## R9 — Rebaseline obligation does not apply

**Decision**: Merge record states `Rebaseline: not required — no audited surface touched`.

**Rationale**: Checked against the authoritative consumer rather than by reading path globs:
`tooling/scripts/check_audited_surface_drift.py` reports no audited-surface match for
`scripts/canary/probes.py`, `docs/design/architecture/data/service-inventory.json`,
`tooling/scripts/validate_architecture_data.py`, the test files, or the runbook.

## R10 — CI runs an older Python than either host

**Decision**: Target Python 3.11 syntax.

**Rationale**: `.github/workflows/test-ci.yml` pins `python-version: '3.11'`, while the office4 venv
and office2 both run 3.12.3. A 3.12-only construct would pass every local check and redden CI after
push. Worth stating because the entire local development and verification loop for this mission runs
on 3.12.

## R11 — Adversarial evidence

No dependency is added, upgraded, or removed in any ecosystem, so the supply-chain adversarial pass has
no security-impacting decision to challenge. The design's contested points were instead surfaced by the
post-plan review point-cut; their dispositions are recorded there. No contested finding was dropped
silently.

## Open items carried into implementation

None blocking. Two consequences are recorded rather than resolved here, both deliberately:

- office4's ledger placement (a component entry with `host: office4` in an inventory that currently
  holds zero office4 entries) is confirmed by #913, per spec C-007.
- The 15 remaining pointer-emitting components are deferred to a follow-up issue, per spec C-005 and
  FR-011.
