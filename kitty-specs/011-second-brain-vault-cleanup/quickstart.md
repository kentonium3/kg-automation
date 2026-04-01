# Quickstart: F011 Second Brain Vault Cleanup

## Prerequisites

Before implementation begins:

1. **Mac second-brain git repo** must be initialized and pushed to GitHub
2. **Kent** must set up git credentials for kgale on office2 (SSH key + .gitconfig)

## Manual Steps (Kent performs these)

### On Mac: Initialize second-brain git repo

```bash
cd ~/second-brain
git init
echo "notes/" > .gitignore
echo ".DS_Store" >> .gitignore
echo "**/.DS_Store" >> .gitignore
git add -A
git commit -m "Initial commit: second-brain non-vault content"
# Create repo on GitHub (kentonium3/second-brain), then:
git remote add origin git@github.com:kentonium3/second-brain.git
git push -u origin main
```

### On office2: Set up git for kgale

```bash
ssh office2-kgale
ssh-keygen -t ed25519 -C "kgale@office2"
cat ~/.ssh/id_ed25519.pub
# Add this key to GitHub (Settings → SSH keys, or as deploy key on the repo)
git config --global user.name "Kent Gale"
git config --global user.email "kent@example.com"  # Use actual email
```

## Verification Commands

### Check vault-snapshot is absent

```bash
ssh office2-claude "systemctl --user status vault-snapshot.timer 2>&1"
# Expected: "could not be found"
```

### Check obsidian-sync after deployment

```bash
ssh office2-claude "systemctl --user status obsidian-sync.service"
# Expected: active (running)
```

### Check bidirectional sync timer

```bash
ssh office2-claude "systemctl --user status second-brain-sync.timer"
# Expected: active (waiting), triggers every 15 minutes
```

### Check no stale path references on office2

```bash
ssh office2-claude "grep -r 'second-brain/vault' /data/services/openclaw/ /home/kgale/second-brain/ 2>/dev/null"
# Expected: no output
```

### End-to-end test

1. Create a test note on Mac in Obsidian (00-Inbox)
2. Wait 5 minutes
3. Verify it appears at `/home/kgale/second-brain/notes/00-Inbox/` on office2
4. Trigger manual inbox processing and verify success
