# Feature Specification: Whisper Transcription Skill

**Feature Branch**: `003-whisper-transcription-skill`
**Created**: 2026-03-28
**Status**: Draft
**Input**: F003 func-spec — harden transcribe-api and build OpenClaw whisper skill

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure Transcription Service (Priority: P1)

Kent needs the existing transcription service hardened so it's no longer exposed to the public internet, ensuring it meets the same security standards as all other services on office2.

**Why this priority**: The `0.0.0.0` binding is a security violation per the architecture rules. This must be fixed before the service is wired into any agent workflow.

**Independent Test**: `ss -tlnp | grep 8787` shows binding to `100.92.197.90` only. No services on office2 remain bound to `0.0.0.0`.

**Acceptance Scenarios**:

1. **Given** the transcribe-api is rebound, **When** `ss -tlnp | grep 8787` is checked, **Then** it shows `100.92.197.90:8787`, not `0.0.0.0:8787`.
2. **Given** the transcribe-api is rebound, **When** OpenClaw calls it at `http://100.92.197.90:8787`, **Then** it responds successfully.
3. **Given** the transcribe-api has a systemd unit, **When** office2 reboots, **Then** the service restarts automatically without manual intervention.

---

### User Story 2 - Audio Transcription via OpenClaw (Priority: P1)

Kent needs to send an audio file to OpenClaw and receive a text transcript, enabling voice-based input for the accountability system.

**Why this priority**: Transcription is a prerequisite for WhatsApp voice note processing (F004+). Without it, voice input is unusable.

**Independent Test**: Send a sample audio file to the OpenClaw whisper skill and receive readable English text back.

**Acceptance Scenarios**:

1. **Given** the whisper skill is installed in OpenClaw, **When** a sample `.ogg` audio file is submitted, **Then** a readable English transcript is returned.
2. **Given** the transcribe-api is temporarily unavailable, **When** the skill is invoked, **Then** a clear error message is returned rather than a silent failure.
3. **Given** an audio file in an unsupported format, **When** the skill is invoked, **Then** a descriptive error is returned indicating the format issue.

---

### User Story 3 - Managed and Documented Service (Priority: P2)

Kent or a future agent needs deployment config committed to the repo and an ops runbook so the transcription service is reproducible and maintainable.

**Why this priority**: Operational documentation ensures the service can be managed without tribal knowledge.

**Independent Test**: A new agent session can follow the runbook to restart the service and understand its API contract.

**Acceptance Scenarios**:

1. **Given** the runbook exists at `docs/handbooks/transcribe-ops.md`, **When** an operator reads it, **Then** they can start, stop, restart, and understand the API contract.
2. **Given** deployment config is committed, **When** the service needs redeployment, **Then** `scripts/transcribe/` contains everything needed to reproduce the setup.

---

### Edge Cases

- What happens when Docker Compose is not installed? → The systemd unit calls `docker compose`; if Compose plugin is missing, the service fails with a clear error in journalctl.
- What happens when the Whisper model files are missing? → The container should fail to start with a log message. Models are excluded from backup (re-downloadable) — document the re-download procedure in the runbook.
- What happens when the audio file is too large? → Document the size limit in the API contract. The skill should surface the error from the transcribe-api, not silently truncate.
- What happens when the transcribe-api is slow (large audio file)? → The skill should have a reasonable timeout and return an error if transcription takes too long.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Security rebind | As Kent, I want the transcribe-api bound to the Tailscale IP so that it's not exposed to the public internet. | High | Open |
| FR-002 | systemd service | As Kent, I want the transcribe-api managed by systemd so that it restarts on boot and failure. | High | Open |
| FR-003 | API contract documentation | As Kent, I want the transcribe-api's HTTP contract documented so that the skill and future integrations have a clear interface spec. | High | Open |
| FR-004 | OpenClaw whisper skill | As Kent, I want an OpenClaw skill that transcribes audio files so that voice input can be processed by the system. | High | Open |
| FR-005 | End-to-end verification | As Kent, I want to verify that a sample audio file produces a correct transcript end-to-end so that I can trust the skill works. | High | Open |
| FR-006 | Ops runbook | As Kent, I want an operations runbook for the transcription service so that maintenance is straightforward. | Medium | Open |
| FR-007 | Architecture doc updates | As Kent, I want architecture documentation updated to reflect the security hardening and service changes. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Service availability | Transcribe service restarts automatically after failure or reboot within 30 seconds | Reliability | High | Open |
| NFR-002 | Transcription speed | A 30-second voice note is transcribed within 30 seconds (within the 60-second inbox processing target) | Performance | High | Open |
| NFR-003 | Error clarity | Transcription failures return human-readable error messages, not stack traces or empty responses | Reliability | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Tailscale-only binding | Port 8787 must bind to `100.92.197.90`, never `0.0.0.0` | Security | High | Open |
| C-002 | No image rebuild | Reuse existing Docker image — do not rebuild or replace the transcribe-api image | Architecture | High | Open |
| C-003 | Agent SSH identity | All commands via `ssh office2-claude`; sudo presented to Kent | Security | High | Open |
| C-004 | Compose-based deployment | Use existing Docker Compose approach; systemd wraps `docker compose up -d` | Architecture | High | Open |
| C-005 | Skill version control | Skill source committed to repo for reproducibility | Architecture | Medium | Open |

### Key Entities

- **Transcribe API**: Existing Docker container running a Whisper model. Accepts audio input via HTTP, returns transcript text.
- **OpenClaw Whisper Skill**: An OpenClaw skill that mediates between OpenClaw and the transcribe-api, accepting audio and returning text.
- **systemd Service**: `transcribe.service` wrapping `docker compose up -d` for lifecycle management.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero services on office2 bound to `0.0.0.0` (verified by `ss -tlnp | grep 0.0.0.0` returning no results for managed services).
- **SC-002**: Transcribe service recovers automatically after failure or reboot within 30 seconds.
- **SC-003**: A 30-second audio sample is transcribed into readable English text within 30 seconds.
- **SC-004**: Transcription errors produce clear, human-readable messages.
- **SC-005**: Deployment config at `scripts/transcribe/` enables full service reproduction from scratch.
- **SC-006**: Runbook at `docs/handbooks/transcribe-ops.md` passes CI validation and documents the API contract.
- **SC-007**: Architecture docs show no `0.0.0.0` bindings remaining in `network-topology.json`.
