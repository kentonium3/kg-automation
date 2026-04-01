# F011 Tasks: Second Brain Vault Cleanup

**Feature**: 011-second-brain-vault-cleanup
**Branch**: main
**Total work packages**: 7
**Total subtasks**: 38

## Dependency graph

```
WP01 (Prerequisites)          WP02 (Vault Rename + Obsidian Sync)
  │                              │
  │                              ├─► WP03 (Repo Path Updates)
  │                              │     │
  │                              │     └─► WP04 (Office2 Agent Deploy)
  │                              │
  │                              └─► WP06 (Architecture Docs)
  │
  └─► WP05 (Sync Timer)
                                 WP04 ──┐
                                 WP05 ──┼─► WP07 (End-to-End Verification)
                                 WP06 ──┘
```

WP01 and WP02 can run in parallel.
WP03 and WP06 can run in parallel after WP02.
WP05 can start as soon as WP01 completes.
WP07 waits for WP04, WP05, and WP06.

## Work packages

### WP01: Prerequisites — Mac repo and office2 git credentials

**Priority**: P0 — foundation
**Dependencies**: none
**Estimated prompt size**: ~250 lines

Initialize the second-brain git repository on Mac, push to GitHub, and
provide Kent with exact commands for setting up git credentials on office2.

**Included subtasks**:
- [x] T001: Initialize git repo in `~/second-brain/` on Mac with `.gitignore` excluding `notes/`
- [x] T002: Create GitHub repo (kentonium3/second-brain), push Mac repo as origin
- [x] T003: Document and present manual git credential setup commands for Kent to run on office2 as kgale

**Prompt file**: [tasks/WP01-prerequisites.md](tasks/WP01-prerequisites.md)

---

### WP02: Vault rename and Obsidian Sync service update

**Priority**: P0 — foundation
**Dependencies**: none
**Estimated prompt size**: ~350 lines

Rename `vault/` to `notes/` on office2, update the obsidian-sync.service
unit file in the repo, deploy it to office2, and verify Obsidian Sync
resumes with the new path.

**Included subtasks**:
- [x] T004: Verify vault-snapshot absence on office2 (confirm no timer, service, or script)
- [x] T005: Rename `/home/kgale/second-brain/vault/` to `/home/kgale/second-brain/notes/` on office2
- [x] T006: Update `scripts/office2/obsidian-sync.service` in repo (vault → notes path)
- [x] T007: Deploy updated obsidian-sync.service to office2 and enable/start it
- [x] T008: Verify Obsidian Sync resumes — create test note on Mac, confirm appears on office2

**Prompt file**: [tasks/WP02-vault-rename-obsidian-sync.md](tasks/WP02-vault-rename-obsidian-sync.md)

---

### WP03: Repository path updates

**Priority**: P1 — path cleanup
**Dependencies**: WP02
**Estimated prompt size**: ~400 lines

Update all files in the kg-automation repo that reference the old
`second-brain/vault` path to use `second-brain/notes`. Only actionable
files — historical docs are left as-is.

**Included subtasks**:
- [ ] T009: Update `scripts/office2/validate-obsidian-sync.sh` (vault → notes) [P]
- [ ] T010: Update `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` (vault → notes) [P]
- [ ] T011: Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (vault → notes) [P]
- [ ] T012: Update `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` (vault → notes) [P]
- [ ] T013: Update `CLAUDE.md` privacy boundary path (vault → notes) [P]
- [ ] T014: Update `ai-agents/claude-code-instructions.md` privacy path (vault → notes) [P]
- [ ] T015: Update `ai-agents/claude-instructions.md` privacy path (vault → notes) [P]

**Prompt file**: [tasks/WP03-repo-path-updates.md](tasks/WP03-repo-path-updates.md)

---

### WP04: Deploy updated agent files to office2

**Priority**: P1 — deployment
**Dependencies**: WP03
**Estimated prompt size**: ~250 lines

Copy the updated agent workspace files from the repo to the deployed
locations on office2 and restart the OpenClaw agents.

**Included subtasks**:
- [ ] T016: Copy updated TOOLS.md and AGENTS.md to `/data/services/openclaw/inbox-agent/`
- [ ] T017: Copy updated TOOLS.md to `/data/services/openclaw/habits-agent/`
- [ ] T018: Restart OpenClaw agents (or present restart commands to Kent)

**Prompt file**: [tasks/WP04-office2-agent-deploy.md](tasks/WP04-office2-agent-deploy.md)

---

### WP05: Bidirectional git sync timer

**Priority**: P1 — new capability
**Dependencies**: WP01
**Estimated prompt size**: ~400 lines

Create the bidirectional sync script and systemd timer, initialize the
git repo on office2, and deploy and enable the timer.

**Included subtasks**:
- [ ] T019: Create `scripts/office2/second-brain-sync.sh` — bidirectional pull/commit/push script
- [ ] T020: Create `scripts/office2/second-brain-sync.service` — systemd unit to run sync script
- [ ] T021: Create `scripts/office2/second-brain-sync.timer` — 15-minute systemd timer
- [ ] T022: Initialize git repo on office2 (`/home/kgale/second-brain/`), add remote, pull from origin
- [ ] T023: Create `.gitignore` on office2 with `notes/` excluded
- [ ] T024: Deploy sync script and timer to office2, enable and start

**Prompt file**: [tasks/WP05-sync-timer.md](tasks/WP05-sync-timer.md)

---

### WP06: Architecture docs and handbooks

**Priority**: P1 — documentation
**Dependencies**: WP02
**Estimated prompt size**: ~500 lines

Update architecture JSON files, their markdown narratives, and operational
handbooks to reflect the vault rename, vault-snapshot removal, and new
bidirectional sync timer.

**Included subtasks**:
- [ ] T025: Update `docs/design/architecture/data/service-inventory.json` — remove vault-snapshot, update obsidian-sync, add second-brain-sync [P]
- [ ] T026: Update `docs/design/architecture/data/data-flows.json` — vault → notes, add sync flow [P]
- [ ] T027: Update `docs/design/architecture/service-inventory.md` narrative [P]
- [ ] T028: Update `docs/design/architecture/data-flows.md` narrative [P]
- [ ] T029: Update `docs/design/architecture/glossary.md` — vault definition → notes [P]
- [ ] T030: Update `docs/design/architecture/security-posture.md` — privacy path [P]
- [ ] T031: Update `docs/design/architecture/backup-and-recovery.md` — backup path [P]
- [ ] T032: Update `docs/handbooks/obsidian-sync-ops.md` — vault → notes, remove git snapshot section
- [ ] T033: Update `docs/handbooks/inbox-ops.md` — vault → notes

**Prompt file**: [tasks/WP06-architecture-docs.md](tasks/WP06-architecture-docs.md)

---

### WP07: End-to-end verification

**Priority**: P2 — validation
**Dependencies**: WP04, WP05, WP06
**Estimated prompt size**: ~300 lines

Run comprehensive verification that all systems work with the new paths:
Obsidian Sync, inbox processing, git bidirectional sync, and no stale
references remain.

**Included subtasks**:
- [ ] T034: Run grep audit for remaining `second-brain/vault` references in repo and on office2
- [ ] T035: Create test note on Mac, verify appears on office2 in `notes/00-Inbox/` within 5 minutes
- [ ] T036: Trigger manual inbox processing run, verify success
- [ ] T037: Push test file from Mac, verify office2 pulls within 15 minutes
- [ ] T038: Create test file on office2, verify appears in origin within 15 minutes

**Prompt file**: [tasks/WP07-end-to-end-verification.md](tasks/WP07-end-to-end-verification.md)

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
- WP02: in_progress
<!-- status-model:end -->
