---
work_package_id: WP01
title: Docker Deploy and systemd Service
lane: planned
dependencies: []
requirement_refs:
- C-001
- C-003
- C-004
- C-005
- C-006
- C-007
- FR-001
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
phase: Phase 1 - Foundation
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-26T06:31:38Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP01 – Docker Deploy and systemd Service

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

**Implementation command**: `spec-kitty implement WP01`

---

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status`. If it says `has_feedback`, read `review_feedback` first.
- **You must address all feedback** before your work is complete.

---

## Objectives & Success Criteria

Deploy Vikunja as a Docker container on office2 with:
- Container running and bound to `100.92.197.90:3456`
- SQLite database persisted to `/data/services/vikunja/data/`
- systemd unit managing the container (start on boot, restart on failure)
- Deployment script and systemd unit committed to `scripts/vikunja/`

**Success**: `curl http://100.92.197.90:3456` returns the Vikunja web UI. `systemctl status vikunja` shows active. Port not bound to `0.0.0.0`.

## Context & Constraints

- **SSH access**: Use `ssh office2-claude` only. Never use `ssh office2-kgale`.
- **Sudo**: The claude user has no sudo. Commands requiring sudo must be presented to Kent for manual execution.
- **Architecture spec**: `docs/design/personal-ai-system-spec-v03.md`
- **Plan**: `kitty-specs/001-vikunja-docker-deploy/plan.md`
- **Research**: `kitty-specs/001-vikunja-docker-deploy/research.md` (see R-001, R-002, R-003)
- **Constitution**: `.kittify/constitution/constitution.md`

**Key constraints**:
- Bind to Tailscale IP `100.92.197.90:3456:3456` — never `0.0.0.0`
- Pin Docker image to a specific version tag — never `latest`
- Data volume at `/data/services/vikunja/data/` — already in Restic backup scope
- No credentials in committed files

## Subtasks & Detailed Guidance

### Subtask T001 – Discover office2 Environment

**Purpose**: Confirm prerequisites before deployment begins.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check Docker is installed: `docker --version`
3. Check Docker Compose availability: `docker compose version` (note: if not installed or not in active use, prefer systemd unit approach per plan)
4. Check for existing Docker Compose files: `find /data/services -name "docker-compose*.yml" -o -name "compose*.yml" 2>/dev/null`
5. Check Tailscale status: `tailscale status`
6. Confirm Tailscale IP: `tailscale ip -4` (should be `100.92.197.90`)
7. Check port 3456 is free: `ss -tlnp | grep 3456`
8. Review existing systemd pattern: `cat /etc/systemd/system/obsidian-sync.service` (if accessible)
9. Verify data directory parent exists: `ls -la /data/services/`

**Files**: None created — discovery only.
**Parallel?**: No — must complete before other subtasks.
**Notes**: If Docker is not installed, STOP and report to Kent. If Tailscale IP differs from expected, update the bind address accordingly and flag the discrepancy.

### Subtask T002 – Select and Pin Vikunja Docker Image Version

**Purpose**: Choose a specific stable Vikunja image version for deterministic deployments.

**Steps**:
1. Check available Vikunja images: `docker search vikunja/vikunja` or check Docker Hub
2. The official image is `vikunja/vikunja` (single-container image with frontend+API+database)
3. Select the latest stable release tag (not `latest`, not `unstable`, not `main`)
4. Record the chosen version for use in T005 and T006
5. Pull the image to verify it works: `docker pull vikunja/vikunja:<version>`

**Files**: Version recorded in `scripts/vikunja/deploy.sh`.
**Parallel?**: No — version needed by T004, T005, T006.
**Notes**: Check Vikunja release notes for any breaking changes. The image name may be `vikunja/vikunja` (v0.24+) or `vikunja/api` + `vikunja/frontend` (older). Use the single combined image.

### Subtask T003 – Create Data Directory

**Purpose**: Ensure the host volume mount point exists before starting the container.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Create directory: `mkdir -p /data/services/vikunja/data`
3. Verify: `ls -la /data/services/vikunja/`
4. Confirm the claude user has write access to this path

**Files**: Directory `/data/services/vikunja/data/` on office2.
**Parallel?**: No — must exist before T006.
**Notes**: If `/data/services/` is not writable by claude, this requires sudo — present to Kent.

### Subtask T004 – Create systemd Unit File

**Purpose**: Define the systemd service that manages the Vikunja Docker container.

**Steps**:
1. Create `scripts/vikunja/vikunja.service` in the repo
2. Model after `obsidian-sync.service` on office2 (discovered in T001)
3. Key configuration:
   - `ExecStart`: `docker run` command with all flags (see T005 for the full command)
   - `ExecStop`: `docker stop vikunja`
   - `Restart=always`
   - `RestartSec=10`
   - `After=docker.service network-online.target`
   - `Wants=docker.service`

**Example unit file structure**:
```ini
[Unit]
Description=Vikunja Task Manager
After=docker.service network-online.target
Wants=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=10
ExecStartPre=-/usr/bin/docker rm -f vikunja
ExecStart=/usr/bin/docker run --rm --name vikunja \
  -p 100.92.197.90:3456:3456 \
  -v /data/services/vikunja/data:/app/vikunja/files \
  -e VIKUNJA_SERVICE_PUBLICURL=http://office2:3456 \
  -e VIKUNJA_DATABASE_TYPE=sqlite \
  -e VIKUNJA_DATABASE_PATH=/app/vikunja/files/vikunja.db \
  vikunja/vikunja:<VERSION>
ExecStop=/usr/bin/docker stop vikunja

[Install]
WantedBy=multi-user.target
```

**Files**: `scripts/vikunja/vikunja.service` (new file in repo).
**Parallel?**: Yes — can be written alongside T005.
**Notes**: The exact volume mount path inside the container depends on the Vikunja version. Check the image docs. Environment variables configure Vikunja to use SQLite and set the public URL. Adjust `VIKUNJA_DATABASE_PATH` if the container expects a different internal path.

### Subtask T005 – Create Deployment Script

**Purpose**: Automate the Docker pull, container creation, and systemd installation steps.

**Steps**:
1. Create `scripts/vikunja/deploy.sh` in the repo
2. Script should:
   - Check Docker is available
   - Check port 3456 is free (or already used by vikunja)
   - Pull the pinned image
   - Copy `vikunja.service` to the systemd directory (requires sudo — output the command for Kent)
   - Reload systemd (requires sudo — output the command for Kent)
   - Enable and start the service (requires sudo — output the command for Kent)
3. Make the script executable: `chmod +x scripts/vikunja/deploy.sh`

**Example sudo commands to present to Kent**:
```bash
sudo cp scripts/vikunja/vikunja.service /etc/systemd/system/vikunja.service
sudo systemctl daemon-reload
sudo systemctl enable vikunja
sudo systemctl start vikunja
```

**Files**: `scripts/vikunja/deploy.sh` (new file in repo).
**Parallel?**: Yes — can be written alongside T004.
**Notes**: The script should clearly separate what the claude user can do (pull image, check prerequisites) from what requires sudo (systemd operations). Print sudo commands for Kent rather than attempting to run them.

### Subtask T006 – Deploy Container on office2

**Purpose**: Execute the deployment on office2.

**Steps**:
1. Copy deployment files to office2 or run from the repo checkout on office2
2. Run `deploy.sh` as claude user
3. Present sudo commands to Kent for execution
4. After Kent runs sudo commands, verify:
   - `docker ps | grep vikunja` shows the container running
   - `ss -tlnp | grep 3456` shows binding to `100.92.197.90` only
   - `curl http://100.92.197.90:3456` returns the Vikunja web page

**Files**: None created — execution step.
**Parallel?**: No — depends on T002-T005.
**Notes**: If the container fails to start, check `docker logs vikunja` and `journalctl -u vikunja` for errors. Common issues: port conflict, volume permission errors, image pull failures.

### Subtask T007 – Install and Enable systemd Unit

**Purpose**: Ensure Vikunja starts on boot and restarts on failure.

**Steps**:
1. Present the following commands to Kent for manual execution:
   ```bash
   sudo cp /path/to/scripts/vikunja/vikunja.service /etc/systemd/system/vikunja.service
   sudo systemctl daemon-reload
   sudo systemctl enable vikunja
   sudo systemctl start vikunja
   ```
2. Verify: `systemctl status vikunja` (should show active)
3. Test restart: `sudo systemctl restart vikunja` (present to Kent)
4. Verify recovery: `systemctl status vikunja` after restart

**Files**: systemd unit installed at `/etc/systemd/system/vikunja.service` on office2.
**Parallel?**: No — final step in WP01.
**Notes**: All `systemctl` write operations require sudo. The claude user can read status but not start/stop/enable services. Present all commands to Kent.

## Risks & Mitigations

- **Docker not installed**: T001 checks. If missing, STOP and report.
- **Port conflict**: T005 checks `ss -tlnp | grep 3456` before proceeding.
- **Docker bypasses firewall**: Mitigated by binding to Tailscale IP, not `0.0.0.0`.
- **Volume permissions**: claude user may not have write access to `/data/services/`. If so, present `mkdir`/`chown` commands to Kent.
- **Vikunja image path changes**: Check image docs for correct volume mount paths.

## Review Guidance

- Confirm `vikunja.service` follows the same pattern as `obsidian-sync.service` on office2
- Verify bind address is `100.92.197.90:3456` — never `0.0.0.0`
- Confirm no credentials appear in any committed file
- Check that deploy.sh clearly separates claude-runnable vs sudo-required steps
- Verify SQLite data path is `/data/services/vikunja/data/`

## Activity Log

- 2026-03-26T06:31:38Z – system – lane=planned – Prompt created.
