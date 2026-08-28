# Implementation Plan: Crontab Backup Coverage

**Branch**: `feat/crontab-backup-coverage` | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)
**Input**: Issue #895 + verified pre-spec investigation (comment 5446708916)

## Summary

Make the `claude` crontab recoverable from backup without depending on a
security-monitor artifact, make the daily agent-drift check observable, and warn
operators before the rebaseline step that destroys host state.

The approach is deliberately *additive*: a new capture component writes the
crontab into `/data/services/`, which the backup already covers. Nothing about
the backup — its source set, schedule, retention, or script — is touched. That
choice is forced by C-002 (a fifth source path would split the restic snapshot
path-group and permanently freeze the existing 17 snapshots from pruning) and by
C-004 (`restic-backup.sh` is root-owned and hand-deployed, so editing it would
reintroduce a manual sudo step — #903).

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; no `python` binary)
**Primary Dependencies**: standard library only — `subprocess`, `json`, `pathlib`, `tempfile`, `os`, `argparse`. No new third-party package, so the supply-chain review below is a no-op by construction.
**Storage**: Flat files on office2 — a captured crontab artifact plus a JSON freshness pointer, both under `/data/services/`. No database.
**Testing**: `pytest` under `tests/office2/crontab_capture/`, with `crontab -l` injected as a callable so tests never touch a real crontab. Existing suite floor is 6177 passing; the mission must not land below it.
**Target Platform**: Ubuntu 24.04 LTS (office2), systemd user session for the `claude` account (`Linger=yes`, 15 user timers already active)
**Project Type**: single
**Performance Goals**: capture completes in under 5 seconds; under 100 KB added per snapshot (NFR-005)
**Constraints**: unprivileged (`claude` only, no sudo); no change to the restic source set; `audited-surfaces.json` `rebaseline_command` byte-unchanged; deploy via the `deploys/queued/` manifest pipeline
**Scale/Scope**: one host, one crontab (~6 lines / ~1 KB), one daily-cadence component registered for health

### Supply-chain posture

The plan adds, upgrades, and removes **zero** dependencies in every ecosystem.
Everything is Python standard library plus `crontab` and `systemctl`, both
already present and already relied on by shipped components. There is therefore
no registry-authenticity, package-freshness, or lifecycle-script decision to
make. Recording this explicitly rather than leaving it silent, per the
directive: silence is not compliance.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Verdict | Evidence |
|---|---|---|
| Change-Risk Taxonomy (Tier Protocol) | **Pass — Tier 3** | Installs a systemd user timer and a stdlib helper; touches no host/foundational surface, no connectivity fabric, and no backup/DB/service config. Matches `deploys/applied/0018-habits-weekly-driver.yaml` (user-timer install, Tier 3). Spec C-006 amended from Tier 2 during planning, because the filed issue assumed a backup-configuration change that C-002 forbids. A restic-recency pre-check is still run voluntarily. |
| Rebaseline Obligation (#557) | **Pass — declared** | Enabling a new user timer drifts `systemd-user-units.txt` and `systemd-user-unit-contents.txt`. Both changes carry a repo-file signal (the unit files are tracked), so felix-deployer's observe-range auto-rebaseline covers them and `expected_baselines` is **not** declared — per the explicit precedent in `deploys/applied/0020-openclaw-ecosystem-update-check.yaml`. |
| Deployment Constraints | **Pass** | Host-path installs ride `deploys/queued/crontab-capture.yaml` + `scripts/deploy/deploy-crontab-capture.py`. Helper and inventory changes ride the shared checkout (self-pull) and correctly need no manifest. |
| Design-time discipline (Directive 6) | **Pass** | The whole capture is deterministic and mechanically verifiable; it is a helper script with no agent turn anywhere in the path. |
| 024-locality-of-change | **Pass** | Three separable concerns, each confined to its own surface; no shared-file contention between them. |
| 025-boy-scout-rule | **Applied** | `security-baseline-ops.md:176` documents "14 baseline files" while the registry and the live host both say 15 (stale since #818). Fixed in passing, in a file IC-01 already edits. |
| 034-test-first-development | **Pass** | Each behavioural requirement gets a failing test before implementation; see Testing Strategy. |
| 030-test-and-typecheck-quality-gate | **Pass** | `make test` + `validate_docs.py` + `validate_architecture_data.py --strict` must be green; suite floor 6177. |

## Project Structure

### Documentation (this mission)

```
kitty-specs/crontab-backup-coverage-01M12V87/
├── spec.md
├── plan.md              # this file
├── research.md
├── data-model.md
├── quickstart.md
└── checklists/requirements.md
```

### Source Code (repository root)

```
scripts/office2/
├── crontab_capture.py            # NEW — the capture helper (system pipeline)
├── crontab-capture.service       # NEW — systemd user unit
└── crontab-capture.timer         # NEW — hourly, Persistent=true

scripts/deploy/
└── deploy-crontab-capture.py     # NEW — manifest entrypoint (--dry-run/--apply)

deploys/queued/
└── crontab-capture.yaml          # NEW — manifest

scripts/openclaw/enforcement/
└── drift_check.py                # MODIFIED — emit a durable freshness pointer

docs/design/architecture/data/
└── service-inventory.json        # MODIFIED — register both components

docs/runbooks/
├── security-baseline-ops.md      # MODIFIED — FR-007 warning + stale count fix
└── governance/post-change-verification.md   # MODIFIED — FR-007 warning

CLAUDE.md                         # MODIFIED — FR-007 warning at the rm

tests/office2/crontab_capture/    # NEW — unit tests
```

## Key design decisions

### Why a systemd user timer, not a sixth cron job

`Linger=yes` for `claude` and 15 user timers already run on office2; the crontab
holds only the five legacy jobs that #890 exists to retire. Adding a sixth would
enlarge the exact surface that issue is about. A timer is also tracked in the
repo, installable through the manifest pipeline, and supports `Persistent=true`
so a run missed while the host is down executes on the next boot — cron silently
skips it.

This has a second-order consequence worth stating plainly, because it **revises
the sequencing rationale recorded in the pre-spec investigation**: with a timer,
this mission performs *no crontab edit at all*. The original C→A→B argument was
"a crontab edit drifts `crontabs.txt`, which invites the rebaseline whose `rm`
destroys the only copy". That specific trigger no longer applies. The ordering
still holds, for a narrower and still-real reason: this mission's own deploy
drifts the systemd baselines and therefore invites a rebaseline, and until the
capture lands, `crontabs.txt` remains the only copy of the crontab. The warning
must precede the deploy that provokes the reset.

### Why `/data/services/host-state/`, not `/data/services/backup/`

Both are inside the backup's existing source set, so either satisfies C-002. The
backup service directory is rejected because its `scripts/` and `state/`
subdirectories are `root:root` while this component runs as `claude` — mixing
ownership inside one service directory is the confusion that produced the #899
privilege-escalation finding. A separate directory also keeps the ownership
boundary legible: the backup *consumes* this artifact, it does not produce it.

### Why hourly capture, when the backup is daily

The snapshot copy refreshes only once per backup cycle regardless of capture
cadence, so hourly does not improve *restore-from-backup* freshness. It improves
the **primary** recovery path: the live artifact under `/data/`, which is on a
different tree from `/home/claude` and would have survived the 2026-08-27
deletion intact. Hourly makes that copy at most one hour stale, and costs
nothing because the capture rewrites the artifact only when the content changed.
`max_age_seconds` is set to twice the interval (7200), matching the established
convention for sub-hourly and hourly components.

### Why FR-006 is not merely a JSON edit

`drift_check.py` writes no state file; its only trace is `/tmp/drift-check.log`,
which `systemd-tmpfiles --remove --boot` empties at every boot. It therefore has
nothing a health check could honestly read. Two independent gates confirm a
`/tmp` probe is not an option: `tests/canary/test_inventory_health_checks.py:131`
pins the set of components probing `/tmp` (only `obsidian-sync-heartbeat` is
grandfathered, owned by #894), and the same file restricts `max_age_seconds` to
pointer methods. So the component must first emit a durable pointer; only then
can it be registered with a check that can actually fail.

## Complexity Tracking

*No Charter Check violations. Table omitted.*

## Testing Strategy

| Requirement | Test |
|---|---|
| FR-001 / FR-003 | Capture writes an artifact byte-identical to the injected `crontab -l` output, reinstallable as-is. |
| FR-004 | Given an empty or error-exit `crontab -l`, the prior artifact is preserved unchanged and the run reports the anomaly. |
| FR-005 | The freshness pointer is written on success and carries a failure signal on failure; explicit-error fields are set so the canary's `_explicit_error` path trips. |
| NFR-003 | Two consecutive runs over unchanged input leave the artifact's content and mtime untouched while refreshing the pointer. |
| Atomicity | A simulated write failure leaves no partial artifact and no partial pointer (tmp + `os.replace`). |
| Inventory | The two new/changed entries pass `validate_architecture_data.py --strict` and `tests/canary/test_inventory_health_checks.py`. |
| Manifest | `python3 -m scripts.deploy.lib.manifest validate_manifest_file deploys/queued/crontab-capture.yaml` passes locally — CI does **not** validate queued manifests (the #891 gap), so this is run by hand before merge. |

## Implementation Concern Map

### IC-01 — Rebaseline destructive-step warning

- **Purpose**: Warn the operator, at every place the destructive rebaseline is documented as a human action, that baselines may hold the only copy of host state.
- **Relevant requirements**: FR-007, C-001, C-005
- **Affected surfaces**: `docs/runbooks/security-baseline-ops.md` (manual-reset procedure, ~line 172), `docs/runbooks/governance/post-change-verification.md:93`, `CLAUDE.md:368`. Also the stale "14 baseline files" → 15 at `security-baseline-ops.md:176`.
- **Sequencing/depends-on**: none — must land first.
- **Risks**: The `rebaseline_command` string in `audited-surfaces.json` must not be touched (C-001) — it is parsed at `rebaseline.py:585-586`, which asserts the first token is `rm` and otherwise degrades every deferred-confirm audit to inconclusive. The occurrences in `docs/diagnostics/**` and `kitty-specs/**` are frozen historical records and are explicitly out of scope; `kitty-specs/` is additionally write-prohibited.

### IC-02 — Crontab capture component

- **Purpose**: Write the `claude` crontab into already-backed-up storage on a schedule, safely, with an observable health signal.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-005; NFR-001, NFR-002, NFR-003, NFR-005; C-002, C-003, C-004
- **Affected surfaces**: `scripts/office2/crontab_capture.py`, `scripts/office2/crontab-capture.{service,timer}`, `scripts/deploy/deploy-crontab-capture.py`, `deploys/queued/crontab-capture.yaml`, `docs/design/architecture/data/service-inventory.json`, `tests/office2/crontab_capture/`
- **Sequencing/depends-on**: IC-01
- **Risks**: The helper must honour the repo's helper conventions (argparse, exit codes 0/1/2, `SUMMARY:` final line, `INFO:`/`WARN:` prefixes, errors to stderr, atomic tmp+`os.replace` writes). The inventory entry must use a pointer method with an absolute `state_path` and an integer `max_age_seconds`, or the canary data-guard test fails. The manifest's `notes` must stay under 2000 characters — exceeding it lets the entrypoint's side effects land and then blocks the applied record, re-applying every 5-minute tick (#891, and #901 for the underlying ordering defect).

### IC-03 — Drift-check observability and registration

- **Purpose**: Give the daily agent-drift check a durable freshness signal and register it so its stall or disappearance is reported.
- **Relevant requirements**: FR-006, NFR-004
- **Affected surfaces**: `scripts/openclaw/enforcement/drift_check.py`, `docs/design/architecture/data/service-inventory.json`
- **Sequencing/depends-on**: IC-01 (ordering discipline only; no technical dependency on IC-02)
- **Risks**: Must not alter the existing crontab entry (C-003, and the whole point of C-005). The pointer belongs under `/data/services/openclaw/state/enforcement/`, following the established per-component state-directory convention — not `/tmp`. `max_age_seconds` sized as the 24h cycle plus slack, mirroring `security-monitor`'s 108000.

## Branch contract (restated)

- Current branch at plan start: `feat/crontab-backup-coverage`
- Planning/base branch: `feat/crontab-backup-coverage`
- Final merge target for this mission: `feat/crontab-backup-coverage`
- `branch_matches_target`: **true**
- `feat/crontab-backup-coverage → main` is a separate, manual step taken after the mandatory post-merge review.
