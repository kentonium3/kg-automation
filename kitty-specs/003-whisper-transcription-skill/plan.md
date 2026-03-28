# Implementation Plan: Whisper Transcription Skill

**Branch**: `003-whisper-transcription-skill` | **Date**: 2026-03-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/003-whisper-transcription-skill/spec.md`

## Summary

Harden the existing `transcribe-api` Docker service by rebinding from `0.0.0.0` to `100.92.197.90`, wrapping it in a systemd unit via Docker Compose, and committing the deployment config. Build an OpenClaw SKILL.md that documents the transcription API contract and instructs the agent how to transcribe audio. Eliminate the last `0.0.0.0` binding on office2.

## Technical Context

**Language/Version**: Bash (deployment scripts), Markdown (OpenClaw skill)
**Primary Dependencies**: Docker, Docker Compose (existing), faster-whisper (existing transcribe-api)
**Storage**: Transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/`
**Testing**: Manual verification — submit audio, confirm transcript
**Target Platform**: Ubuntu 24.04 LTS on office2
**Project Type**: Infrastructure hardening + skill creation
**Performance Goals**: 30-second audio transcribed within 30 seconds
**Constraints**: Tailscale-only binding, no image rebuild, Compose-based deployment
**Scale/Scope**: Single service rebind + one OpenClaw skill

## Research Findings

### Transcribe API Contract (discovered from live service)

- **FastAPI** service, OpenAPI spec at `/openapi.json`
- **Model**: `medium.en` (faster-whisper)
- **Async pattern**: POST returns job ID, poll for result

**Endpoints**:
- `POST /transcribe/file` — multipart upload, returns `TranscriptMeta` (id, status)
- `POST /transcribe/url` — JSON body with URL, returns `TranscriptMeta`
- `GET /transcripts/{id}` — retrieve transcript by ID
- `GET /transcripts/{id}/text` — plain text only
- `GET /transcripts` — list recent transcripts
- `GET /health` — health check

**Workflow**: Upload audio → get job ID → poll `/transcripts/{id}` until status is complete → read `/transcripts/{id}/text`

### Docker Compose Config (existing)

- Image: `transcribe_transcribe` (locally built)
- Ports: `8787:8787` (currently `0.0.0.0`)
- Volumes: `/data/transcripts`, `/data/services/transcribe/models`
- Environment: `WHISPER_MODEL_SIZE=medium.en`, 4 workers, 4GB memory limit
- `restart: unless-stopped` (Docker-level, not systemd)

### OpenClaw Skill Format (researched)

- Skills are `SKILL.md` files with YAML frontmatter
- They are **markdown prompt documents**, not executable code
- The skill teaches the agent how to use its built-in tools (exec, web_search, etc.) to accomplish a task
- For calling the transcribe API, the skill instructs the agent to use `curl` via the exec tool
- Skills can be placed in `~/.openclaw/skills/` or workspace `skills/` directories

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Tailscale-only binding | ✅ Pass | Rebinding from `0.0.0.0` to `100.92.197.90` |
| No image rebuild | ✅ Pass | Reusing existing image, changing only port binding |
| Agent traceability | ✅ Pass | `ssh office2-claude` only |
| Documentation adjacent | ✅ Pass | Runbook and architecture docs updated |
| No credentials needed | ✅ Pass | transcribe-api has no auth |

## Project Structure

### Documentation (this feature)

```
kitty-specs/003-whisper-transcription-skill/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```
scripts/transcribe/
├── docker-compose.yml   # Captured from office2 with corrected port binding
├── transcribe.service   # systemd unit wrapping docker compose
└── deploy.sh            # Deployment helper script

scripts/openclaw/skills/whisper/
└── SKILL.md             # OpenClaw skill for audio transcription

docs/handbooks/
└── transcribe-ops.md    # Operations runbook
```

**Structure Decision**: Infrastructure hardening feature. Deployment scripts committed to `scripts/transcribe/`. OpenClaw skill source committed to `scripts/openclaw/skills/whisper/` and symlinked/copied to the OpenClaw skills directory on office2.

## Dependency Graph

```
WP-01: Security hardening (rebind + systemd + deploy config)
  └── WP-02: OpenClaw skill + API contract documentation
  └── WP-03: Ops runbook + architecture docs + acceptance testing
```

WP-01 must complete first (service must be rebound before skill uses it). WP-02 and WP-03 can proceed in parallel after WP-01.
