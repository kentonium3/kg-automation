---
title: "F001: Vikunja Docker Deploy"
doc_type: func-spec
status: draft
feature: F001
---

# F001: Vikunja Docker Deploy

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

The system has no task store or user-facing UI. Vikunja must be deployed on
office2 as the foundational task storage and web interface layer before any
other feature can be built. This spec covers Docker deployment, initial project
structure, and saved filter configuration.

Current gaps:
- ❌ No task store exists
- ❌ No web UI for task management
- ❌ No Vikunja project hierarchy established
- ❌ No saved filters configured

This spec delivers a running, accessible, backed-up Vikunja instance on office2
with the correct project structure and saved filters ready for agent use.

---

## Problem Statement

**Current State:**
```
office2
└── ❌ No Vikunja instance
└── ❌ No task storage layer
└── ❌ No web UI accessible via Tailscale
```

**Target State:**
```
office2
└── ✅ Vikunja running in Docker (port 3456)
└── ✅ SQLite database persisted to host volume
└── ✅ Included in existing Restic backup (4AM)
└── ✅ Accessible from Mac and iPhone via Tailscale
└── ✅ Project hierarchy: Areas → Projects → Inbox/Someday
└── ✅ Saved filters: Today, Upcoming, Overdue
└── ✅ Labels: personal, intentional
└── ✅ systemd service ensures restart on boot
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Architecture spec**
   - `docs/design/personal-ai-system-spec-v03.md` Section 5.1
   - Understand Vikunja project structure and saved filter definitions
   - Note identity label model (`personal` / `intentional`)

2. **Existing Restic backup config on office2**
   - Find current Restic backup paths and schedule
   - Confirm the SQLite data volume path will be included
   - Note: backup runs at 4AM via systemd/cron

3. **office2 environment**
   - Confirm Docker is installed: `docker --version`
   - Confirm available ports (3456 must be free)
   - Confirm Tailscale is active: `tailscale status`
   - Check existing systemd services pattern for consistency

---

## Functional Requirements

### FR-1: Docker Deployment

**What it must do:**
- Deploy Vikunja as a Docker container on office2
- Persist SQLite database to a host volume (not inside the container)
- Expose on port 3456, bound to Tailscale interface only — never 0.0.0.0
- Pin to a specific Vikunja image version (not `latest`)
- Run as a systemd service that starts on boot and restarts on failure

**Security rules:**
- Port 3456 must NOT be reachable from public internet
- Must bind to Tailscale interface (or localhost with Tailscale forwarding)
- No default admin credentials left in place — set a strong password

**Success criteria:**
- [ ] `docker ps` shows Vikunja container running on office2
- [ ] Web UI reachable at `http://office2:3456` from Mac via Tailscale
- [ ] Web UI reachable from iPhone via Tailscale
- [ ] Container restarts automatically after `docker restart` or reboot
- [ ] SQLite file exists on host filesystem outside the container
- [ ] Port 3456 not reachable from outside Tailscale network

---

### FR-2: Restic Backup Integration

**What it must do:**
- Include the Vikunja SQLite data volume path in the existing Restic backup
- Backup must run as part of the existing 4AM schedule — no new cron job
- No separate backup mechanism needed — piggyback on what exists

**Success criteria:**
- [ ] Vikunja data path included in Restic backup source paths
- [ ] `restic snapshots` confirms Vikunja data appears in next backup run
- [ ] Existing backup schedule and retention policy unchanged

---

### FR-3: Project Hierarchy

**What it must do:**
- Create the following project structure via Vikunja UI or API:

```
Everyday (parent project)
  ├── Inbox
  └── Someday

Personal Growth & Transformation (parent project / Area)
Business Acquisition (parent project / Area)
  └── CT-90day (subproject)
Health & Conditioning (parent project / Area)
Intentional LLC (parent project / Area)
Metal Casework (parent project / Area)
```

- All Area-level projects are parent projects with no tasks of their own
  (convention, not enforced by Vikunja — tasks placed here should be moved
  to a subproject)
- Inbox and Someday live under Everyday, not under an Area

**Success criteria:**
- [ ] All projects and subprojects visible in Vikunja sidebar
- [ ] Inbox project exists and is the default destination for new tasks
- [ ] Someday project exists
- [ ] All five Area projects exist with correct names
- [ ] CT-90day subproject exists under Business Acquisition

---

### FR-4: Labels

**What it must do:**
- Create two labels for identity routing:
  - `personal` (used for tasks belonging to personal Google identity)
  - `intentional` (used for tasks belonging to Intentional LLC identity)

**Success criteria:**
- [ ] Both labels exist and are selectable on any task
- [ ] Labels are visually distinct (different colors)

---

### FR-5: Saved Filters

**What it must do:**
- Create the following saved filters, accessible from the Vikunja sidebar:

| Filter name | Filter expression |
|---|---|
| Today | `due_date <= now/d && done = false` |
| Upcoming | `due_date > now/d && due_date <= now+14d && done = false` |
| Overdue | `due_date < now/d && done = false` |

**Success criteria:**
- [ ] All three saved filters appear in the Vikunja sidebar
- [ ] Today filter returns tasks due today (verified with a test task)
- [ ] Upcoming filter returns tasks due within 14 days
- [ ] Overdue filter returns tasks with past due dates

---

### FR-6: Deployment Documentation

**What it must do:**
- Create a runbook at `docs/handbooks/vikunja-ops.md` covering:
  - How to start/stop/restart the Vikunja service
  - Where the SQLite database lives
  - How to check backup status
  - How to update Vikunja to a new pinned version
  - How to access the web UI via Tailscale

**Success criteria:**
- [ ] Runbook exists at `docs/handbooks/vikunja-ops.md`
- [ ] All five topics covered
- [ ] Passes doc validation (frontmatter compliant)

---

## Out of Scope

- ❌ OpenClaw integration — F002 and F005 handle this
- ❌ Vikunja API authentication for agents — F005 (Vikunja API skill)
- ❌ Task creation or population — later features
- ❌ Google Calendar integration — F012
- ❌ WhatsApp integration — F003
- ❌ HTTPS/TLS termination — Tailscale provides encrypted transport; not needed for phase 1
- ❌ Multi-user setup — single user only

---

## Success Criteria

**Complete when:**

### Deployment
- [ ] Vikunja container running on office2
- [ ] Accessible via Tailscale from Mac and iPhone
- [ ] Pinned image version in Docker run config
- [ ] systemd service restarts on failure and boot
- [ ] Port not exposed to public internet

### Data Safety
- [ ] SQLite persisted to host volume
- [ ] Volume path included in Restic backup

### Structure
- [ ] Project hierarchy matches spec
- [ ] Both identity labels created
- [ ] All three saved filters working

### Documentation
- [ ] `docs/handbooks/vikunja-ops.md` complete and passing CI

### Quality
- [ ] No credentials committed to repo
- [ ] Docker run config or compose file committed to `scripts/vikunja/`
- [ ] Passes `validate_docs.py` in CI

---

## Architecture Principles

### Tailscale-Only Access

Vikunja must never be reachable from the public internet. Tailscale provides
encrypted transport between devices — TLS termination is not required for
phase 1. The binding configuration must enforce this.

### Host Volume for Data

The SQLite database must live on the office2 host filesystem, not inside the
Docker container. This ensures data survives container replacement during
upgrades and is included in Restic backups.

### Pinned Versions

Per the security posture in the constitution, image versions are pinned and
reviewed before updates. Never use `latest`.

### Systemd Management

The Vikunja container must be managed via systemd, consistent with how
`obsidian-sync.service` is managed on office2. No Docker Compose daemon
dependency — a simple systemd unit that calls `docker run` is preferred
unless Docker Compose is already present and in use.

---

## Constitutional Compliance

✅ **Privacy boundary**: No personal data involved in deployment. SQLite data
is local to office2 and covered by existing backup/security posture.

✅ **Security over convenience**: Port bound to Tailscale only. Pinned image
version. No default credentials.

✅ **No credentials in code**: Vikunja admin password set interactively or via
environment variable injected at runtime — never committed to repo.

✅ **Linux/office2 target**: All config targets Ubuntu 24.04 LTS on office2.

✅ **Docs adjacent**: Runbook created alongside deployment config.

---

## Risk Considerations

**Risk: Port exposure**
- Docker's default network mode can bypass ufw/iptables and expose ports
  publicly even when firewall rules exist
- Mitigation: Bind explicitly to Tailscale interface IP, not 0.0.0.0.
  Verify with `ss -tlnp | grep 3456` after deployment.

**Risk: SQLite data loss on container replacement**
- If the database is inside the container, an upgrade wipes all data
- Mitigation: Host volume mount is a hard requirement, not optional

**Risk: Vikunja version drift**
- Running unreviewed updates introduces supply chain risk
- Mitigation: Pin version in run config, document update procedure in runbook

---

## Notes for Implementation

**Pattern discovery (planning phase):**
- Study `obsidian-sync.service` on office2 for systemd unit pattern to copy
- Check if Docker Compose is already installed on office2 before choosing
  between `docker run` and Compose approach
- Vikunja API docs at `https://vikunja.io/docs/api-documentation/` for
  creating projects, labels, and filters programmatically vs manually

**Saved filter syntax reference:**
- Vikunja filter API: `POST /api/v1/filters`
- Filter expressions use `&&`, `||`, field names like `due_date`, `done`,
  operators like `<=`, `>=`, and relative dates like `now/d`, `now+14d`
- **Planning phase must verify**: filter syntax varies across Vikunja versions.
  Confirm the exact syntax against the pinned version's API docs before
  implementing saved filters.

**Key decision for planning phase:**
- Determine whether to create project structure and filters via the web UI
  (manual, no code) or via API calls in a setup script (automated, repeatable)
- A setup script is preferred if it can be committed to `scripts/vikunja/`
  and re-run idempotently

---

**END OF SPECIFICATION**
