# Feature Specification: OpenClaw Install and Configuration

**Feature Branch**: `002-openclaw-install-config`
**Created**: 2026-03-26
**Status**: Draft
**Input**: F002 func-spec — install and configure OpenClaw on office2 as orchestration engine

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Always-On Orchestration Engine (Priority: P1)

Kent needs an always-on orchestration engine on office2 that can execute skills, call the Claude API, and coordinate with Vikunja — without requiring the Mac to be awake.

**Why this priority**: OpenClaw is the foundation for all agent skills (F003-F015). Nothing else can be built until it's running.

**Independent Test**: `systemctl status openclaw` shows active on office2. OpenClaw responds to a basic health check or command.

**Acceptance Scenarios**:

1. **Given** OpenClaw is installed on office2, **When** Kent checks the service status, **Then** `systemctl status openclaw` shows active and running.
2. **Given** office2 has rebooted, **When** Kent checks after boot, **Then** OpenClaw has restarted automatically without manual intervention.
3. **Given** OpenClaw is running, **When** it makes an API call, **Then** the call goes directly to the Anthropic API with no proxy or intermediary.

---

### User Story 2 - Secure Credential Management (Priority: P1)

Kent needs a credential store pattern that safely holds API keys and tokens, accessible only to the claude user, with no secrets in committed files.

**Why this priority**: The Anthropic API key is the highest-value credential in the system. The pattern established here is reused by every subsequent feature.

**Independent Test**: Credential directory has mode 700, files have mode 600, owned by claude. No secrets appear in `git status` or committed files.

**Acceptance Scenarios**:

1. **Given** the credential store is set up, **When** Kent inspects permissions, **Then** the directory is mode 700 and files are mode 600, all owned by claude.
2. **Given** OpenClaw is running, **When** it reads the Anthropic API key, **Then** it authenticates successfully to the Claude API.
3. **Given** the credential store contains a Vikunja API token, **When** OpenClaw uses it, **Then** it can read tasks from Vikunja at `http://100.92.197.90:3456`.

---

### User Story 3 - Vikunja Integration Verified (Priority: P1)

Kent needs confidence that OpenClaw can communicate with Vikunja using a persistent API token, establishing the integration path for all future skills.

**Why this priority**: F005+ skills depend on this connectivity. Verifying it now prevents integration surprises later.

**Independent Test**: A curl command using the stored Vikunja token returns a successful API response from Vikunja.

**Acceptance Scenarios**:

1. **Given** the Vikunja API token is stored in the credential store, **When** a request is made to `http://100.92.197.90:3456/api/v1/info` with the token, **Then** it returns HTTP 200 with version information.
2. **Given** the Vikunja container restarts, **When** the same token is used again, **Then** it still authenticates successfully (token is persistent, not a session JWT).

---

### User Story 4 - Operational Documentation (Priority: P2)

Kent or a future agent needs a runbook documenting how to operate OpenClaw: start, stop, restart, check logs, rotate credentials, and update versions.

**Why this priority**: Important for ongoing operations but not blocking initial deployment.

**Independent Test**: A new agent session can follow the runbook to perform basic OpenClaw operations without prior context.

**Acceptance Scenarios**:

1. **Given** the runbook exists at `docs/handbooks/openclaw-ops.md`, **When** an operator reads it, **Then** they can start, stop, restart, and check logs.
2. **Given** a credential needs rotation, **When** the operator follows the runbook, **Then** they can replace the credential and verify the service reconnects.

---

### Edge Cases

- What happens when Node.js is not installed or is the wrong version on office2? → Installation checks and fails with a clear message.
- What happens when the Anthropic API key is invalid? → OpenClaw should fail to start or log a clear authentication error, not silently degrade.
- What happens when Vikunja is down when OpenClaw starts? → OpenClaw should start regardless; Vikunja connectivity is verified separately, not a startup dependency.
- What happens when the credential store directory already exists? → Installation should be idempotent — skip creation if it exists with correct permissions.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | npm installation | As Kent, I want OpenClaw installed via npm at a pinned version so that the installation is reproducible and auditable. | High | Open |
| FR-002 | Credential store | As Kent, I want a secure credential store at `/data/services/openclaw/secrets/` so that API keys and tokens are protected. | High | Open |
| FR-003 | Anthropic API configuration | As Kent, I want OpenClaw configured to call the Anthropic API directly so that no third-party proxy handles my API traffic. | High | Open |
| FR-004 | systemd service | As Kent, I want OpenClaw managed by systemd so that it starts on boot and restarts on failure. | High | Open |
| FR-005 | Vikunja API token | As Kent, I want a persistent Vikunja API token stored in the credential store so that OpenClaw can authenticate to Vikunja. | High | Open |
| FR-006 | Security baseline reset | As Kent, I want security audit baselines reset after installation so that the new service doesn't trigger false-positive alerts. | Medium | Open |
| FR-007 | Ops runbook | As Kent, I want an operations runbook documenting all OpenClaw procedures so that maintenance is straightforward. | Medium | Open |
| FR-008 | Architecture doc updates | As Kent, I want architecture documentation updated to reflect the new service so that system state documentation stays current. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Service availability | OpenClaw restarts automatically after failure or reboot within 30 seconds | Reliability | High | Open |
| NFR-002 | Credential security | Credential store directory mode 700, files mode 600, owned by claude user | Security | High | Open |
| NFR-003 | API directness | No API calls routed through any proxy, intermediary, or OpenAI-compatible endpoint | Security | High | Open |
| NFR-004 | Installation idempotency | Running the installation steps multiple times causes no errors or duplicates | Reliability | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No third-party API proxy | Anthropic API must be called direct — no LiteLLM, no OpenAI-compatible proxy | Security | High | Open |
| C-002 | No credentials in code | No API keys, tokens, or passwords in any committed file | Security | High | Open |
| C-003 | Pinned version | OpenClaw installed at a specific reviewed version tag, never `latest` | Security | High | Open |
| C-004 | Agent SSH identity | All commands run as claude user via `ssh office2-claude`; sudo presented to Kent | Security | High | Open |
| C-005 | Linux target | All scripts and configs target Ubuntu 24.04 LTS on office2 | Platform | High | Open |
| C-006 | No community skills | No ClawHub or community skills installed during this feature | Security | High | Open |
| C-007 | Credential store pattern | Pattern must be reusable by F003, F012, and all future credential additions | Architecture | High | Open |

### Key Entities

- **Credential Store**: Directory at `/data/services/openclaw/secrets/` containing named credential files (one secret per file, raw value, mode 600).
- **Credential File**: A single file in the credential store containing one secret value. Named by credential identifier (e.g., `anthropic`, `vikunja-api`).
- **systemd Service**: `openclaw.service` unit managing the OpenClaw process lifecycle.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: OpenClaw service is active and responding on office2 (verified by `systemctl status openclaw`).
- **SC-002**: Service recovers automatically after process crash or host reboot within 30 seconds.
- **SC-003**: API calls confirmed direct to Anthropic — no proxy strings in logs (`journalctl -u openclaw` contains no references to litellm, proxy, or openai-compatible endpoints).
- **SC-004**: Credential store exists with correct permissions (directory mode 700, files mode 600, claude-owned).
- **SC-005**: Vikunja API token authenticates successfully from office2 (curl with stored token returns HTTP 200 from Vikunja).
- **SC-006**: Security audit baselines reset — next audit run produces no false-positive alerts for OpenClaw.
- **SC-007**: Runbook at `docs/handbooks/openclaw-ops.md` passes CI validation and covers all operational topics.
- **SC-008**: Architecture docs updated — `service-inventory.json` and `credential-manifest.json` reflect OpenClaw.
