---
title: Transcribe API Operations Runbook
doc_type: runbook
audience: agent-executable
status: draft
---

# Transcribe API Operations Runbook

This runbook covers day-to-day operations for the Whisper transcription API service running on office2.

## Service Overview

The transcribe service provides an HTTP API for audio transcription using faster-whisper.

**Service name**: `transcribe` (systemd)
**Container name**: managed via Docker Compose
**Image**: `transcribe_transcribe` (locally built)
**Port**: `100.92.197.90:8787` (Tailscale IP only)
**Model**: `medium.en` (faster-whisper), English only
**Workers**: 4
**Memory limit**: 4GB
**Compose file**: `/data/services/transcribe/docker-compose.yml`
**Data**: transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/`

## Service Management

### Check status

```bash
# As any user (no sudo required):
systemctl status transcribe
docker ps | grep transcribe
```

### Start / Stop / Restart

```bash
# Requires sudo (run as kgale, not claude):
sudo systemctl start transcribe
sudo systemctl stop transcribe
sudo systemctl restart transcribe
```

### View logs

```bash
# systemd journal (no sudo required):
journalctl -u transcribe -f              # follow live
journalctl -u transcribe --since "1 hour ago"
journalctl -u transcribe --since today

# Docker Compose logs (no sudo required):
docker compose -f /data/services/transcribe/docker-compose.yml logs -f
docker compose -f /data/services/transcribe/docker-compose.yml logs --tail 50
```

## API Contract

### Health Check

```
GET /health
```

Returns service health status.

```bash
curl -s http://100.92.197.90:8787/health
```

### Transcribe File (multipart upload)

```
POST /transcribe/file
Content-Type: multipart/form-data
```

Upload an audio file for transcription. Returns a `TranscriptMeta` object with `id` and `status`.

```bash
curl -X POST http://100.92.197.90:8787/transcribe/file \
  -F "file=@recording.wav"
```

Response:

```json
{"id": "abc123", "status": "processing"}
```

### Transcribe URL

```
POST /transcribe/url
Content-Type: application/json
```

Submit a URL pointing to an audio file. Returns a `TranscriptMeta` object with `id` and `status`.

```bash
curl -X POST http://100.92.197.90:8787/transcribe/url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/audio.wav"}'
```

Response:

```json
{"id": "abc123", "status": "processing"}
```

### Get Transcript

```
GET /transcripts/{id}
```

Returns the full transcript object including metadata and segments.

```bash
curl -s http://100.92.197.90:8787/transcripts/abc123
```

### Get Transcript Text

```
GET /transcripts/{id}/text
```

Returns the plain text of the transcript.

```bash
curl -s http://100.92.197.90:8787/transcripts/abc123/text
```

### List Transcripts

```
GET /transcripts
```

Returns a list of recent transcripts.

```bash
curl -s http://100.92.197.90:8787/transcripts
```

### Async Workflow

The transcription API uses an asynchronous workflow:

1. **Upload**: `POST /transcribe/file` or `POST /transcribe/url` to submit audio
2. **Poll**: `GET /transcripts/{id}` to check status until `status` is `"completed"`
3. **Read**: `GET /transcripts/{id}/text` to retrieve the plain text result

## Data and Backups

### Data locations

- **Transcripts**: `/data/transcripts/`
- **Models**: `/data/services/transcribe/models/`
- **Compose and config**: `/data/services/transcribe/`

### Backup

Transcript data is automatically included in the nightly Restic backup because it resides under `/data/transcripts/` and `/data/services/`, which are in the backup scope.

**Models are excluded from backup** — they are large and re-downloadable from Hugging Face.

## Updating the Docker Image

The image is locally built from the Dockerfile in `/data/services/transcribe/`.

1. **Rebuild the image**:
   ```bash
   cd /data/services/transcribe && docker compose build
   ```
2. **Restart the service** (requires sudo — run as kgale):
   ```bash
   sudo systemctl restart transcribe
   ```
3. **Verify**:
   ```bash
   systemctl status transcribe
   curl -s http://100.92.197.90:8787/health
   ```

## Known Limitations

- **Model**: `medium.en` — English only. Non-English audio will produce poor results.
- **Memory limit**: 4GB — very large audio files may cause out-of-memory failures.
- **Models excluded from backup**: If models are deleted or corrupted, they must be re-downloaded. Rebuilding the image (`docker compose build`) will re-download them from Hugging Face.
- **Model missing on start**: If models are not present, the container will fail to start. Rebuild the image to re-download.

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Service won't start | `journalctl -u transcribe -e` and `docker compose logs` | Check for model loading errors or port conflicts |
| Port not bound | `ss -tlnp \| grep 8787` on office2 | Verify compose file has `100.92.197.90:8787:8787` |
| Transcription fails | Container logs for model loading errors | Check `docker stats` for memory pressure |
| Slow transcription | `docker stats` — check memory and CPU | Verify worker count and memory limit in compose file |
| Connection refused | `systemctl status transcribe` | Start service if stopped |
| Port bound to 0.0.0.0 | `ss -tlnp \| grep 8787` | **Security issue** — stop service, check compose file bind address |

## Security Baseline Reset

After deploying or upgrading the transcribe service, the security monitoring baselines on office2 need to be updated to reflect the new expected state.

### What changes

After a transcribe deployment or upgrade, the following are new expected state:

- Docker container running for transcribe
- systemd service `transcribe.service` enabled and active
- Port 8787 listening on `100.92.197.90`

### Reset procedure

This step may require sudo. Run as kgale if needed:

```bash
# Check current baseline status:
ls -la /data/services/security-monitor/baselines/

# Regenerate baselines:
cd /data/services/security-monitor
./scripts/generate-baselines.sh
```

### When to reset

- After initial transcribe deployment (F003)
- After any image rebuild that changes the container
- After any change to the systemd service file or port binding
