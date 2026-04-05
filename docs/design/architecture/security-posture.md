---
title: Security Posture
doc_type: reference
status: approved
---

# Security Posture

## Network Security

- **Services bind to Tailscale IP** (`100.92.197.90`) unless fronted by Tailscale Serve, which allows `0.0.0.0` binding safely
- No services exposed to the public internet (Tailscale Funnel is disabled)
- No port forwarding or NAT traversal outside Tailscale
- Docker's default networking bypasses iptables/ufw — explicit IP binding is the primary control for non-Serve services

**Tailscale Serve**: Vikunja is fronted by Tailscale Serve, which terminates TLS on port 443 and proxies to the container on localhost:3456. Certs are auto-provisioned from Let's Encrypt and auto-renewed. Access is tailnet-only.

**As of F003**: Transcribe API and OpenClaw bind exclusively to Tailscale IP. Vikunja binds to `0.0.0.0:3456` but is accessed via Tailscale Serve on HTTPS — direct port 3456 is not reachable from outside the host.

## Supply Chain

- Docker images pinned to specific version tags, never `latest`
- No LiteLLM or third-party API proxies — Anthropic API called direct
- No community OpenClaw skills without source review
- All Python dependencies reviewed before installation

## Agent Access Model

| User | Access | Sudo | Purpose |
|------|--------|------|---------|
| `claude` | `ssh office2-claude` | No | Agent operations — all automated actions |
| `kgale` | `ssh office2-kgale` | Yes | Human operations — sudo commands, initial setup |

**Agents must always use the claude user.** The kgale account is for human use only. This ensures all agent actions are traceable.

**Sudo escalation**: When a command requires sudo, agents stop and present the command to Kent for manual execution.

## Credential Security

- No credentials in committed files — ever
- Secrets stored on office2 filesystem (not in repo)
- Interactive auth for manual scripts; stored tokens for automated use
- See [Credentials and Secrets](<./credentials-and-secrets.md>) for the full manifest

## Privacy Boundaries

**Absolute rule**: `~/second-brain/notes/02-Growth/_private/` is never read, written, referenced, or logged by any agent or script under any circumstance. No exceptions.

**Agent context ceiling**: Agents may read `01-Constitution/` docs only from the second brain. All other vault content is off-limits unless explicitly required by a skill definition.

## Policy Exceptions

Exceptions to architecture and security policies are documented here with rationale, scope, and expiration. Each exception must be approved by Kent and linked to the feature that introduced it.

| Constraint | Exception | Rationale | Scope | Expiration | Feature |
|------------|-----------|-----------|-------|------------|---------|
| Official API only (original F004 C-002) | OpenClaw's WhatsApp integration uses Baileys (unofficial WhatsApp Web protocol) | OpenClaw has no Meta Cloud API channel. Baileys is the only WhatsApp path available. | Personal single-user system at low message volume. Account ban risk understood and accepted. | No expiration — this is the native OpenClaw integration path. | F004 |

## Change Control Governance

Change control is governed by a five-tier risk taxonomy (`docs/design/architecture/data/change-risk-taxonomy.json`). Tier 0 (Host/Foundational) changes including UFW, iptables, and SSH configuration follow a Hard Lock protocol — AI agents generate scripts but never execute directly. Tier 1 changes require human approval before execution. See `docs/runbooks/governance/pre-flight-checklist.md` for the full pre-flight assessment and `docs/runbooks/governance/post-change-verification.md` for post-change health checks.

## Security Monitoring

| Check | Schedule | Script | Baselines |
|-------|----------|--------|-----------|
| Docker images | 3AM daily | `audit.sh` | `docker-images.txt` |
| Enabled services | 3AM daily | `audit.sh` | `enabled-services.txt` |
| Listening ports | 3AM daily | `audit.sh` | `listening-ports.txt` |
| SSH keys | 3AM daily | `audit.sh` | `ssh-keys.txt` |
| Crontabs | 3AM daily | `audit.sh` | `crontabs.txt` |
| Pip packages | 3AM daily | `audit.sh` | `pip-packages.txt` |
| Hosts file | 3AM daily | `audit.sh` | `hosts-hash.txt` |
| Python pth files | 3AM daily | `audit.sh` | `pth-files.txt` |

After deploying a new service, baselines must be reset. See [Vikunja Ops Runbook](../../handbooks/vikunja-ops.md#security-baseline-reset) for the procedure.
