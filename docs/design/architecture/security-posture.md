---
title: Security Posture
doc_type: reference
status: approved
tags: [152]
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
| `claude` | `ssh office2-claude` (Mac), or `claude` host in Termius mobile | No | Agent operations — all automated actions. Humans connecting as `claude` is allowed for specific user-bound operations (e.g. `gog-reauth` weekly re-auth — see [phone-termius-setup runbook](<../../runbooks/phone-termius-setup.md>)) |
| `kgale` | `ssh office2-kgale` (Mac), or `kgale` host in Termius mobile | Yes | Human operations — sudo commands, initial setup, emergency ops |

**Agents must always use the claude user.** The kgale account is for human use only by autonomous agents. Humans (Kent) may use either user depending on the task. This ensures all agent actions are traceable.

**Sudo escalation**: When a command requires sudo, agents stop and present the command to Kent for manual execution.

### SSH gates (two layers, in order)

SSH access to office2 passes through **two gates** in sequence:

1. **Tailscale SSH** (network-layer ACL) — tailscaled on office2 intercepts SSH connections to port 22 on the Tailscale IP. With current ACL `action: "accept"`, the connection is allowed through to sshd. With `"check"` it would require browser re-auth (incompatible with Termius mobile). See [ADR-0004](<./adr/0004-tailscale-ssh-with-accept-acl.md>) for the decision rationale.
2. **sshd** (authentication) — standard OpenSSH authentication using `~/.ssh/authorized_keys` per user. The Termius SSH ID public key (cloud-hosted) is installed in both `kgale`'s and `claude`'s `authorized_keys`.

**SSH key rotation impact**: Rotating a Mac-side SSH key affects only the standard sshd path. Tailscale SSH gating is independent of SSH keys. Termius mobile uses its own SSH ID, NOT any Mac key. The 2026-06-09 #575 rediscovery wasted ~30 min troubleshooting `authorized_keys` permissions before noticing this distinction — see [phone-termius-setup § Gotchas](<../../runbooks/phone-termius-setup.md>).

**ACL changes are tracked in [ADR-0004](<./adr/0004-tailscale-ssh-with-accept-acl.md>) § ACL changes log.** Any future change to the tailnet `ssh` rule (action, src/dst/users) must be recorded there. Undocumented changes are how the #575 docs-debt accumulated.

## Credential Security

- No credentials in committed files — ever
- Secrets stored on office2 filesystem (not in repo)
- Interactive auth for manual scripts; stored tokens for automated use
- See [Credentials and Secrets](<./credentials-and-secrets.md>) for the full manifest

## Privacy Boundaries

**Absolute rule**: `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged by any agent or script under any circumstance. No exceptions. (Path renumbered from `02-Growth/_private/` in mission 026 / #152.)

**Agent context ceiling**: Agents may read `03-Constitution/` docs only from the second brain. All other vault content is off-limits unless explicitly required by a skill definition.

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

After deploying a new service, baselines must be reset. See [Security Baseline Operations](<../../runbooks/security-baseline-ops.md>) for the canonical procedure.
