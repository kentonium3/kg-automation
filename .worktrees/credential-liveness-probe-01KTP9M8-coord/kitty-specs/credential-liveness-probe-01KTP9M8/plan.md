# Implementation Plan: Credential Liveness Probe

**Branch**: `kitty/mission-credential-liveness-probe-01KTP9M8` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/credential-liveness-probe-01KTP9M8/spec.md`

## Summary

Adds a 6-hour-cadence liveness probe for `oauth2`-typed credentials. The probe shells out to `gog --account <email> calendar list -j --max-results 1`, parses the result for `invalid_grant`, and classifies any failure as either `dead-routine-7day` (within ±24h of the keyring file mtime + 7 days) or `dead-unexpected`. Failure produces a deduped GitHub issue carrying the exact recovery command (`ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`). The probe is deployed as a separate systemd user timer/service alongside the existing daily `credential-health-check.timer`, so existing signals are untouched. Phone-based recovery via Termius + Tailscale is an acceptance gate.

Closes #572.

## Technical Context

**Language/Version**: Python 3.10+ (system Python on office2 is 3.12; the existing `credential_health_check` package targets 3.10+ syntax via `from __future__ import annotations`).
**Primary Dependencies**: stdlib only — `subprocess`, `dataclasses`, `datetime`, `pathlib`, `typing`, `logging`. Reuses existing `credential_health_check.manifest.Credential`, `github_writer.dedup_check` / `file_alert`. No new third-party packages.
**Storage**: Filesystem — gog keyring at `/home/claude/.config/gogcli/keyring/_gogcli_key_v1_<base64>` (read mtime only; no writes). Credential manifest at `docs/design/architecture/data/credential-manifest.json` (extended with new `liveness_probe` block).
**Testing**: `pytest` with `tmp_path` + `monkeypatch` patterns. Subprocess calls mocked via `monkeypatch.setattr(subprocess, "run", ...)`. Filesystem mtime mocked via `monkeypatch.setattr(pathlib.Path, "stat", ...)` or by writing real test files and freezing time via the existing `--today` CLI override. Coverage gate: `--cov=scripts.security.credential_health_check.liveness --cov-branch --cov-fail-under=90`.
**Target Platform**: Linux server (office2 — Ubuntu 24.04 LTS); runs under systemd user units, claude user. No portability requirements.
**Project Type**: single — the existing `scripts/security/credential_health_check` Python package gains a new submodule.
**Performance Goals**: A single probe call completes in ≤15s (timeout-enforced); a full liveness cycle for all monitored credentials completes in ≤60s wall-clock (NFR-001). Cadence × per-call quota cost is well below Google Calendar API rate limits (NFR-007).
**Constraints**: Token cost zero (deterministic helper, no LLM in probe path). Stdlib only. Manifest schema change is backward-compatible. Probe must not trigger Google account lockout. Recovery command embedded in issues must exactly match the deployed `gog-reauth.sh` path (C-007).
**Scale/Scope**: Single credential monitored at launch (`gog-credentials-keyring` for `kentgale@gmail.com`); schema supports N credentials so future Workspace-internal migration (Option A in `reference_gog_credential_health_gap.md`) doesn't require code changes.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context loaded successfully (no charter file present in `.kittify/charter/`). Section skipped per the runbook: "If the charter file is missing, skip Charter Check and note that it is absent."

Implicit governance gates from CLAUDE.md + Felix Constitution applied:

| Gate | Status | Notes |
|---|---|---|
| Tier classification (change risk) | Pass | Tier 3 (Logic) per C-002. New Python helper + systemd units; no Tier 0/1/2 surfaces. |
| Directive 6 (deterministic vs LLM split) | Pass | Probe is 100% deterministic per C-003. No agent prompts added or modified. |
| Helper invocation form (`-m`) | Pass | CLI invoked via `python3 -m credential_health_check --liveness-only` per C-004. |
| No workarounds for expediency | Pass | Standard `scripts/office2/<unit>.{service,timer}` + `scripts/office2/deploy/<unit>.sh` deploy pattern per C-005. |
| Architecture docs update on service/credential change | Pass | Plan includes `credential-manifest.json` update (FR-014) + `service-inventory.json` update + `signal-to-doc-map.json` consult per Architecture Impact section. |
| Privacy (C-001) | Pass | No vault paths touched. |

## Project Structure

### Documentation (this mission)

```
kitty-specs/credential-liveness-probe-01KTP9M8/
├── spec.md              # Already committed (89b3fc46)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── liveness-result.md
│   ├── manifest-liveness-probe-block.md
│   └── systemd-unit-contract.md
└── tasks.md             # Phase 2 output (NOT created by this command)
```

### Source Code (repository root)

```
scripts/security/credential_health_check/
├── __init__.py                  # unchanged
├── __main__.py                  # MODIFIED: add --liveness-only flag + dispatch
├── cadence.py                   # unchanged
├── github_writer.py             # unchanged (reuse existing dedup_check + file_alert)
├── listing.py                   # MODIFIED: --list --liveness adds oauth2 row
├── liveness.py                  # NEW: probe_oauth_liveness + LivenessResult
├── manifest.py                  # MODIFIED: Credential gains liveness_probe field
├── orchestrator.py              # MODIFIED: add _process_liveness_alert + integrate
├── signals.py                   # unchanged
└── vikunja_writer.py            # unchanged

tests/security/credential_health_check/
├── test_cadence.py              # unchanged
├── test_github_writer.py        # unchanged
├── test_listing.py              # MODIFIED: add --list --liveness coverage
├── test_liveness.py             # NEW: probe_oauth_liveness unit tests
├── test_manifest.py             # MODIFIED: parse new liveness_probe block
├── test_orchestrator.py         # MODIFIED: _process_liveness_alert integration
└── test_signals.py              # unchanged

scripts/office2/
├── credential-liveness-probe.service  # NEW: oneshot unit
├── credential-liveness-probe.timer    # NEW: 6h cadence timer
└── deploy/
    └── credential-liveness-probe.sh   # NEW: idempotent deploy script

docs/design/architecture/data/
├── credential-manifest.json     # MODIFIED: gog-credentials-keyring gains liveness_probe block
└── service-inventory.json       # MODIFIED: new logical service entry for the liveness probe

docs/runbooks/
└── google-workspace-ops.md      # MODIFIED: §Common Issues references the new automatic surface
```

**Structure Decision**: Single-project layout matching the existing `credential_health_check` package shape. The new `liveness.py` submodule sits alongside `cadence.py` / `signals.py` to mirror the existing pattern (one feature per file, public functions imported by the orchestrator).

## Implementation Concern Map

### IC-01 — Liveness probe core

- **Purpose**: Implement the deterministic `probe_oauth_liveness()` function and `LivenessResult` dataclass; this is the pure logic layer with no orchestration or IO-channel concerns.
- **Relevant requirements**: FR-001 through FR-007, FR-019, NFR-001, NFR-002, NFR-003, NFR-004, NFR-005, NFR-007.
- **Affected surfaces**: `scripts/security/credential_health_check/liveness.py` (new), `tests/security/credential_health_check/test_liveness.py` (new).
- **Sequencing/depends-on**: none (foundational).
- **Risks**: Mocking `subprocess.run` + filesystem mtime correctly is essential for deterministic tests. The subprocess timeout boundary (15s) needs an explicit test path. Classification window (±24h) needs round-trip tests at exactly the boundary.

### IC-02 — Manifest schema + Credential dataclass

- **Purpose**: Extend the `Credential` dataclass + manifest parser with the new optional `liveness_probe` block; update the `gog-credentials-keyring` record in `credential-manifest.json` to enable liveness.
- **Relevant requirements**: FR-013, FR-014, NFR-006.
- **Affected surfaces**: `scripts/security/credential_health_check/manifest.py`, `tests/security/credential_health_check/test_manifest.py`, `docs/design/architecture/data/credential-manifest.json`.
- **Sequencing/depends-on**: none (parallel-safe with IC-01).
- **Risks**: Backward-compat: existing manifest readers must continue to work when `liveness_probe` is absent. Schema must remain valid JSON. Cross-reference to `scripts/security/credential_health_check/manifest.py` parser.

### IC-03 — Orchestrator integration + CLI flags

- **Purpose**: Wire `_process_liveness_alert` into `run_cycle`; add `--liveness-only` CLI flag; extend `--list --liveness`; reuse existing `dedup_check` + `file_alert` for GitHub issue surface.
- **Relevant requirements**: FR-008, FR-009, FR-010, FR-011, FR-012, FR-018, FR-019, FR-020.
- **Affected surfaces**: `scripts/security/credential_health_check/orchestrator.py`, `scripts/security/credential_health_check/__main__.py`, `scripts/security/credential_health_check/listing.py`, `tests/security/credential_health_check/test_orchestrator.py`, `tests/security/credential_health_check/test_listing.py`.
- **Sequencing/depends-on**: IC-01, IC-02 (orchestrator imports probe; CLI dispatches; manifest parse provides `liveness_probe` config).
- **Risks**: Dedup title prefix must distinguish `routine-7day` from `unexpected`. Dry-run path must exercise the real probe but suppress the GH write. Coverage gate must pass on the new branches in `orchestrator.py`.

### IC-04 — Systemd units + deploy script

- **Purpose**: Add the new 6h timer + service unit files and an idempotent deploy script mirroring the existing `credential-health-check.sh` pattern.
- **Relevant requirements**: FR-015, FR-016, FR-017, C-005.
- **Affected surfaces**: `scripts/office2/credential-liveness-probe.service` (new), `scripts/office2/credential-liveness-probe.timer` (new), `scripts/office2/deploy/credential-liveness-probe.sh` (new).
- **Sequencing/depends-on**: IC-01, IC-02, IC-03 (deploy script smoke-tests `python3 -m credential_health_check --dry-run --liveness-only`; that command path must exist).
- **Risks**: Timer cadence calendar expression must trigger every 6h with `Persistent=true` so missed firings catch up. Deploy script must be idempotent. Verify `systemctl --user enable --now` succeeds.

### IC-05 — Architecture + runbook doc updates

- **Purpose**: Update `service-inventory.json` + the workspace runbook to point at the new automatic surface; honor the standing CLAUDE.md requirement that every service change updates `docs/design/architecture/data/`.
- **Relevant requirements**: Architecture Impact section in spec.md; implicit governance gate from CLAUDE.md.
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json`, `docs/runbooks/google-workspace-ops.md`.
- **Sequencing/depends-on**: IC-04 (the doc points at the new units).
- **Risks**: Stale or inconsistent service-inventory references. JSON validity. `signal-to-doc-map.json` consult to ensure no doc surface missed.

### IC-06 — Phone-recovery acceptance test

- **Purpose**: Execute the end-to-end phone-based recovery test (FR-021, SC-11) against a real expired-token state. If friction is observed, fold UX tweaks back into `gog-reauth.sh` within this mission.
- **Relevant requirements**: FR-021, SC-11.
- **Affected surfaces**: `scripts/security/gog-reauth.sh` (potential tweaks only; no proactive changes until testing reveals need).
- **Sequencing/depends-on**: IC-01 through IC-05 deployed; mission close blocked until SC-11 passes.
- **Risks**: Token must be in expired state for a real test (can wait for the natural 7-day cycle, or force a re-mint then wait, or revoke at myaccount.google.com/permissions for an unscheduled test). Operator (Kent) owns this acceptance gate.

## Complexity Tracking

No charter violations. Section omitted.

## Architecture Impact

Per the spec's Architecture Impact section, this mission touches change classes `credential-added-or-modified`, `systemd-unit-added-or-modified`, `service-added-or-modified`, and `runbook-modified`. The `docs/design/architecture/data/signal-to-doc-map.json` lookup will be consulted at merge time to confirm all `doc_targets` are addressed.

## Branch Contract (repeated per runbook §Branch Strategy Confirmation)

- Current branch at plan start: `kitty/mission-credential-liveness-probe-01KTP9M8`
- Planning/base branch for this mission: `main`
- Final merge target for completed changes: `main`
- `branch_matches_target`: false (currently on mission coord branch; will be reconciled by the spec-kitty merge command at mission close per rc41 conventions)
