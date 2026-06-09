# Tasks: Credential Liveness Probe

**Mission**: `credential-liveness-probe-01KTP9M8`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Target branch**: `main`
**Planning base branch**: `main`

## Summary

5 work packages, 25 subtasks total. Critical path: WP01/WP02 (parallel) → WP03 → WP04 → WP05. Estimated WP prompt size: 250–500 lines each (within ideal range; no splits needed). All WPs are `execution_mode: code_change` except WP05 (planning artifact / doc updates).

The mission delivers the credential liveness probe (#572) as a 6-hour-cadence systemd-driven probe that surfaces dead OAuth refresh tokens via GitHub issues with embedded recovery commands. Phone-recovery acceptance (SC-11 in spec.md) is an operator-owned gate after WP05 merges and deploys.

## MVP scope

WP01 + WP02 + WP03 are the functional core — once those three are merged, the probe can be invoked from any shell on office2 and will detect a dead token + file an issue. WP04 + WP05 are deployment + documentation.

## Work Packages

### WP01 — Manifest schema + Credential dataclass extension

**Goal**: Extend `manifest.py` to parse the new `liveness_probe` block and update `credential-manifest.json` to enable liveness for `gog-credentials-keyring`. Foundational for WP03; parallel-safe with WP02.

**Priority**: P1 (blocks WP03).
**Independent test**: Run `python3 -c "from credential_health_check.manifest import load_manifest; m = load_manifest('docs/design/architecture/data/credential-manifest.json'); gog = [c for c in m if c.name == 'gog-credentials-keyring'][0]; print(gog.liveness_probe)"`. Should print a populated `LivenessProbeConfig`.

**Prompt**: [tasks/WP01-manifest-schema.md](./tasks/WP01-manifest-schema.md) (~300 lines)

**Included subtasks**:

- [ ] T001 Add `LivenessProbeConfig` dataclass to `manifest.py` (WP01)
- [ ] T002 Extend `Credential` dataclass with `liveness_probe: Optional[LivenessProbeConfig] = None` (WP01)
- [ ] T003 Update manifest parser: read the block, validate required-when-enabled, raise `ManifestQualityError` on unknown subkeys (WP01)
- [ ] T004 Update `docs/design/architecture/data/credential-manifest.json` `gog-credentials-keyring` record with the new block (WP01)
- [ ] T005 Add tests in `test_manifest.py` for: parse-with-block, parse-without-block, parse-disabled, missing-required-when-enabled, unknown-subkey (WP01)

**Dependencies**: none.

**Parallel opportunities**: Parallel with WP02 (different files).

**Risks**:
- Backward-compat: existing manifest readers MUST continue working when block is absent. Test via existing manifest tests staying passing.
- JSON validity after the manifest edit — run `python3 -c "import json; json.load(open('docs/design/architecture/data/credential-manifest.json'))"` to confirm.
- `ManifestQualityError` is the existing exception (do not create a new one).

---

### WP02 — Liveness probe core (probe_oauth_liveness + LivenessResult)

**Goal**: Create `scripts/security/credential_health_check/liveness.py` with the deterministic probe function and tests. Pure logic; orchestrator integration deferred to WP03.

**Priority**: P1 (blocks WP03).
**Independent test**: `pytest tests/security/credential_health_check/test_liveness.py --cov=scripts.security.credential_health_check.liveness --cov-branch --cov-fail-under=90 -v` passes with ≥90% line / ≥85% branch coverage. All 13 contract test cases (per `contracts/liveness-probe-function.md`) pass.

**Prompt**: [tasks/WP02-liveness-probe-core.md](./tasks/WP02-liveness-probe-core.md) (~500 lines)

**Included subtasks**:

- [ ] T006 Create `liveness.py` skeleton with `LivenessClassification` Literal + `LivenessResult` dataclass (frozen=True) (WP02)
- [ ] T007 Implement `probe_oauth_liveness()` happy-path branch (subprocess call → exit 0 → return None + log credential_alive) (WP02)
- [ ] T008 Implement `invalid_grant` detection + classification window (keyring mtime + 7d ± 24h → routine-7day vs unexpected) (WP02)
- [ ] T009 Implement probe-error branches (TimeoutExpired, FileNotFoundError, non-zero exit without invalid_grant) (WP02)
- [ ] T010 Add structured INFO logging (credential_alive, credential_dead, credential_probe_error with all required fields) (WP02)
- [ ] T011 Create `tests/security/credential_health_check/test_liveness.py` with 13 contract test cases (alive, routine, unexpected-early, unexpected-late, boundaries, timeout, missing binary, other failure, recovery_command in dead, recovery_command None in error, raises if disabled, UTC probed_at) (WP02)
- [ ] T012 Verify coverage gate locally: `pytest --cov-branch --cov-fail-under=90` passes (WP02)

**Dependencies**: none (pure helper; doesn't depend on WP01's manifest changes since tests pass a synthetic Credential).

**Parallel opportunities**: Parallel with WP01.

**Risks**:
- Subprocess mocking must be careful — patch `subprocess.run` not `subprocess.Popen`; use `side_effect` for exception raises.
- Path.stat mtime mocking: use `monkeypatch.setattr` on the keyring file's `Path` instance OR write a real fixture file and `os.utime()` to control mtime.
- Cycle classification ±24h boundary tests need exact-edge inputs (7 days - 23h59m → routine; 7 days - 24h01m → unexpected).
- `--cov-fail-under=90` is strict; defensive branches (e.g., `# pragma: no branch` on guards that can't fire when the orchestrator filters correctly) may be needed per `[[reference_pytest_branch_coverage_pragma]]`.

---

### WP03 — Orchestrator integration + CLI flags

**Goal**: Wire `probe_oauth_liveness()` into `run_cycle()`; add `--liveness-only` CLI flag; extend `--list --liveness`; reuse existing `github_writer.dedup_check` / `file_alert` for the GH issue surface.

**Priority**: P1 (blocks WP04).
**Independent test**: `pytest tests/security/credential_health_check/test_orchestrator.py tests/security/credential_health_check/test_listing.py -v` passes. `PYTHONPATH=scripts/security python3 -m credential_health_check --dry-run --liveness-only --manifest docs/design/architecture/data/credential-manifest.json` runs cleanly (logs `alert_would_file` if token is dead, `credential_alive` if alive; NO GitHub issue filed).

**Prompt**: [tasks/WP03-orchestrator-integration.md](./tasks/WP03-orchestrator-integration.md) (~450 lines)

**Included subtasks**:

- [ ] T013 Add `_process_liveness_alert()` to `orchestrator.py` per the contract (probe → dedup → file_alert flow) (WP03)
- [ ] T014 Modify `run_cycle()`: add `liveness_only` kwarg; invoke `_process_liveness_alert` in both modes (defense-in-depth per plan §IC-03) (WP03)
- [ ] T015 Add `liveness_alerts_filed: int = 0` field to `CycleResult` (additive) (WP03)
- [ ] T016 Add `--liveness-only` flag to `__main__.py`; plumb to `run_cycle()` (WP03)
- [ ] T017 Extend `--list --liveness` in `listing.py` per the scope-reduced contract (5 columns: name, enabled, gog_account, keyring_mtime_age, expected_next_expiration, recovery_command — NO live classification column) (WP03)
- [ ] T018 Add tests in `test_orchestrator.py` + `test_listing.py` covering: skip-if-no-block, file-on-routine, separate-issue-on-unexpected, dedup-routine, dry-run-no-file, probe-error-no-file, liveness-only-skips-others, run_cycle-in-both-modes, listing-table-shape (WP03)

**Dependencies**: WP01 (needs `Credential.liveness_probe`), WP02 (needs `probe_oauth_liveness` and `LivenessResult`).

**Parallel opportunities**: None — must wait for WP01 + WP02.

**Risks**:
- Dedup title prefix must be exact: `credential-liveness-routine-7day: <credential_name>` and `credential-liveness-unexpected: <credential_name>`. Mismatched prefixes would re-file issues on every cycle.
- `liveness_alerts_filed` field placement in `CycleResult` — must not break existing dataclass construction (default=0).
- `--list --liveness` table format must match the existing listing output style (tabulate / rich / plain print).
- Reuse of `github_writer.file_alert` requires checking that function's existing signature accepts the right `labels` arg.

---

### WP04 — Systemd units + deploy script

**Goal**: Create the two systemd unit files (`credential-liveness-probe.{service,timer}`) plus the idempotent deploy script. Operator runs the deploy script once post-merge to install + activate.

**Priority**: P2 (deploy-time; functional core is WP03).
**Independent test**: From office2 as claude: `bash /home/claude/kg-automation/scripts/office2/deploy/credential-liveness-probe.sh` exits 0, the timer is active, and the smoke-test `--dry-run --liveness-only` invocation runs cleanly.

**Prompt**: [tasks/WP04-systemd-units.md](./tasks/WP04-systemd-units.md) (~280 lines)

**Included subtasks**:

- [ ] T019 Create `scripts/office2/credential-liveness-probe.service` per contract (oneshot; HOME/PYTHONPATH/EnvironmentFile mirror existing pattern) (WP04)
- [ ] T020 Create `scripts/office2/credential-liveness-probe.timer` per contract (`OnCalendar=*-*-* 00,06,12,18:00:00`, Persistent=true) (WP04)
- [ ] T021 Create `scripts/office2/deploy/credential-liveness-probe.sh` per contract (idempotent; checks `liveness.py` and `gog` binary presence; git pull; cp units; daemon-reload; enable --now; smoke-test dry-run) (WP04)
- [ ] T022 Make deploy script executable: `chmod 755 scripts/office2/deploy/credential-liveness-probe.sh` (WP04)

**Dependencies**: WP03 (deploy smoke-tests the new `--liveness-only` CLI flag).

**Parallel opportunities**: None.

**Risks**:
- `OnCalendar` syntax: must use UTC times. `Persistent=true` must be present.
- Deploy script must NOT require sudo (claude user has no sudo per CLAUDE.md).
- `EnvironmentFile=/data/services/openclaw/secrets/openclaw-gateway.env` path must exist and contain `GOG_KEYRING_PASSWORD`.
- Deploy script's `git pull origin main` step assumes the post-merge state; if this WP merges before the WP03 changes are on main, the smoke-test will fail. Per the rc41 single-mission convention, merge is one atomic op so this isn't a real risk.

---

### WP05 — Architecture + runbook doc updates

**Goal**: Update `service-inventory.json` with the new logical service; update `google-workspace-ops.md` §Common Issues to point at the new automatic surface; consult `signal-to-doc-map.json` for any additional doc targets.

**Priority**: P3 (docs; merge-time housekeeping per CLAUDE.md architecture-docs-first rule).
**Independent test**: `python3 -c "import json; s = json.load(open('docs/design/architecture/data/service-inventory.json')); print(any('credential-liveness-probe' in str(x) for x in s.get('services', s)))"` returns `True`. Workspace runbook §Common Issues references the new auto-surface.

**Prompt**: [tasks/WP05-doc-updates.md](./tasks/WP05-doc-updates.md) (~250 lines)

**Included subtasks**:

- [ ] T023 Update `docs/design/architecture/data/service-inventory.json` with a new entry for the liveness-probe systemd service (WP05)
- [ ] T024 Update `docs/runbooks/google-workspace-ops.md` §Common Issues "Refresh token expired (Testing-app 7-day cycle)" to mention the new automatic-detection surface (GH issue within 6h) (WP05)
- [ ] T025 Consult `docs/design/architecture/data/signal-to-doc-map.json` (per CLAUDE.md "Discovery aid for spec/plan agents") and update any additional doc surfaces it flags as `doc_targets` for change-classes `systemd-unit-added-or-modified` / `service-added-or-modified` / `runbook-modified` (WP05)

**Dependencies**: WP04 (doc references unit names/paths defined there).

**Parallel opportunities**: None.

**Risks**:
- Stale or inconsistent service-inventory references — keep the new entry consistent with the actual unit names from WP04.
- JSON validity after the edit.
- Forgetting a doc surface that `signal-to-doc-map.json` flags — must consult the map per the CLAUDE.md directive.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | LivenessProbeConfig dataclass | WP01 |  |
| T002 | Extend Credential dataclass | WP01 |  |
| T003 | Manifest parser update + validation | WP01 |  |
| T004 | Update credential-manifest.json | WP01 |  |
| T005 | Tests for new manifest parsing | WP01 |  |
| T006 | liveness.py skeleton + LivenessResult | WP02 | [P] |
| T007 | probe_oauth_liveness happy-path | WP02 |  |
| T008 | invalid_grant detection + classification | WP02 |  |
| T009 | Probe-error branches | WP02 |  |
| T010 | Structured INFO logging | WP02 |  |
| T011 | test_liveness.py — 13 contract test cases | WP02 |  |
| T012 | Coverage gate verification | WP02 |  |
| T013 | _process_liveness_alert function | WP03 |  |
| T014 | run_cycle integration + liveness_only kwarg | WP03 |  |
| T015 | CycleResult.liveness_alerts_filed | WP03 |  |
| T016 | --liveness-only CLI flag | WP03 |  |
| T017 | --list --liveness extension | WP03 |  |
| T018 | Orchestrator + listing tests | WP03 |  |
| T019 | systemd .service unit | WP04 |  |
| T020 | systemd .timer unit | WP04 |  |
| T021 | deploy/credential-liveness-probe.sh | WP04 |  |
| T022 | chmod +x on deploy script | WP04 |  |
| T023 | service-inventory.json entry | WP05 |  |
| T024 | workspace runbook §Common Issues update | WP05 |  |
| T025 | signal-to-doc-map.json consult + extras | WP05 |  |

`[P]` flag on T006: WP02 starts with a parallel opportunity against WP01 (different files).

## Sequencing graph

```
       WP01 ─┐
              ├──► WP03 ──► WP04 ──► WP05
       WP02 ─┘
```

Critical path: max(WP01, WP02) + WP03 + WP04 + WP05 = 4 sequential stages.

## Risks (mission-level)

- **Test isolation**: WP02 tests must NOT call real `gog`. Mocking discipline per the contract.
- **Manifest schema drift**: if WP01's manifest edit reaches main without the parser update, manifest-quality validation breaks. The single-mission merge ensures they land together.
- **Dedup title format consistency**: WP03's exact prefix strings must match across the file_alert call site and the dedup_check call site. Test asserts the exact strings.
- **Deploy ordering**: WP04's deploy script smoke-tests the CLI from WP03. After merge to main, operator runs deploy script. This is a manual one-shot post-merge.
- **Phone-recovery acceptance (SC-11)**: Operator-owned. Mission doesn't close until Kent tests on his phone. May reveal `gog-reauth.sh` UX tweaks — fold into the same mission's diff (see Future Work in spec.md re: timing).

## Next command

After all WPs are merged + the deploy script runs on office2, the operator (Kent) executes SC-11 phone test. Mission closes when SC-11 passes.

Suggested next:

- `/spec-kitty.analyze` (optional quality gate to check spec/plan/task consistency before implementation)
- `/spec-kitty.implement WP01` and `/spec-kitty.implement WP02` (parallel) to start the functional core.
