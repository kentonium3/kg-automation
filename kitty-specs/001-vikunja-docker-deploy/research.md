# Research: Vikunja Docker Deploy

**Feature**: 001-vikunja-docker-deploy
**Date**: 2026-03-26

## R-001: Vikunja Docker Image Version

**Decision**: Pin to a specific stable release tag from the Vikunja Docker Hub registry.

**Rationale**: The `latest` tag introduces supply chain risk — an unreviewed update could break the API contract or introduce vulnerabilities. Pinning ensures deterministic deployments and controlled upgrades.

**Action for implementation**: Check available tags at `hub.docker.com/r/vikunja/vikunja` and select the latest stable release. Record the chosen version in the systemd unit and in the ops runbook.

**Alternatives considered**:
- `latest` tag — rejected per security posture (no unreviewed updates)
- Building from source — unnecessary complexity for a well-maintained project

## R-002: Docker Networking — Tailscale Binding

**Decision**: Bind Docker container to `100.92.197.90:3456:3456` (Tailscale IP of office2).

**Rationale**: Docker's default `-p 3456:3456` binds to `0.0.0.0`, which bypasses ufw/iptables and exposes the port publicly. Binding to the Tailscale IP ensures only Tailscale-connected devices can reach the service. Docker does not support binding to interface names directly.

**Alternatives considered**:
- Bind to `127.0.0.1` with Tailscale `serve` forwarding — adds complexity, not needed for phase 1
- Docker network mode `host` — exposes all container ports, rejected
- `0.0.0.0` with firewall rules — Docker bypasses iptables, unreliable

## R-003: Service Management — systemd vs Docker Compose

**Decision**: Use a systemd unit calling `docker run` (preferred). Use Docker Compose only if already installed and actively in use on office2.

**Rationale**: A simple systemd unit is consistent with the existing `obsidian-sync.service` pattern on office2. It provides boot-start, failure-restart, and clear logging via `journalctl` with no additional daemon dependency.

**Action for implementation**: During WP-01, check if Docker Compose is installed and in active use on office2 (`docker compose version` and check for existing compose files in `/data/services/`). If not, use the systemd unit approach.

**Alternatives considered**:
- Docker Compose — acceptable if already present, but adds a dependency if not
- Docker restart policy alone (`--restart=unless-stopped`) — does not integrate with systemd logging or `systemctl` management

## R-004: Setup Script Authentication

**Decision**: Script prompts for Vikunja username and password interactively at runtime, obtains a JWT via `POST /api/v1/login`, uses it for the session, does not persist it.

**Rationale**: No credentials in code or stored files. Stored API tokens are reserved for F005 (Vikunja API skill for agent use). The setup script is run manually by Kent, so interactive prompts are acceptable.

**Alternatives considered**:
- Pre-generated API token in environment variable — deferred to F005
- Hardcoded credentials — rejected per constitution

## R-005: Data Volume Path and Backup

**Decision**: Mount Vikunja SQLite data to `/data/services/vikunja/data/` on the office2 host.

**Rationale**: The Restic backup script at `/data/services/backup/scripts/backup.sh` already backs up `/data/services/` and `/home/claude/`. Placing Vikunja data under `/data/services/vikunja/data/` means it is automatically included in nightly backups with no changes to the backup configuration.

**Alternatives considered**:
- `/home/claude/vikunja-data/` — would also be backed up but doesn't align with the services directory convention
- Custom Restic config addition — unnecessary given the existing backup scope

## R-006: Vikunja API — Filter Syntax

**Decision**: Verify saved filter syntax against the pinned Vikunja version's API documentation before implementing FR-005.

**Rationale**: Vikunja's filter syntax has changed across versions. The func-spec proposes `due_date <= now/d && done = false` but this must be confirmed against the actual API of the pinned version.

**Action for implementation**: During WP-02, after the Vikunja container is running, test filter creation via `POST /api/v1/filters` with a sample expression and verify the response. Adjust syntax if needed.

## R-007: Security Baseline Reset

**Decision**: After deployment, reset security audit baselines at `/data/services/security-monitor/baselines/` to incorporate the new Vikunja container, systemd service, and port 3456.

**Rationale**: The security monitoring system on office2 uses baselines to detect unexpected changes. A new Docker container, systemd service, and open port will trigger alerts unless the baselines are updated.

**Action for implementation**: Document the baseline reset procedure in the ops runbook. The actual reset command may require Kent to run it manually if it needs sudo access.
