# Implementation Plan: Vikunja Docker Deploy

**Branch**: `001-vikunja-docker-deploy` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/001-vikunja-docker-deploy/spec.md`

## Summary

Deploy Vikunja as a Docker container on office2 (Ubuntu 24.04 LTS) to serve as the foundational task store and web UI for the personal AI accountability system. The deployment binds to the Tailscale IP (`100.92.197.90:3456`), persists SQLite data to `/data/services/vikunja/data/` (automatically included in existing Restic backups), and is managed by a systemd unit. An idempotent Python setup script creates the project hierarchy, identity labels, and saved filters via the Vikunja REST API. An ops runbook documents all operational procedures.

## Technical Context

**Language/Version**: Python 3.11+ (setup script), Bash (deployment/systemd)
**Primary Dependencies**: Docker (Vikunja image, pinned version), `requests` (Python HTTP client for setup script)
**Storage**: SQLite (managed by Vikunja, persisted at `/data/services/vikunja/data/`)
**Testing**: Manual verification against acceptance scenarios; `validate_docs.py` for runbook
**Target Platform**: Ubuntu 24.04 LTS on office2 (Dell XPS 8700)
**Project Type**: Infrastructure deployment (no application source code)
**Performance Goals**: Web UI loads within 3 seconds via Tailscale; service restarts within 30 seconds
**Constraints**: Tailscale-only access (bind to `100.92.197.90`), pinned image version, no credentials in code, agent uses `ssh office2-claude` only
**Scale/Scope**: Single user, single server, one Docker container

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| No credentials in code | ✅ Pass | Admin password set interactively; setup script uses runtime JWT |
| Tailscale-only access | ✅ Pass | Bound to `100.92.197.90:3456`, never `0.0.0.0` |
| Pinned versions | ✅ Pass | Docker image uses specific version tag |
| Linux/office2 target | ✅ Pass | All scripts target Ubuntu 24.04 LTS |
| PR required | ✅ Pass | All changes via PR to `main` |
| Agent traceability | ✅ Pass | All commands via `ssh office2-claude`; sudo escalated to Kent |
| Privacy boundary | ✅ Pass | No interaction with second-brain or private paths |
| Documentation adjacent | ✅ Pass | Ops runbook created alongside deployment |

## Project Structure

### Documentation (this feature)

```
kitty-specs/001-vikunja-docker-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (NOT created by /spec-kitty.plan)
```

### Source Code (repository root)

```
scripts/vikunja/
├── deploy.sh            # Docker run + systemd unit installation
├── setup_vikunja.py     # Idempotent project/label/filter setup via REST API
└── vikunja.service      # systemd unit file

docs/handbooks/
└── vikunja-ops.md       # Ops runbook
```

**Structure Decision**: This is an infrastructure deployment feature, not an application. Source artifacts are deployment scripts and config committed to `scripts/vikunja/`. No `src/` or `tests/` directories needed. The setup script is a standalone Python script using only the `requests` library.

## Parallel Work Analysis

Not applicable — solo maintainer, sequential implementation.

## Dependency Graph

```
WP-01: Docker deploy + systemd  (foundation — everything depends on this)
  └── WP-02: Setup script (projects, labels, filters via API)
  └── WP-03: Ops runbook + security baseline reset
  └── WP-04: Verification + acceptance testing
```

WP-01 must complete first. WP-02 and WP-03 can proceed in parallel after WP-01. WP-04 runs last.
