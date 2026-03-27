---
title: Credentials and Secrets
doc_type: reference
status: approved
---

# Credentials and Secrets

Authoritative data: [`data/credential-manifest.json`](data/credential-manifest.json)

## Rules

1. **No credentials in committed files** — ever
2. Interactive auth for manual scripts (e.g., `setup_vikunja.py` prompts for password)
3. Stored tokens for agent/automated use go in the office2 scoped secrets store
4. Credential names are stable identifiers referenced across docs and code

## Active Credentials

| Name | Type | Storage | Used By |
|------|------|---------|---------|
| `vikunja-admin` | username/password | Set interactively (first-run) | Web UI login, `setup_vikunja.py` |
| `restic-password` | password file | `/home/claude/.config/restic/password` | `backup.sh` |
| `tailscale-auth` | system-managed | Managed by `tailscaled` | Tailscale daemon |
| `anthropic` | API key | OpenClaw native auth + `/data/services/openclaw/secrets/anthropic` (backup) | `openclaw-gateway` |
| `vikunja-api` | API token | `/data/services/openclaw/secrets/vikunja-api` | `openclaw-gateway` |

## Planned Credentials (Not Yet Deployed)

| Name | Type | Planned By | Purpose |
|------|------|------------|---------|
| `whatsapp-meta` | API token | F003 | Meta Cloud API for WhatsApp |
| `personal-google` | OAuth | F012 | Personal Google Calendar |
| `intentional-google` | OAuth | F012 (phase 3) | Intentional LLC Workspace |

## Access Model

- **claude user**: Can read secrets in `/home/claude/.config/`. Cannot sudo.
- **kgale user**: Full sudo access. Used for initial credential setup.
- **Container runtime**: Credentials injected via environment variables at runtime, never baked into images.
