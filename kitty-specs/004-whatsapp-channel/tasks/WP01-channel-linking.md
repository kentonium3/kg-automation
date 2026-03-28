---
work_package_id: WP01
title: WhatsApp Channel Linking, DM Config, and E2E Verification
lane: "doing"
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- C-005
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- NFR-001
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 805fa120c0003f8ecee9303e2838fcff7bdff410
created_at: '2026-03-28T18:10:41.637572+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
phase: Phase 1 - Channel Setup
assignee: ''
agent: "claude"
shell_pid: "85118"
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

# Work Package Prompt: WP01 – WhatsApp Channel Linking, DM Config, and E2E Verification

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP01`

---

## Objectives & Success Criteria

Configure DM access control on the existing OpenClaw WhatsApp channel, link the Google Voice WhatsApp account via QR code (Kent must scan), and verify end-to-end text messaging, voice note arrival, session persistence, and port safety.

**Success**:
- `openclaw channels list` shows WhatsApp as "linked, enabled"
- Text message from Kent's iPhone to (617) 564-0182 reaches OpenClaw and reply comes back
- Voice note audio payload arrives in OpenClaw logs
- Session survives OpenClaw restart (reconnects within 30 seconds)
- `ss -tlnp` shows no new publicly exposed ports

## Context & Constraints

- **SSH**: `ssh office2-claude` only. No sudo needed for this WP (OpenClaw is a user-level service).
- **Research**: `kitty-specs/004-whatsapp-channel/research.md` (R-001: Baileys architecture, R-002: current config, R-003: DM policy)
- **OpenClaw ops**: `docs/handbooks/openclaw-ops.md` — service management, config location, log viewing
- **Current WhatsApp config** (already in `~/.openclaw/openclaw.json`):
  ```json
  "channels": {
    "whatsapp": {
      "enabled": true,
      "dmPolicy": "pairing",
      "selfChatMode": false,
      "groupPolicy": "allowlist",
      "debounceMs": 0,
      "mediaMaxMb": 50
    }
  }
  ```
- **Constraint C-001**: No new inbound ports (Baileys is outbound WebSocket only)
- **Constraint C-002**: Agent SSH identity — `ssh office2-claude`
- **Constraint C-003**: Personal DM only — only Kent's personal number accepted
- **Constraint C-005**: Baileys risk accepted — unofficial protocol, account ban risk understood

**CRITICAL**: This WP requires Kent's interactive participation for QR code scanning (T002/T003). The agent cannot complete those steps autonomously. Present the QR code and wait for Kent to scan.

## Subtasks & Detailed Guidance

### Subtask T001 – Configure DM Access Control

**Purpose**: Restrict the WhatsApp channel to only accept messages from Kent's personal number. Without this, anyone who messages the Google Voice number could interact with OpenClaw.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check current config and available options:
   ```bash
   openclaw channels add --help
   cat ~/.openclaw/openclaw.json | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['channels']['whatsapp'], indent=2))"
   ```
3. The `dmPolicy` is already `"pairing"` which requires an explicit pairing step. This is a good baseline.
4. Check if there's an `allowFrom` or equivalent field to whitelist Kent's personal number:
   ```bash
   openclaw channels capabilities --channel whatsapp 2>&1
   ```
5. If `allowFrom` is available, configure it with Kent's personal WhatsApp number. The exact format may be:
   - International format: `+1XXXXXXXXXX`
   - WhatsApp JID format: `1XXXXXXXXXX@s.whatsapp.net`
6. If no explicit `allowFrom` field exists, the `dmPolicy: "pairing"` combined with the initial pairing flow should suffice. Document the finding.
7. Ensure `groupPolicy` remains `"allowlist"` (already set — blocks all group chats).

**Files**: `~/.openclaw/openclaw.json` on office2 (edit if needed).

**Validation**:
- [ ] DM access restricted to Kent's personal number (or pairing policy active)
- [ ] Group policy blocks all group chats
- [ ] Config verified via `openclaw channels list` or config inspection

**Parallel?**: No — must complete before T002.

**IMPORTANT**: Ask Kent for his personal WhatsApp number if you don't have it. Do not guess.

### Subtask T002 – Display QR Code for Linking

**Purpose**: Initiate the WhatsApp Web linking flow so Kent can scan the QR code from his iPhone.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Run the login command:
   ```bash
   openclaw channels login --channel whatsapp
   ```
3. This should display a QR code in the terminal (or provide a URL/code to scan)
4. Present the QR code or instructions to Kent
5. If the command fails, check:
   - Is the WhatsApp channel enabled? (`openclaw channels list`)
   - Is OpenClaw gateway running? (`systemctl --user status openclaw-gateway`)
   - Check logs: `journalctl --user -u openclaw-gateway --since "5 minutes ago"`

**Files**: None.

**Validation**:
- [ ] QR code displayed successfully
- [ ] Kent is presented with clear instructions to scan

**Parallel?**: No — sequential.

**NOTE**: The QR code has a timeout (typically 20-60 seconds). If Kent can't scan in time, re-run the command.

### Subtask T003 – Kent Scans QR Code and Verify Linking

**Purpose**: Complete the pairing by having Kent scan the QR code, then verify the channel is linked.

**Steps**:
1. Kent opens WhatsApp on iPhone → Settings → Linked Devices → Link a Device
2. Kent scans the QR code displayed in the terminal
3. Wait for the pairing to complete (should take a few seconds)
4. Verify the channel is linked:
   ```bash
   openclaw channels list
   ```
   Expected: `WhatsApp default: linked, enabled`
5. Check deeper status:
   ```bash
   openclaw channels status --deep
   ```
6. If pairing fails:
   - Check if the Google Voice number has WhatsApp installed and registered
   - Check OpenClaw logs: `journalctl --user -u openclaw-gateway --since "5 minutes ago"`
   - Re-run the login command and try again

**Files**: None.

**Validation**:
- [ ] `openclaw channels list` shows "linked, enabled"
- [ ] `openclaw channels status --deep` shows connected status
- [ ] Baileys session stored at `~/.openclaw/credentials/whatsapp/`

**Parallel?**: No — depends on T002.

### Subtask T004 – End-to-End Text Message Test

**Purpose**: Verify that a text message from Kent's iPhone WhatsApp reaches OpenClaw and a reply comes back.

**Steps**:
1. SSH to office2 and tail the logs:
   ```bash
   journalctl --user -u openclaw-gateway -f
   ```
2. Ask Kent to send "hello" from his personal iPhone WhatsApp to (617) 564-0182
3. Watch the logs for the incoming message
4. Verify OpenClaw processes the message and sends a reply
5. Ask Kent to confirm the reply arrived on his iPhone
6. If no message arrives:
   - Check channel status: `openclaw channels status --deep`
   - Check if DM policy is blocking: the `pairing` policy may require Kent to be explicitly paired
   - Check logs for errors

**Files**: None (verification only).

**Validation**:
- [ ] Incoming message visible in OpenClaw logs
- [ ] OpenClaw sends a reply
- [ ] Kent confirms reply arrived on iPhone
- [ ] Round-trip time is under 10 seconds (SC-001)

**Parallel?**: No — depends on T003.

### Subtask T005 – Voice Note Arrival Test

**Purpose**: Verify that a voice note sent from Kent's iPhone arrives at OpenClaw as an audio payload. Transcription is F003 scope — here we only verify the audio arrives.

**Steps**:
1. Continue tailing logs: `journalctl --user -u openclaw-gateway -f`
2. Ask Kent to send a short voice note from his personal WhatsApp to (617) 564-0182
3. Watch the logs for the incoming media message
4. Verify the log shows:
   - Message type indicates audio/voice note
   - Media payload is present (file reference, size, etc.)
5. If media doesn't arrive, check `mediaMaxMb` config (currently 50MB — should be sufficient)

**Files**: None (verification only).

**Validation**:
- [ ] Voice note message visible in OpenClaw logs
- [ ] Audio payload/reference present in the message data
- [ ] No errors related to media handling

**Parallel?**: No — depends on T003.

### Subtask T006 – Session Persistence Test

**Purpose**: Verify the Baileys session survives an OpenClaw restart without requiring QR code re-scanning.

**Steps**:
1. Verify session credentials exist:
   ```bash
   ls -la ~/.openclaw/credentials/whatsapp/
   ```
2. Restart OpenClaw:
   ```bash
   systemctl --user restart openclaw-gateway
   ```
3. Wait up to 30 seconds for reconnection
4. Check channel status:
   ```bash
   openclaw channels status --deep
   ```
   Expected: still "linked"
5. Send another test message from Kent's iPhone to verify messages still flow
6. If session doesn't reconnect:
   - Check logs: `journalctl --user -u openclaw-gateway --since "2 minutes ago"`
   - Check if credentials directory still has session files
   - Check reconnection config if available

**Files**: None (verification only).

**Validation**:
- [ ] Session credentials persist in `~/.openclaw/credentials/whatsapp/`
- [ ] Channel reconnects within 30 seconds after restart (NFR-001)
- [ ] Messages still flow after restart

**Parallel?**: No — depends on T004 (need a working channel to test persistence).

### Subtask T007 – Verify No New Ports

**Purpose**: Confirm that the WhatsApp channel integration did not open any new inbound ports on office2. Baileys uses outbound WebSocket only.

**Steps**:
1. Check listening ports:
   ```bash
   ss -tlnp
   ```
2. Compare with the expected baseline — only these managed services should be listening:
   - `100.92.197.90:3456` — Vikunja
   - `100.92.197.90:8787` — transcribe-api
   - `127.0.0.1:18789` — OpenClaw gateway
3. Verify no new entries related to WhatsApp, Baileys, or WebSocket listening
4. Check specifically for any `0.0.0.0` bindings:
   ```bash
   ss -tlnp | grep 0.0.0.0
   ```
   No managed services should appear.

**Files**: None (verification only).

**Validation**:
- [ ] No new listening ports compared to pre-deployment
- [ ] No `0.0.0.0` bindings for managed services
- [ ] OpenClaw gateway still on `127.0.0.1:18789` only

**Parallel?**: No — should be last verification step.

## Risks & Mitigations

- **QR code timeout**: Re-run `openclaw channels login --channel whatsapp` if it expires.
- **Google Voice WhatsApp not set up**: Kent must have WhatsApp registered on the Google Voice number before this WP starts. If not set up, this is a blocker.
- **DM policy blocks Kent**: If `pairing` mode requires additional config, check OpenClaw docs for how to pair a specific number.
- **Baileys session doesn't persist**: Check the credentials directory. If empty after restart, the session storage may not be configured correctly.
- **Meta bans the account**: This is the accepted Baileys risk. If it happens during testing, try again with the same or a different number.

## Review Guidance

- Verify `openclaw channels list` shows "linked, enabled"
- Verify Kent confirmed text message round-trip works
- Verify voice note arrival is logged
- Verify session survives restart
- Verify `ss -tlnp` shows no new ports
- Verify no credentials appear in any committed file

## Activity Log

- 2026-03-28T18:00:42Z – system – lane=planned – Prompt created.
- 2026-03-28T18:10:42Z – claude – shell_pid=85118 – lane=doing – Assigned agent via workflow command
