# Research: Vikunja repeat cutover support

Authored by Codex gpt-6.1-sol, read-only, 2026-11-08; kept as delivered except the heading below and the issue citation wording.

**Read-only implementation research — `fix/vikunja-repeat-cutover`**

Verified the specification and packet §§12–15 against source. No files were edited, no database files were read, and the excluded cutover directory was not accessed. Tests and Office2 commands were not run. Paths below are repository-relative unless absolute.

**Requirement-by-requirement changes**

| FR | Exact change location and smallest change | Tests and fixtures to reuse | Risk |
|---|---|---|---|
| FR-001 | `scripts/deploy/vikunja_release/core.py:119`, `_VERSION_RE`: add an explicit `-rrule\.[0-9]+` alternative. This also covers `allowed_value():177`, release validation `:402`, and `readiness.wait_ready():136`. | `tests/deploy/test_vikunja_release_core.py`, `_record():51`; `test_vikunja_release_readiness.py`, `_wait():96`, `_info():44`, `Clock`/`Curl`. Test accepted rrule versions and malformed suffixes in loading, emitting, and readiness. | Avoid unintentionally accepting arbitrary prereleases. |
| FR-002 | `core.py:688`, `_parse_pinned()`, specifically `:694`: change `r:` to `r:*`. Preserve `verify_archive():708` hashing and parsing the same open handle. | Core tests `_build_archive():554`, `_add():548`; stage tests `_build_archive():83`. Add gzip variants, changed compressed bytes, wrong size/hash, corrupt gzip; retain existing same-handle regression tests. | Pin original published gzip bytes, never recompressed or decompressed bytes. |
| FR-003 | `scripts/deploy/deploy-vikunja-release-stage.py:232`, `Stage._load()`: accept tagged output, resolve reported references, require pinned config identity, then retain `_verify_facts():246`. At `core.verify_archive():740`, validate/return embedded `RepoTags`; preflight collisions in `Stage.check():109`. Replace misleading untagged diagnostics. | `tests/deploy/test_deploy_vikunja_release_stage.py`: `_build_archive():83`, `FakeDocker:116`, `Env:202`. Model imported tags; test tagged success, wrong ID/reference, mixed output, collision, failed inspection, and retained rollback refs. | `docker load` changes tags before verification. Never clean up blindly by image ID. |
| FR-004 | `scripts/deploy/vikunja_release/dbsafety.py:755`, `rollback_guard()`: retain container/tag/sidecar/hash guards; replace `is_migrated()` rejection `:803` with exact snapshot `pre_version` equality. Pass required rollback version from `scripts/vikunja/rollback_release.py:741`, `finish()`. | `tests/deploy/test_vikunja_release_db.py`: `make_db():70`, `restored():564`, `_guard():577`; reverse obsolete matching-hash RRULE rejection `:660`. Rollback tests: `Scenario:204`, `_prepared():305`. | Missing/wrong snapshot version must fail **before** tagging or starting. |
| FR-005 | `rollback_release.py:795`, `_recover_marker_code()`: validate marker release/config/rollback image and exact pre-version against the current record. In `recover_pre_snapshot():827`, remove schema-based rejection `:868`; retain phase and Docker guards. | `tests/deploy/test_vikunja_rollback.py`: `Recover:1004`, `write_marker():1049`; retain phase refusal cases `:1115`; replace obsolete repeats/WAL rejection `:1179` with preexisting-RRULE success and mismatched-marker failures. | Never admit `snapshotted` to pre-snapshot recovery: tagging may have succeeded before its marker update. |
| FR-006 | `rollback_release.py:338`, `MIGRATION_OWNED_COLUMNS`: remove `repeats`; retain legacy conversion exclusions. `_count_post_cutover_writes():394` / `prepare():585`: privately label subscription backfill as included conservatively. | Rollback tests `Scenario:204`, `_with():878`, `test_each_post_cutover_write_is_counted():886`; add existing-rule edit and subscription-backfill cases. | Existing accounting measures net changed rows, not every operation. Do not subtract backfill from acknowledged loss. |
| FR-007 | `rollback_release.py:613`, `_wait_pre_version()`: remove any-2.4 fallback `:617–629` and `_FALLBACK_VERSION_RE:129`. Require exact snapshot version in `finish():734` and `_start_and_record():696`. | Replace `test_finish_without_pre_version_requires_2_4():720` with missing/wrong version refusal and exact-version readiness cases. | Checking only readiness discovers incompatibility after the previous image has started. |
| FR-008 | `scripts/deploy/deploy-vikunja-release-activate.py:504`, `_cutover()`: gate after snapshot marker persistence `:520–521`, before `docker tag :528`. Add shared snapshot-baseline functions in a new `scripts/deploy/vikunja_release/baseline.py`; extend release validation at `core.py:400`. | `tests/deploy/test_deploy_vikunja_release_activate.py`: `Env:302`, `_make_db():290`, `World`, `FakeClock`, `Timing:936`, `assert_lock_held_end_state():385`. Extend fixtures with migrations/repeats/subscriptions. Test every mismatch, receipt-write failure, deadline, crash/replay, and zero tag/up calls on failure. Reuse DB tests’ `make_wal_data_dir():89` and durability/mode checks. | Recovery follows the snapshot route. Privacy and elapsed-time checks need explicit coverage. |
| FR-009 | Add `scripts/vikunja/verify_release_upgrade.py`; share baseline calculations with FR-008. Keep `cutover_verify.py:2` unchanged: it verifies the unrelated token-identity cutover through API GETs. | New acceptance test module; reuse synthetic builders from DB tests (`make_db():70`, `make_wal_data_dir():89`), extended into a reusable repeat-cutover fixture. Test missing/extra migrations, changed rule, lost task, corruption, wrong subscriptions, retained duplicates. | Use a stable private post-upgrade copy; never `immutable=1` on live WAL-backed data. |
| FR-010 | `services/vikunja/release.json:3–27,40–42`: new release/source/archive/config/tag, previous-release rollback and both custody sources. Add queued STAGE manifest; refactor change-set tests **in STAGE**. | `test_vikunja_cutover_change_set.py`: `_release():68`, `_manifest():79`, `expected_post_checks():150`, `_vikunja_entry():207`; add temporary-tree STAGE/history cases. Also separate historical route fixtures described below. | Packet values are local provenance, not fresh published-download verification. |
| FR-011 | Add queued ACTIVATE separately after STAGE applies. Update `docs/design/architecture/data/service-inventory.json:20,25` and `docs/design/architecture/service-inventory.md:202` plus Vikunja summary row. Preserve Compose active/never. | Same change-set helpers; require current ACTIVATE identities and new inventory together. Reject wrong-release manifests and premature inventory promotion. | Do not compare still-running inventory to the staged release. |
| FR-012 | Update `docs/runbooks/vikunja-release-cutover.md` at the anchors listed below. | Retain first-cutover regression tests; validate documentation with `python3 tooling/scripts/validate_docs.py`. Add focused checks for candidate contents and release-specific commands where practical. | Historical recovery and first-install instructions are unsafe to execute unchanged. |

**FR-008 insertion, failure state, recovery, and timing**

The insertion is precisely after:

```python
self._advance("snapshotted", snapshot_dir=..., snapshot_sha=..., tasks_before=...)
```

at `deploy-vikunja-release-activate.py:520`, and before the image-selection call at `:528`. Replace the sensitive `ACTIVATE_SNAPSHOT` detail emission at `:522–524` while adding the gate.

Existing durable phases are `started → stopped → snapshotted → retagged → started_new → verified`; success is `phase=verified, outcome=success`. `_NEXT:147` maps the last completed phase to the attempted phase.

For the smallest implementation, retain these phases and record the specific failing gate through a stable marker error code. A gate failure therefore records:

```text
phase=snapshotted
failed_phase=retagged
outcome=failed
error=<specific gate code>
```

This accurately means image selection was the next permitted transition; the error identifies the preceding prerequisite failure.

`Activate.apply():449` catches `Fail`, invokes `_cleanup():571`, and rethrows. Unexpected exceptions use `ACTIVATE_INTERNAL_ERROR`; exhausted outage time becomes `ACTIVATE_OUTAGE_DEADLINE`. Cleanup has its own 120-second budget and attempts logs, Compose down, active-tag removal, and no-container confirmation. Successful cleanup leaves **no active image selected and no service container**; retained release/rollback images remain. Cleanup failures are separately reported, so absence must not be promised when cleanup reports otherwise.

`main():674–678` reports through `core.run_cli` and accumulated `ACTIVATE_FAILED_AT` / `ACTIVATE_CLEANUP` lines. Replay refuses another attempt.

Recovery uses:

```text
rollback_release.py --snapshot <private snapshot directory> --prepare
Kent performs the printed restore
rollback_release.py --snapshot ... --finish --ack-post-cutover-writes ...
```

It does **not** use `--recover-pre-snapshot`: `_recover_marker_code():795` refuses `snapshotted` with `RECOVER_MARKER_PAST_RETAG`. There is no `--recover` option.

Snapshot work is substantial: raw DB/WAL/SHM copy, second work copy, checkpoint, integrity check, `VACUUM INTO`, result integrity check, task count, hash, and fsyncs (`dbsafety.py:610–706`). Its budget is **up to 120 seconds**, capped by remaining outage (`activate.py:516–519`). Readiness receives **up to 180 seconds**, also capped; it is not reserved (`:540–547`).

Actual Office2 snapshot duration is unknown. A 120-second snapshot plus a 180-second readiness poll already consumes the whole 300-second window before Docker overhead. Give the gate a deadline of `min(30 seconds, remaining outage)` and rehearse snapshot plus gate on an authorized representative-size fixture. Existing timing tests simulate elapsed time; they do not prove deployed-size performance.

**Reviewed baseline and release binding**

Prefer a committed, data-free artifact such as:

```text
services/vikunja/baselines/v2.7.1-670-420c7bcb75.json
```

Include the exact sorted pre-upgrade migration IDs, previous version/image identity, schema-identity algorithm/version and digest, and the exact ten expected added IDs. Include a reviewed target-schema identity for acceptance. Exclude production counts, repeat hashes, paths, and timestamps.

Bind its repository-relative path and SHA256 from `release.json`. Extend `core.RELEASE_SCHEMA:400` and `load_release():450` to validate the binding, contained path, digest, unique migration IDs, and version/image consistency. The current validator rejects unknown keys (`_validate():429`); simply adding JSON fields will fail. Hash and parse the same baseline bytes. Include the artifact in candidate packaging.

Define schema identity as SHA256 of canonical UTF-8 JSON containing rows:

```sql
SELECT type, name, tbl_name, sql
FROM main.sqlite_master
ORDER BY type COLLATE BINARY, name COLLATE BINARY, tbl_name COLLATE BINARY;
```

Preserve SQL text and JSON `null`; exclude `rootpage`, schema cookie, row order, and file-layout facts. Version the serialization. Do not globally lowercase or collapse whitespace inside SQL literals.

Opening through Python `sqlite3`, SELECTs, and the configured connection options in `dbsafety._connect():423` do not themselves rewrite schema text. However, `VACUUM INTO` rebuilds tables/indexes by executing stored DDL; it copies views/triggers separately. Therefore byte-identical schema text across arbitrary SQLite versions is not an unconditional guarantee. SQLite also normalizes stored CREATE statements. Generate the reviewed baseline through the same consolidation route and require before/after schema-identity fixture tests on Python 3.12 and 3.13, including altered tables, quoted identifiers, indexes, triggers, and SQL literals. Fail for review rather than silently normalizing away a discrepancy. See [SQLite schema-table rules](https://www.sqlite.org/schematab.html) and [VACUUM implementation](https://raw.githubusercontent.com/sqlite/sqlite/master/src/vacuum.c).

The reviewed 155-ID list, schema digest, and ten-ID addition list remain inputs to obtain and review; counts in the packet cannot substitute for them.

**Private receipts and output containment**

Place `baseline.json` beside `<snapshot_dir>/snapshot.json`; place acceptance evidence under a private subdirectory there. Use 0700 directories and 0600 receipts, exclusive/no-follow creation, complete writes, file fsync, then parent fsync. Reuse the pattern in `dbsafety._write_new_json():480`, but give the new receipt its own validator: that function currently enforces the snapshot-record schema.

Bind private evidence to snapshot SHA, reviewed-baseline SHA, release/config identity, exact migrations/schema identity, task count, repeat count/hash, expected subscriptions and baseline duplicate count. Hash ordered repeat tuples using canonical JSON with explicit null handling, including only nonempty rules.

Existing output already violates the new privacy requirement:

- `ACTIVATE_SNAPSHOT` emits snapshot directory, hash, and task count (`activate.py:522`).
- Success emits elapsed outage time (`:565`).
- Migration details can emit conversion aggregates (`:564`).
- Snapshot code calls `record_installed()` for private copies/receipts (`dbsafety.py:618,681,698`), placing private paths in the deploy reporting channel.

Remove sensitive values from public details and installed-file reporting; retain them privately. Emit stable check/result codes. Add seeded-value assertions covering stdout, stderr, failure excerpts, and installed reports.

Correction to the packet’s implied persistence model: `lib/applied.py:36` copies the manifest and adds application metadata; it does **not** automatically store verification stdout. Thus any private value embedded in verification commands or notes is retained verbatim. Separately, failed-command stdout/stderr excerpts are captured by `lib/apply.py:167,177` and forwarded by `felix-deployer/_tick.py:750`. Sanitize at the producer; truncation is not privacy protection.

**Subscription expectation**

Migration `/home/kgale/repos/vikunja-harness/pkg/migration/20261021192508.go:72` uses task entity type **3**. Its implementation `:78–140` includes all existing tasks/users, no deleted-task or user-status filter, deduplicates eligible creator/assignee pairs, and preserves existing subscription rows, including muted rows and duplicates.

Run this against the consolidated pre-upgrade snapshot:

```sql
WITH eligible(task_id, user_id) AS (
    SELECT t.id, t.created_by_id
    FROM tasks AS t
    JOIN users AS u ON u.id = t.created_by_id
    UNION
    SELECT a.task_id, a.user_id
    FROM task_assignees AS a
    JOIN tasks AS t ON t.id = a.task_id
    JOIN users AS u ON u.id = a.user_id
),
missing AS (
    SELECT e.task_id, e.user_id
    FROM eligible AS e
    WHERE NOT EXISTS (
        SELECT 1
        FROM subscriptions AS s
        WHERE s.entity_type = 3
          AND s.entity_id = e.task_id
          AND s.user_id = e.user_id
    )
)
SELECT
    (SELECT count(*) FROM subscriptions WHERE entity_type = 3)
    + (SELECT count(*) FROM missing)
    AS expected_task_subscription_rows;
```

Existing duplicates remain in the first count; `UNION` deduplicates additions. Acceptance should require expected total rows, no missing eligible pairs, and unchanged duplicate excess—not unconditional zero duplicates. Preserve existing keys/muted choices; equal totals alone can conceal substitutions.

**FR-009 execution and runbook changes**

Use the new release-upgrade script through Office2’s checkout:

```sh
ssh office2-claude \
  'python3 /home/claude/kg-automation/scripts/vikunja/verify_release_upgrade.py ...'
```

Arguments should identify the private snapshot/receipt and stable private post-upgrade copy. The documented fleet runtime is Python **3.12**; development/CI also exercises 3.13 (`.github/workflows/test-ci.yml:28–40`). Python’s `sqlite3` is already required by `dbsafety.py:43`; no SQLite CLI is necessary. This is repository evidence, not fresh host verification.

Update runbook **§7, Acceptance** (`:543`), especially historical legacy-conversion procedure `:567–640` and B4 `:695`. Preserve B3’s hash-stable double-copy method `:663`. Run task/repeat/migration/schema/integrity/subscription comparisons before the disposable write probe.

Other required runbook anchors:

- Introduction and §§1–3 (`:13,106,128,211`): exact from/to, custody, existing roots, release-specific marker, candidate contents.
- Pre-STAGE checks (`:181–206`): active/Compose already exist; remove expected first-install failures.
- §4a / §6b (`:289,448`): two PRs, revised path sets, no Compose edit.
- §§4d–6 (`:394,413,484`): previous identity, private gate, sanitized output.
- §§8–10 (`:793,827,991,1115`): exact-version rollback and gate-failure recovery distinction.
- §11 (`:1185`): tagged-import cleanup.
- Error table (`:1213`): new gate codes and revised schema-guard semantics.

**STAGE/ACTIVATE tests and manifest fields**

`test_vikunja_cutover_change_set.py:72`, `_resolve_manifest_path()`, currently selects queued ACTIVATE or the lexicographically latest applied ACTIVATE. After STAGE changes `release.json`, it selects historical 0034 and compares it against the new record. Inventory assertions `:213,226` likewise compare the running previous release against the staged release. Both break before ACTIVATE.

Ship phase-aware test refactoring with STAGE:

- Identify first-cutover history explicitly by `0034-vikunja-release-activate.yaml`, the first-cutover issue (see #1087), and its exact postchecks; compare against a frozen first-cutover release fixture. Preserve 0033/0034 unchanged.
- Keep historical Compose-diff tests `:88–142` explicitly historical.
- During new STAGE, require new STAGE bindings while inventory still describes the previous deployed release.
- During ACTIVATE, require a current-release queued/applied ACTIVATE and matching new inventory.
- Never let an invalid queued ACTIVATE silently fall back to history.
- Reuse `expected_post_checks():150`; parameterize manifest/root inputs for temporary-tree positive and negative cases.
- Remove Compose from repeat ACTIVATE’s path set. The existing `test_cutover_path_set_is_exact_and_present():240` checks constants/file existence, **not the actual PR diff**. Check the real diff during PR assembly/review.

Both new manifests need:

```yaml
schema_version: v1
name: vikunja-release-stage # or vikunja-release-activate
issue: kentonium3/kg-automation#1095
tier: 2
entrypoint: scripts/deploy/deploy-vikunja-release-stage.py # corresponding helper
audited_surface: true
expected_baselines:
  - docker-images.txt
verification:
  pre:
    - <corresponding entrypoint> --dry-run
  post:
    - <exact identity checks>
created_at: <fresh timestamp>
created_by: <actual creator>
notes: <reviewed release-specific instructions, at most 2000 characters>
```

Use `issue` or `mission_slug`, not both. STAGE postchecks verify the new local release tag/config and retained previous ref/image. ACTIVATE verifies container config ID and exact API version. Leave `apply_mode`, `applied_at`, and `rebaseline` to the deployer.

Exact focused test command:

```sh
python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py
```

Full non-live suite, per `Makefile:23`:

```sh
python3 -m pytest -q --ignore=docs/archive
```

**Tagged-load semantics and additional blockers**

Current `_load():232` extracts only stdout `Loaded image ID: sha256:…` matches into a set. Empty means `STAGE_LOAD_OUTPUT_UNPARSEABLE`; anything other than the singleton pinned config ID means `STAGE_LOADED_ID_UNEXPECTED`. Tagged output therefore fails after importing `kentonium3/vikunja:v2.8.0-rrule.2`.

There is **no automatic image cleanup**. `STAGE_LOADED_UNTAGGED` is a diagnostic, now inaccurate. Runbook §11 must verify the imported tag’s ID, remove only that exact tag when appropriate, and consider image deletion only after proving no remaining refs/container and excluding rollback.

Rollback `_untag_active():261` delegates to `dbsafety.untag_active():342`. It requires at least one matching reviewed local release/rollback keeper (`:369`), not an exact tag set. The imported tag is harmless alongside the local release tag, but cannot replace that keeper.

Further packet omissions:

- Historical tests load mutable real `release.json` while retaining old fake identities: stage `Env:202`, activate `Env:312`, rollback module `:38,46`. Freeze historical records and use explicit repeat-cutover fixtures.
- `tests/deploy/test_vikunja_release_consistency.py:77` hardcodes current rollback to `v2.4.0`; derive current expected version and retain a separate historical case.
- Stage tests’ manifest assertions `test_deploy_vikunja_release_stage.py:750` and resolver `:63` have the same history ambiguity.
- Candidate archive command at runbook `:156` must include the new baseline artifact/module and any acceptance script needed before merge.
- Existing roots are allowed; only new candidate/custody/snapshot destinations are create-only. Preserve the old successful marker and check the **new** marker absent.
- No helper requires 155 migrations or repeat conversion to rerun. Keep structured migration-success verification; do not introduce conversion-count requirements.
- Published-download identities, rollback archive custody/hash/size, reviewed migration/schema baselines, notification disposition, and representative timing remain unverified inputs.

**Proposed work packages**

1. **Release/archive compatibility and historical fixtures** — FR-001–003; freeze old release fixtures and repair mutable-record assumptions.
2. **Rollback correctness** — FR-004–007; depends on WP1 fixtures/version support.
3. **Trusted baseline, private gate, and acceptance verifier** — FR-008–009 plus privacy/timing tests; depends on WP1, with recovery integration against WP2.
4. **STAGE change set and repeat-cutover runbook** — FR-010/012, including phase-aware change-set tests and candidate packaging; depends on WP1–3.
5. **ACTIVATE change set** — FR-011, inventory promotion and final gate/recovery instructions; depends on successful applied STAGE and the separate production decision.

## Planning decisions

**Decision**: Add a preflight on a private copy of the live database before ACTIVATE (FR-013).
**Rationale**: A baseline mismatch found only inside ACTIVATE leaves Vikunja down until Kent restores. A preflight finds it with the service still up and measures the consolidation time.
**Alternatives considered**: Gate only, rejected because every mismatch would cost an outage. Reading the live database directly, rejected by the standing rule and because it is not a stable copy.

**Decision**: Keep the existing marker phases and record gate failures through a stable error code.
**Rationale**: It is the smallest change, and recovery from `snapshotted` already routes through snapshot rollback.
**Alternatives considered**: A new `gated` phase, rejected because it adds replay and recovery states with no safety gain.

**Decision**: Two PRs from one mission.
**Rationale**: An ACTIVATE manifest runs on merge, so it cannot share a PR with STAGE.
**Alternatives considered**: Two missions, rejected because STAGE and ACTIVATE share one design and one review.

## Post-plan review (Codex gpt-6.1-sol, read-only, 2026-11-08)

Two MATERIAL findings, both folded into the plan: no supported recovery from a crash before `snapshotted` is recorded (plan D4a, FR-005), and private log locations and times left in shared failure output (plan D4). The review found the gate ordering, gate-failure rollback, preflight feasibility, schema-identity route and two-PR split sound. Actual `claude` access on Office2 and representative timing remain to be shown by preflight itself.
