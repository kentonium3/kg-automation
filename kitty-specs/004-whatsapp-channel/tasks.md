# Work Packages: WhatsApp Channel

**Inputs**: Design documents from `kitty-specs/004-whatsapp-channel/`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual verification against acceptance scenarios. No automated test suite.

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package must be independently deliverable and testable.

**Prompt Files**: Each work package references a matching prompt file in `tasks/`.

---

## Work Package WP01: WhatsApp Channel Linking, DM Config, and E2E Verification (Priority: P0)

**Goal**: Configure DM access control, link the Google Voice WhatsApp account to OpenClaw via QR code (Kent interactive), and verify end-to-end text messaging, voice note arrival, session persistence, and port safety.
**Independent Test**: `openclaw channels list` shows WhatsApp as linked. Text message from Kent's iPhone reaches OpenClaw and reply comes back. Voice note audio payload arrives in logs.
**Prompt**: `tasks/WP01-channel-linking.md`
**Requirement Refs**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, NFR-001, NFR-002, C-001, C-002, C-003, C-004, C-005
**Estimated Prompt Size**: ~400 lines

### Included Subtasks
- [ ] T001 Configure DM access control (`allowFrom` with Kent's personal number)
- [ ] T002 Run `openclaw channels login --channel whatsapp` to display QR code
- [ ] T003 Kent scans QR code — verify channel shows "linked"
- [ ] T004 End-to-end text message test (Kent sends "hello", OpenClaw replies)
- [ ] T005 Voice note arrival test (Kent sends voice note, verify audio payload in logs)
- [ ] T006 Session persistence test (restart OpenClaw, verify reconnection within 30s)
- [ ] T007 Verify no new ports (`ss -tlnp` unchanged from pre-deployment)

### Implementation Notes
- SSH to office2 as claude: `ssh office2-claude`
- WhatsApp channel is already added and enabled in OpenClaw — just needs linking
- Current config: `dmPolicy: "pairing"`, `groupPolicy: "allowlist"`, `mediaMaxMb: 50`
- QR code step is interactive — Kent must be present to scan from iPhone WhatsApp
- OpenClaw is a user-level systemd service: `systemctl --user restart openclaw-gateway`
- Check logs via: `journalctl --user -u openclaw-gateway -f`
- Baileys session stored at `~/.openclaw/credentials/whatsapp/`

### Parallel Opportunities
- None — sequential (config → link → verify)

### Dependencies
- None (starting package)

### Risks & Mitigations
- **QR code expires**: Re-run `openclaw channels login --channel whatsapp` if it times out
- **DM access control config unclear**: Check `openclaw channels add --help` for exact flags
- **Session doesn't persist**: Check `~/.openclaw/credentials/whatsapp/` for stored session after restart
- **Google Voice WhatsApp not set up**: Kent must have WhatsApp installed and registered on the Google Voice number before linking

---

## Work Package WP02: Ops Runbook and Architecture Documentation (Priority: P1)

**Goal**: Create the operations runbook for the WhatsApp channel, update architecture documentation to reflect the Baileys integration, and update the credential manifest.
**Independent Test**: `docs/handbooks/whatsapp-ops.md` passes doc validation. Architecture docs reflect WhatsApp channel. Credential manifest updated.
**Prompt**: `tasks/WP02-docs-architecture.md`
**Requirement Refs**: FR-008, FR-009
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [ ] T008 Create `docs/handbooks/whatsapp-ops.md` with channel overview, pairing procedure, session management, re-pairing, Baileys risk acceptance, troubleshooting
- [ ] T009 Update `docs/design/architecture/data/service-inventory.json` (add WhatsApp channel info to OpenClaw entry)
- [ ] T010 Update `docs/design/architecture/data/credential-manifest.json` (update `whatsapp-meta` planned credential to reflect Baileys session approach)
- [ ] T011 Update markdown architecture docs (`service-inventory.md`, note WhatsApp channel under OpenClaw)

### Implementation Notes
- Runbook follows format of `docs/handbooks/vikunja-ops.md` and `docs/handbooks/transcribe-ops.md`
- YAML frontmatter: `title, doc_type: handbook, status: draft`
- JSON files are authoritative; markdown is narrative
- The credential manifest's planned `whatsapp-meta` entry should be updated to reflect that Baileys manages credentials internally, not the external credential store
- Run `python tooling/scripts/validate_docs.py` to check runbook passes CI

### Parallel Opportunities
- T008 (runbook), T009-T010 (JSON updates), T011 (markdown updates) are all parallel-safe — different files

### Dependencies
- Depends on WP01 (must know the actual linked state to document accurately)

### Risks & Mitigations
- **Doc validation failure**: Check frontmatter against existing runbooks. Run validation before committing.
- **JSON schema mismatch**: Read existing entries before editing — match exact field names.

---

## Dependency Graph

```
WP01: Channel Linking + DM Config + E2E Verification (Kent interactive)
  └── WP02: Ops Runbook + Architecture Docs
```

WP01 must complete first (channel must be linked before documentation).

## Subtask-to-WP Coverage Matrix

| Subtask | WP | Description |
|---------|-----|-------------|
| T001 | WP01 | Configure DM access control |
| T002 | WP01 | Display QR code for linking |
| T003 | WP01 | Kent scans QR, verify linked |
| T004 | WP01 | E2E text message test |
| T005 | WP01 | Voice note arrival test |
| T006 | WP01 | Session persistence test |
| T007 | WP01 | Verify no new ports |
| T008 | WP02 | Create runbook |
| T009 | WP02 | Update service-inventory.json |
| T010 | WP02 | Update credential-manifest.json |
| T011 | WP02 | Update markdown arch docs |

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: planned
<!-- status-model:end -->
