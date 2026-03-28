---
work_package_id: WP02
title: OpenClaw Whisper Skill and End-to-End Verification
lane: planned
dependencies:
- WP01
requirement_refs:
- C-005
- FR-003
- FR-004
- FR-005
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-03-28T16:22:31Z'
subtasks:
- T007
- T008
- T009
- T010
phase: Phase 2 - Implementation
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-28T16:22:31Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 – OpenClaw Whisper Skill and End-to-End Verification

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP02 --base WP01`

---

## Objectives & Success Criteria

Create an OpenClaw SKILL.md that documents the transcription API contract and instructs the OpenClaw agent to transcribe audio files using curl via the exec tool. Install the skill on office2, commit the source to the repo, and verify end-to-end with a sample audio file.

**Success**:
- `~/.openclaw/skills/whisper/SKILL.md` exists on office2 and is loadable by OpenClaw
- `scripts/openclaw/skills/whisper/SKILL.md` committed to repo
- A sample `.ogg` audio file submitted through the API produces readable English transcript text
- Transcription errors produce clear, human-readable messages (not stack traces or empty responses)

## Context & Constraints

- **SSH**: `ssh office2-claude` only. No sudo needed for this WP.
- **Research**: `kitty-specs/003-whisper-transcription-skill/research.md` (R-001: API contract, R-003: skill format, R-004: connectivity)
- **Data model**: `kitty-specs/003-whisper-transcription-skill/data-model.md` (TranscriptMeta entity)
- **Constraint C-005**: Skill source must be committed to repo for version control
- **API base URL**: `http://100.92.197.90:8787` (Tailscale IP, confirmed reachable after WP01)
- **OpenClaw skill directory**: `~/.openclaw/skills/` on office2 (per `docs/handbooks/openclaw-ops.md`)
- **Skill format**: SKILL.md files with YAML frontmatter — markdown prompt documents, NOT executable code

**PREREQUISITE**: WP01 must be complete. The transcribe-api must be rebound to `100.92.197.90:8787` and reachable before this WP starts.

## Subtasks & Detailed Guidance

### Subtask T007 – Write SKILL.md

**Purpose**: Create the OpenClaw skill file that teaches the agent how to transcribe audio using the transcribe-api. This is a markdown prompt document — it tells the agent what curl commands to run and how to interpret responses.

**Steps**:
1. Create `scripts/openclaw/skills/whisper/SKILL.md` in the repo
2. Include YAML frontmatter with skill metadata:
   ```yaml
   ---
   name: whisper
   description: Transcribe audio files using the Whisper transcription service
   version: 1.0.0
   ---
   ```
3. Document the full API contract in the skill body:

   **Endpoints**:
   | Endpoint | Method | Purpose |
   |----------|--------|---------|
   | `POST /transcribe/file` | Multipart file upload | Submit audio for transcription |
   | `POST /transcribe/url` | JSON body | Submit audio URL for transcription |
   | `GET /transcripts/{id}` | — | Get transcript status and result |
   | `GET /transcripts/{id}/text` | — | Get plain text transcript |
   | `GET /transcripts` | — | List recent transcripts |
   | `GET /health` | — | Health check |

4. Write the async workflow instructions for the agent:

   **Step 1 — Upload audio file**:
   ```bash
   curl -s -X POST http://100.92.197.90:8787/transcribe/file \
     -F "file=@/path/to/audio.ogg" \
     -H "Accept: application/json"
   ```
   Response: `{"id": "<job_id>", "status": "queued", ...}`

   **Step 2 — Poll for completion**:
   ```bash
   curl -s http://100.92.197.90:8787/transcripts/<job_id>
   ```
   Poll every 2 seconds until `status` is `"complete"` or `"error"`.
   Maximum 60 seconds (30 polls at 2-second intervals).

   **Step 3 — Retrieve transcript text**:
   ```bash
   curl -s http://100.92.197.90:8787/transcripts/<job_id>/text
   ```
   Returns plain text transcript.

5. Include error handling instructions:
   - If `POST /transcribe/file` returns non-200: report the HTTP status and response body
   - If status becomes `"error"`: report the error from the transcript object
   - If polling exceeds 60 seconds: report timeout — audio may be too long or service overloaded
   - If health check fails: report service unreachable

6. Include supported audio formats:
   - `audio/ogg` (Opus codec) — WhatsApp voice notes
   - `audio/mp4`, `audio/m4a` — general audio
   - `audio/wav`, `audio/mpeg` — standard formats
   - Note: faster-whisper supports most audio formats via ffmpeg

7. Include usage examples:
   - "Transcribe this voice note" → upload file, poll, return text
   - "What did they say in this audio?" → same workflow
   - Health check: `curl -s http://100.92.197.90:8787/health`

**Files**:
- `scripts/openclaw/skills/whisper/SKILL.md` (new file in repo)

**Validation**:
- [ ] Skill has YAML frontmatter with name, description, version
- [ ] Full API contract documented with all endpoints
- [ ] Async workflow (upload → poll → read) clearly explained with curl examples
- [ ] Error handling guidance included
- [ ] Endpoint URL is `http://100.92.197.90:8787` (Tailscale IP)
- [ ] No hardcoded secrets or credentials

**Parallel?**: No — must be written before T008.

### Subtask T008 – Install Skill on office2

**Purpose**: Deploy the SKILL.md to the OpenClaw skills directory on office2 so OpenClaw can use it.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Create the skill directory:
   ```bash
   mkdir -p ~/.openclaw/skills/whisper
   ```
3. Copy the SKILL.md from the repo to office2:
   ```bash
   scp scripts/openclaw/skills/whisper/SKILL.md office2-claude:~/.openclaw/skills/whisper/SKILL.md
   ```
   Or write the file directly via SSH if scp is impractical from the worktree.
4. Verify the file exists and is readable:
   ```bash
   ls -la ~/.openclaw/skills/whisper/SKILL.md
   cat ~/.openclaw/skills/whisper/SKILL.md | head -20
   ```
5. Check if OpenClaw recognizes the skill (if there's a list/reload command — check `openclaw --help` or `docs/handbooks/openclaw-ops.md`)

**Files**:
- `~/.openclaw/skills/whisper/SKILL.md` on office2 (deployed)

**Validation**:
- [ ] Skill file exists at `~/.openclaw/skills/whisper/SKILL.md`
- [ ] File is readable by the claude user
- [ ] OpenClaw can load/see the skill (if verifiable)

**Parallel?**: No — depends on T007.

### Subtask T009 – Commit Skill Source to Repo

**Purpose**: Ensure the skill source is version-controlled in the repo for reproducibility (constraint C-005).

**Steps**:
1. Verify `scripts/openclaw/skills/whisper/SKILL.md` exists in the worktree (written in T007)
2. Ensure the directory structure is created: `scripts/openclaw/skills/whisper/`
3. This file will be committed as part of the worktree's changes during review

**Files**:
- `scripts/openclaw/skills/whisper/SKILL.md` (already created in T007 — confirm it's tracked)

**Validation**:
- [ ] File exists in repo at `scripts/openclaw/skills/whisper/SKILL.md`
- [ ] Content matches what's deployed on office2

**Parallel?**: Yes — can happen alongside T008 (one writes to office2, one confirms repo copy).

### Subtask T010 – End-to-End Verification

**Purpose**: Verify that the complete workflow works — submit a sample audio file to the transcribe-api and receive a readable English transcript.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. First, verify the API is healthy:
   ```bash
   curl -s http://100.92.197.90:8787/health
   ```
3. Create or find a sample audio file. Options:
   - Use `ffmpeg` to generate a short test audio with speech synthesis (if `espeak` or similar is available):
     ```bash
     espeak "This is a test of the whisper transcription service" --stdout | \
       ffmpeg -i pipe:0 -codec:a libopus -f ogg /tmp/test-audio.ogg
     ```
   - Or use any existing `.ogg`, `.wav`, or `.mp3` file on office2
   - Or download a short public-domain audio clip
4. Submit the audio file:
   ```bash
   curl -s -X POST http://100.92.197.90:8787/transcribe/file \
     -F "file=@/tmp/test-audio.ogg" \
     -H "Accept: application/json"
   ```
   Capture the `id` from the response.
5. Poll for completion:
   ```bash
   # Replace <job_id> with actual ID from step 4
   curl -s http://100.92.197.90:8787/transcripts/<job_id>
   ```
   Repeat until `status` is `"complete"`.
6. Retrieve transcript text:
   ```bash
   curl -s http://100.92.197.90:8787/transcripts/<job_id>/text
   ```
7. Verify the transcript:
   - Is it readable English?
   - Does it approximately match the spoken content?
   - Is response time acceptable? (target: 30-second audio within 30 seconds, per NFR-002)
8. Test error handling — submit an invalid file:
   ```bash
   echo "not audio" > /tmp/bad-file.ogg
   curl -s -X POST http://100.92.197.90:8787/transcribe/file \
     -F "file=@/tmp/bad-file.ogg"
   ```
   Verify the API returns an error (not a crash or empty response).

**Files**: None (verification only).

**Validation**:
- [ ] Health check passes
- [ ] Sample audio produces a transcript
- [ ] Transcript is readable English
- [ ] Transcription completes within reasonable time (< 30s for short audio)
- [ ] Invalid input produces a clear error, not a crash
- [ ] API is reached at `100.92.197.90:8787` (Tailscale IP)

**Parallel?**: No — must be the last step (depends on T007-T009).

## Risks & Mitigations

- **Audio format not supported**: If transcribe-api rejects `.ogg` files, try `.wav` or `.mp3`. Document the limitation in the skill and runbook. Research indicates faster-whisper supports ogg via ffmpeg.
- **Async polling**: If the job takes longer than expected, increase the polling timeout. For very large files, the 60-second timeout may not be enough — document this as a known limitation.
- **Skill not recognized by OpenClaw**: Check the skill directory structure and file permissions. Consult `docs/handbooks/openclaw-ops.md` for the expected skill layout.
- **No test audio available**: Generate one using `ffmpeg` + `espeak` or `festival`. If text-to-speech tools aren't available on office2, record a short audio clip or download a public-domain sample.

## Review Guidance

- Verify the SKILL.md contains the complete API contract (all endpoints, methods, request/response formats)
- Verify the async workflow is clearly documented (upload → poll → read)
- Verify error handling instructions are present and practical
- Verify the endpoint URL is the Tailscale IP (`100.92.197.90:8787`), not `localhost`
- Verify the E2E test produced a real transcript (not a mock or placeholder)
- Verify the skill source in the repo matches what's deployed on office2

## Activity Log

- 2026-03-28T16:22:31Z – system – lane=planned – Prompt created.
