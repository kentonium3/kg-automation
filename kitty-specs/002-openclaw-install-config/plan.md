# Implementation Plan: OpenClaw Install and Configuration

**Branch**: `002-openclaw-install-config` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/002-openclaw-install-config/spec.md`

## Summary

Install OpenClaw v2026.3.24 on office2 via npm global install, configure it to call the Anthropic API directly using a SecretRef file source pointing at `/data/services/openclaw/secrets/anthropic`, set Sonnet as the model, and run it as a systemd service. Establish the credential store pattern for all future features. Kent runs the interactive onboarding wizard; the implementation captures the generated systemd unit as the canonical deployment artifact. Ops runbook and architecture doc updates included.

## Technical Context

**Language/Version**: Node.js 22.22.1 (already on office2), TypeScript (OpenClaw runtime)
**Primary Dependencies**: OpenClaw v2026.3.24 (npm global), Anthropic API (direct)
**Storage**: JSON files managed by OpenClaw at `/data/services/openclaw/data/`; credential files at `/data/services/openclaw/secrets/`
**Testing**: Manual verification against acceptance scenarios
**Target Platform**: Ubuntu 24.04 LTS on office2
**Project Type**: Infrastructure deployment (no application source code)
**Performance Goals**: Service restarts within 30 seconds; API calls direct to Anthropic
**Constraints**: No API proxy, no credentials in code, pinned version, claude user only
**Scale/Scope**: Single user, single server, one service

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| No credentials in code | ✅ Pass | Credential store on office2, SecretRef file source, never committed |
| No third-party API proxy | ✅ Pass | Anthropic API direct via OpenClaw native config |
| Pinned versions | ✅ Pass | `openclaw@v2026.3.24` |
| No community skills | ✅ Pass | No ClawHub skills installed in this feature |
| Linux/office2 target | ✅ Pass | All commands target Ubuntu 24.04 LTS |
| Agent traceability | ✅ Pass | All commands via `ssh office2-claude`; sudo to Kent |
| Privacy boundary | ✅ Pass | No second-brain interaction |
| Documentation adjacent | ✅ Pass | Ops runbook + architecture docs updated |

## Project Structure

### Documentation (this feature)

```
kitty-specs/002-openclaw-install-config/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (NOT created by /spec-kitty.plan)
```

### Source Code (repository root)

```
scripts/openclaw/
├── install.sh           # npm install + directory setup + credential instructions
└── openclaw.service     # Captured systemd unit (from onboard, then adjusted)

docs/handbooks/
└── openclaw-ops.md      # Ops runbook
```

**Structure Decision**: Infrastructure deployment feature. The only committed artifacts are the captured systemd unit, an install helper script, and the runbook. OpenClaw itself is installed globally via npm. Configuration lives at `~/.openclaw/openclaw.json` on office2 (claude user's home). Credentials live at `/data/services/openclaw/secrets/`.

## OpenClaw Configuration Design

### Config file: `/home/claude/.openclaw/openclaw.json`

```json5
{
  // Anthropic API — direct, no proxy
  models: {
    providers: {
      anthropic: {
        apiKey: {
          source: "file",
          path: "/data/services/openclaw/secrets/anthropic"
        }
      }
    }
  },
  // Model selection — let OpenClaw resolve latest Sonnet
  agents: {
    defaults: {
      model: {
        primary: "anthropic/claude-sonnet-4-6"
      },
      workspace: "/data/services/openclaw/data"
    }
  },
  // Gateway — loopback only, no external exposure
  gateway: {
    mode: "local",
    bind: "loopback"
  }
}
```

### Credential store: `/data/services/openclaw/secrets/`

```
/data/services/openclaw/secrets/    (mode 700, owned by claude)
├── anthropic                       (mode 600, raw API key)
└── vikunja-api                     (mode 600, raw Vikunja token)
```

### Data directory: `/data/services/openclaw/data/`

Automatically included in Restic backup (under `/data/services/`).

## Dependency Graph

```
WP-01: Install OpenClaw + credential store + onboarding  (foundation)
  └── WP-02: Configure + capture systemd unit + verify API
  └── WP-03: Vikunja token + connectivity verification
  └── WP-04: Ops runbook + architecture docs + security baseline
  └── WP-05: Acceptance testing
```

WP-01 must complete first. WP-02 depends on WP-01. WP-03 depends on WP-02. WP-04 can start after WP-02. WP-05 runs last.

## Parallel Work Analysis

Not applicable — solo maintainer, sequential implementation. WP-04 (docs) can proceed in parallel with WP-03 after WP-02 completes.
