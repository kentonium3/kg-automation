# Work Packages: Whisper Transcription Skill

**Inputs**: Design documents from `kitty-specs/003-whisper-transcription-skill/`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual verification against acceptance scenarios. No automated test suite.

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package must be independently deliverable and testable.

**Prompt Files**: Each work package references a matching prompt file in `tasks/`.

---

## Work Package WP01: Security Hardening — Rebind, systemd, Deploy Config (Priority: P0)

**Goal**: Capture the existing docker-compose.yml, rebind `transcribe-api` from `0.0.0.0` to `100.92.197.90`, create a systemd unit wrapping Docker Compose, create a deploy script, and verify the service is reachable after rebind.
**Independent Test**: `ss -tlnp | grep 8787` shows `100.92.197.90:8787` only. `curl http://100.92.197.90:8787/health` returns OK. `systemctl is-active transcribe` returns `active`.
**Prompt**: `tasks/WP01-security-hardening.md`
**Requirement Refs**: FR-001, FR-002, FR-005, NFR-001, C-001, C-002, C-003, C-004
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [x] T001 Capture existing `docker-compose.yml` from `/data/services/transcribe/` on office2
- [x] T002 Update port binding from `"8787:8787"` to `"100.92.197.90:8787:8787"` in compose file
- [x] T003 Create `scripts/transcribe/transcribe.service` systemd unit wrapping `docker compose up -d`
- [x] T004 Create `scripts/transcribe/deploy.sh` deployment helper script
- [x] T005 Deploy: stop existing container, copy updated compose to office2, start via systemd (Kent runs sudo for systemd install)
- [x] T006 Verify rebind: `ss -tlnp | grep 8787`, health check at Tailscale IP, connectivity test

### Implementation Notes
- SSH to office2 as claude: `ssh office2-claude`
- Capture the existing compose file first (T001) before modifying anything
- The systemd unit follows the pattern from `scripts/vikunja/vikunja.service` (F001)
- The compose file change is a single line: `ports: - "8787:8787"` → `ports: - "100.92.197.90:8787:8787"`
- Docker Compose is used (not `docker run`) per constraint C-004
- Kent must run `sudo` for systemd unit installation — present exact commands
- After rebind, OpenClaw reaches transcribe-api at `http://100.92.197.90:8787` (not localhost)

### Parallel Opportunities
- T003 (systemd unit) and T004 (deploy script) can be written in parallel with T001-T002

### Dependencies
- None (starting package — must complete before WP02 and WP03)

### Risks & Mitigations
- **Rebind breaks connectivity**: Docker on Tailscale IP may behave differently. Test immediately after rebind. If broken, revert compose and restart.
- **Existing container state lost**: Models are on a volume mount (`/data/services/transcribe/models/`) — safe across restarts. No rebuild needed.
- **systemd install requires sudo**: Present exact commands to Kent, wait for confirmation.

---

## Work Package WP02: OpenClaw Whisper Skill and End-to-End Verification (Priority: P1)

**Goal**: Create the OpenClaw SKILL.md that documents the transcription API contract and instructs the agent to transcribe audio via curl. Install the skill on office2 and verify with a sample audio file.
**Independent Test**: Submit a sample `.ogg` audio file through the skill and receive readable English transcript text.
**Prompt**: `tasks/WP02-openclaw-skill.md`
**Requirement Refs**: FR-003, FR-004, FR-005, NFR-002, NFR-003, C-005
**Estimated Prompt Size**: ~300 lines

### Included Subtasks
- [ ] T007 Write `SKILL.md` with full API contract, async workflow instructions, and error handling guidance
- [ ] T008 Install skill to `~/.openclaw/skills/whisper/SKILL.md` on office2
- [ ] T009 Commit skill source to `scripts/openclaw/skills/whisper/SKILL.md` in repo
- [ ] T010 End-to-end verification: submit sample audio to transcribe-api via skill workflow, confirm transcript

### Implementation Notes
- The skill is a markdown prompt document, NOT executable code
- It teaches the OpenClaw agent to use `curl` via its exec tool to call the API
- Async workflow: `POST /transcribe/file` → get job ID → poll `GET /transcripts/{id}` → read `GET /transcripts/{id}/text`
- The skill must include the full API contract (endpoints, methods, input/output formats)
- Error handling: skill instructs agent to check HTTP status codes, poll status field, and surface errors as readable messages
- Skill endpoint uses `http://100.92.197.90:8787` (Tailscale IP, confirmed in research R-004)
- For verification, use a sample `.ogg` file (WhatsApp voice note format) — can generate one via `ffmpeg` or use any short audio clip

### Parallel Opportunities
- T009 (commit to repo) can happen alongside T008 (install on office2)

### Dependencies
- Depends on WP01 (transcribe-api must be rebound and reachable at Tailscale IP before skill can call it)

### Risks & Mitigations
- **Audio format not supported**: WhatsApp voice notes are `audio/ogg` (Opus). If transcribe-api rejects it, document the limitation and note conversion needed. Research indicates faster-whisper supports ogg natively.
- **Async polling timeout**: Large files may take longer. Skill should instruct agent to poll up to 60 seconds with 2-second intervals.
- **Skill format incorrect**: Follow the pattern from `docs/handbooks/openclaw-ops.md` skill directory structure. If OpenClaw doesn't load the skill, check `~/.openclaw/skills/` directory permissions and naming.

---

## Work Package WP03: Ops Runbook, Architecture Docs, and Final Acceptance (Priority: P1)

**Goal**: Create the operations runbook for the transcription service, update architecture documentation to reflect the security hardening, and verify zero `0.0.0.0` bindings remain.
**Independent Test**: `docs/handbooks/transcribe-ops.md` passes doc validation. `network-topology.json` shows no `0.0.0.0` bindings. `security-posture.md` confirms all services Tailscale-only.
**Prompt**: `tasks/WP03-docs-architecture.md`
**Requirement Refs**: FR-003, FR-006, FR-007
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [ ] T011 Create `docs/handbooks/transcribe-ops.md` with service overview, API contract, start/stop/restart, image update, log inspection, known limitations
- [ ] T012 Update `docs/design/architecture/data/service-inventory.json`: transcribe-api entry (bind_ip, systemd_unit, deployed_by)
- [ ] T013 Update `docs/design/architecture/data/network-topology.json`: port 8787 entry (remove 0.0.0.0 warning, set bind_ip to 100.92.197.90)
- [ ] T014 Update `docs/design/architecture/service-inventory.md` and `docs/design/architecture/security-posture.md` to reflect changes
- [ ] T015 Verify zero `0.0.0.0` bindings remain in architecture docs and on live system

### Implementation Notes
- Runbook follows the format of `docs/handbooks/vikunja-ops.md` (F001) — read it for structure
- Runbook must include the full API contract from research.md (endpoints, methods, input/output)
- YAML frontmatter on runbook: `id, doc_type: handbook, title, status, level, owners, last_validated, version`
- Architecture doc updates are a standing requirement per CLAUDE.md — not optional
- JSON files are authoritative; markdown files are narrative views derived from JSON
- Run `python tooling/scripts/validate_docs.py` to check runbook passes CI validation

### Parallel Opportunities
- T011 (runbook), T012-T013 (JSON updates), T014 (markdown updates) are all parallel-safe — different files
- T015 (verification) runs last

### Dependencies
- Depends on WP01 (must know the actual deployed state to document accurately)

### Risks & Mitigations
- **Doc validation failure**: Check frontmatter fields against `docs/standards/` requirements. Run validation script before committing.
- **JSON schema mismatch**: Read existing entries in `service-inventory.json` and `network-topology.json` to match structure exactly.
- **Stale architecture data**: Read current JSON files during implementation — don't assume values from the spec. The F002 implementation may have changed fields.

---

## Dependency Graph

```
WP01: Security Hardening (rebind + systemd + deploy config)
  ├── WP02: OpenClaw Skill + E2E Verification  [parallel with WP03]
  └── WP03: Ops Runbook + Architecture Docs     [parallel with WP02]
```

WP01 must complete first. WP02 and WP03 can proceed in parallel after WP01.

## Subtask-to-WP Coverage Matrix

| Subtask | WP | Description |
|---------|-----|-------------|
| T001 | WP01 | Capture existing docker-compose.yml |
| T002 | WP01 | Update port binding |
| T003 | WP01 | Create systemd unit |
| T004 | WP01 | Create deploy script |
| T005 | WP01 | Deploy rebind |
| T006 | WP01 | Verify rebind |
| T007 | WP02 | Write SKILL.md |
| T008 | WP02 | Install skill on office2 |
| T009 | WP02 | Commit skill to repo |
| T010 | WP02 | E2E verification |
| T011 | WP03 | Create runbook |
| T012 | WP03 | Update service-inventory.json |
| T013 | WP03 | Update network-topology.json |
| T014 | WP03 | Update markdown arch docs |
| T015 | WP03 | Verify zero 0.0.0.0 bindings |

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: in_progress
<!-- status-model:end -->
