# Implementation Plan: Backup Integrity Observability

**Branch**: `feat/backup-integrity-observability` | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)
**Input**: #902 (second half), #903, #906

## Summary

Three defects with one shape: a mechanism intended to make failure visible did
not. A prune failure was unrepresentable in the backup's state pointer; the
backup script's repo/host divergence was uncompared; and the crontab recovery
procedure re-implemented header stripping in prose, where it rotted.

The unifying fix is to remove each *unenforced coupling* — the place where two
things had to agree and nothing checked that they did.

The security constraint that shapes everything: `/data/services/backup/scripts/`
must stay non-claude-writable, because it holds a `NOPASSWD` sudo target and a
writable directory on that path is equivalent to `NOPASSWD: ALL`. That was #899,
a real privilege escalation fixed on 2026-08-27. So the pipeline cannot install
`backup.sh`, and #903 resolves as **detection plus a written decision**, not
automation.

## Technical Context

**Language/Version**: Python 3.12 (canary probe, comparator, helper flag) and bash (the backup script itself). office2 is python3-only; a bare `python` exits 127.
**Primary Dependencies**: standard library only — `hashlib`, `json`, `pathlib`, `argparse`, `subprocess`. No dependency is added, upgraded, or removed in any ecosystem, so the supply-chain review below is a no-op by construction.
**Storage**: Flat files — the existing `last-backup.json` state pointer gains a field; the comparator emits its own freshness pointer under `/data/services/`.
**Testing**: `pytest`. Health assertions are driven through the real `scripts.canary.probes.run_probe`, never a reimplementation — a hand-rolled judge would not have caught the defects being fixed. Suite floor is 6216.
**Target Platform**: Ubuntu 24.04 LTS (office2), systemd user session for `claude`, plus one privileged manual install step performed by the operator.
**Project Type**: single
**Performance Goals**: comparator completes in under 5 seconds reading two files (NFR-004).
**Constraints**: `/data/services/backup/scripts/` stays `root:root`; new pointer fields must be readable by the explicit-error scan; exactly one implementation of header stripping.
**Scale/Scope**: one host, one backup script, one crontab artifact, two new/modified health checks.

### Supply-chain posture

Zero dependencies added, upgraded, or removed. Everything is Python standard
library plus `restic`, `crontab`, and `systemctl`, all already present and
already relied upon. Recorded explicitly rather than left silent.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Verdict | Evidence |
|---|---|---|
| Change-Risk Taxonomy | **Pass — Tier 3** | Helper flag, comparator, canary probe extension, docs. The one Tier-2-adjacent artifact (`restic-backup.sh`) is changed only in the repo; installing it is the operator's privileged step, deliberately outside the pipeline per C-002. |
| #899 boundary | **Pass — respected by design** | The plan explicitly rejects making `/data/services/backup/scripts/` claude-writable. Verified live: the directory is `root:root 755` and `touch` as `claude` returns permission denied, while `sudo -n -l` confirms the `NOPASSWD` grant on `backup.sh` is still in place. Both halves of the #899 condition were re-checked rather than assumed. |
| Rebaseline Obligation (#557) | **Pass — declared** | The comparator ships as a systemd user timer, so `scripts/office2/*.{service,timer}` matches the `systemd-user-units` audited surface and carries a repo-file signal; the observe-range auto-rebaseline covers it and `expected_baselines` is not declared. Precedent: `applied/0020`, and confirmed empirically by the #895 deploy on 2026-08-28. |
| Deployment Constraints | **Pass** | Comparator + units ride a `deploys/queued/` manifest. The helper flag and canary change ride the shared checkout (self-pull) and correctly need no manifest. `restic-backup.sh` is the documented exception. |
| Design-time discipline (Directive 6) | **Pass** | Every check here is deterministic; no LLM turn anywhere in the path. |
| 025-boy-scout-rule | **Applied** | The `restic-backup` inventory `expected` prose currently describes only the backup exit code; it is corrected to describe prune as well, since it will no longer be true otherwise. |
| 034-test-first-development | **Pass** | Each behavioural requirement gets a failing test first; SC-005 is itself a test that fails when a coupling is broken. |
| 030-test-and-typecheck-quality-gate | **Pass** | `make test` + `validate_docs.py` + `validate_architecture_data.py --strict`, floor 6216. |

## Project Structure

### Documentation (this mission)

```
kitty-specs/backup-integrity-observability-01M1414D/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
└── checklists/requirements.md
```

### Source Code (repository root)

```
scripts/office2/
├── restic-backup.sh              # MODIFIED — record the prune outcome
├── backup_script_drift.py        # NEW — repo vs deployed comparator
├── backup-script-drift.service   # NEW — systemd user unit
├── backup-script-drift.timer     # NEW — daily
└── crontab_capture.py            # MODIFIED — --emit-body

scripts/canary/
└── probes.py                     # MODIFIED — read prune_exit_code

scripts/deploy/
└── deploy-backup-script-drift.py # NEW — manifest entrypoint

deploys/queued/
└── backup-script-drift.yaml      # NEW — manifest

docs/design/architecture/data/
└── service-inventory.json        # MODIFIED — register comparator; correct restic-backup expected

docs/runbooks/
├── restic-backup-ops.md          # MODIFIED — prune signal + manual-install decision
└── crontab-recovery.md           # NEW — the recovery procedure, where an operator looks

docs/INDEX.md                     # MODIFIED — runbook-added + runbook-modified
docs/DEVELOPER_PORTAL.md          # MODIFIED — runbook-added signal
docs/design/architecture/
├── service-inventory.md          # MODIFIED — comparator entry
├── service-dependencies.view.md  # MODIFIED — comparator node
└── ../felix-capability-roadmap.md # MODIFIED — capability note

tests/office2/                    # NEW/MODIFIED — comparator, emit-body round-trip
tests/canary/                     # MODIFIED — prune failure is unhealthy
```

## Key design decisions

### The prune good-set is `{0}`, and must not mirror `restic_exit_code`

An earlier draft of this plan said the new check "mirrors the existing
`restic_exit_code` handling exactly". That is wrong and dangerous.
`_RESTIC_OK_EXIT_CODES` is `{0, 3}` because a restic *backup* exiting 3 completed
with warnings but still produced a snapshot. For `forget --prune`, 3 carries no
such guarantee — and the backup script already agrees with this, treating only
`PRUNE_RC == 0` as success. Reusing the backup's set would silently accept a
prune that did not apply retention, which is the exact failure being fixed.

Prune success is `{0}`. Tests must cover `0`, `1`, `3`, and `127`, with `3`
asserted **unhealthy** — that is the case a careless implementation gets wrong.

### Why the prune sentinel is `127`, not `null`

`BACKUP_RC` already initialises to `127` with the comment `"not run" sentinel`.
`PRUNE_RC` follows the same convention rather than inventing a second one.

The alternative — `null` when not attempted — was rejected because it reopens the
exact hole being fixed. A script killed between a successful backup and the prune
would write `restic_exit_code: 0` with `prune_exit_code: null`, and since the
explicit-error scan ignores non-integers, that reads **healthy**. A `127` sentinel
reads unhealthy, which is correct: retention did not happen and nobody knows why.

The cost is that a failed backup also reports a failed prune, because the script
exits before pruning. That is double signalling on an already-unhealthy
component, which is acceptable and arguably accurate.

### Why `probes.py` must change rather than reusing an existing key

`_explicit_error` reads exactly seven keys: `restic_exit_code`, `exit_code`,
`exit_status`, `status`, `errors`, `error`, `cycle_error`. A field named
`prune_exit_code` is invisible to it.

Two options were considered. Smuggling the failure into `errors` needs no canary
change, but conflates two distinct facts and makes the pointer less
self-describing. Adding `prune_exit_code` to the scan mirrors the existing
`restic_exit_code` handling exactly, keeps the semantics separate, and lets the
inventory `expected` prose state the truth. The second is chosen; it is a
few lines and only fires when the key is present, so existing components are
unaffected (NFR-002).

### The Tier-2 backup-recency gate stays prune-agnostic

`scripts/deploy/lib/snapshot.py` also reads `last-backup.json`, via
`verify_restic_recent`, to gate Tier-2 deploys on a recent good backup. It uses
key-based `data.get("restic_exit_code")`, so a new field is inert to it —
verified, and that satisfies NFR-002 for the second consumer.

It must **stay** prune-agnostic. A failed prune does not invalidate the snapshot;
the backup is still there and still restorable, which is what a Tier-2 pre-flight
actually needs to know. Wiring prune failure into that gate would block deploys
for a disk-hygiene problem. The asymmetry is deliberate: prune failure makes the
*component* unhealthy (alert the operator) but must not make the *backup*
untrusted (block deploys). Recorded because the obvious next edit for a future
reader is to add it in both places.

### Doc surfaces required by the signal-to-doc map

Queried with `match.change_class` (nested under `match`, not top level):
`service-added-or-modified` and `systemd-unit-added-or-modified` require
`service-inventory.json`, `service-inventory.md`, `service-dependencies.view.md`,
`felix-capability-roadmap.md`, and `audited-surfaces.json`; `runbook-added`
requires `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`; `runbook-modified`
requires `docs/INDEX.md`. `audited-surfaces.json` needs no change — its
`systemd-user-units` surface already matches `scripts/office2/*.{service,timer}`
— and that no-change rationale is recorded rather than the file silently skipped.

Two further change classes apply and were missed on the first pass, caught in
review and confirmed by querying the map: `deploy-manifest-added` requires
`docs/runbooks/deploy/discipline.md` and `scripts/deploy/lib/README.md`;
`office2-service-deployment` requires `discipline.md`,
`docs/runbooks/deploy/office2-deploy-paths.md`, and `service-inventory.json`.
Each gets an update or an explicit no-change rationale.

### The manifest carries `verification.post` even though Tier 3 does not require it

The schema only mandates a `verification` block for Tiers 1 and 2, and the deploy
tests explicitly accept a minimal Tier 3 manifest. That makes "the deploy worked"
too easy to fake: an entrypoint can exit cleanly having installed nothing. The
manifest declares `verification.post` regardless — timer enabled, a concrete next
elapse, and a pointer present with a fail-closed shape.

### The privileged install needs a trusted source, not just a protected target

Both reviewers independently raised this and they are right. The plan protected
the *destination* — `/data/services/backup/scripts/` stays root-owned — but the
draft install command read its *source* from `/home/claude/kg-automation`, a
claude-writable checkout, and installed it as root into a NOPASSWD target.

That is not #899 (the grant is not equivalent to `NOPASSWD: ALL`), but it weakens
the same boundary at the handoff: an unprivileged account can influence what the
operator installs as root. Having reasoned carefully about the destination, I
missed the source — the same shape, one step upstream.

The install procedure therefore verifies before it trusts: the operator checks
the source against a trusted reference (the commit hash they reviewed), installs,
and then confirms what actually landed. The comparator provides the
after-the-fact half of that check independently.

### A pre-existing hole in restic freshness, found by review

Verified through the real probe: a pointer with `restic_exit_code: 0`,
`snapshot_timestamp_utc: null`, and a fresh `script_finished_at_utc` reports
**ok=True, stale=False**. `TIMESTAMP_KEYS` falls through to the next candidate
key, so a run that finished without producing a snapshot reads healthy — while
the inventory's own `expected` prose asserts the snapshot timestamp "must be
non-null".

This predates the mission and is not caused by it, but it is the same defect
class as #902 in the same component, and leaving it would mean shipping "backup
integrity observability" with a hole where a missing snapshot reads fresh. Folded
in as FR-009: freshness fails closed when `restic_exit_code` is present and the
snapshot timestamp is absent, null, or unparseable.

### Why #903 resolves as detection, not automation

Making the deploy pipeline install `backup.sh` requires the applier — running as
`claude` — to write `/data/services/backup/scripts/`. That directory holds a
`NOPASSWD` sudo target. A claude-writable directory on such a path is precisely
#899, where the grant became equivalent to `NOPASSWD: ALL`. Automating this
deploy would re-open a fixed privilege escalation to save a manual step.

So the install stays privileged and manual, and the mission's contribution is to
make divergence *visible* — which is the load-bearing half anyway, since the
current state's safety rests on nobody having made a mistake yet.

A pleasing consequence: the comparator's first real act will be to report drift,
because this mission changes `restic-backup.sh` and the host will not have it
until the operator installs it. The tool proves itself on its own change.

### Why the body emitter, not a corrected pattern

Fixing the stale `grep` re-arms the same trap for the next header change. The
defect is that removal of the header is implemented twice — once in code, once in
prose — with nothing binding them. `--emit-body` reuses `strip_header()`, so
there is one implementation, and SC-005's test fails if a future header change
breaks the round trip.

## Complexity Tracking

*No Charter Check violations. Table omitted.*

## Implementation Concern Map

### IC-01 — Prune outcome recorded and acted upon

- **Purpose**: Make a prune failure representable and consequential.
- **Relevant requirements**: FR-001, FR-002, FR-003; NFR-001, NFR-002; C-003
- **Affected surfaces**: `scripts/office2/restic-backup.sh`, `scripts/canary/probes.py`, `docs/design/architecture/data/service-inventory.json`, `tests/canary/`
- **Sequencing/depends-on**: none
- **Risks**: `probes.py` is shared by every component; the change must be inert when the key is absent. The `restic-backup.sh` edit does not reach the host without the operator's privileged install, so the repo will legitimately lead the host until then.

### IC-02 — Backup script divergence detection

- **Purpose**: Report repo/host divergence for the one script whose correctness the Tier-2 guarantee depends on.
- **Relevant requirements**: FR-004, FR-005, FR-008; NFR-004; C-001, C-002
- **Affected surfaces**: `scripts/office2/backup_script_drift.py`, `scripts/office2/backup-script-drift.{service,timer}`, `scripts/deploy/deploy-backup-script-drift.py`, `deploys/queued/backup-script-drift.yaml`, `service-inventory.json`, `docs/runbooks/restic-backup-ops.md`, `tests/office2/`
- **Sequencing/depends-on**: none technically; reads better after IC-01 since IC-01 is what it will first detect
- **Risks**: An unreadable deployed copy must report **inconclusive**, never match — a comparator that fails open is the defect class it exists to prevent. Must not attempt to remediate: it observes only, and writing to that directory is forbidden by C-001.

### IC-03 — Crontab recovery without a hand-written strip

- **Purpose**: One implementation of header removal, and a recovery procedure where an operator will find it.
- **Relevant requirements**: FR-006, FR-007; NFR-003
- **Affected surfaces**: `scripts/office2/crontab_capture.py`, `docs/runbooks/crontab-recovery.md`, `docs/INDEX.md`, `tests/office2/crontab_capture/`
- **Sequencing/depends-on**: none
- **Risks**: `--emit-body` must not write anything — it is used during recovery, when the artifact must not be disturbed. The round-trip test must assert against the original input, not against the emitter's own output.

## Branch contract (restated)

- Current branch at plan start: `feat/backup-integrity-observability`
- Planning/base branch: `feat/backup-integrity-observability`
- Final merge target for this mission: `feat/backup-integrity-observability`
- `branch_matches_target`: **true**
- `feat → main` is a separate manual step after the mandatory post-merge review.
