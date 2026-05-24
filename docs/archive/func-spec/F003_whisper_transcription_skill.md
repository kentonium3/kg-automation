---
title: "F003: Whisper Transcription Skill"
doc_type: func-spec
status: draft
feature: F003
---

# F003: Whisper Transcription Skill

**Version**: 1.0
**Priority**: HIGH
**Type**: Skill + Security Hardening

---

## Executive Summary

A Whisper transcription service is already running on office2 (`transcribe-api`
on port 8787), deployed before F001. F004 does not redeploy Whisper — it creates
the OpenClaw skill that calls the existing service, and fixes the service's
security posture (currently bound to `0.0.0.0`, must be rebound to the Tailscale
IP consistent with all other services).

Current gaps:
- ❌ OpenClaw has no skill to transcribe audio
- ❌ `transcribe-api` bound to `0.0.0.0` — security violation per architecture rules
- ❌ `transcribe-api` has no systemd unit — not restart-safe, not version-controlled
- ❌ `transcribe-api` not documented in a runbook

This spec delivers an OpenClaw whisper skill that transcribes WhatsApp voice note
audio, secured and properly managed.

---

## Problem Statement

**Current State:**
```
office2
└── ✅ transcribe-api running (Docker, port 8787, 0.0.0.0) — manual deploy
└── ✅ OpenClaw running (F002)
└── ❌ OpenClaw has no transcription skill
└── ❌ transcribe-api bound to 0.0.0.0 (security violation)
└── ❌ transcribe-api has no systemd unit (not restart-safe)
└── ❌ transcribe-api not in repo, not reproducible
```

**Target State:**
```
office2
└── ✅ transcribe-api running (Docker, port 8787, 100.92.197.90)
└── ✅ transcribe-api managed by systemd (transcribe.service)
└── ✅ transcribe-api config committed to scripts/transcribe/
└── ✅ OpenClaw whisper skill calls transcribe-api at 100.92.197.90:8787
└── ✅ Voice audio → skill → transcript text returned to OpenClaw
└── ✅ Runbook at docs/runbooks/transcribe-ops.md
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Existing service**
   - `docs/design/architecture/data/service-inventory.json` — `transcribe-api`
     entry: Docker image `transcribe_transcribe`, port 8787, `0.0.0.0` bind,
     data at `/data/services/transcribe/`, models excluded from backup
   - SSH to office2 and inspect the running container:
     `docker inspect transcribe_transcribe` or `docker ps` — understand what
     image, volumes, and environment it uses before touching it
   - Identify the API contract: what endpoint does it expose? What does it
     accept (multipart audio? base64? file path?)? What does it return?

2. **OpenClaw skill system**
   - `docs/runbooks/openclaw-ops.md` — skill directory at
     `/home/claude/.openclaw/skills/`
   - OpenClaw skill documentation at https://docs.openclaw.ai — understand
     how skills receive input, call external services, and return results
   - Study how OpenClaw passes WhatsApp voice note audio to a skill

3. **Security posture**
   - `docs/design/architecture/data/network-topology.json` — access rules
     section explicitly states all services must bind to `100.92.197.90`,
     never `0.0.0.0`
   - `docs/design/architecture/change-control.md` — update protocol

4. **F001 and F002 artifacts**
   - `scripts/vikunja/vikunja.service` — systemd unit pattern to copy for
     `transcribe.service`
   - `docs/runbooks/vikunja-ops.md` — runbook format to match

---

## Functional Requirements

### FR-1: Transcribe API Security Hardening

**What it must do:**
- Rebind `transcribe-api` from `0.0.0.0` to `100.92.197.90` (Tailscale IP)
- This requires stopping the container, updating its run configuration, and
  restarting it
- The rebound service must still be reachable from OpenClaw on the same host
  (loopback or Tailscale IP — confirm during planning which works given Docker
  networking on the Tailscale interface)

**Security rule**: `0.0.0.0` binding is prohibited per the architecture access
rules. This is the last remaining `0.0.0.0`-bound service on office2.

**Success criteria:**
- [ ] `ss -tlnp | grep 8787` shows bind to `100.92.197.90`, not `0.0.0.0`
- [ ] transcribe-api is still reachable from OpenClaw after rebind
- [ ] No public exposure confirmed from outside Tailscale

---

### FR-2: Transcribe API systemd Service

**What it must do:**
- Create a systemd unit `transcribe.service` that manages the transcribe-api
  Docker container
- Service starts on boot, restarts on failure, runs as `claude` user
- Docker run config committed to `scripts/transcribe/` in the repo (including
  the correct `100.92.197.90` bind)
- Follows the pattern established by `vikunja.service` (F001)

**Success criteria:**
- [ ] `systemctl is-active transcribe` returns `active`
- [ ] Container restarts automatically after failure
- [ ] `scripts/transcribe/transcribe.service` committed to repo
- [ ] `scripts/transcribe/deploy.sh` committed to repo (reproducible deployment)

---

### FR-3: Transcribe API Contract Documentation

**What it must do:**
- Document the transcribe-api's HTTP contract during the planning/research phase:
  - Endpoint URL and method
  - Input format (audio file format, size limits, accepted MIME types)
  - Output format (transcript text structure, timestamps if any)
  - Error responses
- This contract is required before the OpenClaw skill can be written
- Document in the runbook and in a comment block in the skill file

**Success criteria:**
- [ ] API contract documented in `docs/runbooks/transcribe-ops.md`
- [ ] Accepted audio formats confirmed (at minimum: ogg/opus from WhatsApp
  voice notes, mp4/m4a from general audio)

---

### FR-4: OpenClaw Whisper Skill

**What it must do:**
- Create an OpenClaw skill that:
  1. Accepts audio input (from a WhatsApp voice note payload)
  2. Calls `transcribe-api` at `http://100.92.197.90:8787` (or confirmed
     equivalent) with the audio data
  3. Returns the transcript text to OpenClaw for further processing
- The skill must handle transcription errors gracefully — if transcription
  fails, return a clear error rather than silently failing
- The skill must declare the `transcribe-api` endpoint in its configuration,
  not hardcode it in skill logic

**Input context:**
- WhatsApp voice notes are delivered as `audio/ogg` (Opus codec) via the
  Meta Cloud API media endpoint
- OpenClaw receives the media URL or payload — the skill must handle whatever
  format OpenClaw presents (confirm during planning)

**Success criteria:**
- [ ] Skill installed in OpenClaw skill directory
- [ ] Given a WhatsApp voice note, OpenClaw returns transcript text
- [ ] Transcription errors surface as readable messages, not silent failures
- [ ] Skill source committed to `scripts/openclaw/skills/whisper/` in repo

---

### FR-5: End-to-End Verification

**What it must do:**
- Send a real WhatsApp voice note to the system number and confirm transcript
  is produced
- Note: This requires F003 (WhatsApp channel) to be complete. If F003 is not
  yet deployed, verify by calling the skill directly with a test audio file.
- Direct skill verification (F003 not required):
  - Use a sample `.ogg` voice file
  - Call the skill via OpenClaw's skill test mechanism
  - Confirm transcript output

**Success criteria:**
- [ ] Direct skill test with sample audio file produces transcript
- [ ] Transcript is readable English (not garbled)
- [ ] Response time acceptable per constitution target (inbox processing
  within 60 seconds — transcription should complete well within that)
- [ ] End-to-end WhatsApp voice note → transcript verified once F003 is live
  (can be tracked as a follow-up acceptance criterion)

---

### FR-6: Operations Runbook

**What it must do:**
- Create `docs/runbooks/transcribe-ops.md` covering:
  - What the transcribe-api is and which Whisper model it runs
  - How to start/stop/restart the service
  - The API contract (endpoint, input, output)
  - How to update the Docker image
  - How to check transcription logs
  - Known audio format limitations

**Success criteria:**
- [ ] Runbook exists at `docs/runbooks/transcribe-ops.md`
- [ ] API contract documented
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F003 changes the deployed system. Update the following as part of
implementation — not as a separate task.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Update `transcribe-api` entry: change `bind_ip` from `0.0.0.0` to `100.92.197.90`; add `systemd_unit: transcribe.service`; update `deployed_by` to `F003` |
| `data/network-topology.json` | Update port 8787 entry: change `bind_ip` to `100.92.197.90`, remove `"WARNING: bound to all interfaces"`, set `public_exposure: none` |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Update transcribe-api row: bind IP, systemd unit, deployed_by; add F004 Deployment Details section |
| `security-posture.md` | Note that `0.0.0.0` binding has been eliminated — all services now Tailscale-only |

### No Changes Required

- `credential-manifest.json` — no new credentials
- `hardware-inventory.json` — no hardware changes
- `data-flows.json` / `data-flows.md` — full data flow documented in F006
- `physical-topology.md` — no topology changes

**Success criteria:**
- [ ] `network-topology.json` shows no `0.0.0.0` bindings
- [ ] `service-inventory.json` has `transcribe-api` updated with `F003`
- [ ] `security-posture.md` reflects elimination of last `0.0.0.0` service

---

## Out of Scope

- ❌ Redeploying Whisper from scratch — existing service is reused
- ❌ Intent parsing of transcripts — F006
- ❌ Task creation from transcripts — F006+
- ❌ Path B (Obsidian inbox) integration — F007 (inbox-processor skill)
- ❌ WhatsApp channel setup — F004
- ❌ Whisper model selection or tuning — existing model is used as-is
- ❌ Changing the transcribe-api Docker image — rebind only, no image change

---

## Success Criteria

**Complete when:**

### Security
- [ ] `transcribe-api` bound to `100.92.197.90`, not `0.0.0.0`
- [ ] No services on office2 bound to `0.0.0.0`

### Service Management
- [ ] `transcribe.service` running and enabled
- [ ] Deploy config committed to `scripts/transcribe/`

### Skill
- [ ] OpenClaw whisper skill installed and functional
- [ ] Direct audio test produces correct transcript
- [ ] Skill source in `scripts/openclaw/skills/whisper/`

### Documentation
- [ ] `docs/runbooks/transcribe-ops.md` complete and CI-passing
- [ ] Architecture docs updated — `0.0.0.0` eliminated from network topology

---

## Architecture Principles

### Reuse What Exists

The transcribe-api is running and working. Installing a second Whisper
instance would waste resources, duplicate maintenance burden, and create
confusion. F004 wires up what's already there.

### Zero 0.0.0.0 Bindings

This feature eliminates the last `0.0.0.0`-bound service on office2. After
F004, every service is Tailscale-only. This is the security posture the
architecture requires and the constitution mandates.

---

## Constitutional Compliance

✅ **Security over convenience**: Rebinding to Tailscale IP closes the last
public exposure gap on office2.

✅ **Zero manual maintenance**: `transcribe.service` systemd unit ensures
the service restarts without human intervention.

✅ **Docs adjacent**: API contract documented in runbook alongside deployment.

✅ **Linux/office2 target**: All changes target Ubuntu 24.04 LTS.

---

## Risk Considerations

**Risk: Rebinding breaks OpenClaw → transcribe-api connectivity**
- Docker networking on a Tailscale-bound interface may behave differently
  than 0.0.0.0. OpenClaw running on the same host may need to use the
  Tailscale IP rather than localhost to reach the rebound service.
- Mitigation: Planning phase inspects Docker network mode of existing
  container before rebinding. Test connectivity immediately after rebind
  before proceeding.

**Risk: Existing container state is lost during rebind**
- If the container is rebuilt rather than just restarted with new config,
  any runtime state is lost (model cache, etc.).
- Mitigation: Models are excluded from backup intentionally (re-downloadable).
  The rebind should be done by updating the run config and restarting, not
  by removing and recreating the image.

**Risk: WhatsApp voice note format not supported**
- WhatsApp voice notes are `audio/ogg` with Opus codec. If the existing
  Whisper deployment doesn't accept this format natively, conversion may
  be needed.
- Mitigation: Planning phase confirms accepted audio formats against the
  API contract before writing the skill.

---

## Notes for Implementation

**Discovery first:**
- Before writing any code, SSH to office2 and run
  `docker inspect transcribe_transcribe` to get the full container config
- Confirm the API endpoint with a test call:
  `curl -X POST http://localhost:8787/transcribe -F "file=@test.ogg"`
  (or equivalent based on what the API expects)
- The API contract must be known before the skill can be written

**Rebind approach:**
- If the container is run via `docker run`, update the `-p` flag from
  `0.0.0.0:8787:8787` to `100.92.197.90:8787:8787`
- If the container is run via Docker Compose, update the `ports` mapping
- Capture the final run config in `scripts/transcribe/` before the rebind
  so the deployment is reproducible

**OpenClaw skill placement:**
- Skills are installed to `/home/claude/.openclaw/skills/`
- Skill source should also be committed to `scripts/openclaw/skills/whisper/`
  in the repo for reproducibility and version control

---

**END OF SPECIFICATION**
