# Research: OpenClaw Install and Configuration

**Feature**: 002-openclaw-install-config
**Date**: 2026-03-26

## R-001: OpenClaw Installation Method

**Decision**: Install via `npm install -g openclaw@v2026.3.24` (npm global).

**Rationale**: Official installation method. Simpler than git clone for version pinning and updates. `npm install -g openclaw@v2026.3.24` pins deterministically. The func-spec originally proposed git clone, but npm global is the documented path.

**Alternatives considered**:
- Git clone + build — more control but requires manual build steps, not the official method
- `openclaw@latest` — rejected per constitution (no unpinned versions)

## R-002: Node.js Availability

**Decision**: Use existing Node.js v22.22.1 on office2.

**Rationale**: Already installed, meets OpenClaw's requirement (22.16+). No installation needed.

## R-003: API Key Configuration

**Decision**: Use OpenClaw's SecretRef with `source: "file"` pointing at `/data/services/openclaw/secrets/anthropic`.

**Rationale**: OpenClaw's config supports `SecretRef` objects with three source types: `env`, `file`, and `exec`. The `file` source reads the secret from a file path at runtime without exposing it in the process environment. This is the most secure option and aligns with the constitution's credential security requirements.

**Config pattern**:
```json5
{
  models: {
    providers: {
      anthropic: {
        apiKey: {
          source: "file",
          path: "/data/services/openclaw/secrets/anthropic"
        }
      }
    }
  }
}
```

**Alternatives considered**:
- Environment variable (`ANTHROPIC_API_KEY`) — exposes key in process environment (`/proc/PID/environ`)
- systemd `EnvironmentFile=` — keeps key out of unit file but still in process environment
- Config file inline — key in `openclaw.json`, risk of accidental commit

## R-004: systemd Service Approach

**Decision**: Let `openclaw onboard --install-daemon` create the systemd unit, then capture, adjust, and commit as the canonical artifact at `scripts/openclaw/openclaw.service`.

**Rationale**: The onboarding wizard knows the correct ExecStart command, environment, and dependencies for the installed version. Capturing the generated unit avoids guessing at the correct configuration while giving us full ownership of the result.

**Post-capture adjustments to verify/apply**:
- `User=claude` (ensure it runs as claude, not root)
- `WorkingDirectory` points to correct data path
- Credential loading uses the SecretRef mechanism (not env var injection)
- `Restart=always`, `RestartSec=10` (match vikunja.service pattern)

**Alternatives considered**:
- Manual unit creation from scratch — risk of incorrect ExecStart for npm global binary
- Using `--install-daemon` as-is without capture — no version control, no audit trail

## R-005: OpenClaw Config Location

**Decision**: Config at `~/.openclaw/openclaw.json` (claude user's home: `/home/claude/.openclaw/openclaw.json`).

**Rationale**: This is OpenClaw's default config location. The onboarding wizard creates it. We customize it post-onboard to add the SecretRef file source and workspace path.

## R-006: Gateway Binding

**Decision**: Gateway binds to loopback only (`gateway.bind: "loopback"`).

**Rationale**: OpenClaw's gateway listens on port 18789 by default. Since no external access is needed for F002 (channels come in F003+), binding to loopback prevents any network exposure. This can be adjusted when WhatsApp webhook support is added.

## R-007: Model Selection

**Decision**: Set `primary: "anthropic/claude-sonnet-4-6"` in config. Let OpenClaw resolve the latest Sonnet.

**Rationale**: Per user direction. Anthropic is the default provider in OpenClaw — model can be specified as `anthropic/claude-sonnet-4-6` or just `claude-sonnet-4-6`.

## R-008: Vikunja API Token

**Decision**: Kent generates a persistent API token in Vikunja UI (Settings → API Tokens), names it `openclaw-agent`, and places the raw token value in `/data/services/openclaw/secrets/vikunja-api`.

**Rationale**: Persistent tokens survive Vikunja restarts (unlike session JWTs). Manual generation via UI is appropriate for a one-time setup. The token name provides traceability.

**Verification**: `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info`
