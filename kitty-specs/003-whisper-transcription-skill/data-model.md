# Data Model: Whisper Transcription Skill

**Feature**: 003-whisper-transcription-skill
**Date**: 2026-03-28

## Overview

No new data models created. This feature reuses the existing transcribe-api and its data structures.

## Transcribe API Entities (existing, documented for reference)

### TranscriptMeta

Returned by `POST /transcribe/file` and `POST /transcribe/url`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | yes | Unique transcript identifier |
| status | string | yes | Job status (queued, processing, complete, error) |
| title | string | no | Optional title |
| tags | string[] | no | Optional tags |
| source | string | no | Source reference |
| duration_seconds | number | no | Audio duration |
| created_at | string | yes | Timestamp |
| file | string | no | File path reference |

### File System Artifacts

```
/data/services/transcribe/
├── docker-compose.yml      # Updated with Tailscale IP binding
├── Dockerfile              # Existing, not modified
├── app/                    # Application code, not modified
├── models/                 # Whisper models (excluded from backup)
├── requirements.txt        # Python deps, not modified
└── scripts/                # Utility scripts

/data/transcripts/          # Output directory for completed transcripts
```
