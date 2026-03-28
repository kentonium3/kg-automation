---
work_package_id: WP01
title: Security Hardening — Rebind, systemd, Deploy Config
lane: "doing"
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- FR-001
- FR-002
- FR-005
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 269a77126db5a7345f7011b71e1419d0e1f81241
created_at: '2026-03-28T16:33:45.650607+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Foundation
assignee: ''
agent: "claude"
shell_pid: "68164"
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

# Work Package Prompt: WP01 – Security Hardening — Rebind, systemd, Deploy Config

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP01`

---

## Objectives & Success Criteria

Capture the existing Docker Compose configuration for the `transcribe-api` service on office2, rebind it from `0.0.0.0:8787` to `100.92.197.90:8787` (Tailscale IP only), create a systemd unit to manage the service lifecycle via Docker Compose, create a deployment script, and deploy the changes.

**Success**:
- `ss -tlnp | grep 8787` shows `100.92.197.90:8787`, not `0.0.0.0:8787`
- `curl http://100.92.197.90:8787/health` returns a successful response
- `systemctl is-active transcribe` returns `active`
- `scripts/transcribe/docker-compose.yml`, `scripts/transcribe/transcribe.service`, and `scripts/transcribe/deploy.sh` committed to repo

## Context & Constraints

- **SSH**: `ssh office2-claude` only. The claude user does **not** have sudo. Commands requiring sudo must be presented to Kent to run manually.
- **Research**: `kitty-specs/003-whisper-transcription-skill/research.md` (R-002: rebind approach, R-004: connectivity)
- **Pattern**: `scripts/vikunja/vikunja.service` — reference systemd unit from F001. Note: Vikunja uses `docker run` directly; this feature uses Docker Compose (`docker compose up -d`).
- **Constraint C-001**: Port 8787 must bind to `100.92.197.90`, never `0.0.0.0`
- **Constraint C-002**: Reuse existing Docker image — do NOT rebuild or replace the image
- **Constraint C-004**: Use Docker Compose, not `docker run`. systemd wraps `docker compose up -d`
- **Constraint C-003**: Agent SSH identity — all commands via `ssh office2-claude`
- **Existing compose location on office2**: `/data/services/transcribe/docker-compose.yml`
- **Existing image**: `transcribe_transcribe` (locally built)
- **Volumes**: `/data/transcripts` (output), `/data/services/transcribe/models` (Whisper models)

## Subtasks & Detailed Guidance

### Subtask T001 – Capture Existing docker-compose.yml

**Purpose**: Copy the existing compose file from office2 into the repo before making any changes. This creates a reproducible record and a rollback reference.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Read the existing compose file: `cat /data/services/transcribe/docker-compose.yml`
3. Copy the full contents into a new file in the repo at `scripts/transcribe/docker-compose.yml`
4. Inspect the compose file and note:
   - The current `ports` mapping (expect `"8787:8787"` which means `0.0.0.0:8787:8787`)
   - The `build` directive (should reference local build context)
   - Volume mounts
   - Environment variables (`WHISPER_MODEL_SIZE`, workers, etc.)
   - Memory limits
   - Restart policy
5. Also capture `docker ps --format '{{.Names}} {{.Ports}}' | grep transcribe` output to confirm current binding

**Files**:
- `scripts/transcribe/docker-compose.yml` (new file in repo — exact copy of live config)

**Validation**:
- [ ] Compose file captured to repo
- [ ] Port mapping confirmed as `0.0.0.0:8787->8787/tcp` (or similar)

**Parallel?**: No — must complete before T002.

### Subtask T002 – Update Port Binding

**Purpose**: Change the port binding from `0.0.0.0` (all interfaces) to `100.92.197.90` (Tailscale only). This is the core security fix.

**Steps**:
1. In the repo copy at `scripts/transcribe/docker-compose.yml`, change the `ports` section:
   - **From**: `"8787:8787"` (or `- "8787:8787"`)
   - **To**: `"100.92.197.90:8787:8787"` (or `- "100.92.197.90:8787:8787"`)
2. Do NOT change any other settings (image, volumes, environment, memory limits, restart policy)
3. Verify the change is correct — the format is `HOST_IP:HOST_PORT:CONTAINER_PORT`

**Example** of the ports section after change:
```yaml
ports:
  - "100.92.197.90:8787:8787"
```

**Files**:
- `scripts/transcribe/docker-compose.yml` (edit in repo)

**Validation**:
- [ ] Only the port binding line changed
- [ ] IP address is exactly `100.92.197.90` (Tailscale IP)
- [ ] No other settings modified

**Parallel?**: No — depends on T001.

### Subtask T003 – Create systemd Unit

**Purpose**: Create a systemd service file that manages the transcribe-api lifecycle via Docker Compose. This ensures the service starts on boot, restarts on failure, and can be managed with `systemctl`.

**Steps**:
1. Create `scripts/transcribe/transcribe.service` in the repo
2. Follow the Docker Compose wrapping pattern (different from Vikunja's `docker run` pattern):
   - `Type=oneshot` with `RemainAfterExit=yes` (Docker Compose runs in background with `-d`)
   - `ExecStart=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml up -d`
   - `ExecStop=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml down`
   - `User=claude`
   - `Restart=on-failure` with `RestartSec=10`
   - Requires `docker.service` and `network-online.target`
3. Alternatively, if Docker Compose supports `docker compose up` (foreground mode without `-d`):
   - `Type=simple`
   - `ExecStart=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml up`
   - `ExecStop=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml down`
   - This is simpler and lets systemd manage the process directly
4. Check which approach works by testing on office2

**Reference** — Vikunja's systemd unit (`scripts/vikunja/vikunja.service`) uses `docker run` directly:
```ini
[Unit]
Description=Vikunja Task Manager
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=claude
Restart=always
RestartSec=10
ExecStartPre=-/usr/bin/docker rm -f vikunja
ExecStart=/usr/bin/docker run --rm --name vikunja ...
ExecStop=/usr/bin/docker stop vikunja

[Install]
WantedBy=multi-user.target
```

**Recommended transcribe.service structure**:
```ini
[Unit]
Description=Transcribe API (Whisper)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=claude
ExecStart=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml up -d
ExecStop=/usr/bin/docker compose -f /data/services/transcribe/docker-compose.yml down
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Files**:
- `scripts/transcribe/transcribe.service` (new file in repo)

**Validation**:
- [ ] Unit file uses Docker Compose, not `docker run`
- [ ] References `/data/services/transcribe/docker-compose.yml` (absolute path)
- [ ] `User=claude` set
- [ ] Restart policy configured
- [ ] Depends on `docker.service`

**Parallel?**: Yes — can be written alongside T001/T002 (independent file).

### Subtask T004 – Create deploy.sh Script

**Purpose**: Create a deployment helper script that copies the updated compose file to office2, installs the systemd unit, and provides the commands Kent needs to run with sudo.

**Steps**:
1. Create `scripts/transcribe/deploy.sh` in the repo
2. The script should:
   - Copy `docker-compose.yml` to `/data/services/transcribe/docker-compose.yml` on office2
   - Copy `transcribe.service` to a staging location (claude can't write to `/etc/systemd/system/`)
   - Print the sudo commands Kent needs to run:
     - `sudo cp /path/to/staged/transcribe.service /etc/systemd/system/transcribe.service`
     - `sudo systemctl daemon-reload`
     - `sudo systemctl enable transcribe`
     - `sudo systemctl start transcribe`
3. Make the script executable: `chmod +x scripts/transcribe/deploy.sh`

**Example structure**:
```bash
#!/usr/bin/env bash
set -euo pipefail

REMOTE="office2-claude"
COMPOSE_DEST="/data/services/transcribe/docker-compose.yml"
SERVICE_STAGING="/tmp/transcribe.service"

echo "=== Transcribe API Deployment ==="

# Copy compose file
echo "[1/3] Copying docker-compose.yml..."
scp scripts/transcribe/docker-compose.yml "${REMOTE}:${COMPOSE_DEST}"

# Copy service file to staging
echo "[2/3] Staging systemd unit..."
scp scripts/transcribe/transcribe.service "${REMOTE}:${SERVICE_STAGING}"

echo ""
echo "=== MANUAL STEPS (Kent runs these) ==="
echo "ssh office2-kgale"
echo ""
echo "# Stop existing container"
echo "docker compose -f ${COMPOSE_DEST} down"
echo ""
echo "# Install systemd unit"
echo "sudo cp ${SERVICE_STAGING} /etc/systemd/system/transcribe.service"
echo "sudo systemctl daemon-reload"
echo "sudo systemctl enable transcribe"
echo "sudo systemctl start transcribe"
echo ""
echo "# Verify"
echo "systemctl status transcribe"
echo "ss -tlnp | grep 8787"
echo "curl http://100.92.197.90:8787/health"
```

**Files**:
- `scripts/transcribe/deploy.sh` (new file in repo)

**Validation**:
- [ ] Script is executable
- [ ] No hardcoded secrets
- [ ] Sudo commands are printed, not executed
- [ ] Uses `ssh office2-claude` for non-sudo operations

**Parallel?**: Yes — can be written alongside T001-T003 (independent file).

### Subtask T005 – Deploy Rebind

**Purpose**: Execute the deployment — stop the existing container, apply the updated compose file with the new port binding, and start the service via systemd.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Stop the existing container:
   ```bash
   docker compose -f /data/services/transcribe/docker-compose.yml down
   ```
   Or if it was started via `docker run`:
   ```bash
   docker stop <container_name>
   ```
3. Copy the updated `docker-compose.yml` from repo to `/data/services/transcribe/docker-compose.yml` on office2
4. Stage the systemd unit: copy `transcribe.service` to `/tmp/transcribe.service` on office2
5. Present the following sudo commands to Kent:
   ```
   sudo cp /tmp/transcribe.service /etc/systemd/system/transcribe.service
   sudo systemctl daemon-reload
   sudo systemctl enable transcribe
   sudo systemctl start transcribe
   ```
6. Wait for Kent to confirm the commands have been run
7. Verify the container is running: `docker ps | grep transcribe`

**Files**: None (deployment operations on office2).

**Validation**:
- [ ] Existing container stopped cleanly
- [ ] Updated compose file deployed to office2
- [ ] systemd unit installed (by Kent via sudo)
- [ ] Service started via systemd

**Parallel?**: No — sequential, depends on T001-T004.

**CRITICAL**: Do NOT attempt to run sudo commands. Present them to Kent and wait for confirmation.

### Subtask T006 – Verify Rebind

**Purpose**: Confirm the service is correctly rebound, reachable, and operational.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check port binding:
   ```bash
   ss -tlnp | grep 8787
   ```
   Expected: `100.92.197.90:8787` — NOT `0.0.0.0:8787`
3. Check service health:
   ```bash
   curl -s http://100.92.197.90:8787/health
   ```
   Expected: successful health response
4. Check systemd status:
   ```bash
   systemctl is-active transcribe
   ```
   Expected: `active`
5. Verify no `0.0.0.0` bindings remain for managed services:
   ```bash
   ss -tlnp | grep 0.0.0.0
   ```
   Review output — no managed services should appear (ignore system services like sshd if applicable)
6. Verify Docker container is running:
   ```bash
   docker ps --format '{{.Names}} {{.Ports}}' | grep transcribe
   ```
   Expected: shows `100.92.197.90:8787->8787/tcp`

**Files**: None (verification only).

**Validation**:
- [ ] Port bound to `100.92.197.90:8787` confirmed
- [ ] Health endpoint responds
- [ ] systemd reports active
- [ ] No `0.0.0.0` bindings on managed services
- [ ] Docker shows correct port mapping

**Parallel?**: No — must be the last step in WP01.

## Risks & Mitigations

- **Rebind breaks connectivity**: If `curl http://100.92.197.90:8787/health` fails after rebind, check Docker network mode. The container may need `network_mode: host` or a specific Docker network. Revert compose file and restart if needed.
- **Docker Compose not available as plugin**: If `docker compose` (v2) is not available, try `docker-compose` (v1 standalone). Update the systemd unit accordingly.
- **systemd Type mismatch**: If `Type=oneshot` with `RemainAfterExit=yes` doesn't work well with Docker Compose, switch to `Type=simple` with foreground mode (`docker compose up` without `-d`).
- **Existing container managed differently**: If the container was started via `docker run` instead of `docker compose`, the stop command needs to match. Check `docker inspect` output first.

## Review Guidance

- Verify `ss -tlnp | grep 8787` shows only `100.92.197.90`, not `0.0.0.0`
- Verify the compose file in repo matches what's deployed on office2
- Verify the systemd unit correctly references the compose file path
- Verify no sudo commands were run by the agent — only presented to Kent
- Verify no image rebuild occurred (constraint C-002)

## Activity Log

- 2026-03-28T16:22:31Z – system – lane=planned – Prompt created.
- 2026-03-28T16:33:46Z – claude – shell_pid=68164 – lane=doing – Assigned agent via workflow command
