# Implementation Plan: Suppress expected drift alerts during rebaseline

**Branch**: `fix/862-drift-alert-rebaseline-suppression` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/drift-alert-rebaseline-suppression-01KY7GZZ/spec.md`
**Source issue**: kentonium3/kg-automation#862

## Summary

The security-monitor audit (`scripts/office2/security-monitor/audit.sh`) pages on
any baseline drift with zero awareness of felix-deployer's deferred-confirm
rebaseline. When an audited-surface deploy lands within the audit window, the audit
fires a false `error` page for drift felix-deployer has already recorded as expected.

**Approach**: add a small, tested Python helper that reads felix-deployer's
pending-rebaseline token (`rebaseline-pending.json`) and, reusing felix-deployer's
own `read_token` + `MAX_AGE_SECONDS` staleness definition, returns the set of
baselines with **fresh, expected** in-flight drift. `audit.sh` calls this helper
**once per run** to load that set into a shell variable; `check_baseline()` then
withholds the *push* for a drifted baseline that is in the set (while still writing
the audit log and `drift-events.jsonl`), and pages exactly as today for every other
drift. The coupling is one-directional and read-only. Fail-safe by construction:
any error, missing/stale token, or unreadable state yields an **empty** set → the
audit alerts exactly as it does today.

## Technical Context

**Language/Version**: Python 3 (office2 is python3-only — no `python` binary) for the
helper; Bash for the `audit.sh` integration.
**Primary Dependencies**: Reuses `scripts/deploy/felix-deployer/rebaseline.py`
(`read_token`, `MAX_AGE_SECONDS`) as the single source of truth for token schema and
staleness. Standard library only (`json`, `datetime`, `pathlib`).
**Storage**: Reads (never writes) `/data/services/felix-deployer/state/rebaseline-pending.json`.
**Testing**: `pytest` unit tests for the helper (token present/fresh/stale/absent/
malformed; membership; empty-on-error). Bash integration verified by a live office2
round-trip during deploy (SC-001/002/003).
**Target Platform**: office2 (Ubuntu 24.04). Helper lives in the checkout at
`/home/claude/kg-automation/...`; `audit.sh` invokes it by absolute path, matching the
existing pattern where `audit.sh` already sources
`/home/claude/kg-automation/scripts/common/alert_bus.sh`.
**Project Type**: single (scripts + tests in the kg-automation repo).
**Performance Goals**: One Python subprocess per audit run (NFR-001: ≤100 ms added).
NOT per baseline — the helper returns the whole expected set in one call.
**Constraints**: read-only cross-subsystem coupling (C-001); reuse felix-deployer's
token schema + staleness (C-002); deterministic decision as a tested helper (C-003);
deploy via manifest, `audited_surface: false` (audit.sh matches no audited pattern).
**Scale/Scope**: ~15 baselines per audit run; token normally clears within ~10 s.

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23)

- `/data/services/felix-deployer/state/` is `claude:claude`, mode `drwxrwxr-x`
  (traversable + readable by the `claude` user). The audit runs via `sg docker -c`
  as the **claude user** (group changes to docker; user stays claude), so it can
  read the `0600 claude`-owned token. **No permission barrier.**
- Checkout present at `/home/claude/kg-automation/scripts/deploy/felix-deployer/rebaseline.py`.
- Deployed audit copy at `/data/services/security-monitor/scripts/audit.sh`
  (`claude:claude`, executable) — re-synced via the canonical
  `scripts/deploy/deploy-security-monitor-audit.py` (precedent: applied manifest
  `0022-systemd-unit-content-baseline.yaml`).
- `audit.sh` is **not** an audited surface (`scripts/office2/security-monitor/*.sh`
  matches no pattern in `audited-surfaces.json`) → **rebaseline not required**.

## Charter Check

*GATE: passed (compact charter context; no blocking directives surfaced).*

- **DIR-006 (deterministic-where-possible)**: the suppress/alert decision is fully
  deterministic → routed into a tested Python helper, not agent judgment. ✅
- **DIR-014 (documentation-synchronization)**: FR-007 requires updating the security
  posture / observability-and-alerting narratives and any affected machine-readable
  data describing the coupling. ✅ (covered in IC-03)
- **DIR-015 (probe real environment during design)**: office2 probe completed above. ✅
- **Engineering principle — single source of truth**: the helper reuses
  felix-deployer's `read_token` + `MAX_AGE_SECONDS` rather than reparsing/redefining
  "expected" or "stale" (C-002). ✅
- **Guardrail preference / fail-safe**: ambiguity resolves toward alerting; the
  security-detection channel never loses a true positive (NFR-003). ✅

## Project Structure

### Documentation (this mission)

```
kitty-specs/drift-alert-rebaseline-suppression-01KY7GZZ/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # /spec-kitty.tasks output (NOT created here)
```

### Source Code (repository root)

```
scripts/
  deploy/
    felix-deployer/
      rebaseline.py            # EXISTING — reused (read_token, MAX_AGE_SECONDS)
      expected_drift.py        # NEW — the query helper (reads token → fresh expected set)
  office2/
    security-monitor/
      audit.sh                 # MODIFIED — one helper call per run + per-baseline suppress
tests/
  deploy/ (or scripts/deploy/felix-deployer/tests/)
      test_expected_drift.py   # NEW — unit tests for the helper
deploys/
  queued/
    drift-alert-rebaseline-suppression.yaml   # NEW — Tier-3 manifest, audited_surface: false
docs/design/architecture/
  security-posture… / observability-and-alerting…  # MODIFIED per FR-007 (+ any data/*.json)
```

**Structure Decision**: Single-project layout. The new helper is co-located with
`rebaseline.py` under `scripts/deploy/felix-deployer/` so it can `import rebaseline`
directly (same directory → no cross-package path gymnastics) and reuse its token
reader + staleness constant. `audit.sh` (the consumer) invokes the helper by absolute
checkout path, consistent with how it already sources `alert_bus.sh`.

## Implementation Concern Map

### IC-01 — Expected-drift query helper (deterministic core)

- **Purpose**: Given the live felix-deployer state, return the set of baseline names
  with fresh, expected in-flight drift — the single deterministic decision point.
- **Relevant requirements**: FR-001, FR-002, FR-004, FR-005; NFR-001, NFR-002;
  C-001, C-002, C-003.
- **Affected surfaces**: `scripts/deploy/felix-deployer/expected_drift.py` (new);
  imports `rebaseline.read_token` + `rebaseline.MAX_AGE_SECONDS`.
- **Sequencing/depends-on**: none.
- **Behavior contract**: `--list` prints the space-separated expected-baseline set to
  stdout (empty when: no token / unreadable / malformed / stale [age > MAX_AGE_SECONDS]).
  Exit 0 always (never fails the caller). Read-only. A `is_expected(name)` mode may be
  provided but the run-once `--list` path is what `audit.sh` uses (NFR-001).
- **Risks**: importing `rebaseline` pulls its `audited_surfaces` import — wrap in
  try/except so any import failure degrades to an empty set (fail-safe), never raises.

### IC-02 — audit.sh integration (per-baseline suppression at the alert boundary)

- **Purpose**: Consult the expected set and withhold the push for expected baselines
  only, preserving all other alerting including non-baseline IOC alerts.
- **Relevant requirements**: FR-003, FR-006; NFR-003.
- **Affected surfaces**: `scripts/office2/security-monitor/audit.sh` — load the set
  once (`EXPECTED_DRIFT=$(python3 <helper> --list 2>/dev/null || true)`); in
  `check_baseline()`, when a diff is found and `$name` ∈ `$EXPECTED_DRIFT`, still
  `log` + `emit_drift_event` but **skip** `alert` (so `ALERT` is not set for that
  baseline → no push if nothing else alerts).
- **Sequencing/depends-on**: IC-01.
- **Risks**: (a) suppression MUST be scoped to the `check_baseline` drift path only —
  the generic `alert()` used for IOCs (`/tmp/pglog`, sysmon, `/etc/hosts`) must NEVER
  be suppressed. (b) word-boundary membership test (avoid substring false-matches
  between baseline names). (c) helper-call failure → empty var → today's behavior.

### IC-03 — Deploy + documentation sync

- **Purpose**: Ship the audit.sh change to office2 through the manifest discipline and
  record the new coupling in architecture docs.
- **Relevant requirements**: FR-007; C-004.
- **Affected surfaces**: `deploys/queued/drift-alert-rebaseline-suppression.yaml`
  (entrypoint `scripts/deploy/deploy-security-monitor-audit.py`, tier 3,
  `audited_surface: false`, mirroring `0022`); the new helper deploys via
  felix-deployer's self-pull (checkout-resident, no separate copy);
  `docs/design/architecture/` security-posture + observability-and-alerting narratives
  (+ any affected `data/*.json`) describing the read-only audit↔felix-deployer coupling
  and its fail-safe rules.
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: live-verify (SC-001/002/003) requires a real or simulated in-flight token
  — plan the verification to inject a synthetic pending token on office2 (read-only to
  felix-deployer; the audit only reads it) rather than waiting for an organic deploy.
```
