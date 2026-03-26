---
title: Security Posture
doc_type: reference
status: approved
---

# Security Posture

## Network Security

- **All services bind to Tailscale IP only** (`100.92.197.90`), never `0.0.0.0`
- No services exposed to the public internet
- No port forwarding or NAT traversal outside Tailscale
- Docker's default networking bypasses iptables/ufw — explicit IP binding is the only reliable control

**Known exception**: `transcribe-api` is currently bound to `0.0.0.0:8787`. This should be rebound to the Tailscale IP in a future hardening pass.

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
- See [Credentials and Secrets](credentials-and-secrets.md) for the full manifest

## Privacy Boundaries

**Absolute rule**: `~/second-brain/vault/Notes/02-Growth/_private/` is never read, written, referenced, or logged by any agent or script under any circumstance. No exceptions.

**Agent context ceiling**: Agents may read `01-Constitution/` docs only from the second brain. All other vault content is off-limits unless explicitly required by a skill definition.

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
