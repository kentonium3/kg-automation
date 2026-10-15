# Research: Backup alerts name why the run failed

All facts verified 2026-10-15 against `main` @ `dfff40b1` and live office2 state.

## R1 — Does the canary already page on a failed run?

- **Decision**: Yes. #1067's original premise, a delay of about 7 h, predates #1063. The scope narrows to naming the cause.
- **Evidence**:
  - The canary evaluates `last-backup.json` against `restic-backup`'s `key_ledger` every 15 min.
  - `/data/services/alert-bus/ledger/2026-10-1{4,5}.jsonl` show `felix-canary:restic-backup` pages at 10-14 21:40Z, 10-15 03:47Z and 09:47Z, a 6 h re-remind.
  - felix-health-check pages independently at 11:00 and 23:00.
- **Alternatives considered**:
  - A direct alert from `backup.sh`, rejected because root would run claude-writable code (#899).
  - A claude path watcher, rejected because it would double-page.

## R2 — Pointer schema version

- **Decision**: Keep `schema_version: 2` and add `failure_reason` as an additive key.
- **Rationale**:
  - `schema_version` is adjudicated with `good_values: [2]`. Bumping to 3 means accepting `[2, 3]` across the manual-install window: the live producer emits 2 until Kent installs the new script. That leaves a vestige to clean up later.
  - The key is diagnostic-only, so no consumer's reading of existing keys changes.
  - The reconciliation harness, not the version number, is what guards the key set.
- **Alternatives considered**:
  - Bump to 3 with a transitional `[2, 3]`. Rejected: an extra moving part, and a migration vestige.

## R3 — Where the cause text is attached

- **Decision**: In `scripts/canary/probes.py::_probe_freshness_with_ledger`, on every non-ok `ProbeResult` it returns: unhealthy, explicit-error, non-anchor freshness failure, and stale anchor.
- **Rationale**:
  - It is the only function with both `pointer` and `ledger` in scope.
  - `health.evaluate` copies the evidence straight through (`health.py:158`). `run._build_alert` uses the evidence as the description (`run.py:165-195`).
  - felix-health-check's coverage calls `health.evaluate` (`coverage.py:185`) and renders `f.evidence` (`felix_health_check/run.py:297`). The health-check therefore inherits the cause with no change of its own (FR-006).
- **Unknown verdicts**: `unknown` (`_unevaluable`) is left undecorated. If a document couldn't be evaluated, its cause key isn't trustworthy either. This is conservative and allowed by spec edge case 3.
- **Dedup**: `dedup.decide` keys on outcome, last emission, and the optional `signal` (`dedup.py:177`). It never keys on evidence, so the enrichment cannot change cadence (NFR-001). `signal` is never set by this change.

## R4 — The ledger contract is closed

- **Fact**: Contract rule 1 (`kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`) allows only `adjudicated`, `diagnostic_only` and `reconciliation_harness`. The validator enforces it (`KEY_LEDGER_MEMBERS`, `validate_architecture_data.py:180`; rule `key-ledger-unknown-member`).
- **Decision**: Add an optional `cause` member under a new **rule 9**, specified in `contracts/key-ledger-cause-member.md`. Append a dated, add-only amendment to the authoritative contract file, which the validator and tests cite as authority. The canary's runtime reader ignores the member when it is malformed; the validator is not the only line of defence.
- **Alternatives considered**:
  - Put the code-to-text map in canary code. Rejected: it would key on a component (C-003) and split the declaration from the ledger.
  - Have the producer write plain words in the pointer. Rejected: root-written free text would reach alerts verbatim, and NFR-002 requires declared text only.

## R5 — Producer classification

- **Codes**:
  - `backup_mount_missing`: `mountpoint -q` fails.
  - `repo_inaccessible`: `restic snapshots --latest 1` fails.
  - `backup_failed`: `restic backup` returns a code outside {0, 3}.
  - `unclassified`: any other non-zero script exit.
- **Completed runs** are `null`, including prune or integrity failures, because `prune_exit_code` and `last_integrity_check_utc` already page with self-describing evidence.
- **Mechanism**:
  - A `FAILURE_REASON=null` default sits beside the other sentinels.
  - Each fatal branch sets the JSON literal (for example `FAILURE_REASON='"backup_mount_missing"'`) before `exit 1`.
  - `write_state_pointer` captures `rc=$?` as its first statement and sets `"unclassified"` when `rc != 0` and no reason was set.
  - The heredoc emits `"failure_reason": $FAILURE_REASON`. Values come from a fixed literal set only (NFR-003, C-001).
- **Test harness**: `tests/office2/restic_backup/test_pointer_emission.py` already drives every fatal exit with stubs (`STUB_MOUNT_RC`, `STUB_SNAPSHOTS_FAIL`, `STUB_BACKUP_RC`), and pins the key set (`FINAL_FOURTEEN_KEYS`, which becomes fifteen). `test_ledger_reconciliation.py` executes the script and fails in both directions on any key the ledger has not declared.

## R6 — Deploy path

- **Fact**: `felix-canary.service` and `felix-health-check.service` run `python3 -m …` with `WorkingDirectory=/home/claude/kg-automation`. The inventory is read repo-relative (`registry.py:109`).
- **Decision**: No manifest. felix-deployer's pull is the deploy. Verify live on the next tick.
- **Note**: the producer half goes live only through Kent's manual install (C-002). Until then, the canary sees no `failure_reason` and behaves exactly as today. That transition is FR-008's "absent" case, which is tested.

## R7 — Audited surfaces

- **Fact**: no `audited-surfaces.json` pattern matches any touched path. The nearest, `systemd-user-units`, covers `scripts/office2/*.service|*.timer|*.target|*.path` and `scripts/office2/deploy/*.sh`.
- **Decision**: `Rebaseline: not required — no audited surface touched`.
