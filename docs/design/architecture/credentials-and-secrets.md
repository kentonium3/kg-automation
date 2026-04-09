---
title: Credentials and Secrets
doc_type: reference
status: approved
last_updated: '2026-04-06'
updated_by: maintenance-2026-04-06
---

# Credentials and Secrets

Authoritative data: [`data/credential-manifest.json`](<./data/credential-manifest.json>)

This document describes the secret management model for kg-automation: what
credentials exist, where they live, who manages them, and which consumers use
them. For expiry policies and review cadences, see the manifest.

---

## Storage Mechanisms

kg-automation uses four distinct secret storage mechanisms. Each credential
uses the mechanism appropriate to the tool that owns or consumes it. There is
no single unified secret store — that is a deliberate trade-off favoring
simplicity on a Tailscale-gated personal server.

### 1. Tool-native auth store (gog)

Used by: `personal-google`

`gog` (the Google Workspace CLI) manages its own OAuth2 token store via
`gog auth credentials` and `gog auth add`. Credentials are stored in
gog's internal directory on office2. This is the correct home for any
credential that `gog` consumes — agents interact via the `gog` CLI rather
than directly with credential files.

### 2. OpenClaw native auth

Used by: `anthropic`, `whatsapp-session`

OpenClaw manages these internally. The Anthropic API key lives in
`/home/claude/.openclaw/agents/main/agent/auth-profiles.json`. The
WhatsApp session is managed by OpenClaw's Baileys integration in
`~/.openclaw/credentials/whatsapp/`. Neither is touched directly —
OpenClaw handles auth refresh and session management.

### 3. Scoped plaintext files (mode 600)

Used by: `vikunja-api`

OpenClaw skills read credentials at runtime via `cat /data/services/openclaw/secrets/<name>`.
Files are owned by the `claude` user, mode 600. This pattern is appropriate
for API tokens consumed by skills via `exec` calls. It is not used for
credentials that have their own native management mechanism.

### 4. System-managed or standalone tool

Used by: `restic-password`, `tailscale-auth`, `vikunja-admin`

These credentials are owned and managed by their respective tools (Restic,
Tailscale daemon, Vikunja's login endpoint). Neither OpenClaw nor agents
interact with them directly.

---

## Storage Mechanism Summary

```mermaid
graph TD
    subgraph "gog auth store"
        G[personal-google<br/>OAuth2 refresh token]
    end

    subgraph "OpenClaw native"
        A[anthropic<br/>API key]
        W[whatsapp-session<br/>Baileys session]
    end

    subgraph "Scoped plaintext<br/>/data/services/openclaw/secrets/"
        V[vikunja-api<br/>API token]
    end

    subgraph "System / standalone tool"
        R[restic-password<br/>password file]
        T[tailscale-auth<br/>system-managed]
        VA[vikunja-admin<br/>runtime JWT only]
    end

    subgraph "Consumers"
        OC[openclaw-gateway]
        SK[OpenClaw skills<br/>vikunja-api, google-calendar]
        BK[backup.sh]
        TS[tailscaled]
        UI[Vikunja web UI<br/>setup_vikunja.py]
    end

    G -->|gog CLI| SK
    A -->|native auth| OC
    W -->|Baileys| OC
    V -->|cat secrets file| SK
    R -->|password-file flag| BK
    T -->|daemon-managed| TS
    VA -->|runtime JWT| UI
```

---

## Active Credentials

| Name | Type | Storage Mechanism | Used By |
|------|------|-------------------|---------|
| `vikunja-admin` | username/password | Runtime JWT, not stored | Vikunja web UI, `setup_vikunja.py` |
| `restic-password` | password file | Standalone — `/home/claude/.config/restic/password` | `backup.sh` |
| `tailscale-auth` | system-managed | Managed by `tailscaled` | Tailscale daemon |
| `anthropic` | API key | OpenClaw native auth store | `openclaw-gateway` |
| `vikunja-api` | API token | Scoped plaintext — `/data/services/openclaw/secrets/vikunja-api` | OpenClaw skills |
| `whatsapp-session` | session | OpenClaw native (Baileys) | `openclaw-gateway` |
| `personal-google` | OAuth2 | gog auth store | `gog` CLI via google-calendar skill |

---

## Planned Credentials

| Name | Type | Planned By | Purpose |
|------|------|------------|---------|
| `intentional-google` | OAuth2 | F012 (phase 3) | Intentional LLC Google Workspace — separate credential from personal-google |

---

## Access Model

- **claude user**: Owns and reads secrets in `/data/services/openclaw/secrets/`
  and `~/.openclaw/`. Cannot sudo. All agent and skill execution runs as claude.
- **kgale user**: Full sudo access. Used for initial credential setup and any
  operation requiring elevated privileges.
- **Containers**: Credentials injected via environment or read from mounted
  paths at runtime — never baked into images.

---

## Security Posture

All credentials are protected by the Tailscale-only network posture — office2
is not publicly reachable. Additional mitigations: UFW, fail2ban, SSH hardening,
and the ClawHub install approval requirement in the Felix Constitution.

**Known risk**: Credentials stored as plaintext files are vulnerable to
exfiltration if the `claude` account is compromised (e.g., via a malicious
OpenClaw skill). Precedent exists for this attack vector. Encrypting secrets
at rest is tracked as the long-term mitigation under R-001 in the
[risk register](<../../archive/risk-register.md>) (archived; now [issue #114](https://github.com/kentonium3/kg-automation/issues/114)) and D06 in the
[capability roadmap](<../felix-capability-roadmap.md>).

---

## Rules

1. **No credentials in committed files** — ever
2. Interactive auth for manual scripts (`setup_vikunja.py` pattern)
3. Use the mechanism native to the consuming tool — don't store credentials
   in a different mechanism just for uniformity
4. Credential names are stable identifiers referenced across docs and code
5. All new credentials must be added to `credential-manifest.json` before
   or alongside their first use
