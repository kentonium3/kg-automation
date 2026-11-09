# Mission review: vikunja-repeat-cutover-01M6YRJG

Reviewer: Claude Sonnet 5.5 (independent of Codex gpt-6.1-sol WP01-05/07 and Claude Opus 5.5 WP06). Date: 2026-11-09.
Tree: /home/kgale/repos/kg-automation-1095, branch fix/vikunja-repeat-cutover, `git diff main...HEAD -- . ':!kitty-specs'`.

## Verdict: PASS WITH FOLLOW-UPS

No MATERIAL finding. Every producer/consumer joint on the stage, activate, gate, preflight, verifier, rollback and runbook path agrees on field names, phases, codes and paths. Follow-ups are EDGE only.

## Method and evidence

- Read the diff for core.py, dbsafety.py, baseline.py, activate, stage, rollback_release.py, preflight, verifier, release.json, both manifests, and the runbook sections for ingress, PR1, preflight, gate, acceptance and rollback.
- Loaded the real release.json and its bound baseline with the repo loaders: record valid, baseline hash and identity bind (previous_version v2.7.1-670-420c7bcb75, previous_image_config equals rollback.image_id, 155 pre-upgrade IDs incl. SCHEMA_INIT, 10 added IDs). No DB opened.
- PR1 coherence run: copied HEAD to a scratch git repo outside the repository, removed the three PR2 paths (inventory JSON and markdown restored to main's content), ran `tests/deploy` with the repo venv (Python 3.13): 1814 passed, 4 skipped. The phase-aware logic selects the STAGE phase and the previous-release inventory is accepted.

## Joint-by-joint walk

| Joint | Producer | Consumer | Result |
|---|---|---|---|
| Ingress to STAGE file names | stage_release_archive.py derives one dest dir from dirname of both archive paths; both are in `release-artifacts/fc451cc51412/`, which is sha[:12] of the new archive | STAGE opens `record.archive.path` (.tar.gz) and the rollback ref is a local keeper tag | Agrees. The ingress test now uses the frozen first-cutover fixture, so this layout is checked only by reading (EDGE-4). |
| STAGE embedded tag | `verify_archive` returns validated `repo_tags` | `check` refuses a conflicting tag before load; `_load` verifies each reported ref resolves to the config digest; re-run after a partial load is accepted (embedded tag equals digest) | Agrees. |
| Snapshot to gate | `dbsafety.snapshot` returns `snapshot_dir`, `db_path`, `db_sha256`, `tasks_count` (resolved paths) | `baseline.gate` uses `db_path`, `snapshot_dir`, `db_sha256`; receipt written create-only 0600 in a euid-owned 0700 dir, fsync file then parent | Agrees. |
| Gate to marker | gate raises GATE_* with phase `snapshotted` | `_cleanup` records `failed_phase=retagged`, `error=<code>`; no docker tag or up follows | Agrees; tested by real-gate ordering and crash-window tests. |
| Gate failure to rollback | marker phase `snapshotted` | `--recover-pre-snapshot` returns RECOVER_MARKER_PAST_RETAG (only started/stopped allowed); `--prepare`/`--finish` accept outcome failed or null | Agrees; end-to-end test `test_gate_failure_snapshot_rollback_and_pre_snapshot_refusal` runs gate failure, prepare, restore stand-in, finish and checks the previous image and version. |
| Rollback identity | marker/snapshot `pre_version` comes from `wait_ready(rollback_version(rec))` | `rollback_guard(rollback_version=...)` requires `snapshot.pre_version == rollback_version(release)`; `_start_and_record` waits for that exact version; `baseline.previous_version`, activate and rollback all derive it from `rollback.ref` the same way | Agrees. `rollback.ref` is now `office2.local/vikunja:v2.7.1-670-420c7bcb75`, a keeper tag, so `untag_active` (which refuses unless the image keeps another name) is safe in activate cleanup and in rollback. |
| Recover pre-snapshot | marker written at start with release_version, config_digest, rollback_image_id, pre_version | `_recover_identity_code` compares exactly those four keys; null-outcome crash windows (started, stopped) accepted; active absent or at rollback image accepted | Agrees. |
| Gate receipt to verifier | `baseline.json` keys: schema_version, snapshot_sha256, baseline_sha256, release_version, config_digest, baseline, aggregates | `_receipt_valid` plus binding to `snapshot.json` (`snapshot_dir`, `db_path`, `pre_version`, `running_image_id`, `tasks_count`), record and a fresh `compare` equal to stored aggregates | Agrees. Paths come from the marker in resolved form, matching `snap.resolve()`. |
| Preflight to gate | preflight calls `dbsafety.snapshot` on a stable copy and `baseline.compare(snap["db_path"], facts)` | the same `compare` as the gate and the verifier | Agrees; copy removed on every exit path including SIGTERM/SIGHUP. |
| Readiness | `readiness.migration_ok` needs only "Ran all migrations successfully."; the RRULE summary is optional | ACTIVATE no longer needs the conversion summary (C-004) | Agrees. |
| Version regex | `_VERSION_RE` now accepts `-rrule.N` | the only version regex in scripts; used by release schema, readiness expected version and emit allowlist | Agrees. |
| Runbook follow-ups | rollback prints rebaseline commands only if `security-baseline-ops.md` contains them verbatim | that file still contains both commands | Agrees. |

Ownership and permissions: the new euid and mode checks (gate receipt directory, verifier `_private_directory`, preflight `open_private_root` on the failures root) assume the deployer and the `claude` user share an effective uid. Evidence for that in existing code: dbsafety.py documents the trust boundary as the same user (`claude`), the pre-change runbook says the felix-deployer ticks "as `claude`", and the unchanged rollback `--prepare` already opens the failures root and reads the snapshot directory under the same euid rule. Host facts are not verified here (EDGE-5).

PR1 isolation: the diff queues only `deploys/queued/vikunja-release-stage.yaml`; the ACTIVATE manifest and the inventory pair are the only PR2 paths. Merging PR1 can run only STAGE. Compose and applied 0033/0034 are untouched (C-001, C-003). Queued manifest names repeat the applied names (`vikunja-release-stage`); `scripts/deploy/lib/applied.py` numbers applied entries by sequence, so the repeat is expected to be accepted (unverified against the live deployer, EDGE-8).

NFR-002: grep of the added lines for snapshot paths, timestamps, counts and task data found only synthetic test sentinels and the pre-existing office4 custody paths in release.json. Public output now carries stable codes only (activate, core.run_cli, installed-file report removed from dbsafety). The committed baseline holds migration IDs, schema hashes and image identities only. Preflight prints two elapsed-second values; verifier prints per-check PASS/FAIL. Rollback output (Claude-run, not deployer-retained) still prints snapshot and failures paths and write counts, which Kent needs for the restore decision.

NFR-001: gate deadline `min(30 s, remaining outage)`; ACTIVATE_OUTAGE_DEADLINE takes precedence (activate `except Exception` branch also maps an expired outage). Preflight caps comparison at 25 s and the whole run at 90 s. Actual timings are a runtime fact for the preflight.

## FR trace

| FR | Code | Test that fails without it | Verdict |
|---|---|---|---|
| FR-001 | core.py:120 `_VERSION_RE` (-rrule.N) | test_vikunja_release_core.py, release record tests with malformed variants | Met |
| FR-002 | core.py `_parse_pinned` `r:*`, EOFError/zlib.error; sha/size pin unchanged | test_vikunja_release_core.py `test_gzip_pins_transport_bytes_before_parsing`, `..._tarfile_parses_the_hashed_handle` | Met |
| FR-003 | stage `check`/`_load`/`_LOADED_RE`, core `repo_tags`; cleanup is tag-only | test_deploy_vikunja_release_stage.py `test_tagged_import_and_reapply_retain_rollback_and_keepers`, `test_import_tag_preflight_refuses_before_loading`, `test_tagged_load_verifies_every_reported_identity` | Met |
| FR-004 | dbsafety `rollback_guard` (sha plus exact pre_version; migrated check removed) | test_vikunja_release_db.py `test_guard_accepts_matching_rrule_restores`, `test_guard_refuses_a_sha_mismatch` | Met |
| FR-005 | rollback_release.py `_recover_marker_code`, `_recover_identity_code`, `_recover_state_code` | test_vikunja_rollback.py `test_activation_death_recovers_through_running_previous_image`, `test_unfinished_recovery_runs_previous_rrule_image`, `test_recovery_refuses_foreign_or_missing_marker_identity`, `test_unfinished_later_phases_never_allow_recovery` | Met |
| FR-006 | rollback_release.py `MIGRATION_OWNED_COLUMNS` (repeats compared), `subscription_backfill_included` in prepare record | test_vikunja_rollback.py `test_existing_rules_and_subscription_backfill_count_as_writes` | Met |
| FR-007 | `rollback_guard` exact match, `finish` uses `rollback_version(ctx.release)`, fallback regex removed | `test_finish_requires_exact_pre_version_before_image_mutation`, `test_guard_requires_snapshot_exact_previous_version` | Met |
| FR-008 | baseline.py `gate`, `compare`, `write_receipt`; activate `_cutover` | test_deploy_vikunja_release_activate.py `test_real_gate_failure_ordering_and_replay`, `test_receipt_both_fsyncs_precede_tag`, `test_gate_crash_windows_refuse_replay`; test_vikunja_release_baseline.py | Met |
| FR-009 | scripts/vikunja/verify_release_upgrade.py | test_vikunja_release_acceptance.py (uses the real `snapshot` and `gate` to produce the receipt) | Met |
| FR-010 | services/vikunja/release.json, queued stage manifest, committed baseline | test_vikunja_cutover_change_set.py phase matrix and manifest checks; test_vikunja_release_consistency.py | Met |
| FR-011 | queued activate manifest, inventory JSON/markdown, phase-aware tests | `test_phase_matrix`, `test_invalid_queued_activate_never_falls_back`; PR1 scratch run above | Met |
| FR-012 | docs/runbooks/vikunja-release-cutover.md | test_vikunja_cutover_change_set.py runbook assertions; test_vikunja_release_readiness.py | Met |
| FR-013 | scripts/vikunja/preflight_release_baseline.py | test_vikunja_release_preflight.py (unstable copy, budget, cleanup) | Met |
| FR-014 | inventory pair, runbook, docs/INDEX.md | change-set phase tests | Met in code; absent from acceptance-matrix.json (the matrix was scaffolded before FR-014 was added; known, see EDGE-1) |

## Findings

MATERIAL: none.

EDGE:

1. kitty-specs/vikunja-repeat-cutover-01M6YRJG/acceptance-matrix.json has no FR-014 row (added after scaffolding). Add a row or record the omission.
2. scripts/deploy/deploy-vikunja-release-stage.py (apply `except Fail` block) emits STAGE_IMPORT_CLEANUP_REQUIRED for every Fail in the load block, including STAGE_LOAD_FAILED and STAGE_TAG_RELEASE_FAILED where nothing may have been imported. Mildly over-cautious, not unsafe.
3. ACTIVATE `--dry-run` does not read or verify the bound baseline (plan lists BASELINE_GATE only); a bad baseline surfaces in preflight (required by the runbook) or at the gate (fail-closed, but inside the outage). Optionally call `baseline.load_bound` in dry-run.
4. tests/deploy/test_vikunja_stage_release_archive.py now uses the frozen first-cutover fixture, so ingress is not exercised against the real record's layout (both archives in one `fc451cc51412` dest, .tar.gz basename). Reading the code shows it works.
5. Ownership: preflight, verifier and gate receipt rely on deployer and `claude` sharing an effective uid. Supported by existing code and the old runbook; host fact unverified. A mismatch fails closed with PREFLIGHT_FAILED / ACCEPTANCE_RECEIPT_FAILED.
6. Rollback output (Claude-run) prints snapshot and failures paths; fine under the spec's deployer-output scope, note if the retained-output scope is widened.
7. The per-WP narrative requirement references differing from frontmatter, and the seven lane worktrees left after the refused coordination teardown, are known and accepted.
8. Queued manifest names reuse applied names (`vikunja-release-stage`, `-activate`); relies on the deployer numbering by sequence. Unverified on the host.

## Risks

- Residual crash after retag restarts the unverified new image (documented in the runbook section 8 and the manifest).
- Preflight timing on the live database is the only evidence for NFR-001 and SC-005; it is a runtime check, not a test.
- Receipt validation requires integer subscription IDs and muted of NULL/0/1; an unexpected column value would fail the gate closed (GATE_RECEIPT_WRITE_FAILED), caught by preflight only for compare, not for receipt shape.

## Follow-ups

- Add the FR-014 row to the acceptance matrix.
- Optional: dry-run baseline load; narrow STAGE_IMPORT_CLEANUP_REQUIRED; one ingress test against the real record layout.
- After consolidation: retrospective and post-merge Codex diff review per the standing arc.
