# Quickstart: Obsidian Sync on office2

**Feature**: F010 (010-obsidian-sync-office2)
**Date**: 2026-04-01

This guide covers the exact commands Kent runs on office2 as the `kgale` user
to set up Obsidian Sync. All artifacts (service file, snapshot script, timer)
are created by implementation WPs and committed to the repo before this guide
is executed.

## Prerequisites

- [ ] `ob` CLI installed at `/usr/bin/ob` (already present, v0.0.8)
- [ ] Obsidian Sync subscription active (already in use on Mac and iPhone)
- [ ] Implementation WPs merged (service file, snapshot script, runbook ready)

## Step 1: Login to Obsidian Account

SSH to office2 as kgale:

```bash
ssh office2-kgale
ob login --email <your-obsidian-email>
```

Enter password and MFA code when prompted. Verify:

```bash
ob sync-list-remote
```

Expected: shows your vault(s) by name and ID.

## Step 2: Setup Sync

```bash
ob sync-setup \
  --vault "<vault-name-from-step-1>" \
  --path /home/kgale/second-brain/vault \
  --device-name office2 \
  --password "<your-e2ee-password>"
```

Verify:

```bash
ob sync-list-local
ob sync-status --path /home/kgale/second-brain/vault
```

## Step 3: Configure Sync Behavior

```bash
ob sync-config \
  --path /home/kgale/second-brain/vault \
  --mode bidirectional \
  --conflict-strategy merge \
  --excluded-folders "02-Growth/_private" \
  --device-name office2
```

## Step 4: Test One-Shot Sync

```bash
ob sync --path /home/kgale/second-brain/vault
```

Verify backfill — inbox notes from March 22 onward should appear:

```bash
ls -lt /home/kgale/second-brain/vault/00-Inbox/
```

## Step 5: Update .gitignore

Append the required exclusions to the second-brain repo's `.gitignore`:

```bash
cat ~/repos/kg-automation/scripts/office2/gitignore-additions.txt >> /home/kgale/second-brain/.gitignore
```

Verify:

```bash
cat /home/kgale/second-brain/.gitignore
```

## Step 6: Install and Enable Systemd Service

```bash
mkdir -p ~/.config/systemd/user

# Copy service file from repo
cp ~/repos/kg-automation/scripts/office2/obsidian-sync.service ~/.config/systemd/user/

# Enable linger (requires sudo — run from kgale account)
sudo loginctl enable-linger kgale

# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now obsidian-sync
```

Verify:

```bash
systemctl --user status obsidian-sync
```

Expected: `active (running)`.

## Step 7: Install Git Snapshot Timer

```bash
# Copy snapshot script and timer
cp ~/repos/kg-automation/scripts/office2/vault-snapshot.sh ~/helper-scripts/
cp ~/repos/kg-automation/scripts/office2/vault-snapshot.timer ~/.config/systemd/user/
cp ~/repos/kg-automation/scripts/office2/vault-snapshot.service ~/.config/systemd/user/

chmod +x ~/helper-scripts/vault-snapshot.sh

# Enable timer
systemctl --user daemon-reload
systemctl --user enable --now vault-snapshot.timer
```

Verify:

```bash
systemctl --user list-timers | grep vault
```

## Step 8: Run Validation Script

Copy and run the automated validation:

```bash
cp ~/repos/kg-automation/scripts/office2/validate-obsidian-sync.sh ~/helper-scripts/
chmod +x ~/helper-scripts/validate-obsidian-sync.sh
~/helper-scripts/validate-obsidian-sync.sh
```

Expected: all checks PASS. If any FAIL, see troubleshooting below.

## Step 9: Verification Tests

### Sync latency (Mac → office2)

Create a test note on Mac in the vault. Wait 5 minutes. Check office2:

```bash
ls -lt /home/kgale/second-brain/vault/00-Inbox/ | head -5
```

### Sync latency (office2 → Mac)

```bash
echo "# Test note from office2" > /home/kgale/second-brain/vault/00-Inbox/test-sync-office2.md
```

Wait 5 minutes. Verify it appears on Mac. Then delete the test note from
both devices.

### Reboot persistence

```bash
sudo reboot
# After reboot, SSH back in:
systemctl --user status obsidian-sync
```

### Manual snapshot test

```bash
~/helper-scripts/vault-snapshot.sh
```

Verify clean commit and push.

## Step 10: Verify Backfill

Compare inbox file counts between office2 and Mac:

```bash
# On office2 (as kgale):
ls /home/kgale/second-brain/vault/00-Inbox/ | wc -l
```

```bash
# On Mac:
ls ~/second-brain/vault/Notes/00-Inbox/ | wc -l
```

Counts should match (or be within sync latency — a few files difference is OK).

## Step 11: Trigger Backfill Processing

After confirming sync is current, trigger a manual inbox processing run
(run as claude user):

```bash
ssh office2-claude
openclaw agent --agent felix-admin-capture \
  --message "Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, route valid goal declarations, and write the processing log." \
  --json --timeout 300
```

Verify processing log:

```bash
ls -t /home/kgale/second-brain/agents/logs/inbox-processing-*.md | head -1
```

## Related Documentation

- Operations runbook: `docs/handbooks/obsidian-sync-ops.md`
- Architecture: `docs/design/architecture/service-inventory.md`
- Inbox processor: `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
