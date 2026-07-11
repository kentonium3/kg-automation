# Implementation Plan: Felix component-health canary registry

**Branch**: `feat/felix-canary-registry` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/felix-canary-registry-01KX8T7B/spec.md`

## Summary

Build a deterministic **health-canary runner** — a sibling scanner to `felix-trust-scan`, sharing the
`scripts/common/alert_bus/` emit library — that on a systemd-timer schedule reads each component's
declared `health_check` directly from `service-inventory.json`, computes the component's `health` per
ADR-0006, gates alerting on the declared `status` (only `active`/`running`; `suspended`-class
suppressed), and emits `stale`/`failed`/`degraded` conditions to the #701 alert bus. Freshness is driven
by a new machine-readable `max_age_seconds` field on `health_check`. The restic backup is the first
concrete canary (#511): its script writes a `last-backup.json` health-pointer and it is registered in the
inventory with a freshness `health_check`.

## Technical Context

**Language/Version**: Python 3.12 (office2 system Python; stdlib-only, matching `scripts/trust/` and `scripts/common/alert_bus/`)
**Primary Dependencies**: `scripts/common/alert_bus/` (#701 emit lib + #706 ledger); `service-inventory.json` as the canary source of truth; standard library `urllib` (http probe), `subprocess` (shell probe), `json`/`datetime` (tick-file freshness). No third-party packages.
**Storage**: JSON/JSONL state files on office2 — a per-run tick-signal (`last-tick.json`) and a dedup-state file under `/data/services/felix-canary/state/`; alerts also flow to the shared alert-bus ledger (#706). No database.
**Testing**: pytest, unit + contract style matching `scripts/trust/` tests; deterministic (no network in unit tests — probes are injected/mocked; a live self-check path validates on office2).
**Target Platform**: office2 (Ubuntu 24.04) as a `systemd --user` timer; runnable locally for tests.
**Project Type**: single (Python package under `scripts/canary/`).
**Performance Goals**: full evaluation pass over all registered components ≤ 30 s (NFR-002); detection latency ≤ one 15-min interval + one delivery attempt (NFR-001).
**Constraints**: no LLM in the hot path (NFR-003, 0 tokens); single-component probe failure never aborts the pass (NFR-004); every computed alert written to the ledger even on delivery failure (NFR-005); canaries derived from the inventory only, no separate `canaries.json` (C-001); emit only via the shared bus lib (C-002); vocabulary/gating per ADR-0006 (C-003).
**Scale/Scope**: ~38 inventory entries today (~30 service-type, evaluated; the rest are code records, exempt).

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Project charter context is **compact / minimal**; no org-charter packs present (`org_charter.present=false`). No charter gates conflict with this plan.
- Governing local doctrine that DOES apply (treated as gates):
  - **ADR-0006** — status-gates-health contract. The plan adopts it verbatim (C-003). ✅
  - **Engineering Principle #8** — suspension as an operational state → suppression by construction (FR-003). ✅
  - **Engineering Principle #6 / Directive 6** — deterministic work in scripts, no LLM in the hot path (FR-009/NFR-003). ✅
  - **coherence/doctrine.md INV-003** — one canonical alert stream; emit only via the #701 bus (C-002). ✅
  - **No silent fallback (INV-002)** — coverage gaps and unknowns are surfaced, never dropped (FR-006). ✅

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-canary-registry-01KX8T7B/
├── plan.md              # this file
├── research.md          # Phase 0 — decisions + rationale
├── data-model.md        # Phase 1 — entities, schema, state transitions
├── contracts/           # Phase 1 — evaluation contract, health_check schema delta, CLI contract
├── quickstart.md        # Phase 1 — run/add-a-canary/deploy/verify
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/canary/
├── __init__.py
├── registry.py          # read service-inventory.json → CanaryTarget set + coverage-gap set
├── probes.py            # http / shell / tick-file freshness probe evaluators → ProbeResult
├── health.py            # ProbeResult → HealthResult per ADR-0006; status-gate
├── dedup.py             # dedup-state read/write; suppress repeat alerts within window
└── run.py               # orchestrator entrypoint: iterate → evaluate → dedup → emit → tick-signal

tests/canary/            # pytest unit + contract tests (registry, probes, health-gate, dedup, run)

scripts/office2/restic-backup.sh                  # + last-backup.json writer (#511)
deploys/queued/00NN-felix-canary-registry.yaml    # systemd timer + unit install manifest
docs/runbooks/canary-registry-ops.md              # ops runbook
docs/design/architecture/data/service-inventory.json  # + max_age_seconds fields; register backup + canary runner
```

> **Test-location note (deploy-gotcha guard):** tests live under `tests/canary/` (repo test root), NOT
> co-located under `scripts/canary/tests/`, to avoid the #701-mission stale-co-located-test class. The
> pre-push `make test` runs the repo test tree; keep all new tests there.

## Implementation Concern Map

Architectural intent decomposed into concerns (IC-##) that `/spec-kitty.tasks` will translate into work
packages. Dependencies noted for lane sequencing.

| IC | Concern | Depends on | Notes |
|----|---------|-----------|-------|
| **IC-01** | `max_age_seconds` schema + freshness fields on `health_check`; validator support | — | Add optional `max_age_seconds` to service-inventory `health_check`; extend `validate_architecture_data.py` to accept/validate it. Foundation for freshness probes. |
| **IC-02** | Canary registry loader (`registry.py`) | IC-01 | Read inventory → yield CanaryTarget for each service-type entry; classify alert-eligibility by `status` (ADR-0006); emit coverage-gap set for active/running entries lacking usable `health_check` (FR-006). |
| **IC-03** | Probe evaluators + health computation (`probes.py` + `health.py`) | IC-01 | http/shell/tick-file probes → ProbeResult; `health.py` maps to HealthResult (healthy/stale/failed/degraded/unknown) per ADR-0006; applies status-gate. Pure/deterministic, unit-tested with injected inputs. |
| **IC-04** | Runner orchestration (`run.py` + `dedup.py`) | IC-02, IC-03 | Iterate targets → evaluate → dedup within window → emit stale/failed/degraded via `alert_bus` → write tick-signal + per-component ledger (FR-004/005/008); fail-safe per NFR-004; CLI `--once`/`--dry-run`/`--self-check`. |
| **IC-05** | Restic backup health-pointer + registration (#511) | IC-01 | `restic-backup.sh` writes `last-backup.json` (authoritative `snapshot_timestamp_utc` from `restic snapshots --latest 1 --json`, atomic .tmp+mv); register backup in inventory with freshness `health_check` + `max_age_seconds` (28h). First real canary (FR-007, SC-005). |
| **IC-06** | Deploy: systemd timer + manifest + self-observability | IC-04, IC-05 | `deploys/queued/00NN-*.yaml` installs the `felix-canary` service+timer (15-min); `OnFailure=` hook emits via the alert-bus shim (out-of-band crash alert); register the runner itself in inventory (FR-010). Rebaseline required (systemd unit audited). |
| **IC-07** | Docs + coherence | IC-04, IC-05, IC-06 | Runbook `canary-registry-ops.md`; register in INDEX + DEVELOPER_PORTAL; update service-inventory narrative; note the canary registry under coherence INV-003; record decision(s) in coherence/decisions.jsonl. |

## Phase 0: Outline & Research

See [research.md](research.md). Resolves: runner structure (sibling — decided), freshness representation
(`max_age_seconds` — decided), probe-method taxonomy, dedup design, severity mapping, cadence, and the
**self-observability boundary** (how far SC-006 is met without the deferred #269 watchdog).

## Phase 1: Design & Contracts

- [data-model.md](data-model.md) — CanaryTarget, ProbeResult, HealthResult, the `health_check` schema
  delta (`max_age_seconds`), the dedup-state and tick-signal shapes; the health-value state set and the
  status→alert-eligibility gate as invariants.
- [contracts/](contracts/) — the evaluation contract (health_check → HealthResult), the `health_check`
  JSON schema delta, and the `run.py` CLI contract.
- [quickstart.md](quickstart.md) — run locally, add a canary (declare a health_check), deploy to office2,
  verify SC-001…006.

## Branch contract

- Current branch at plan: `feat/felix-canary-registry`
- Planning/base branch: `feat/felix-canary-registry`
- Final merge target: `feat/felix-canary-registry` → (post-merge Codex) → `main`
- `branch_matches_target`: true
