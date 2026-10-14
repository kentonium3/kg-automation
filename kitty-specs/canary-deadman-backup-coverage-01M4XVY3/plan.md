# Implementation Plan: Canary dead-man's switch and backup coverage in felix-health-check

**Branch**: `fix/canary-deadman-backup-coverage` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/canary-deadman-backup-coverage-01M4XVY3/spec.md`

**Branch contract**: planning base = merge target = `fix/canary-deadman-backup-coverage` (cut from `main` at `d35a7538`; single topology, no coordination branch). The mission consolidates into this branch. After the mandatory post-merge Codex review, `fix/canary-deadman-backup-coverage` is merged into `main` by hand. felix-deployer then applies the manifest.

**Planning questions**: minimized on Kent's instruction ("proceed with #1063 on your own", 2026-10-14; decision `DM-01M4XVYKP0998SAA02GFY4F16M`). Every design choice below is recorded with its rationale and alternatives in [research.md](research.md), so the post-plan reviewers (paula-patterns, debugger-debbie, Codex) can challenge it.

## Summary

The health check gains two **coverage checks**: is the canary ticking, and is the backup healthy? Each one is evaluated by calling the canary's own per-component evaluation, `scripts.canary.health.evaluate`, on that component's `service-inventory.json` declaration. The health check therefore holds no copy of any bound, good-set or freshness rule; it *observes* through the canary's code, independent of the canary's *process*. A coverage failure folds into the existing `FAILURES_DETECTED` verdict, and an inability to evaluate folds into `UNKNOWN`. Both already alert through the `felix-alert` bus. The run record gains one nested key, `coverage_checks`, chosen so the canary's existing #891 probe of that record is unaffected. The shell script moves into the repo and runs from the checkout. A queued manifest retires the host copy and proves the new coverage live.

## Technical Context

**Language/Version**: Python 3.12 (office2 system `python3`; no venv for this service; the unit runs `/usr/bin/python3 -m scripts.office2.felix_health_check.run`). Bash for the existing service checks.
**Primary Dependencies**: standard library only. In-repo: `scripts.canary.registry` (`load_inventory`, `load_targets`), `scripts.canary.health` (`evaluate`, `HealthResult`) and `scripts.common.alert_bus` (already used). No new third-party dependency (DIRECTIVE_051 supply-chain section: not applicable, nothing is added).
**Storage**: JSON files only. Read: `docs/design/architecture/data/service-inventory.json` (repo checkout), `/data/services/felix-canary/state/last-tick.json`, `/data/services/backup/state/last-backup.json`. Written: `/data/services/openclaw/felix-health-check/last-run.json` (atomic, existing writer).
**Testing**: pytest, offline. Effects are injected (`read_state`, inventory path, script runner, emit). Fixtures are real-shaped: the 2026-10-14 `last-backup.json` and `last-tick.json` are captured verbatim, and the failure shapes are derived from `scripts/office2/restic-backup.sh`'s not-mounted path, not invented. The existing `scripts/office2/felix_health_check/tests/test_run.py` must stay green.
**Target Platform**: office2 (Ubuntu 24.04), `claude` user systemd.
**Project Type**: single repo, scripts layout.
**Performance Goals**: the two coverage checks are local file reads plus one inventory parse, ≤ 5 s added per run (NFR-002). The inventory is ~3,000 lines of JSON, so it parses in milliseconds.
**Constraints**: C-001 reuse, not copy; C-002 observe code, not process; C-003 no new alert channel; C-004 Tier 3 and manifest-deployed. The run record must stay compatible with the canary's #891 probe (FR-006; see the contract).
**Scale/Scope**: about 4 source files, about 3 test files, 1 deploy entrypoint, 1 manifest, and 3–4 doc/data files.

## Charter Check

| Gate (charter) | Status |
|---|---|
| Testing Standards: pytest for non-trivial Python; fixtures mirror real inputs | PASS (planned): real captured pointers; the incident shape is derived from the producer script |
| No dead code before `for_review` | PASS (planned): `coverage.py`'s only caller is `run.py:main`, the live systemd entrypoint |
| Integration verification (no-staging-aware) | PASS (planned): form (a) is a pre-merge, read-only `coverage` dry run against real office2 pointers (`--dry-run` entrypoint over SSH). Form (b) is the post-merge manifest post-check, which reads the live run record. |
| Change-Risk Tier | Tier 3 (scripts, user units unchanged). No Tier 0/1/2 action. |
| Rebaseline obligation | `scripts/office2/deploy/felix-health-check.sh` matches the `systemd-user-units` audited surface → manifest `audited_surface: true`. No deployed unit content changes, so the expected deployer outcome is `cleared_clean` (verified in `rebaseline.py:833–845`). |
| Deploy discipline | `deploys/queued/health-check-coverage.yaml` with an entrypoint, pre (`--dry-run`) and post checks |
| Architecture docs standing directive | service-inventory.json `felix-health-check` entry + `service-inventory.md` + `observability-and-alerting.md` + restic-backup-ops runbook |
| Directive 6 (deterministic vs stochastic) | All deterministic; no LLM involved |

No violations; Complexity Tracking is not needed.

## Project Structure

### Documentation (this mission)

```
kitty-specs/canary-deadman-backup-coverage-01M4XVY3/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── health-check-run-record.md
└── tasks.md             # /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/office2/felix_health_check/
├── run.py                 # MODIFIED: repo script path; coverage folded into verdict/alert/record
├── coverage.py            # NEW: evaluate the coverage components via scripts.canary.health.evaluate
├── health-check.sh        # NEW (moved from ~/helper-scripts on office2, mode 755): header fixed
└── tests/
    ├── test_run.py        # MODIFIED: existing tests kept green, script-path expectations updated
    ├── test_coverage.py   # NEW: verdict branches, fail-closed inability fixtures
    ├── test_agreement.py  # NEW: health check vs canary agree over a document corpus (SC-003)
    └── fixtures/          # NEW: real captured pointers (2026-10-14) + derived failure shapes
scripts/office2/deploy/felix-health-check.sh   # MODIFIED: preflight the repo script path
scripts/deploy/deploy-health-check-coverage.py # NEW: --dry-run / --apply entrypoint
tests/deploy/test_deploy_health_check_coverage.py # NEW
deploys/queued/health-check-coverage.yaml      # NEW manifest
docs/design/architecture/data/service-inventory.json  # felix-health-check entry: coverage + mutual watch
docs/design/architecture/service-inventory.md
docs/design/architecture/observability-and-alerting.md
docs/runbooks/restic-backup-ops.md               # "who tells you backups stopped"
```

**Structure Decision**: the coverage logic sits in the health-check package (`coverage.py`), next to its only caller. The shell script moves into the same package, so the wrapper resolves it relative to `__file__` and never through a host path.

## Implementation Concern Map

### IC-01 — Coverage evaluation through the canary's own path

- **Purpose**: produce one finding per coverage component (`felix-canary`, `restic-backup`) by evaluating that component's inventory declaration with `scripts.canary.health.evaluate`, mapping the canary outcome to the health-check verdict classes, and failing closed on every inability.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, NFR-003, NFR-004, C-001, C-002
- **Affected surfaces**: `scripts/office2/felix_health_check/coverage.py`, its tests and fixtures
- **Sequencing/depends-on**: none
- **Risks**: (1) the `suppressed` outcome, when a declaration's status is not alert-eligible, must not read as healthy; it maps to unknown (research R3). (2) Non-file effects must be refused rather than performed, so the health check never executes an inventory-declared shell command (research R4). (3) A naive-datetime or malformed pointer raises inside the probe; `health.evaluate` already catches that and maps it to unknown. Test it, don't re-wrap it.

### IC-02 — Wrapper integration: verdict, alert, run record, script location

- **Purpose**: fold coverage findings into the one verdict with failure > script-missing > unknown > healthy precedence. List every finding in the alert body, record `coverage_checks` in `last-run.json` without disturbing the #891 probe, run the repo-tracked script, and keep the coverage checks running even when the shell script is missing or times out.
- **Relevant requirements**: FR-004, FR-005, FR-006, FR-007, NFR-003
- **Affected surfaces**: `run.py`, `health-check.sh` (new in repo), `tests/test_run.py`
- **Sequencing/depends-on**: IC-01
- **Risks**: the run record's key namespace is shared with the canary's `_explicit_error` and `TIMESTAMP_KEYS` conventions (see the contract). A top-level `error`, `errors`, `status` or `exit_status` key, or any timestamp key ranked above `ran_at_utc`, would silently change how the canary judges the health check. A coverage-module import failure must become `UNKNOWN`, not a crash; the unit has no `OnFailure=`, though the canary's 13 h freshness probe is the backstop.

### IC-03 — Deploy, retire host copy, live proof

- **Purpose**: a manifest whose entrypoint (dry-run: reports what it would do and evaluates coverage read-only against live pointers; apply: runs the health check once, verifies the live record carries both coverage checks and the repo script path, then moves the host copy out of `~/helper-scripts/` into a dated retired file) plus a `felix-health-check.sh` preflight that points at the repo script.
- **Relevant requirements**: FR-008, FR-009, SC-002, SC-005, C-004
- **Affected surfaces**: `scripts/deploy/deploy-health-check-coverage.py`, `tests/deploy/test_deploy_health_check_coverage.py`, `deploys/queued/health-check-coverage.yaml`, `scripts/office2/deploy/felix-health-check.sh`
- **Sequencing/depends-on**: IC-02
- **Risks**: the apply runs a real health check, so a genuine failure at deploy time alerts Kent. That is correct, but the deploy must still succeed when the verdict is `FAILURES_DETECTED` and must fail only on `UNKNOWN`/`SCRIPT_MISSING` or a record missing coverage. Retire by move, not delete, so it is reversible. Manifest notes must stay ≤ 2000 characters; office2 has no pytest, so there is no pytest pre-check.

### IC-04 — Architecture docs and inventory

- **Purpose**: document the mutual watch and the new coverage in the inventory JSON and its narrative views, and add "what tells you backups stopped" to the backup runbook.
- **Relevant requirements**: FR-010
- **Affected surfaces**: `service-inventory.json` (`felix-health-check` entry `expected`/`note`), `service-inventory.md`, `observability-and-alerting.md`, `restic-backup-ops.md`
- **Sequencing/depends-on**: IC-02 (describe what was built)
- **Risks**: `validate_architecture_data.py` is a blocking gate. The canary reads the `felix-health-check` `health_check` block, so only `expected`/`note` prose changes there; `method`, `endpoint`, `max_age_seconds` and `success_status_values` stay byte-identical.

## Follow-ups (filed, not built — C-005)

- Direct `felix-alert` from `backup.sh` on the "not mounted" path.
- `health-check.sh`'s `is-active` on `felix-core-digest.timer` cannot see a dormant timer (#1062 class). The script gets a comment saying so.
