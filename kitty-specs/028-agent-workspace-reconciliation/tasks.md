# Tasks: Agent Workspace Reconciliation

**Mission**: 028-agent-workspace-reconciliation
**Date**: 2026-04-13
**Branch**: `main` → `main`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Capture main/AGENTS.md from office2 to repo | WP01 | [P] | [D] |
| T002 | Capture main/TOOLS.md from office2 to repo | WP01 | [D] |
| T003 | Capture main/IDENTITY.md from office2 to repo | WP01 | [D] |
| T004 | Capture capture/AGENTS.md from office2 to update repo | WP01 | [D] |
| T005 | Archive and remove main-patches/ directory | WP01 | | [D] |
| T006 | Generate baseline-manifest.json from reconciled state | WP02 | | [D] |
| T007 | Generate factory-baselines.json with known factory hashes | WP02 | [D] |
| T008 | Create drift-check-config.json with agent mapping | WP02 | [D] |
| T009 | Create drift-check.py — CLI entry, manifest loading, hash computation | WP03 | | [D] |
| T010 | Implement three-way diff logic (current vs baseline for both sides) | WP03 | | [D] |
| T011 | Implement factory-default threshold detection | WP03 | | [D] |
| T012 | Write pytest tests for detection engine | WP03 | | [D] |
| T013 | Implement auto-deploy action (repo→office2 via SCP) | WP04 | | [D] |
| T014 | Implement auto-capture action (office2→repo + git commit) | WP04 | | [D] |
| T015 | Implement conflict detection and notification routing | WP04 | | [D] |
| T016 | Implement WhatsApp notification via openclaw agent --deliver | WP04 | | [D] |
| T017 | Implement GitHub issue creation for conflicts/factory transitions | WP04 | | [D] |
| T018 | Write pytest tests for remediation and notification logic | WP04 | | [D] |
| T019 | Create deploy-028.sh following safe-deploy pattern | WP05 | |
| T020 | Deploy reconciled tasker files repo→office2 via SCP | WP05 | |
| T021 | Install drift-check.py + cron job on office2 | WP05 | |
| T022 | Post-reconciliation zero-drift verification (hash comparison) | WP05 | |
| T023 | Controlled drift test (introduce change, verify detection + action) | WP05 | |
| T024 | Write runbook: agent-workspace-reconciliation.md | WP06 | |
| T025 | Document factory-default lifecycle policy in runbook | WP06 | |
| T026 | Document last-author-wins enforcement strategy in runbook | WP06 | |
| T027 | Update docs/INDEX.md with new runbook entry | WP06 | |

## Work Packages

### WP01: Office2 captures and main-patches retirement

**Priority**: Critical — all other WPs depend on this
**Goal**: Capture 4 files from office2 into the repo, retire the main-patches/ overlay pattern
**Dependencies**: None
**Estimated prompt size**: ~350 lines
**Prompt**: [WP01-office2-captures-and-retirement.md](tasks/WP01-office2-captures-and-retirement.md)

- [x] T001 Capture main/AGENTS.md from office2 to repo (WP01)
- [x] T002 Capture main/TOOLS.md from office2 to repo (WP01)
- [x] T003 Capture main/IDENTITY.md from office2 to repo (WP01)
- [x] T004 Capture capture/AGENTS.md from office2 to update repo (WP01)
- [x] T005 Archive and remove main-patches/ directory (WP01)

**Implementation sketch**:
1. SCP each file from office2 workspace path to repo agent directory
2. Verify content matches (sha256 comparison)
3. Move main-patches/ contents to a git-tracked archive note, then delete the directory
4. Commit all captures + retirement as a single commit

**Risks**: Office2 connectivity. Mitigation: verify SSH before starting.

---

### WP02: Baseline manifests and enforcement config

**Priority**: High — enforcement script depends on these artifacts
**Goal**: Generate machine-readable JSON manifests recording post-reconciliation state
**Dependencies**: WP01
**Estimated prompt size**: ~300 lines
**Prompt**: [WP02-baseline-manifests-and-config.md](tasks/WP02-baseline-manifests-and-config.md)

- [x] T006 Generate baseline-manifest.json from reconciled state (WP02)
- [x] T007 Generate factory-baselines.json with known factory hashes (WP02)
- [x] T008 Create drift-check-config.json with agent mapping (WP02)

**Implementation sketch**:
1. Write a Python helper script to probe all agent workspaces on office2, compute SHA256 hashes, and output baseline-manifest.json
2. Manually curate factory-baselines.json from known unmodified template hashes (research.md R6)
3. Create drift-check-config.json with agent→workspace mapping (research.md R7), notification config, enforcement mode

**Parallel opportunities**: T007 and T008 are independent of each other.

---

### WP03: Enforcement script — detection engine

**Priority**: High — core enforcement logic
**Goal**: Build the drift detection engine that reads manifests, computes current hashes, and classifies drift via three-way diff
**Dependencies**: WP02
**Estimated prompt size**: ~400 lines
**Prompt**: [WP03-enforcement-detection-engine.md](tasks/WP03-enforcement-detection-engine.md)

- [x] T009 Create drift-check.py — CLI entry, manifest loading, hash computation (WP03)
- [x] T010 Implement three-way diff logic (current vs baseline for both sides) (WP03)
- [x] T011 Implement factory-default threshold detection (WP03)
- [x] T012 Write pytest tests for detection engine (WP03)

**Implementation sketch**:
1. Create `scripts/openclaw/enforcement/drift-check.py` with argparse CLI
2. Load baseline-manifest.json and factory-baselines.json
3. For each agent+file: compute current repo hash (local), compute current office2 hash (via SSH)
4. Compare current hashes against baseline → classify as: no-change, repo-changed, office2-changed, both-changed
5. Check factory-default files against factory-baselines.json
6. Output structured drift report (JSON to stdout)
7. Write pytest tests with mock manifests and hash fixtures

**Risks**: SSH latency for hash computation. Mitigation: batch SSH commands.

---

### WP04: Enforcement script — remediation and notification

**Priority**: High — actions the enforcement script takes on detected drift
**Goal**: Implement auto-deploy, auto-capture, conflict notification, and factory-default alerts
**Dependencies**: WP03
**Estimated prompt size**: ~450 lines
**Prompt**: [WP04-enforcement-remediation-notification.md](tasks/WP04-enforcement-remediation-notification.md)

- [x] T013 Implement auto-deploy action (repo→office2 via SCP) (WP04)
- [x] T014 Implement auto-capture action (office2→repo + git commit) (WP04)
- [x] T015 Implement conflict detection and notification routing (WP04)
- [x] T016 Implement WhatsApp notification via openclaw agent --deliver (WP04)
- [x] T017 Implement GitHub issue creation for conflicts/factory transitions (WP04)
- [x] T018 Write pytest tests for remediation and notification logic (WP04)

**Implementation sketch**:
1. Auto-deploy: SCP repo file → office2 workspace path, verify hash post-copy, update baseline manifest
2. Auto-capture: SCP office2 file → repo path, git add + commit with `chore: drift-reconcile` prefix, update baseline manifest
3. Conflict routing: when both sides changed, compose alert message with agent/file/direction details
4. WhatsApp: shell out to `openclaw agent --deliver --channel whatsapp --to <number> --message "<alert>"`
5. GitHub issue: shell out to `gh issue create --repo <repo> --title "<title>" --body "<body>" --label drift-alert`
6. pytest: mock subprocess calls, test routing logic, test manifest updates

**Parallel opportunities**: T016 and T017 are independent notification implementations.

---

### WP05: Deploy and integration verification

**Priority**: High — validates the entire mission end-to-end
**Goal**: Deploy reconciled tasker files + enforcement cron to office2, verify with controlled drift test
**Dependencies**: WP01, WP04
**Estimated prompt size**: ~400 lines
**Prompt**: [WP05-deploy-and-integration.md](tasks/WP05-deploy-and-integration.md)

- [ ] T019 Create deploy-028.sh following safe-deploy pattern (WP05)
- [ ] T020 Deploy reconciled tasker files repo→office2 via SCP (WP05)
- [ ] T021 Install drift-check.py + cron job on office2 (WP05)
- [ ] T022 Post-reconciliation zero-drift verification (hash comparison) (WP05)
- [ ] T023 Controlled drift test (introduce change, verify detection + action) (WP05)

**Implementation sketch**:
1. Create deploy-028.sh: pre-flight (Restic age check, SSH reachability, --backup-confirmed gate), copy artifacts (tasker files + enforcement script), verify, post-flight smoke test
2. SCP 4 reconciled tasker files to `/data/services/openclaw/tasker-agent/`
3. SCP drift-check.py + config to office2, add cron entry via `crontab -e` or helper
4. Run drift-check.py manually to produce zero-drift verification report
5. Introduce a 1-line change to a deployed file, run drift-check.py, verify detection + auto-remediation

**Risks**: Tier 2 — deploy touches production agent workspaces. Mitigation: Restic backup confirmed pre-flight, --backup-confirmed flag.

---

### WP06: Runbook and documentation

**Priority**: Standard — documents the system for future sessions
**Goal**: Write the reconciliation runbook, factory-default lifecycle policy, and update docs index
**Dependencies**: WP04
**Estimated prompt size**: ~300 lines
**Prompt**: [WP06-runbook-and-documentation.md](tasks/WP06-runbook-and-documentation.md)

- [ ] T024 Write runbook: agent-workspace-reconciliation.md (WP06)
- [ ] T025 Document factory-default lifecycle policy in runbook (WP06)
- [ ] T026 Document last-author-wins enforcement strategy in runbook (WP06)
- [ ] T027 Update docs/INDEX.md with new runbook entry (WP06)

**Implementation sketch**:
1. Write `docs/runbooks/agent-workspace-reconciliation.md` covering: what the enforcement script does, how to run it manually, how the three-way diff works, how to add a new agent, how to handle conflicts
2. Include factory-default lifecycle policy section: trigger (hash divergence from factory baseline), detection mechanism, response (issue + notification), capture workflow
3. Include last-author-wins strategy explanation with the decision matrix
4. Add entry to docs/INDEX.md under Runbooks section

**Parallel opportunities**: WP06 can run in parallel with WP05 (different file surfaces).

## Parallelization Summary

```
WP01 ──→ WP02 ──→ WP03 ──→ WP04 ──→ WP05
                                  └──→ WP06  (parallel with WP05)
```

Lane A: WP01 → WP02 → WP03 → WP04 → WP05
Lane B: WP06 (starts after WP04, parallel with WP05)

## MVP Scope

WP01 + WP02 delivers the reconciliation and baseline. WP03-WP04 deliver enforcement. WP05 validates. WP06 documents.

Minimum viable: WP01 alone resolves the immediate drift problem (#156/#157). Everything else is durability.
