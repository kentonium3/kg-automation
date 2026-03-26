---
title: "F002: OpenClaw Install and Configuration"
doc_type: func-spec
status: draft
feature: F002
---

# F002: OpenClaw Install and Configuration

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

Vikunja is running (F001 complete). OpenClaw is the orchestration and
intelligence layer that drives everything else — WhatsApp intake, inbox
processing, heartbeats, and escalation. It must be installed and configured
on office2 before any agent skills can be built. This spec covers installation,
base configuration, Claude API connection, and systemd service management.

Current gaps:
- ❌ OpenClaw not installed on office2
- ❌ No Claude API connection configured
- ❌ No systemd service for always-on operation
- ❌ No credential store structure for agent secrets

This spec delivers a running, always-on OpenClaw instance on office2 connected
to the Anthropic API directly, with the credential store pattern established
for all subsequent features.

---

## Problem Statement

**Current State:**
```
office2
└── ✅ Vikunja running (F001)
└── ❌ OpenClaw not installed
└── ❌ No orchestration engine
└── ❌ No credential store
```

**Target State:**
```
office2
└── ✅ Vikunja running (F001)
└── ✅ OpenClaw installed (pinned version, git clone)
└── ✅ Claude API configured (Anthropic direct — no proxy)
└── ✅ Credential store at /data/services/openclaw/secrets/ (mode 700, claude-owned)
└── ✅ systemd service: openclaw.service (starts on boot, restarts on failure)
└── ✅ Vikunja API token stored in credential store
└── ✅ Baseline persona/onboarding complete
└── ✅ Security audit baseline reset to include new service
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Architecture spec**
   - `docs/design/personal-ai-system-spec-v03.md` Sections 5.1 and 5.2
   - Understand OpenClaw's role: orchestration + intelligence, Vikunja is the store
   - Note: Anthropic API direct — no LiteLLM, no third-party routing

2. **F001 artifacts — understand what's already established**
   - `scripts/vikunja/vikunja.service` — systemd unit pattern to copy for openclaw.service
   - `docs/handbooks/office2-backup-and-security.md` — credential store location,
     `claude` user permissions, security audit baseline reset procedure
   - `docs/handbooks/vikunja-ops.md` — runbook format to match for openclaw-ops.md

3. **OpenClaw documentation**
   - https://openclaw.ai and https://github.com/openclaw/openclaw
   - Identify current stable release version to pin
   - Understand onboarding flow and persona configuration
   - Understand skill directory structure for later features

4. **office2 environment**
   - Confirm Node.js version available (OpenClaw requires Node.js)
   - Confirm pnpm or npm available
   - Check `/data/services/` directory structure established by F001

---

## Functional Requirements

### FR-1: Installation

**What it must do:**
- Install OpenClaw via git clone to `/data/services/openclaw/app/`
- Pin to a specific reviewed release tag — never install from `latest` or
  unreviewed commits
- Install dependencies (pnpm install && pnpm run build)
- Installation owned by `claude` user, consistent with F001 pattern

**Security rules (from constitution directive 2):**
- No community ClawHub skills installed during this feature
- Installation source must be the official openclaw/openclaw GitHub repo
- Pinned version must be recorded in the ops runbook

**Success criteria:**
- [ ] OpenClaw installed at `/data/services/openclaw/app/`
- [ ] Specific version tag recorded in `docs/handbooks/openclaw-ops.md`
- [ ] `claude` user owns all installation files
- [ ] Build completes without errors

---

### FR-2: Credential Store

**What it must do:**
- Establish credential store at `/data/services/openclaw/secrets/`
- Directory mode 700, owned by `claude` user
- Store the following named credential files (mode 600 each):
  - `anthropic` — Anthropic API key
  - `vikunja-api` — Vikunja JWT token for agent use (not the admin password)
- Credential files contain the raw secret value only — no YAML, no JSON
- No credentials committed to the repo under any circumstances

**Pattern note:** This credential store is the foundation for all subsequent
features. F003 will add `whatsapp-meta`, F012 will add `personal-google`.
The pattern established here must be consistent and reusable.

**Success criteria:**
- [ ] `/data/services/openclaw/secrets/` exists, mode 700, owned by `claude`
- [ ] `anthropic` credential file exists, mode 600
- [ ] `vikunja-api` credential file exists, mode 600
- [ ] No credential files or values appear in any committed file
- [ ] `git status` shows no secrets-related files tracked

---

### FR-3: Base Configuration

**What it must do:**
- Configure OpenClaw to use the Anthropic API directly
  (no LiteLLM, no OpenAI-compatible proxy, no third-party routing)
- Set Claude Sonnet as the model
- Point OpenClaw to the credential store for API key resolution
- Configure OpenClaw's data/memory directory at
  `/data/services/openclaw/data/`
- Complete the OpenClaw onboarding/persona setup for Kent's assistant

**Success criteria:**
- [ ] OpenClaw starts and connects to Anthropic API successfully
- [ ] Model confirmed as Claude Sonnet in OpenClaw config
- [ ] No API calls routed through any proxy or third-party endpoint
- [ ] Data directory at `/data/services/openclaw/data/` (included in
  existing Restic backup coverage via `/data/services/`)
- [ ] Onboarding complete — OpenClaw has a functional persona

---

### FR-4: systemd Service

**What it must do:**
- Create `/etc/systemd/system/openclaw.service`
- Service starts on boot, restarts automatically on failure
- Runs as `claude` user
- Follows the same pattern established by `vikunja.service` (F001) and
  `obsidian-sync.service`

**Success criteria:**
- [ ] `systemctl is-active openclaw` returns `active`
- [ ] Service survives a `systemctl restart openclaw`
- [ ] Service starts automatically after simulated reboot
  (`sudo systemctl stop openclaw && sudo systemctl start openclaw`)
- [ ] Service logs accessible via `journalctl -u openclaw`

---

### FR-5: Vikunja API Token

**What it must do:**
- Generate a dedicated Vikunja API token for the `claude` agent user
  (not the admin password, not a session JWT — a persistent API token)
- Store token in `/data/services/openclaw/secrets/vikunja-api` (mode 600)
- Verify OpenClaw can reach Vikunja at `http://100.92.197.90:3456`
  (Tailscale IP established in F001) using this token

**Note:** F001 bound Vikunja to the Tailscale IP. OpenClaw must use the
same IP, not `localhost` or `office2`, since both services run on office2
but the binding is to the Tailscale interface.

**Success criteria:**
- [ ] Vikunja API token generated and stored in credential store
- [ ] OpenClaw can authenticate to Vikunja API using stored token
- [ ] Token is persistent (survives Vikunja container restart)

---

### FR-6: Security Audit Baseline Reset

**What it must do:**
- After OpenClaw service is running, reset the security audit baselines
  to incorporate the new service
- This prevents the daily 3AM audit from generating false-positive alerts
- Follow the procedure documented in `docs/handbooks/office2-backup-and-security.md`

**Success criteria:**
- [ ] Security audit baselines reset after OpenClaw installation
- [ ] Next audit run (or manual test run) produces no alerts for OpenClaw

---

### FR-7: Operations Runbook

**What it must do:**
- Create `docs/handbooks/openclaw-ops.md` covering:
  - Installed version (pinned tag)
  - How to start/stop/restart the OpenClaw service
  - Where credentials live and how to rotate them
  - How to update OpenClaw to a new pinned version
  - How to view logs
  - How to verify Anthropic API connectivity
  - Skill directory location (for future features)

**Success criteria:**
- [ ] Runbook exists at `docs/handbooks/openclaw-ops.md`
- [ ] All topics covered
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F002 changes the deployed system. The following architecture docs must be
updated as part of implementation (not as a separate task — update alongside
the work package that deploys the change).

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add OpenClaw service entry |
| `data/credential-manifest.json` | Move `anthropic` from `planned_credentials` to `credentials`; add `vikunja-api` as active |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add OpenClaw to Running Services table and Deployment Details |
| `credentials-and-secrets.md` | Move `anthropic` and `vikunja-api` from Planned to Active tables |

### No Changes Required

- `network-topology.json` — OpenClaw exposes no new ports
- `physical-topology.md` — No hardware changes
- `data-flows.json` / `data-flows.md` — Data flow changes come in F005–F010
- `backup-and-recovery.md` — OpenClaw data is under `/data/services/`, already covered

### JSON Field Requirements

Set `last_updated` to deployment date and `updated_by` to `"F002"` on each
modified JSON file.

**Success criteria for this section:**
- [ ] `service-inventory.json` includes OpenClaw entry with version, paths, systemd unit
- [ ] `credential-manifest.json` shows `anthropic` and `vikunja-api` as active (not planned)
- [ ] `service-inventory.md` and `credentials-and-secrets.md` match their JSON sources
- [ ] All modified JSON files have `updated_by: "F002"`

---

## Out of Scope

- ❌ WhatsApp integration — F003
- ❌ Whisper transcription skill — F004
- ❌ Vikunja API skill — F005
- ❌ Any OpenClaw skills — F005 onwards
- ❌ Heartbeat/cron configuration — F010
- ❌ Community ClawHub skills — never, per constitution
- ❌ Any LiteLLM or proxy configuration — explicitly prohibited

---

## Success Criteria

**Complete when:**

### Installation
- [ ] OpenClaw installed at pinned version under `/data/services/openclaw/`
- [ ] Owned by `claude` user
- [ ] Build succeeds

### Credential Store
- [ ] `/data/services/openclaw/secrets/` established with correct permissions
- [ ] `anthropic` and `vikunja-api` credentials stored
- [ ] No secrets in repo

### Configuration
- [ ] Direct Anthropic API connection confirmed (no proxy)
- [ ] Claude Sonnet model active
- [ ] Onboarding complete

### Service
- [ ] `openclaw.service` running and enabled
- [ ] Restarts on failure
- [ ] Logs accessible

### Integration
- [ ] OpenClaw authenticated to Vikunja API
- [ ] API call to Vikunja succeeds from OpenClaw

### Security
- [ ] Audit baselines reset

### Documentation
- [ ] `docs/handbooks/openclaw-ops.md` complete and CI-passing

---

## Architecture Principles

### Direct Anthropic API — No Exceptions

The constitution directive is explicit: Anthropic API called direct, no
third-party proxies. This is a supply chain security requirement, not a
preference. Any OpenClaw configuration that routes through LiteLLM or an
OpenAI-compatible endpoint violates the constitution.

### Credential Store Pattern

The pattern established here — named files in a mode-700 directory, mode-600
per file, owned by `claude`, under `/data/services/openclaw/secrets/` — is
the pattern all subsequent features follow. F003, F012, and later features
add credentials to this same store. Do not invent a different pattern.

### Data Under /data/services/

All OpenClaw runtime data (memory, logs, skill state) lives under
`/data/services/openclaw/`. This directory is covered by the existing Restic
backup. No new backup configuration needed.

### systemd Consistency

The `openclaw.service` unit follows the same pattern as `vikunja.service`
and `obsidian-sync.service`. Consistency in service management reduces
operational overhead.

---

## Constitutional Compliance

✅ **Security over convenience**: Pinned version, no proxy, credential store
with tight permissions, no secrets in repo.

✅ **Privacy boundary**: No personal data involved in this infrastructure
feature. `02-Growth/_private/` not touched.

✅ **No credentials in code**: All secrets in `/data/services/openclaw/secrets/`,
never in committed files.

✅ **Linux/office2 target**: All config targets Ubuntu 24.04 LTS.

✅ **Docs adjacent**: Runbook created alongside deployment.

✅ **Zero manual maintenance**: systemd ensures OpenClaw restarts without
human intervention.

---

## Risk Considerations

**Risk: OpenClaw version contains supply chain compromise**
- OpenClaw is a young, fast-moving project (19 days old at launch per its
  own marketing). Pinning and reviewing before install is essential.
- Mitigation: Pin to a specific reviewed tag. Read the changelog before
  any version bump. The security audit's Docker image diff and process
  monitoring will detect unexpected network activity post-install.

**Risk: Anthropic API key exposure**
- The API key is the highest-value credential in this system.
- Mitigation: Mode-600 file, `claude`-user-only access, never logged,
  never in environment variables that could appear in `ps` output. Verify
  with `cat /proc/$(pgrep -f openclaw)/environ` after startup to confirm
  key is not in process environment.

**Risk: OpenClaw connects to unexpected external endpoints**
- OpenClaw's skill system could make outbound calls to unreviewed services.
- Mitigation: No skills installed in this feature. Monitor new external
  connections via the security audit's port and process scanning after
  installation.

---

## Notes for Implementation

**Pattern discovery (planning phase):**
- Read `scripts/vikunja/vikunja.service` for systemd unit template to copy
- Read `docs/handbooks/vikunja-ops.md` for runbook structure to match
- Check OpenClaw's README for the correct env var or config file for
  setting the API provider and model
- Determine whether OpenClaw reads API key from env var, config file, or
  its own secrets mechanism — use whichever approach keeps the key out of
  process environment and committed files

**Vikunja API token generation:**
- Vikunja persistent tokens are generated via Settings → API Tokens in the
  web UI, or via `POST /api/v1/tokens`
- Use a named token (e.g., `openclaw-agent`) for traceability
- Record token name (not value) in runbook

**Key verification steps:**
- After startup, verify no proxy in API calls:
  `journalctl -u openclaw | grep -i "litellm\|proxy\|openai"` should return nothing
- Verify Vikunja connectivity:
  `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info`

---

**END OF SPECIFICATION**
