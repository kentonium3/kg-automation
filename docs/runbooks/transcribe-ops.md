---
title: Transcribe API Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Transcribe API Operations Runbook

This runbook covers day-to-day operations for the Whisper transcription API service running on office2.

## Service Overview

The transcribe service provides an HTTP API for audio transcription using faster-whisper.

**Service name**: `transcribe` (systemd)
**Container name**: `transcribe-api` (managed via Docker Compose)
**Image**: `transcribe-transcribe` (locally built)
**Port**: `100.92.197.90:8787` (Tailscale IP only)
**Model**: `medium.en` (faster-whisper), English only
**Workers**: 4
**Memory limit**: 4GB
**GPU**: GTX 1060 6GB via `nvidia-container-toolkit`, `compute_type=int8`, ~830 MiB VRAM, ~7x real-time
**Source in repo**: `services/transcribe/` (Dockerfile, app/, requirements.txt, docker-compose.yml, transcribe.service)
**Compose file on office2**: `/home/claude/kg-automation/services/transcribe/docker-compose.yml` (clone of this repo)
**Data**: transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/` (bind mounts; unchanged when source moved into git in #190)

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
docker compose -f /home/claude/kg-automation/services/transcribe/docker-compose.yml logs -f
docker compose -f /home/claude/kg-automation/services/transcribe/docker-compose.yml logs --tail 50

# Or just by container name:
docker logs -f transcribe-api
docker logs --tail 50 transcribe-api
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

- **Source code**: `services/transcribe/` in the kg-automation repo (clone at `/home/claude/kg-automation/services/transcribe/` on office2)
- **Transcripts**: `/data/transcripts/` (bind mount into container at `/data/transcripts`)
- **Models**: `/data/services/transcribe/models/` (bind mount into container at `/models`)
- **systemd unit (deployed)**: `/etc/systemd/system/transcribe.service`
- **systemd unit (source)**: `services/transcribe/transcribe.service` in repo

### Backup

Transcript data is automatically included in the nightly Restic backup because it resides under `/data/transcripts/` and `/data/services/`, which are in the backup scope.

**Models are excluded from backup** — they are large and re-downloadable from Hugging Face.

**Source code** is backed by git — the repo at `/home/claude/kg-automation/` is included in Restic too, but the canonical source-of-truth is GitHub.

## Updating the Service

Since #190, the source lives in `services/transcribe/` in this repo. The deploy flow is git-based — no scp, no in-place edits on office2.

### Code changes (Dockerfile, app/, requirements.txt, docker-compose.yml)

1. **Edit in your local clone of this repo**, on the Mac. Test locally if possible.
2. **Commit and push** to main:
   ```bash
   cd ~/repos/kg-automation
   git add services/transcribe/
   git commit -m "feat(transcribe): <change description>"
   git push origin main
   ```
3. **Pull on office2** (no sudo required):
   ```bash
   ssh office2-claude "cd /home/claude/kg-automation && git pull origin main"
   ```
4. **Rebuild and restart** (rebuild only needed for code/dep changes; pure config changes can skip `--build`):
   ```bash
   ssh office2-claude "cd /home/claude/kg-automation/services/transcribe && docker compose up -d --build"
   ```
   Or via systemd (which doesn't rebuild — for that, do step above first):
   ```bash
   ssh office2-kgale "sudo systemctl restart transcribe"
   ```
5. **Verify**:
   ```bash
   systemctl status transcribe
   curl -s http://100.92.197.90:8787/health
   nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv  # confirm GPU still in use
   ```

### Systemd unit changes (`services/transcribe/transcribe.service`)

The unit is **not** auto-deployed by `git pull` — it lives under `/etc/systemd/system/` which requires sudo. After editing the source unit in repo:

```bash
ssh office2-kgale "sudo cp /home/claude/kg-automation/services/transcribe/transcribe.service /etc/systemd/system/transcribe.service && sudo systemctl daemon-reload && sudo systemctl restart transcribe"
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
