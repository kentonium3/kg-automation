---
work_package_id: WP03
title: Ops Runbook, Architecture Docs, and Final Acceptance
lane: planned
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-03-28T16:22:31Z'
subtasks:
- T011
- T012
- T013
- T014
- T015
phase: Phase 2 - Documentation
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

# Work Package Prompt: WP03 – Ops Runbook, Architecture Docs, and Final Acceptance

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP03 --base WP01`

---

## Objectives & Success Criteria

Create the operations runbook for the transcription service, update all architecture documentation to reflect the security hardening and systemd management, and verify that zero `0.0.0.0` bindings remain in documentation and on the live system.

**Success**:
- `docs/handbooks/transcribe-ops.md` exists with valid frontmatter and passes CI validation
- `service-inventory.json` updated: transcribe-api has `bind_ip: "100.92.197.90"`, `systemd_unit: "transcribe.service"`, `deployed_by: "F003"`
- `network-topology.json` updated: port 8787 shows `bind_ip: "100.92.197.90"`, no `0.0.0.0` warnings
- `security-posture.md` notes elimination of last `0.0.0.0` binding
- `service-inventory.md` updated with current transcribe-api details

## Context & Constraints

- **SSH**: `ssh office2-claude` for live verification (T015). Other subtasks are repo-only edits.
- **Research**: `kitty-specs/003-whisper-transcription-skill/research.md` (R-001: API contract for runbook)
- **Data model**: `kitty-specs/003-whisper-transcription-skill/data-model.md` (TranscriptMeta entity)
- **Architecture docs**: `docs/design/architecture/` — JSON files are authoritative, markdown is narrative
- **Runbook pattern**: `docs/handbooks/vikunja-ops.md` — follow this format for structure and frontmatter
- **Doc standards**: YAML frontmatter fields per `docs/standards/` and `CLAUDE.md`
- **Standing requirement**: Architecture docs must be updated for any service/credential/network change (CLAUDE.md)

**PREREQUISITE**: WP01 must be complete. The actual deployed state must be known to document accurately.

## Subtasks & Detailed Guidance

### Subtask T011 – Create Operations Runbook

**Purpose**: Create a comprehensive ops runbook for the transcription service so any operator or agent can manage it without tribal knowledge.

**Steps**:
1. Read `docs/handbooks/vikunja-ops.md` for the runbook format and structure to follow
2. Create `docs/handbooks/transcribe-ops.md` with the following sections:

   **Frontmatter** (match the pattern from vikunja-ops.md):
   ```yaml
   ---
   title: Transcribe API Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```

   **Service Overview**:
   - Service name: `transcribe` (systemd), container managed via Docker Compose
   - Image: `transcribe_transcribe` (locally built)
   - Port: `100.92.197.90:8787` (Tailscale IP only)
   - Model: `medium.en` (faster-whisper), 4 workers, 4GB memory limit
   - Data: transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/`
   - Compose file: `/data/services/transcribe/docker-compose.yml`

   **Service Management**:
   ```bash
   # Check status
   systemctl status transcribe
   docker ps | grep transcribe

   # Start / Stop / Restart
   sudo systemctl start transcribe
   sudo systemctl stop transcribe
   sudo systemctl restart transcribe

   # View logs
   docker compose -f /data/services/transcribe/docker-compose.yml logs -f
   journalctl -u transcribe -f
   ```

   **API Contract** (from research.md R-001):
   - Document all endpoints: `/health`, `/transcribe/file`, `/transcribe/url`, `/transcripts/{id}`, `/transcripts/{id}/text`, `/transcripts`
   - Include request/response examples for each endpoint
   - Document the async workflow: upload → poll → read

   **Updating the Docker Image**:
   - The image is locally built from `/data/services/transcribe/`
   - To rebuild: `cd /data/services/transcribe && docker compose build`
   - After rebuild: `sudo systemctl restart transcribe`
   - Note: this rebuilds from the Dockerfile in that directory

   **Checking Transcription Logs**:
   ```bash
   docker compose -f /data/services/transcribe/docker-compose.yml logs --tail 50
   ```

   **Known Limitations**:
   - Model: `medium.en` — English only
   - Memory limit: 4GB — large files may fail
   - Models are excluded from backup (re-downloadable from Hugging Face)
   - If models are missing, the container fails to start — re-download by rebuilding

   **Troubleshooting**:
   - Service won't start: check `journalctl -u transcribe -e` and `docker compose logs`
   - Port not bound: verify compose file has `100.92.197.90:8787:8787`
   - Transcription fails: check container logs for model loading errors
   - Slow transcription: check memory usage (`docker stats`) and worker count

3. Run doc validation:
   ```bash
   python tooling/scripts/validate_docs.py
   ```

**Files**:
- `docs/handbooks/transcribe-ops.md` (new file)

**Validation**:
- [ ] Frontmatter matches project conventions (title, doc_type: handbook, status)
- [ ] All API endpoints documented with examples
- [ ] Start/stop/restart commands documented
- [ ] Log viewing commands documented
- [ ] Image update procedure documented
- [ ] Known limitations listed
- [ ] Passes `validate_docs.py`

**Parallel?**: Yes — independent of T012-T014.

### Subtask T012 – Update service-inventory.json

**Purpose**: Update the transcribe-api entry in the service inventory to reflect the security hardening and systemd management.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Find the `transcribe-api` entry
3. Update the following fields:
   - `bind_ip`: change from `"0.0.0.0"` to `"100.92.197.90"`
   - Add or update `systemd_unit`: `"transcribe.service"`
   - Update `deployed_by`: `"F003"`
   - Update `port_binding` or equivalent to show `"100.92.197.90:8787:8787"`
4. Preserve all other fields (image, volumes, environment, etc.)
5. Ensure valid JSON after editing

**Files**:
- `docs/design/architecture/data/service-inventory.json` (edit)

**Validation**:
- [ ] `bind_ip` is `"100.92.197.90"`
- [ ] `systemd_unit` is `"transcribe.service"`
- [ ] `deployed_by` includes `"F003"`
- [ ] JSON is valid (no syntax errors)
- [ ] No unrelated fields changed

**Parallel?**: Yes — independent of T011, T013, T014.

### Subtask T013 – Update network-topology.json

**Purpose**: Update the port 8787 entry to reflect the Tailscale-only binding and remove the `0.0.0.0` warning.

**Steps**:
1. Read `docs/design/architecture/data/network-topology.json`
2. Find the port 8787 / transcribe-api entry
3. Update:
   - `bind_ip`: change from `"0.0.0.0"` to `"100.92.197.90"`
   - Remove any `"WARNING: bound to all interfaces"` or similar warning text
   - Set `public_exposure`: `"none"` (or equivalent field)
4. Verify no other entries still reference `0.0.0.0`
5. Ensure valid JSON

**Files**:
- `docs/design/architecture/data/network-topology.json` (edit)

**Validation**:
- [ ] Port 8787 entry shows `bind_ip: "100.92.197.90"`
- [ ] No `0.0.0.0` warnings remain in the file
- [ ] `public_exposure` set to `"none"` or equivalent
- [ ] JSON is valid
- [ ] No unrelated entries changed

**Parallel?**: Yes — independent of T011, T012, T014.

### Subtask T014 – Update Markdown Architecture Docs

**Purpose**: Update the narrative architecture documents to reflect the security changes.

**Steps**:
1. Read and update `docs/design/architecture/service-inventory.md`:
   - Find the transcribe-api row/section
   - Update bind IP to `100.92.197.90`
   - Add systemd unit: `transcribe.service`
   - Update deployed_by to include F003
   - Add an "F003 Deployment Details" section if the doc follows the pattern of having per-feature deployment notes

2. Read and update `docs/design/architecture/security-posture.md`:
   - Find the section about service bindings or network exposure
   - Note that the last `0.0.0.0`-bound service has been eliminated
   - State that all managed services on office2 are now Tailscale-only
   - Add F003 to any "changes by feature" tracking if present

3. Both files should be consistent with their JSON counterparts (JSON is authoritative)

**Files**:
- `docs/design/architecture/service-inventory.md` (edit)
- `docs/design/architecture/security-posture.md` (edit)

**Validation**:
- [ ] `service-inventory.md` shows transcribe-api with `100.92.197.90` binding
- [ ] `service-inventory.md` shows `transcribe.service` systemd unit
- [ ] `security-posture.md` notes zero `0.0.0.0` bindings remain
- [ ] Both files are consistent with their JSON sources
- [ ] No unrelated sections modified

**Parallel?**: Yes — independent of T011-T013 (different files).

### Subtask T015 – Verify Zero 0.0.0.0 Bindings

**Purpose**: Final verification that no `0.0.0.0` bindings remain in architecture documentation or on the live system.

**Steps**:
1. Check architecture docs for `0.0.0.0`:
   ```bash
   grep -r "0.0.0.0" docs/design/architecture/data/
   ```
   Expected: no results for managed service bindings (sshd or system services are acceptable)

2. Check narrative docs:
   ```bash
   grep -r "0.0.0.0" docs/design/architecture/*.md
   ```
   Expected: only historical references or "eliminated" language, not active bindings

3. SSH to office2 and check the live system:
   ```bash
   ssh office2-claude
   ss -tlnp | grep 0.0.0.0
   ```
   Review output: managed services (Vikunja, OpenClaw, transcribe) should NOT appear. System services like sshd (`0.0.0.0:22`) are acceptable and outside our control.

4. Specifically verify all three managed services are Tailscale-only:
   ```bash
   ss -tlnp | grep -E '(3456|18789|8787)'
   ```
   All three should show `100.92.197.90:` prefix.

**Files**: None (verification only).

**Validation**:
- [ ] No `0.0.0.0` bindings for managed services in JSON data files
- [ ] No active `0.0.0.0` bindings in narrative docs
- [ ] Live system shows all managed services on `100.92.197.90`
- [ ] Vikunja (3456), OpenClaw (18789), transcribe (8787) all confirmed Tailscale-only

**Parallel?**: No — must be the last step (depends on T011-T014 being complete).

## Risks & Mitigations

- **Doc validation failure**: Check frontmatter fields carefully against existing runbooks. Run `python tooling/scripts/validate_docs.py` before finishing.
- **JSON schema mismatch**: Read existing entries in both JSON files before editing — match the exact field names and structure used by other entries.
- **Stale data in docs**: Read the current files during implementation. Don't assume values from the spec — F001 and F002 may have changed field names or structures.
- **grep false positives for 0.0.0.0**: The string `0.0.0.0` may appear in historical context, comments, or documentation about what changed. Only flag it if it appears as an active binding value.

## Review Guidance

- Verify runbook covers: service overview, management commands, API contract, image updates, logs, limitations
- Verify JSON files are valid and only the transcribe-api entries were changed
- Verify markdown is consistent with JSON (JSON is authoritative)
- Verify `security-posture.md` explicitly states zero `0.0.0.0` bindings remain
- Verify the grep checks in T015 return clean results
- Run `python tooling/scripts/validate_docs.py` and confirm no failures

## Activity Log

- 2026-03-28T16:22:31Z – system – lane=planned – Prompt created.
