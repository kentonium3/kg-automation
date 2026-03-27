# Work Packages: OpenClaw Install and Configuration

**Inputs**: Design documents from `kitty-specs/002-openclaw-install-config/`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual verification against acceptance scenarios. No automated test suite.

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package must be independently deliverable and testable.

**Prompt Files**: Each work package references a matching prompt file in `tasks/`.

---

## Work Package WP01: Install OpenClaw and Credential Store (Priority: P0)

**Goal**: Install OpenClaw via npm at pinned version, create credential store and data directories with correct permissions.
**Independent Test**: `openclaw --version` returns `v2026.3.24`. Credential store directory exists with mode 700.
**Prompt**: `tasks/WP01-install-credential-store.md`
**Requirement Refs**: FR-001, FR-002, NFR-002, NFR-004, C-002, C-003, C-004, C-005

### Included Subtasks
- [x] T001 Verify Node.js version on office2 (22.16+ required)
- [x] T002 Install OpenClaw via `npm install -g openclaw@v2026.3.24`
- [x] T003 Create directory structure (`/data/services/openclaw/secrets/`, `/data/services/openclaw/data/`)
- [x] T004 Set credential store permissions (directory mode 700, claude-owned)
- [x] T005 Create `scripts/openclaw/install.sh` in repo (captures installation steps)
- [x] T006 Provide Kent with instructions for placing the Anthropic API key

### Implementation Notes
- SSH to office2 as claude: `ssh office2-claude`
- npm global install does not require sudo on most setups; verify
- If npm global install requires sudo, present the command to Kent
- Credential file placement is manual by Kent — provide exact commands with paths

### Parallel Opportunities
- T005 (install script) can be written alongside T002-T004

### Dependencies
- None (starting package)

### Risks & Mitigations
- npm global install may require sudo → check `npm config get prefix` and adjust
- Node.js version too old → T001 checks first; if wrong version, stop and report

---

## Work Package WP02: Onboarding, Configuration, and systemd Capture (Priority: P0)

**Goal**: Run OpenClaw onboarding (Kent interactive), customize config with SecretRef file source for API key, capture and adjust the generated systemd unit.
**Independent Test**: `openclaw.json` has SecretRef pointing to credential file. `scripts/openclaw/openclaw.service` exists in repo with correct User/paths.
**Prompt**: `tasks/WP02-onboard-config-systemd.md`
**Requirement Refs**: FR-003, FR-004, NFR-001, NFR-003, C-001

### Included Subtasks
- [x] T007 Provide Kent with onboarding commands and expected prompts
- [x] T008 After Kent completes onboarding, verify OpenClaw is running
- [x] T009 Customize `~/.openclaw/openclaw.json` with SecretRef, workspace path, gateway loopback
- [x] T010 Capture the generated systemd unit file
- [x] T011 Adjust captured unit (User=claude, paths, Restart=always, RestartSec=10)
- [x] T012 Commit captured unit to `scripts/openclaw/openclaw.service`
- [x] T013 Install adjusted unit (sudo — present to Kent) and verify service

### Implementation Notes
- Kent runs `openclaw onboard --install-daemon` interactively
- After onboard, find the generated unit: `systemctl cat openclaw` or check `~/.config/systemd/user/`
- The onboarding may create a user-level service; we may need to convert to system-level
- Config customization: edit `/home/claude/.openclaw/openclaw.json` to add SecretRef and workspace path
- Verify no proxy: `journalctl -u openclaw | grep -i "litellm\|proxy\|openai"` should return nothing

### Parallel Opportunities
- None — sequential (onboard → capture → adjust → install)

### Dependencies
- Depends on WP01 (OpenClaw must be installed, credentials placed)

### Risks & Mitigations
- Onboarding creates user-level systemd unit instead of system-level → convert and adjust
- Config format differs from research → inspect actual `openclaw.json` and adapt
- OpenClaw doesn't support SecretRef file source in this version → fall back to EnvironmentFile= pattern per user direction

---

## Work Package WP03: Vikunja Token and Connectivity (Priority: P0)

**Goal**: Generate and store a persistent Vikunja API token, verify OpenClaw can reach Vikunja.
**Independent Test**: `curl` with stored token returns HTTP 200 from Vikunja. Token survives Vikunja restart.
**Prompt**: `tasks/WP03-vikunja-token.md`
**Requirement Refs**: FR-005

### Included Subtasks
- [ ] T014 Provide Kent with Vikunja token generation instructions (UI: Settings → API Tokens)
- [ ] T015 Provide Kent with token placement command (`/data/services/openclaw/secrets/vikunja-api`)
- [ ] T016 Verify token permissions (mode 600, claude-owned)
- [ ] T017 Verify Vikunja connectivity from office2 using stored token
- [ ] T018 Verify token persists across Vikunja container restart

### Implementation Notes
- Kent generates token in Vikunja UI (name: `openclaw-agent`)
- Kent places raw token value in credential file
- Verification: `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info`
- Restart verification: Kent runs `sudo systemctl restart vikunja`, then re-verify

### Parallel Opportunities
- None — sequential (generate → place → verify)

### Dependencies
- Depends on WP02 (OpenClaw must be running and configured)

### Risks & Mitigations
- Vikunja doesn't support persistent API tokens → check if only session JWTs are available; may need a different auth approach
- Token permission wrong → T016 verifies before connectivity test

---

## Work Package WP04: Ops Runbook, Architecture Docs, Security Baseline (Priority: P1)

**Goal**: Create ops runbook, update architecture documentation JSON and markdown, reset security baselines.
**Independent Test**: Runbook passes `validate_docs.py`. Architecture JSON files have `updated_by: "F002"`. Security audit produces no false positives.
**Prompt**: `tasks/WP04-docs-security.md`
**Requirement Refs**: FR-006, FR-007, FR-008

### Included Subtasks
- [ ] T019 Create `docs/handbooks/openclaw-ops.md` with frontmatter
- [ ] T020 Document start/stop/restart, logs, credential rotation, version updates, skill directory
- [ ] T021 Update `docs/design/architecture/data/service-inventory.json` with OpenClaw entry
- [ ] T022 Update `docs/design/architecture/data/credential-manifest.json` (move anthropic/vikunja-api from planned to active)
- [ ] T023 Update `docs/design/architecture/service-inventory.md` and `credentials-and-secrets.md`
- [ ] T024 Reset security audit baselines on office2 (may require sudo — present to Kent)

### Implementation Notes
- Runbook format: match `docs/handbooks/vikunja-ops.md` structure
- JSON updates: set `last_updated` to today, `updated_by` to `"F002"`
- Security baseline reset: follow procedure in `docs/handbooks/vikunja-ops.md#security-baseline-reset`
- All markdown must pass `validate_docs.py`

### Parallel Opportunities
- T019-T023 (docs) can proceed in parallel with T024 (security baseline)
- WP04 can start after WP02 completes, in parallel with WP03

### Dependencies
- Depends on WP02 (needs actual service details for runbook and architecture docs)

### Risks & Mitigations
- Security baseline reset requires sudo → present to Kent
- Architecture JSON schema mismatch → read existing files first, match format

---

## Work Package WP05: Acceptance Testing (Priority: P1)

**Goal**: Verify all acceptance scenarios from the spec. Document pass/fail results.
**Independent Test**: All acceptance scenarios pass. No proxy in logs. Credentials secure.
**Prompt**: `tasks/WP05-acceptance.md`
**Requirement Refs**: FR-001, FR-003, NFR-001, NFR-002, NFR-003

### Included Subtasks
- [ ] T025 Verify `systemctl status openclaw` shows active
- [ ] T026 Verify service restarts after `systemctl restart openclaw` (sudo — present to Kent)
- [ ] T027 Verify no proxy references in logs (`journalctl -u openclaw`)
- [ ] T028 Verify credential store permissions (directory 700, files 600, claude-owned)
- [ ] T029 Verify Vikunja connectivity with stored token
- [ ] T030 Verify API key not in process environment (`cat /proc/$(pgrep -f openclaw)/environ`)
- [ ] T031 Document acceptance results

### Implementation Notes
- All checks via `ssh office2-claude`
- Restart test requires Kent for sudo
- Process environment check (T030) is critical — verifies SecretRef file source works correctly
- Document results as pass/fail in `docs/handbooks/f002-acceptance-results.md`

### Parallel Opportunities
- T025-T030 are independent checks (can run in parallel)
- T031 runs last

### Dependencies
- Depends on WP01, WP02, WP03, WP04 (all must be complete)

### Risks & Mitigations
- OpenClaw process name differs from expected → use `pgrep -f openclaw` or check `systemctl show openclaw --property=MainPID`

---

## Dependency & Execution Summary

- **Sequence**: WP01 → WP02 → WP03 + WP04 (parallel) → WP05
- **Parallelization**: WP03 and WP04 can proceed simultaneously after WP02
- **MVP Scope**: WP01 + WP02 = OpenClaw installed, configured, and running with API key

---

## Requirements Coverage Summary

| Requirement ID | Covered By Work Package(s) |
|----------------|----------------------------|
| FR-001 | WP01, WP05 |
| FR-002 | WP01 |
| FR-003 | WP02, WP05 |
| FR-004 | WP02 |
| FR-005 | WP03 |
| FR-006 | WP04 |
| FR-007 | WP04 |
| FR-008 | WP04 |
| NFR-001 | WP02, WP05 |
| NFR-002 | WP01, WP05 |
| NFR-003 | WP02, WP05 |
| NFR-004 | WP01 |
| C-001 | WP02 |
| C-002 | WP01 |
| C-003 | WP01 |
| C-004 | WP01 |
| C-005 | WP01 |
| C-006 | WP02 |
| C-007 | WP01 |

---

## Subtask Index (Reference)

| Subtask ID | Summary | Work Package | Priority | Parallel? |
|------------|---------|--------------|----------|-----------|
| T001 | Verify Node.js version | WP01 | P0 | No |
| T002 | npm install OpenClaw | WP01 | P0 | No |
| T003 | Create directory structure | WP01 | P0 | No |
| T004 | Set credential store permissions | WP01 | P0 | No |
| T005 | Create install.sh in repo | WP01 | P0 | Yes |
| T006 | Instructions for API key placement | WP01 | P0 | No |
| T007 | Provide onboarding commands to Kent | WP02 | P0 | No |
| T008 | Verify onboarding result | WP02 | P0 | No |
| T009 | Customize openclaw.json config | WP02 | P0 | No |
| T010 | Capture generated systemd unit | WP02 | P0 | No |
| T011 | Adjust captured unit | WP02 | P0 | No |
| T012 | Commit unit to scripts/openclaw/ | WP02 | P0 | No |
| T013 | Install adjusted unit (sudo) and verify | WP02 | P0 | No |
| T014 | Instructions for Vikunja token generation | WP03 | P0 | No |
| T015 | Instructions for token placement | WP03 | P0 | No |
| T016 | Verify token permissions | WP03 | P0 | No |
| T017 | Verify Vikunja connectivity | WP03 | P0 | No |
| T018 | Verify token persists across restart | WP03 | P0 | No |
| T019 | Create openclaw-ops.md with frontmatter | WP04 | P1 | Yes |
| T020 | Document operational procedures | WP04 | P1 | Yes |
| T021 | Update service-inventory.json | WP04 | P1 | Yes |
| T022 | Update credential-manifest.json | WP04 | P1 | Yes |
| T023 | Update markdown architecture docs | WP04 | P1 | Yes |
| T024 | Reset security baselines (sudo) | WP04 | P1 | Yes |
| T025 | Verify service active | WP05 | P1 | Yes |
| T026 | Verify service restart recovery | WP05 | P1 | No |
| T027 | Verify no proxy in logs | WP05 | P1 | Yes |
| T028 | Verify credential permissions | WP05 | P1 | Yes |
| T029 | Verify Vikunja connectivity | WP05 | P1 | Yes |
| T030 | Verify API key not in process environment | WP05 | P1 | Yes |
| T031 | Document acceptance results | WP05 | P1 | No |

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
<!-- status-model:end -->
