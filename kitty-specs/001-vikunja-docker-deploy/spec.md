# Feature Specification: Vikunja Docker Deploy

**Feature Branch**: `001-vikunja-docker-deploy`
**Created**: 2026-03-26
**Status**: Draft
**Input**: F001 func-spec — deploy Vikunja on office2 as foundational task store and web UI

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Access Task Management from Any Device (Priority: P1)

Kent needs to view, create, and manage tasks from his Mac, iPhone, or any Tailscale-connected device via a web browser, without requiring the Mac to be awake.

**Why this priority**: Without an accessible task store and UI, no other feature in the system can function. This is the foundation.

**Independent Test**: Navigate to `http://office2:3456` from Mac via Tailscale and confirm the Vikunja web UI loads and is functional.

**Acceptance Scenarios**:

1. **Given** Vikunja is deployed on office2, **When** Kent opens `http://office2:3456` from Mac via Tailscale, **Then** the Vikunja web UI loads and Kent can log in.
2. **Given** Vikunja is deployed on office2, **When** Kent opens `http://office2:3456` from iPhone via Tailscale, **Then** the Vikunja web UI loads and is usable on mobile.
3. **Given** office2 has rebooted, **When** Kent accesses the Vikunja URL, **Then** the service is running (auto-started by systemd) and the UI loads without manual intervention.

---

### User Story 2 - Organized Project Structure Ready for Agent Use (Priority: P1)

Kent needs a pre-configured project hierarchy with Areas, Inbox, Someday, and identity labels so that tasks captured by agents land in the right place from day one.

**Why this priority**: Agents (F005+) will write tasks via the API. Without the correct project structure and labels, tasks have nowhere to go and no identity routing.

**Independent Test**: Run the setup script, then verify via Vikunja UI that all projects, labels, and filters exist.

**Acceptance Scenarios**:

1. **Given** Vikunja is running, **When** the setup script is executed, **Then** the project hierarchy (Everyday/Inbox/Someday, five Area projects, CT-90day subproject) is created.
2. **Given** the setup script has run once, **When** it is run again, **Then** no duplicate projects, labels, or filters are created (idempotent).
3. **Given** projects and labels exist, **When** Kent creates a task in Vikunja, **Then** the `personal` and `intentional` labels are available for selection.

---

### User Story 3 - Filtered Task Views (Priority: P2)

Kent needs saved filters (Today, Upcoming, Overdue) in the Vikunja sidebar so he can quickly see what needs attention without manually searching.

**Why this priority**: Filters are important for daily use but are lower priority than having the service running and structured.

**Independent Test**: Create test tasks with various due dates, then verify each saved filter returns the correct subset.

**Acceptance Scenarios**:

1. **Given** saved filters are configured, **When** Kent clicks "Today" in the sidebar, **Then** only tasks due today (and not completed) are shown.
2. **Given** saved filters are configured, **When** Kent clicks "Upcoming", **Then** tasks due within the next 14 days (excluding today) are shown.
3. **Given** saved filters are configured, **When** Kent clicks "Overdue", **Then** only tasks with past due dates (not completed) are shown.

---

### User Story 4 - Data Survives Upgrades and Disasters (Priority: P1)

Kent needs confidence that task data is not lost when the container is replaced during an upgrade, and that it is included in nightly backups.

**Why this priority**: Data loss would undermine trust in the entire system. This is a foundational safety requirement.

**Independent Test**: Verify the SQLite file exists on the host filesystem (not inside the container). Verify the Restic backup source paths include the Vikunja data volume. Run a backup and confirm Vikunja data appears in the snapshot.

**Acceptance Scenarios**:

1. **Given** Vikunja is running with tasks, **When** the container is stopped and replaced with a new one using the same volume, **Then** all tasks are preserved.
2. **Given** the Vikunja data volume path is added to Restic config, **When** the 4AM backup runs, **Then** `restic snapshots` shows the Vikunja data directory in the latest snapshot.

---

### User Story 5 - Ops Runbook for Maintenance (Priority: P2)

Kent (or a future agent) needs a runbook documenting how to operate Vikunja: start, stop, restart, check backups, update versions, and access the UI.

**Why this priority**: Important for ongoing operations but not blocking initial deployment.

**Independent Test**: A new Claude Code session can follow the runbook to perform basic Vikunja operations without prior context.

**Acceptance Scenarios**:

1. **Given** the runbook exists at `docs/handbooks/vikunja-ops.md`, **When** an operator reads it, **Then** they can start, stop, and restart the Vikunja service.
2. **Given** the runbook exists, **When** a version update is needed, **Then** the runbook documents the process for pinning a new version and redeploying.

---

### Edge Cases

- What happens when Docker is not installed on office2? → Planning phase must verify; deployment script should fail with a clear error message.
- What happens when port 3456 is already in use? → Deployment should check and fail with a clear message rather than silently binding elsewhere.
- What happens when the Vikunja API is not yet ready when the setup script runs? → Script must wait for readiness or retry with a timeout.
- What happens when Restic backup config format is unexpected? → Provide the path addition as a manual step for Kent if automation is not straightforward.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Docker container deployment | As Kent, I want Vikunja running in Docker on office2 so that I have an always-on task store. | High | Open |
| FR-002 | Restic backup integration | As Kent, I want the Vikunja SQLite data path explicitly added to Restic backup source config so that task data is included in nightly backups. | High | Open |
| FR-003 | Project hierarchy creation | As Kent, I want the correct project structure (Areas, Inbox, Someday) created via API so that tasks can be organized from day one. | High | Open |
| FR-004 | Identity labels | As Kent, I want `personal` and `intentional` labels created so that tasks can be routed to the correct Google identity in later features. | Medium | Open |
| FR-005 | Saved filters | As Kent, I want Today, Upcoming, and Overdue saved filters so that I can quickly see what needs attention. | Medium | Open |
| FR-006 | Ops runbook | As Kent, I want a runbook documenting Vikunja operations so that maintenance is straightforward. | Medium | Open |
| FR-007 | Automated setup script | As Kent, I want project structure, labels, and filters created by an idempotent Python script using the Vikunja REST API so that setup is repeatable and committed to the repo. | High | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Service availability | Vikunja service restarts automatically after failure or reboot within 30 seconds | Reliability | High | Open |
| NFR-002 | Backup coverage | Vikunja data directory appears in Restic snapshots within one backup cycle (by next 4AM run) | Reliability | High | Open |
| NFR-003 | Setup script idempotency | Running the setup script multiple times produces no duplicates and no errors | Reliability | High | Open |
| NFR-004 | Web UI responsiveness | Vikunja web UI loads within 3 seconds from Mac or iPhone via Tailscale | Performance | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Tailscale-only access | Port 3456 must be bound to Tailscale interface or localhost only — never 0.0.0.0 | Security | High | Open |
| C-002 | No credentials in code | Vikunja admin password must not appear in any committed file | Security | High | Open |
| C-003 | Pinned image version | Docker image must use a specific version tag, never `latest` | Security | High | Open |
| C-004 | Host volume for SQLite | Database must persist on host filesystem, not inside the container | Reliability | High | Open |
| C-005 | Agent SSH identity | All deployment commands run as `claude` user via `ssh office2-claude`; sudo commands presented to Kent for manual execution | Security | High | Open |
| C-006 | Linux target | All scripts and configs target Ubuntu 24.04 LTS on office2 | Platform | High | Open |
| C-007 | No public internet exposure | Vikunja management port must never be reachable outside Tailscale network | Security | High | Open |

### Key Entities

- **Project**: A Vikunja project representing an Area (Personal Growth, Business Acquisition, etc.) or functional bucket (Inbox, Someday). Projects can have parent-child relationships.
- **Label**: Identity tag (`personal` or `intentional`) applied to tasks for Google identity routing in later features.
- **Saved Filter**: A named query (Today, Upcoming, Overdue) that appears in the Vikunja sidebar for quick task views.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Vikunja web UI is accessible from Mac and iPhone via Tailscale within 3 seconds of page load.
- **SC-002**: Service recovers automatically after container crash or host reboot — UI accessible again within 30 seconds.
- **SC-003**: Task data survives container replacement — all tasks present after stopping old container and starting new one with same volume.
- **SC-004**: Vikunja data directory confirmed present in Restic snapshot after next scheduled backup run.
- **SC-005**: Setup script creates all projects, labels, and filters on first run, and produces no duplicates on subsequent runs.
- **SC-006**: Port 3456 is not reachable from any device outside the Tailscale network (verified with `ss -tlnp`).
- **SC-007**: Runbook at `docs/handbooks/vikunja-ops.md` passes CI validation and covers all operational topics.
