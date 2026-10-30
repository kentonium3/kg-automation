# Mission Review Report: vikunja-image-deploy-01M65D3V

**Reviewer**: Claude Sonnet 5.5 (`claude-sonnet-5-5`, Anthropic), acting as reviewer-renata. It is independent of the implementers (Claude Opus 5.5) and of the per-WP reviewer (Codex gpt-6.1-sol).
**Date**: 2026-10-30
**Mission**: `vikunja-image-deploy-01M65D3V` — Vikunja image-archive staging and activation deploy route (mission 121, tracking issue #1087)
**Baseline commit**: `8dda8b24c07983beb948eb5b88cc1bd54a6564f0` (`meta.json` `baseline_merge_commit`); the diff was taken against `origin/main`
**Merged commit**: `9579d231d0a37e0b9b888eea60d0c8d8cdd84b0b`
**HEAD at review start**: `656fcc82` on `feat/vikunja-image-deploy`. All code citations below are to that tree.
**WPs reviewed**: WP01..WP09, all `done` (`spec-kitty agent tasks status`: 9/9)

**Provenance caveat.** While this review ran, another actor landed `3ea8dd73` ("fsync the parent of every created private folder") and left uncommitted edits in `scripts/deploy/deploy-vikunja-release-activate.py`, `scripts/deploy/vikunja_release/dbsafety.py` and `scripts/vikunja/rollback_release.py`. Those edits move `ACTIVATION_LOCK_NAME` and the lock code into `dbsafety`. I did not review them and made no change to them. The `tests/deploy` run below was against that moving working tree.

---

## Gate Results

### Gate 1 — Contract tests
- Result: **N/A**. `tests/contract/` belongs to the spec-kitty source repo. This repo (kg-automation) has no equivalent.
- Substitute: `tests/deploy` (see below).

### Gate 2 — Architectural tests
- Result: **N/A**, for the same reason (`tests/architectural/` is spec-kitty source repo only).

### Gate 3 — Cross-repo E2E
- Result: **N/A**. There is no spec-kitty-end-to-end-testing equivalent for a deploy route in this repo.
- Substituted by the WP05 sandbox evidence (`docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md`). That is a real run on office2 of the one engine behaviour fakes cannot prove: Compose v5.3.1 with a missing tag and `pull_policy: never` exits 1 "No such image" and starts no container, and `pull_count=0`. The record was posted to #1087 before the run, and the run used `office2-claude`.

### Substitute — `tests/deploy`
- Command: `/home/kgale/repos/kg-automation/.venv/bin/python -m pytest tests/deploy -p no:cacheprovider -q -rs`
- Exit: 0. **1440 passed, 3 skipped** (the skips are `test_state_isolation.py`, which needs a real `/data`). Output is in `.../scratchpad/mr-deploy2.log`.
- Mission test files: 8 files, about 250 tests (core 56, db 43, readiness 26, stage 33, activate 40, rollback 49, ingress 36, change-set 11).
- Caveat: the tree was being edited by another actor during the run (see above).

### Gate 4 — Issue Matrix
- File: `kitty-specs/vikunja-image-deploy-01M65D3V/issue-matrix.json`
- Rows: 2.
  - `#1087`: verdict `in-mission`, `title: "<fill at WP-implementation time>"`, `evidence_ref: "mission tracking issue; delivered by WP01-WP09"`.
  - `#853`: verdict `not-applicable` (auto-classified, `pr_or_commit_ref`). This one is terminal.
- Empty / `unknown` verdicts: 0.
- Non-terminal verdicts surviving to `done`: **1** (`#1087` `in-mission`).
- Unfilled placeholder: 1 (`#1087` title).
- `deferred-with-followup` rows missing a handle: 0.
- Result: **FAIL**. In `specify_cli/cli/commands/review/_issue_matrix.py` and `policy/merge_gates.py:437`, `in-mission` is explicitly non-terminal and "must NOT survive to mission `done`/merge". Here it survived. The skill treats this as a HARD FAIL.

---

## FR Coverage Matrix

Sources of truth: `spec.md` as amended 2026-10-30, and research R-9..R-24 (these override R-1..R-8). The coverage-map check passed: every `owned_files` entry of WP01..WP09 appears in `git diff origin/main..HEAD`.

| FR ID | Description (brief) | WP Owner | Test File(s) | Test Adequacy | Finding |
|-------|---------------------|----------|--------------|---------------|---------|
| FR-001 | STAGE dry run reports and changes nothing | WP03 | test_deploy_vikunja_release_stage.py (`test_dry_run_plans_and_makes_zero_mutating_calls`, `..._read_only_in_every_state`) | ADEQUATE | — |
| FR-002 | STAGE apply: verify hash, load, tag, check digest/platform/version/user | WP01, WP03 | test_vikunja_release_core.py, test_deploy_vikunja_release_stage.py | PARTIAL | RISK-2: no real `docker load` output fixture. Only `Loaded image ID: <id>` is synthetic (stage test :180). It fails closed. |
| FR-003 | STAGE refusals (hash/missing/stable-name mismatch) | WP01, WP03 | stage tests (`test_refusals_exit_1_with_no_load_and_no_tag`, `test_loaded_id_other_than_config_digest...`) | ADEQUATE | — |
| FR-004 | Rollback image verified; STAGE never touches containers or Compose | WP03 | stage tests | ADEQUATE | — |
| FR-005 | STAGE idempotent | WP03 | `test_apply_is_a_noop_once_staged` | ADEQUATE | — |
| FR-006 | Ingress via `office2-claude`, create-only 0700, hash re-verified | WP07 | test_vikunja_stage_release_archive.py (36) | ADEQUATE | The remote shell commands (`ln -T`, `set -o noclobber`) are pinned as strings only. Their semantics on office2 are unexercised until the packet's `--dry-run`/`--apply`. |
| FR-007 | Compose changes exactly `image:` plus `pull_policy: never` | WP08 | test_vikunja_cutover_change_set.py (`..._exactly_two_lines`, `test_any_other_change_is_detected`) | ADEQUATE | — |
| FR-008 | ACTIVATE dry run reports preconditions | WP04 | activate tests (`test_dry_run_reports_every_precondition_and_mutates_nothing`, per-precondition) | ADEQUATE | — |
| FR-009 | Stop, snapshot with service down, hash, integrity check | WP02, WP04 | test_vikunja_release_db.py (real sqlite), activate tests | ADEQUATE | — |
| FR-010 | Start, verify image, `/api/v1/info` 200 + version, migration log | WP02, WP04 | readiness tests, activate tests | PARTIAL | **RISK-1 (HIGH):** the migration-log check uses a synthetic unquoted line (`activate.py:66`, `readiness test:269`). The release's real slog format is not matched. |
| FR-011 | Failure: stop new container, keep logs and snapshot, record, never start old image | WP04 | `test_failure_after_down_ends_locked_with_marker_failed`, `..._cleanup_captures_logs_before_its_down` | ADEQUATE | — |
| FR-012 | At most one stop/start; durable marker; replays inert | WP01, WP04 | `test_crash_after_each_phase_then_replay_is_inert`, `test_marker_is_created_before_the_stop`, lock tests | ADEQUATE | — |
| FR-013 | Scripted rollback to 2.4.0 | WP06 | test_vikunja_rollback.py (49) | ADEQUATE | The wording "returns the image selection to `vikunja/vikunja:2.4.0`" is satisfied by retagging `active`, not by a Compose edit (DRIFT-3, LOW). The 2.4.0 `/info` string `v2.4.0` is derived from the ref, not captured live (RISK-2). |
| FR-014 | Refuse 2.4.0 on a migrated DB | WP02, WP06 | db tests (real sqlite guard, WAL/SHM, sha), rollback tests | ADEQUATE | — |
| FR-015 | Every Kent step has an exact command | WP06, WP09 | rollback output templates; runbook | PARTIAL | I hand-checked the runbook's `rollback_release.py`, retire and `ssh office2-kgale` commands against the code, and they match. No automated test pins runbook commands to CLI flags. |
| FR-016 | Architecture records and stale runbooks corrected | WP08, WP09 | `test_inventory_json_matches_compose_and_release`, `test_inventory_markdown_matches` | ADEQUATE | — |
| FR-017 | INV-1 / INV-2 on every startup path; residual risk stated | WP02, WP04, WP05, WP06 | guard tests, ordering tests, WP05 live evidence | ADEQUATE | Host-boot behaviour was not exercised (the evidence doc says so). The residual is stated in the manifest notes and the packet. |
| FR-018 | Time limit on every operation; 300 s outage deadline | WP01, WP02, WP04 | `test_every_subprocess_call_is_time_bounded`, `test_outage_deadline_crossed_mid_readiness`, `test_realistic_cumulative_outage_exhaustion`, `test_cleanup_stays_inside_its_budget...` | PARTIAL | The deadline code is correct (see NFR check). Raw file copy and `fsync` in `_copy_hashed` have no time bound (RISK-5, LOW). |
| FR-019 | Output carries only allowlisted values | WP01 and all | `test_seeded_text_never_reaches_stdout_stderr_or_the_marker`, `test_every_line_is_allowlisted_on_the_happy_path`, stage/rollback/ingress equivalents | ADEQUATE | — |
| FR-020 | Cancel path, distinct retry, replayed success reconciled | WP04, WP06, WP09 | `test_success_replay_reconciles_read_only`, `..._that_does_not_reconcile_fails`, `test_non_success_marker_refuses...` | ADEQUATE | — |

**Legend**: ADEQUATE = the test constrains the required behaviour; PARTIAL = the test exists but a fixture diverges from production or a clause is unconstrained.

NFR and constraint check:
- **NFR-001 (300 s)**: met in code. `Deadline(OUTAGE_S=300)` is created immediately before `compose down` (`activate.py:467`). Every subprocess in `_cutover` runs through `_within`, which re-caps the timeout to `min(nominal, remaining)` per call (`:494-513`). The readiness budget is capped to what remains (`:563`) and `outage.check` runs before success (`:581`). Cleanup has its own 120 s budget with a 35 s untag reserve.
- **NFR-002 (no dry-run side effects)**: tested.
- **NFR-003**: met for FR-001..FR-020.
- **NFR-004 (rollback ≤ 15 min)**: every step is bounded. The runbook gives a budget; there is no automated timer.
- **C-001**: nothing is on `main` (`origin/main..HEAD` is 22 commits, all on the mission branch).
- **C-002**: grep shows `office2-kgale` only inside printed operator strings (`rollback_release.py:45,150`). `sudo` appears only in the printed template (`:148-149`) and is never executed. `office2-codex` does not appear.
- **C-003**: Compose is changed only through git.
- **C-006**: no `docker pull`. `pull_policy: never`.
- **C-007**: allowlist tests.

---

## Drift Findings

### DRIFT-1: Issue matrix left non-terminal at merge (Gate 4)

**Type**: PROCESS GATE (spec-kitty merge/review contract)
**Severity**: HIGH
**Spec reference**: mission-review Gate 4; `_issue_matrix.py` `IssueMatrixVerdict`
**Evidence**: `kitty-specs/vikunja-image-deploy-01M65D3V/issue-matrix.json` row `#1087`: `"verdict": "in-mission"`, `"title": "<fill at WP-implementation time>"`, `wp/fr/nfr/sc/scope/repo: null`. The mission is `done` and merged (`meta.json` `merged_at 2026-10-30T06:24:46Z`).

**Analysis**: `in-mission` is accepted at per-WP approval but "must NOT survive to mission `done`/merge". The scaffolded row was never resolved, so the merge-time terminal-verdict rule did not constrain this mission. Either the gate did not fire for this repo or the matrix was not re-read. The row also still carries the scaffold placeholder, and no WP/FR mapping was ever recorded. Remedy (not applied; I do not fix): the orchestrator resolves `#1087` to a terminal verdict with evidence, probably `fixed` after the post-merge fixes land, or `deferred-with-followup` while the cutover go is pending, and fills the title.

### DRIFT-2: Duplicated constants that must agree, with only literal-equality tests

**Type**: CROSS-WP DRIFT
**Severity**: LOW (already being de-duplicated in the working tree, uncommitted)
**Spec reference**: contracts/entrypoints.md; analysis-report.md I1
**Evidence** at `656fcc82`:
- `ACTIVATION_LOCK_NAME = "activation.lock"` at `scripts/deploy/deploy-vikunja-release-activate.py:135` and `scripts/vikunja/rollback_release.py:122`. The latter's comment says "a cross-check belongs to WP08/WP09". The only cross-check is a literal `==` at `tests/deploy/test_vikunja_rollback.py:989`.
- `rollback_version()` is implemented twice (`activate.py:164`, `rollback_release.py:811`) with a docstring promising they match; `test_rollback_version_is_derived_like_wp04` (`test_vikunja_rollback.py:1078`) only checks `v2.4.0`.
- The Compose argv is built in `activate.py:211` and `rollback_release.py:257`.
- Timeouts `COMPOSE_TIMEOUT`, `DOCKER_TIMEOUT` and `READY_BUDGET_S` are redefined per file.

**Analysis**: If one copy changes (a lock rename, or a different `-p`/project flag), ACTIVATE and rollback stop excluding each other. That is the exact INV-1 serialisation the WP06 review (CRITICAL) introduced. Today the tests catch literal drift. The uncommitted working-tree change moves the lock name into `dbsafety`, which resolves it for the lock; `rollback_version` and the Compose argv remain duplicated.

### DRIFT-3: FR-013 wording vs the indirection design

**Type**: SPEC WORDING
**Severity**: LOW
**Spec reference**: FR-013 ("returns the image selection to `vikunja/vikunja:2.4.0`"), FR-007
**Evidence**: `rollback_release.py:733` tags `active` to the rollback ID. Compose keeps `image: office2.local/vikunja:active` (`docker-compose.yml` diff).
**Analysis**: The behaviour is right and is what R-9/R-11 designed. FR-013's text predates it, and analysis I2 acknowledged the same class of drift for a different clause. Docs-only.

---

## Risk Findings

### RISK-1: ACTIVATE's migration-log check does not match the release's real log format, so a healthy cutover is torn down

**Type**: BOUNDARY-CONDITION / SYNTHETIC-FIXTURE
**Severity**: **HIGH**
**Location**: `scripts/deploy/vikunja_release/readiness.py:303-306` (`migration_ok`), consumed at `scripts/deploy/deploy-vikunja-release-activate.py:574-580`
**Trigger condition**: any successful start of the release image with its default logging.

**Evidence**:
- `migration_ok` accepts a line only if `stripped.endswith("Ran all migrations successfully.")` (`readiness.py:305`). R-8 and the spec say the log must *contain* the message.
- At the release revision (`git show 420c7bcb75231be9b6571fdfdf76a1a62f2aebd8:pkg/log/logging.go`), `createHandler` uses `slog.NewTextHandler`, or `slog.NewJSONHandler` for `structured`. `pkg/migration/migration.go:86` calls `log.Info("Ran all migrations successfully.")`. slog's text handler quotes any message containing a space, so the line is `time=… level=INFO msg="Ran all migrations successfully."`, which ends in `."`. The JSON handler ends in `."}`.
- I ran `migration_ok` on both real-shaped lines (`.../scratchpad/mr-probe.py`). Result: **`(False, None)` for both**. It returns `(True, None)` only for the test fixtures' hand-written `INFO Ran all migrations successfully.`.
- The fixtures are synthetic: `tests/deploy/test_deploy_vikunja_release_activate.py:66` (`"2026-10-30T12:00:03Z INFO Ran all migrations successfully.\n"`) and `tests/deploy/test_vikunja_release_readiness.py:269-270`. `tests/deploy/fixtures/vikunja_release/` has no log capture.

**Failure scenario**: On the go, the service starts on the release, `/api/v1/info` returns the right version, and the migration really ran. `migration_ok` returns False, so ACTIVATE raises `ACTIVATE_MIGRATION_LOG_MISSING` (`:579-580`). Cleanup then captures logs, runs `compose down` and untags `active`, and writes marker `failed`. The production service goes down on a DB that is already migrated, and Kent has to do a full `--prepare`/restore/`--finish` rollback to 2.4.0 for what was a good cutover. INV-1 holds, so there is no data loss. The cutover is deterministically unable to succeed, and the failure is blamed on the release. The per-WP reviews and the 1440 passing tests could not see this because every fixture is hand-written.

**Not affected**: the RRULE summary regex (`readiness.py:62-66`) is unanchored, so it still matches inside a quoted msg. The `counts` result is simply `None` today, because the same synthetic assumption applies.

### RISK-2: Production shapes that were never captured: `docker load` output, `/api/v1/info` version strings, container logs

**Type**: SYNTHETIC-FIXTURE
**Severity**: MEDIUM
**Location**: `deploy-vikunja-release-stage.py:_LOADED_ID_RE`; `activate.py:164` / `rollback_release.py:811` (`rollback_version`); `readiness.py` log handling
**Trigger condition**: the first real run on office2.
**Evidence**: `tests/deploy/fixtures/vikunja_release/README.md` lists captured shapes only for `index.json`, `manifest.json`, config, `docker info`, image inspect and container inspect. Not captured: `docker load` output, any `/api/v1/info` body, any container log. The 2.4.0 pre-version expected by ACTIVATE (`PRE_VERSION`) and rollback readiness is `v` plus the tag of `vikunja/vikunja:2.4.0`, computed, not observed.
**Analysis**: Each of these fails closed. A wrong `docker load` shape gives `STAGE_LOAD_OUTPUT_UNPARSEABLE` after a real load, leaving an untagged image that needs the R-18 recovery. A wrong 2.4.0 version string makes ACTIVATE's `PRE_VERSION` precondition unmet (caught at the deployer's dry-run, before any stop). A wrong rollback version string fails `--finish` readiness after 2.4.0 has started, which triggers cleanup and the cycle of restoring again. RISK-1 is the one that has already been shown wrong. The fix is cheap: capture real lines in the candidate dry-run (R-19) and pin them as fixtures.

### RISK-3: ACTIVATE untags `active` without proving the 2.4.0 image keeps another name

**Type**: ERROR-PATH / ASYMMETRY
**Severity**: MEDIUM
**Location**: `deploy-vikunja-release-activate.py:223-228` (`_active_is_rollback`), `:515-524` (`_untag_active`), `:533-534`; contrast `rollback_release.py:266-278`
**Trigger condition**: `vikunja/vikunja:2.4.0` was removed or retagged between STAGE and ACTIVATE, while the container's `Config.Image` is `office2.local/vikunja:active`. (`_container_is_rollback` accepts either ref, `:237`.)
**Analysis**: The rollback helper refuses to untag unless the image "keeps another known name", so `docker image rm` can only ever untag (`rollback_release.py:269-273`). ACTIVATE has no such guard. Its preconditions check that `active` resolves to the rollback ID, never that `rollback.ref` still does. After `compose down` removes the container, `docker image rm office2.local/vikunja:active` on the image's last tag deletes the 2.4.0 image. `ACTIVATE_ROLLBACK_IMAGE_LOST` (`:533`) then fires only after the deletion, in the middle of the outage. The mission's central safety asset (the rollback image) is lost. It is recoverable by `docker load` of the rollback archive that ingress also copies, but not within the outage. STAGE checks the ref at its own time only (`stage.py:49-53`). The packet's candidate dry-run narrows the window, but nothing makes the ACTIVATE precondition itself prove it.

### RISK-4: Replays and long retry windows produce a failing manifest every 5 minutes

**Type**: BOUNDARY-CONDITION (accepted)
**Severity**: LOW
**Location**: `activate.py:353-385`
**Analysis**: Non-success markers exit 1 on every tick (R-1/R-17, documented in the manifest notes). This is an accepted design cost. The alert noise continues until Kent merges the cancel commit. No code change implied.

### RISK-5: Snapshot file copy and `fsync` carry no time bound

**Type**: BOUNDARY-CONDITION
**Severity**: LOW
**Location**: `dbsafety.py:123-161` (`_copy_hashed`), called from `snapshot()` (`:466-471`)
**Analysis**: FR-018 says every operation has a time limit. SQLite work is bounded by a progress handler, but `os.read`/`os.write`/`os.fsync` in the copy loop are not. The deployer applies no timeout either. Stalled storage during the snapshot is the one place the 300 s outage deadline cannot interrupt. The deadline is checked only after each copy completes. Unlikely on local disk.

### RISK-6: ACTIVATE depends on PyYAML at import; no other `scripts/deploy` entrypoint does

**Type**: ENVIRONMENT
**Severity**: LOW
**Location**: `activate.py:89` (`import yaml`)
**Analysis**: The deployer runs the entrypoint by shebang with the host's `python3`. If office2's system Python lacks PyYAML, `--dry-run` dies with an `ImportError` traceback on stderr. That is fail-safe, because it happens before any stop, but it bypasses the R-16 output allowlist. The packet's candidate dry-run (R-19) is the only thing that would catch it. `_compose_on_active` could be done without a YAML library.

### RISK-7: SC-002 "task count unchanged" is not checked by any entrypoint

**Type**: COVERAGE
**Severity**: LOW
**Location**: `activate.py:542-546` records `tasks_before` only; runbook `vikunja-release-cutover.md:536`
**Analysis**: The after-count is a manual packet step, and the spec lists SC-002 as `[build]`. Acceptable because only Kent's acceptance proves the data is intact, but the runbook and the manifest `post` do not make the automatic part explicit.

### RISK-8: Final-cycle approvals carry no recorded reasoning

**Type**: PROCESS
**Severity**: LOW
**Location**: `tasks/WP01..WP09/review-cycle-*.md` (final cycle of each WP)
**Evidence**: The approving cycles are a single line, "Approved by codex-gpt-6.1-sol: approval:WPNN" (WP01 c4, WP04 c3, WP05 c1, WP07 c4, WP08 c1, WP09 c2). The rejection cycles are thorough and specific (WP06 c5/c6 are good).
**Analysis**: Six WPs have no stated check list for the approving pass, including WP05, whose one cycle ended 5 minutes after its for_review transition (03:47:41 to 03:52:42 on the event log), and WP08, the production Compose change. RISK-1 shows what that audit gap can hide.

---

## Review-history verification (step 4)

The high-cycle WPs are WP01 (4 cycles), WP06 (6 cycles, reopened once after `approved`), and WP07 (4). Event log read as history, sorted by `at`: 100% of lane moves are via the workflow (`actor: user/claude/merge`); there is no arbiter override and no `migration:*` actor. Spot checks that the fixes shipped in the final code:

| Blocking finding | Evidence in final tree |
|---|---|
| WP06 c1-c2: ACTIVATE needs its own lifetime lock because the deploylock belongs to the tick | `activate.py:389-409` takes `activation.lock`; `rollback_release.py:465-500` takes it too |
| WP06 c5: marker-write failure bypasses post-up cleanup | `_start_and_record` wraps marker persistence (`rollback_release.py:745-752`) |
| WP06 c6 P1: late marker-write failure leaves a false success marker | `_persist_rolled_back` re-reads and raises `MarkerDurabilityUncertain` (`:701-717`) |
| WP06 c6 P2: broken output prevents cleanup | `ctx.best_effort = True`; `emit`/`write_line` swallow `OSError`/`ValueError` (`:199-228`) |
| WP04: outage re-capping; log capture inside the deadline | `_within` (`activate.py:494-513`), `log_capture_timeout` (`:154-157`) |

All resolved as claimed. The WP09 reopen (cycle 1) and the WP06 approved-to-planned reopen at 05:58 (triggered by WP09) are visible and were closed.

---

## Silent Failure Candidates

| Location | Condition | Silent result | Spec impact |
|----------|-----------|---------------|-------------|
| `readiness.py:294-310` (`migration_ok`) | log missing, unreadable, or in an unexpected format | `(False, None)`, indistinguishable | RISK-1: a format mismatch is reported as `ACTIVATE_MIGRATION_LOG_MISSING`; the code cannot tell "not migrated" from "line not recognised" |
| `readiness.py:195-280` (`capture_logs`) | any error, timeout, cap | `None` | Never raises by design. ACTIVATE turns `None` into `ACTIVATE_LOGS_NOT_CAPTURED`, which tears down a working release (conservative, FR-011 safe) |
| `core.py:483-485` (`_absent`) | any stderr containing "no such image/object/container" | treated as absent (`None`) | An unrelated error that happens to contain these words reads as "image absent" in `image_id`, `image_facts`, `container_image`. Low likelihood |
| `readiness.py:80-109` (`_probe`) | curl error, non-200, bad JSON, oversize | `"retry"` | After 180 s, `READY_TIMEOUT` with no distinction between "down" and "wrong response" |
| `dbsafety.py:254-272` (`_remove_tree_fd`) | unlink/rmdir fail | swallowed | Scratch `work/` may survive; the snapshot stays valid (documented) |
| `activate.py:662-666` (`_private`) | private log write fails | `pass` | Failure diagnostics lost; the stable code is still printed |
| `rollback_release.py:1008-1015` (`_private_detail`) | any exception | `None` | Same; best effort by design |

---

## Security Notes

| Finding | Location | Risk class | Recommendation |
|---------|----------|------------|----------------|
| No `shell=True`, `os.system` or `os.popen` anywhere in the new code (grep clean). `core.run` requires list argv, a positive timeout, and sets `stdin=DEVNULL`. | `core.py:316-337` | SHELL-INJECTION | None |
| The ingress runs remote shell strings, with every dynamic value passed through `shlex.quote`. The destination is restricted to one component under `/data/services/vikunja/release-artifacts/`. Sources under `/home/codex` are refused. | `stage_release_archive.py:97-136,143-166` | SHELL-INJECTION / PATH-TRAVERSAL | None. The values originate from the reviewed `release.json`. |
| Private folders use `O_NOFOLLOW`/`O_DIRECTORY`, `dir_fd`-relative creation and `fstat` owner/mode checks. Marker and lock are opened no-follow. | `dbsafety.py:175-228`, `core.py:841-931` | PATH-TRAVERSAL / SYMLINK | None |
| Lock scope: ACTIVATE holds `activation.lock` from before the marker read to process exit. Rollback holds the deployer lock plus `activation.lock` from the marker gate to the end. All refusals precede any Docker call. | `activate.py:389-436,452-478`; `rollback_release.py:971-981` | LOCK-TOCTOU | Keep the two lock names single-sourced (DRIFT-2). |
| HTTP: all probes use `curl --max-time` with a `core.run` kill at `max_time+2` and a body cap (64 KiB). No Python HTTP client. | `readiness.py:73-109` | UNBOUND-HTTP | None |
| Subprocess time limits exist for every Docker, Compose, curl and ssh call. File I/O in the snapshot copy is unbounded. | `dbsafety.py:123-161` | UNBOUND-IO | RISK-5 |
| Privacy allowlist: `emit` redacts anything not a count, hex ID, absolute path, UTC timestamp, version, phase/outcome, or code under a code key. Marker and `snapshot.json` validators use the same allowlist. Seeded-secret tests exist in all four entrypoints. | `core.py:158-208,784-822` | INFO-DISCLOSURE (C-007) | None |
| Account discipline: ingress uses the fixed `ssh -o BatchMode=yes office2-claude` prefix. `office2-kgale` appears only in printed instructions for Kent. `sudo` appears only in a printed template and is never executed. No `office2-codex` anywhere. | `stage_release_archive.py:70`; `rollback_release.py:45,148-150` | PRIVILEGE | None |
| Archive trust: size then sha256 is checked on one open descriptor before tarfile parses that same handle; the path is never reopened; JSON members are capped at 1 MiB. | `core.py:623-766` | TOCTOU / DESERIALISATION | None |
| The restore command Kent runs uses `sudo install … && sudo rm -f` against `kgale`-owned data. It is generated from allowlisted values only. | `rollback_release.py:147-150` | PRIVILEGE | None |
| The Compose `post` check in the manifest requires `jq` and `curl` on office2, unverified here. | `deploys/queued/vikunja-release-activate.yaml` `verification.post` | ENVIRONMENT | Confirm in the packet's candidate dry-run. |

---

## Final Verdict

**FAIL**

### Verdict rationale

The architecture is sound and unusually well tested. All 20 FRs are traceable to tests; INV-1 and INV-2 hold in every code path I traced; the 300 s deadline is enforced per call; no `shell=True`; locks cover the full critical sections; the four lock-related review defects of WP06 are fixed in the final code; and the WP05 live run confirms the Compose fail-closed assumption. But two HIGH findings are unaccepted. **RISK-1**: `migration_ok` cannot recognise the release's real slog output (`msg="Ran all migrations successfully."`), so ACTIVATE would tear down a healthy cutover and force a full rollback; every test fixture for that line is hand-written. **DRIFT-1**: Gate 4 fails, because the issue matrix still carries a non-terminal `in-mission` row and an unfilled placeholder title at `done`. Either finding alone makes the verdict FAIL under the skill's rule 8. Neither blocks quickly: RISK-1 is a few-line matching change (R-8's own wording is "contains") plus a captured real log fixture, and DRIFT-1 is a one-row edit.

### Required before the go (blocking)

1. RISK-1: make the migration check recognise the real log format, and capture a real release log line (and the other shapes in RISK-2) as fixtures.
2. DRIFT-1: resolve `issue-matrix.json` row `#1087` to a terminal verdict with evidence and fill its title.

### Open items (non-blocking)

- RISK-3 (MEDIUM): add an ACTIVATE precondition that `rollback.ref` still resolves to the rollback ID before the first untag, as the rollback helper already does.
- RISK-2 (MEDIUM): capture `docker load` output, the 2.4.0 `/api/v1/info` body and real container logs during the packet's candidate dry-run, and pin them as fixtures.
- DRIFT-2 (LOW): finish de-duplicating `rollback_version` and the Compose argv; the lock-name change is in the working tree, uncommitted.
- RISK-5, RISK-6, RISK-7, RISK-8 and DRIFT-3 (LOW), as described.
- Already handled by another actor, not re-counted: parent-directory fsync durability (commit `3ea8dd73`, labelled a post-merge review HIGH in its test header).
- INFO: `core.registered_summaries` has no production caller (tests only). Everything else in `scripts/deploy/vikunja_release/` has a live caller from an entrypoint or helper.
- INFO: the PyYAML and `jq`/`curl` presence on office2 is unverified from this host (no network or ssh was used).

### Findings count

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 2 | RISK-1, DRIFT-1 |
| MEDIUM | 2 | RISK-2, RISK-3 |
| LOW | 7 | DRIFT-2, DRIFT-3, RISK-4, RISK-5, RISK-6, RISK-7, RISK-8 |

---

## Retrospective Reminder

The canonical post-merge sequence is: **mission review → author or verify retrospective (`retrospect create`) → surface findings (`summary` aggregates; `synthesize` reviews proposals)**.

Check performed: `.kittify/missions/01M65D3V047EQFZ0RNYG5E48H7/retrospective.yaml` does **not** exist (this repo has no `.kittify/missions/` directory). The record is at `kitty-specs/vikunja-image-deploy-01M65D3V/retrospective.yaml` (provenance `runtime_post_completion`, `findings_status: has_findings`, `created_at 2026-10-30T06:24:48Z`). It is auto-generated and records the review-loop counts (WP01 3 rejections, WP02 2, and so on) and the analysis-report findings. It has no human-authored entries. The skill's documented path and this repo's actual location differ; the operator should confirm which one `spec-kitty retrospect summary` reads.

Then surface findings:

- `spec-kitty retrospect summary` — cross-mission aggregation (read-only; does NOT author)
- `spec-kitty agent retrospect synthesize --mission vikunja-image-deploy-01M65D3V` — inspect proposals (dry-run by default)
- `spec-kitty agent retrospect synthesize --mission vikunja-image-deploy-01M65D3V --apply` — apply proposals (mutates)

Worth recording in the retrospective: the migration-log fixture was hand-written by the implementer and never compared with the application source at the release revision; the per-WP approvals did not catch it.
