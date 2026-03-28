# Research: Whisper Transcription Skill

**Feature**: 003-whisper-transcription-skill
**Date**: 2026-03-28

## R-001: Transcribe API Contract

**Decision**: Use the existing FastAPI-based transcription service with its async job pattern.

**API Contract** (discovered from live OpenAPI spec at `/openapi.json`):

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/health` | GET | — | Health status |
| `/transcribe/file` | POST | Multipart file upload | `TranscriptMeta` (id, status) |
| `/transcribe/url` | POST | JSON `{"url": "..."}` | `TranscriptMeta` (id, status) |
| `/transcripts/{id}` | GET | — | Full transcript object |
| `/transcripts/{id}/text` | GET | — | Plain text transcript |
| `/transcripts` | GET | `?limit=N&status=S` | List of recent transcripts |

**Async workflow**: Upload → get job ID → poll status → read text when complete.

**Model**: `medium.en` (faster-whisper), 4 workers, 4GB memory limit.

## R-002: Docker Compose Rebind Approach

**Decision**: Update the `ports` mapping in `docker-compose.yml` from `"8787:8787"` to `"100.92.197.90:8787:8787"` and wrap with a systemd unit.

**Rationale**: Kent's direction — keep Docker Compose, add systemd for lifecycle management. The systemd unit calls `docker compose up -d` and `docker compose down` for start/stop.

**Current Compose file**: `/data/services/transcribe/docker-compose.yml`. Image is locally built (`build: .`). Volumes: `/data/transcripts` and `/data/services/transcribe/models`.

## R-003: OpenClaw Skill Format

**Decision**: Create a `SKILL.md` markdown file that documents the transcription API and instructs the agent to use `curl` via its exec tool.

**Rationale**: OpenClaw skills are markdown prompt documents, not executable code. They teach the agent what tools to use and how. For calling the transcribe API, the skill provides the API contract and step-by-step instructions using curl or equivalent.

**Skill location**: `~/.openclaw/skills/whisper/SKILL.md` on office2 (runtime), `scripts/openclaw/skills/whisper/SKILL.md` in repo (version control).

## R-004: Connectivity After Rebind

**Decision**: After rebinding to `100.92.197.90:8787`, OpenClaw (running on the same host) accesses the service via the Tailscale IP, not localhost.

**Rationale**: When Docker binds to a specific IP, the service is only reachable on that IP. Since both OpenClaw and transcribe-api run on office2, the agent uses `http://100.92.197.90:8787` in skill instructions.

**Risk**: If Tailscale is down, the service is unreachable even locally. This is acceptable per the architecture — Tailscale-only is the security requirement.
