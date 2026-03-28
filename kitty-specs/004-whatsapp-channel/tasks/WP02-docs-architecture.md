---
work_package_id: WP02
title: Ops Runbook and Architecture Documentation
lane: planned
dependencies:
- WP01
requirement_refs:
- FR-008
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-03-28T18:00:42Z'
subtasks:
- T008
- T009
- T010
- T011
phase: Phase 2 - Documentation
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-28T18:00:42Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 – Ops Runbook and Architecture Documentation

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP02 --base WP01`

---

## Objectives & Success Criteria

Create the operations runbook for the WhatsApp channel, update architecture documentation to reflect the Baileys integration, and update the credential manifest to reflect that Baileys manages credentials internally (not the external credential store).

**Success**:
- `docs/handbooks/whatsapp-ops.md` exists with valid frontmatter and passes CI validation
- `service-inventory.json` updated with WhatsApp channel info under OpenClaw
- `credential-manifest.json` updated: `whatsapp-meta` planned entry updated to reflect Baileys approach
- Architecture markdown docs updated

## Context & Constraints

- **SSH**: `ssh office2-claude` for any live-state verification. Most subtasks are repo-only edits.
- **Research**: `kitty-specs/004-whatsapp-channel/research.md` (R-001 through R-006)
- **Runbook pattern**: `docs/handbooks/vikunja-ops.md` and `docs/handbooks/transcribe-ops.md`
- **Architecture docs**: JSON is authoritative, markdown is narrative
- **Standing requirement**: Architecture docs must be updated for any service/credential/network change

**PREREQUISITE**: WP01 must be complete. The actual linked state must be known to document accurately.

## Subtasks & Detailed Guidance

### Subtask T008 – Create Operations Runbook

**Purpose**: Create a comprehensive ops runbook for the WhatsApp channel so any operator or agent can manage it.

**Steps**:
1. Read `docs/handbooks/transcribe-ops.md` and `docs/handbooks/vikunja-ops.md` for format reference
2. Create `docs/handbooks/whatsapp-ops.md` with:

   **Frontmatter**:
   ```yaml
   ---
   title: WhatsApp Channel Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```

   **Channel Overview**:
   - Channel type: WhatsApp via OpenClaw native Baileys integration
   - Dedicated number: (617) 564-0182 (Google Voice)
   - Protocol: Baileys (unofficial WhatsApp Web — see Risk Acceptance below)
   - Authentication: QR code linked device pairing
   - Session storage: `~/.openclaw/credentials/whatsapp/` on office2
   - DM policy: `pairing` — only paired users can message
   - Group policy: `allowlist` — no group chats by default

   **Verify Channel Status**:
   ```bash
   ssh office2-claude
   openclaw channels list
   openclaw channels status --deep
   ```

   **Re-pairing (if session drops)**:
   ```bash
   openclaw channels login --channel whatsapp
   # Kent scans QR code from WhatsApp → Settings → Linked Devices → Link a Device
   openclaw channels list  # verify "linked"
   ```

   **Session Management**:
   - Session survives OpenClaw restarts automatically
   - Session may drop if: Kent unlinks from phone, Baileys library update, or WhatsApp account ban
   - To check session files: `ls -la ~/.openclaw/credentials/whatsapp/`

   **Log Viewing**:
   ```bash
   journalctl --user -u openclaw-gateway -f              # follow live
   journalctl --user -u openclaw-gateway --since "1 hour ago" | grep -i whatsapp
   ```

   **Troubleshooting**:
   | Symptom | Check | Fix |
   |---------|-------|-----|
   | Messages not arriving | `openclaw channels status --deep` | Re-pair if disconnected |
   | Channel shows "not linked" | Session credentials missing | Re-run QR login flow |
   | Unauthorized messages getting through | Check `dmPolicy` in config | Ensure `pairing` policy active |
   | Media not arriving | Check `mediaMaxMb` setting | Increase if needed |

   **Baileys Risk Acceptance**:
   - OpenClaw uses Baileys (unofficial WhatsApp Web protocol) — this is the only WhatsApp path in OpenClaw
   - Meta could ban the account at any time for using unofficial clients
   - Accepted risk for personal single-user system at low message volume
   - If banned: pair a new number via the QR login flow
   - Policy exception documented in `docs/design/architecture/security-posture.md`

3. Run doc validation:
   ```bash
   python tooling/scripts/validate_docs.py
   ```

**Files**:
- `docs/handbooks/whatsapp-ops.md` (new file)

**Validation**:
- [ ] Frontmatter matches project conventions
- [ ] Pairing and re-pairing procedures documented
- [ ] Troubleshooting table included
- [ ] Baileys risk acceptance documented
- [ ] Passes `validate_docs.py`

**Parallel?**: Yes — independent of T009-T011.

### Subtask T009 – Update service-inventory.json

**Purpose**: Add WhatsApp channel information to the OpenClaw entry in the service inventory.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Find the OpenClaw / `openclaw-gateway` entry
3. Add or update fields to indicate WhatsApp channel:
   - Add a `channels` field (or similar) noting `whatsapp` is active via Baileys
   - Add `deployed_by` reference including `F004`
   - Update `last_updated` metadata
4. Do NOT add a separate service entry — WhatsApp is a channel within OpenClaw, not a standalone service
5. Ensure valid JSON

**Files**:
- `docs/design/architecture/data/service-inventory.json` (edit)

**Validation**:
- [ ] OpenClaw entry includes WhatsApp channel reference
- [ ] `deployed_by` includes F004
- [ ] JSON is valid
- [ ] No unrelated entries changed

**Parallel?**: Yes — independent of T008, T010, T011.

### Subtask T010 – Update credential-manifest.json

**Purpose**: Update the planned `whatsapp-meta` credential entry to reflect that Baileys manages credentials internally, not the external credential store.

**Steps**:
1. Read `docs/design/architecture/data/credential-manifest.json`
2. Find the `whatsapp-meta` entry in `planned_credentials`
3. Update it to reflect the actual approach:
   - Move from `planned_credentials` to `credentials` (it exists now, just differently than planned)
   - Change `type` to `session-managed` or similar
   - Update `scope` to reflect Baileys session, not Meta Cloud API
   - Add `storage`: `~/.openclaw/credentials/whatsapp/ (managed by OpenClaw/Baileys)`
   - Add `deployed_by`: `F004`
   - Add `notes`: explaining Baileys session management and that no external credential store entry is needed
4. Remove the `whatsapp-webhook-token` if it was added as planned (it's no longer needed)
5. Ensure valid JSON

**Files**:
- `docs/design/architecture/data/credential-manifest.json` (edit)

**Validation**:
- [ ] `whatsapp-meta` moved from planned to active with Baileys info
- [ ] No `whatsapp-webhook-token` entry (not needed)
- [ ] JSON is valid
- [ ] Accurately reflects that credentials are OpenClaw-managed, not in external store

**Parallel?**: Yes — independent of T008, T009, T011.

### Subtask T011 – Update Markdown Architecture Docs

**Purpose**: Update narrative architecture documents to reflect the WhatsApp channel integration.

**Steps**:
1. Read and update `docs/design/architecture/service-inventory.md`:
   - Under the OpenClaw entry, note that WhatsApp channel is active via Baileys
   - Add F004 to deployment details section
   - Note the dedicated number: (617) 564-0182

2. Verify `docs/design/architecture/security-posture.md`:
   - The Baileys policy exception was already added during planning
   - Verify it's still accurate after implementation
   - No additional changes expected unless the implementation revealed new information

3. Both files should be consistent with their JSON counterparts

**Files**:
- `docs/design/architecture/service-inventory.md` (edit)
- `docs/design/architecture/security-posture.md` (verify — may not need changes)

**Validation**:
- [ ] `service-inventory.md` notes WhatsApp channel under OpenClaw
- [ ] Consistent with JSON sources
- [ ] No unrelated sections modified

**Parallel?**: Yes — independent of T008-T010.

## Risks & Mitigations

- **Doc validation failure**: Check frontmatter carefully. Run `validate_docs.py` before finishing.
- **JSON schema mismatch**: Read existing entries before editing — match exact structure.
- **Credential manifest confusion**: The shift from Meta Cloud API to Baileys means the credential model is fundamentally different. Document clearly that Baileys sessions are managed by OpenClaw, not the external credential store.

## Review Guidance

- Verify runbook covers: channel overview, pairing, re-pairing, session management, troubleshooting, risk acceptance
- Verify JSON files are valid and only relevant entries changed
- Verify credential manifest accurately reflects Baileys approach (not Meta Cloud API)
- Verify markdown is consistent with JSON
- Run `python tooling/scripts/validate_docs.py` and confirm no failures

## Activity Log

- 2026-03-28T18:00:42Z – system – lane=planned – Prompt created.
