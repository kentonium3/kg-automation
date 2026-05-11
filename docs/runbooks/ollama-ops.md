---
title: Ollama Operations Runbook
doc_type: runbook
audience: agents_and_humans
status: draft
last_updated: '2026-05-11'
updated_by: '#211'
---

# Ollama Operations Runbook

This runbook covers day-to-day operations for the Ollama local LLM inference service running on office2.

## Service Overview

Ollama is a host-binary LLM inference runtime, GPU-accelerated via the GTX 1060. It was installed alongside the GPU rollout in #80 as a forward-looking capability — there is no active agent workload pointing at it yet. The transcribe-api service shares the same GPU; see [Relationship to transcribe-api](#relationship-to-transcribe-api).

**Service name**: `ollama.service` (systemd, system-level, runs as `ollama` user)
**Binary**: `/usr/local/bin/ollama` (installed via official `ollama.com/install.sh`)
**Port**: `127.0.0.1:11434` — **localhost only**, not exposed via Tailscale
**Version baseline**: `0.23.2` (deployed 2026-05-08)
**GPU**: GTX 1060 6GB, auto-detected via NVIDIA driver
**Data path**: `/usr/share/ollama/.ollama/` (models under `models/`)
**Backup**: excluded — models are re-pullable from ollama.com; minimal user state
**Deployed by**: `issue-80-gpu-install` (2026-05-08)

**Source-of-truth in this repo**:

- Service-inventory entry: [`docs/design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>) (`ollama`), [`docs/design/architecture/service-inventory.md`](<../design/architecture/service-inventory.md>) §Ollama
- Hardware (GPU): [`docs/design/architecture/data/hardware-inventory.json`](<../design/architecture/data/hardware-inventory.json>) `hosts[0].gpu`

## Service Details

| Surface | Value |
|---|---|
| Binary | `/usr/local/bin/ollama` |
| Systemd unit | `ollama.service` (system-level) |
| Run-as user | `ollama` |
| Listen address | `127.0.0.1:11434` |
| Tailscale exposure | none (localhost only — use SSH port-forward or an explicit `tailscale serve` rule if remote access is later needed) |
| Models directory | `/usr/share/ollama/.ollama/models/` (not world-readable; inspect via `ollama list`) |
| Config file | `/etc/systemd/system/ollama.service` |

## Health Check

The `claude` user can hit the API directly — no sudo required:

```
curl -s http://127.0.0.1:11434/api/version
```

Expected response: `{"version":"0.23.2"}` (or whatever the current installed version is).

If the curl returns nothing or a connection-refused error, the service is down — see [Troubleshooting](#troubleshooting).

## Starting / Stopping / Restarting

Ollama is a system-level systemd unit, so service control requires sudo. The `claude` user cannot do this — present the command to Kent and have him run it as `kgale`:

```
sudo systemctl start ollama
```

```
sudo systemctl stop ollama
```

```
sudo systemctl restart ollama
```

Status checks do **not** require sudo:

```
systemctl status ollama --no-pager
```

```
journalctl -u ollama -n 100 --no-pager
```

## Pulling a Model

The `claude` user can pull models without sudo — the `ollama` CLI talks to the running service over the local socket.

```
ollama pull <model-name>
```

Example:

```
ollama pull llama3.2:3b
```

Models are stored under `/usr/share/ollama/.ollama/models/`. They are excluded from Restic backups by design — re-pullable from ollama.com, no user data.

List installed models:

```
ollama list
```

Remove a model:

```
ollama rm <model-name>
```

## GPU Verification

Confirm a model is actually using the GPU rather than falling back to CPU:

```
ollama run llama3.2:3b "hello"
```

A 3B-parameter model on the GTX 1060 should complete a short prompt in **roughly 2 seconds wall-clock**. If it takes 30+ seconds, the run is on CPU — investigate driver / GPU detection per [Troubleshooting](#troubleshooting).

Cross-check VRAM occupancy while a prompt is in flight:

```
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

Idle baseline with no model resident: ~50–100 MiB used. With `llama3.2:3b` loaded: expect a few hundred MiB to a few GiB depending on quantization. With both Ollama and transcribe-api active, the GTX 1060's 6 GiB ceiling is the bound — see [Relationship to transcribe-api](#relationship-to-transcribe-api).

## Relationship to transcribe-api

Both Ollama and [`transcribe-api`](<./transcribe-ops.md>) run on office2's GTX 1060. They are independent services (Ollama is a host binary; transcribe is a Docker container with `nvidia-container-toolkit`) but share the same 6 GiB VRAM pool:

- `transcribe-api` holds ~830 MiB resident for the `medium.en` Whisper model at `compute_type=int8` (constant while the service is up).
- Ollama only allocates VRAM during an inference call and releases it shortly after the model becomes idle (default keep-alive 5 minutes).

Under sustained simultaneous load, VRAM contention is possible — Ollama may fail to load a large model, or transcribe may experience throughput degradation. Mitigations:

- Prefer 3B-parameter quantized models on Ollama (`llama3.2:3b` is the validated baseline).
- If contention emerges as a real workload pattern, consider a larger GPU or moving one of the two services off office2.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl http://127.0.0.1:11434/api/version` fails or hangs | Service not running | `systemctl status ollama` — if inactive, restart via sudo per [Starting / Stopping / Restarting](#starting--stopping--restarting); inspect `journalctl -u ollama` for boot-time errors |
| `ollama run` is slow (~30s+ for a short prompt on `llama3.2:3b`) | Running on CPU rather than GPU | Confirm driver: `nvidia-smi` — must show GTX 1060 and a driver version. Check `journalctl -u ollama` for "no compatible GPUs found" or CUDA errors. Verify CUDA stack is intact (driver `535.288.01`, CUDA 12.2 per hardware inventory). Restart ollama after any driver change. |
| `ollama pull` hangs or fails | Outbound network to ollama.com blocked or registry transient error | Retry. If persistent, test connectivity: `curl -s https://registry.ollama.com -I`. office2 is Tailscale-gated but has unrestricted outbound — UFW egress is permissive. |
| Port 11434 collision on startup | Another process bound to 11434 | `ss -tlnp \| grep 11434` (need sudo for the pid name). Stop the conflicting process; restart ollama. No other kg-automation service currently uses 11434. |
| VRAM exhaustion (`failed to load model` while transcribe-api is active) | GTX 1060 6 GiB ceiling exceeded | Either pause transcribe-api temporarily (`sudo systemctl stop transcribe`) or use a smaller-quantization Ollama model. See [Relationship to transcribe-api](#relationship-to-transcribe-api) for sizing. |
| `ollama list` returns nothing after a pull | Pull failed silently or interrupted | Re-pull. The models directory is owned by the `ollama` user — claude cannot inspect it directly, but `ollama list` is the authoritative answer. |
