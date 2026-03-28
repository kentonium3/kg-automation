---
name: whisper
description: Transcribe audio files using the Whisper transcription service
version: 1.0.0
---

# Whisper Transcription Skill

You can transcribe audio files using the Whisper transcription service running on office2. The service uses faster-whisper with the `medium.en` model and exposes a REST API.

## API Base URL

```
http://100.92.197.90:8787
```

## API Contract

| Endpoint | Method | Content-Type | Purpose |
|----------|--------|-------------|---------|
| `POST /transcribe/file` | POST | `multipart/form-data` | Upload an audio file for transcription |
| `POST /transcribe/url` | POST | `application/json` | Submit an audio URL for transcription |
| `GET /transcripts/{id}` | GET | — | Get transcript status and full result |
| `GET /transcripts/{id}/text` | GET | — | Get plain text transcript only |
| `GET /transcripts` | GET | — | List recent transcripts |
| `GET /health` | GET | — | Health check |

## Transcription Workflow

Transcription is **asynchronous**. You upload the audio, receive a job ID, poll for completion, then retrieve the text. Use the `exec` tool to run these curl commands.

### Step 1 — Check service health

Before submitting audio, verify the service is running:

```bash
curl -s http://100.92.197.90:8787/health
```

If this fails or returns an error, the transcription service is down. Report this to the user.

### Step 2 — Upload audio file

```bash
curl -s -X POST http://100.92.197.90:8787/transcribe/file \
  -F "file=@/path/to/audio.ogg" \
  -H "Accept: application/json"
```

**Response** (JSON):
```json
{"id": "<job_id>", "status": "queued", "filename": "audio.ogg", "created_at": "..."}
```

Save the `id` value for the next steps.

To submit audio from a URL instead:

```bash
curl -s -X POST http://100.92.197.90:8787/transcribe/url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/audio.ogg"}'
```

### Step 3 — Poll for completion

```bash
curl -s http://100.92.197.90:8787/transcripts/<job_id>
```

Repeat every **2 seconds** until the `status` field is `"completed"` or `"failed"`.

**Maximum polling duration**: 60 seconds (30 polls at 2-second intervals). If the job has not completed after 60 seconds, report a timeout to the user.

**Status values**:
- `queued` — waiting to be processed
- `processing` — transcription in progress
- `completed` — transcript is ready
- `failed` — transcription failed

### Step 4 — Retrieve transcript text

Once status is `"completed"`, get the plain text:

```bash
curl -s http://100.92.197.90:8787/transcripts/<job_id>/text
```

This returns the transcript as plain text. Present it to the user.

To get the full transcript object with metadata:

```bash
curl -s http://100.92.197.90:8787/transcripts/<job_id>
```

### Listing recent transcripts

To see recent transcription jobs:

```bash
curl -s http://100.92.197.90:8787/transcripts
```

## Error Handling

- **Health check fails**: Report that the Whisper transcription service at `100.92.197.90:8787` is unreachable. The service may need to be restarted on office2.
- **Upload returns non-200**: Report the HTTP status code and the response body to the user. Common causes: unsupported file format, file too large, or service error.
- **Status becomes `"failed"`**: Read the `error` field from the transcript object (`GET /transcripts/<job_id>`) and report it to the user.
- **Polling exceeds 60 seconds**: Report a timeout. The audio file may be very long or the service may be overloaded. Suggest the user try again later or with a shorter audio clip.
- **Empty transcript**: The audio may contain no speech, be too noisy, or be in a language other than English. Report this to the user.

## Supported Audio Formats

The service accepts most common audio formats via ffmpeg:

- `audio/ogg` (Opus codec) — WhatsApp voice notes
- `audio/mp4`, `audio/m4a` — general mobile/desktop audio
- `audio/wav` — uncompressed audio
- `audio/mpeg` (`mp3`) — compressed audio
- Most other formats supported by ffmpeg

The model is `medium.en` (English-optimized). Non-English audio will produce poor results.

## Usage Examples

**"Transcribe this voice note"** or **"What did they say in this audio?"**:
1. Upload the file with `POST /transcribe/file`
2. Poll `GET /transcripts/<job_id>` until complete
3. Retrieve text with `GET /transcripts/<job_id>/text`
4. Present the transcript to the user

**"Check if the transcription service is running"**:
```bash
curl -s http://100.92.197.90:8787/health
```

**"Show me recent transcriptions"**:
```bash
curl -s http://100.92.197.90:8787/transcripts
```
