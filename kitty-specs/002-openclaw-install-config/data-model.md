# Data Model: OpenClaw Install and Configuration

**Feature**: 002-openclaw-install-config
**Date**: 2026-03-26

## Overview

This feature creates infrastructure on office2, not application data models. The entities below describe file system artifacts, not database tables.

## File System Entities

### Credential Store

```
/data/services/openclaw/secrets/    (directory, mode 700, owner: claude)
├── anthropic                       (file, mode 600, raw Anthropic API key)
└── vikunja-api                     (file, mode 600, raw Vikunja persistent token)
```

**Rules**:
- One secret per file, raw value only (no JSON, no YAML, no key=value)
- Directory readable only by claude user (mode 700)
- Files readable only by claude user (mode 600)
- Pattern reused by F003 (`whatsapp-meta`), F012 (`personal-google`), etc.

### Configuration

```
/home/claude/.openclaw/openclaw.json    (JSON5, created by onboard, then customized)
```

**Key fields**:
- `models.providers.anthropic.apiKey` — SecretRef pointing to credential file
- `agents.defaults.model.primary` — `anthropic/claude-sonnet-4-6`
- `agents.defaults.workspace` — `/data/services/openclaw/data`
- `gateway.bind` — `loopback`

### Data Directory

```
/data/services/openclaw/data/    (directory, owner: claude, in Restic backup scope)
```

OpenClaw's workspace, sessions, and agent state. Automatically backed up as part of `/data/services/`.

### systemd Unit

```
/etc/systemd/system/openclaw.service    (installed by sudo, source in repo)
scripts/openclaw/openclaw.service       (canonical artifact in repo)
```

Captured from `openclaw onboard --install-daemon`, adjusted, and committed.
