---
work_package_id: WP01
title: Prerequisites — Mac Repo and Office2 Git Credentials
lane: "doing"
dependencies: []
requirement_refs:
- FR-15
- FR-16
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 001469d86b01754a066625ccc3ed52697568c5f7
created_at: '2026-04-01T18:37:52.447799+00:00'
subtasks: [T001, T002, T003]
shell_pid: "17035"
agent: "claude-code"
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP01: Prerequisites — Mac Repo and Office2 Git Credentials

## Implementation command

```bash
spec-kitty implement WP01
```

## Objective

Initialize the second-brain git repository on Mac, create the GitHub remote,
push, and provide Kent with the exact commands to set up git credentials on
office2. This WP unblocks WP05 (bidirectional sync timer).

## Context

- **Mac second-brain path**: `~/second-brain/`
- **Mac vault path**: `~/second-brain/notes/` (already renamed, Obsidian Sync active)
- **Mac .git/ was removed** during earlier cleanup — needs reinitialization
- **GitHub org**: kentonium3
- **office2 kgale user**: has no .gitconfig, no SSH keys (confirmed by research)
- **claude user cannot**: write to kgale's home directory or run sudo

## Subtask guidance

### T001: Initialize git repo on Mac

**Purpose**: Create a fresh git repository in `~/second-brain/` with proper
`.gitignore` that excludes the vault.

**Steps**:
1. Create `.gitignore` in `~/second-brain/` with the following content:
   ```
   # Vault content — managed by Obsidian Sync, not git
   notes/

   # macOS
   .DS_Store
   **/.DS_Store
   ```
2. Run `git init` in `~/second-brain/`
3. Stage all non-ignored files (`git add -A`)
4. Create initial commit: `git commit -m "Initial commit: second-brain non-vault content"`

**Files affected**:
- `~/second-brain/.gitignore` (new)
- `~/second-brain/.git/` (new)

**Validation**:
- [ ] `git status` shows clean working tree
- [ ] `git log` shows one commit
- [ ] `notes/` directory is not tracked (verify with `git ls-files notes/` — should be empty)

### T002: Create GitHub repo and push

**Purpose**: Create the remote repository on GitHub and push the local repo.

**Steps**:
1. Create the repo on GitHub: `gh repo create kentonium3/second-brain --private --source=. --push`
   - If `gh` is not available or fails, provide manual steps:
     - Create repo at https://github.com/new (private)
     - `git remote add origin git@github.com:kentonium3/second-brain.git`
     - `git push -u origin main`
2. Verify push succeeded: `git log --oneline origin/main`

**Validation**:
- [ ] `git remote -v` shows origin pointing to kentonium3/second-brain
- [ ] `git log --oneline origin/main` matches local HEAD

### T003: Document manual git setup for office2

**Purpose**: Kent must run these commands himself as kgale on office2. The
agent cannot perform these steps.

**Present these exact commands to Kent**:

```bash
# SSH to office2 as kgale (not claude!)
ssh office2-kgale

# Generate SSH key pair
ssh-keygen -t ed25519 -C "kgale@office2" -f ~/.ssh/id_ed25519
# Press Enter for no passphrase (or set one if preferred)

# Display public key to add to GitHub
cat ~/.ssh/id_ed25519.pub
# Copy this output → go to https://github.com/settings/keys → "New SSH key"
# Title: "office2-kgale", paste the key

# Configure git identity
git config --global user.name "Kent Gale"
git config --global user.email "<kent's email>"

# Test GitHub access
ssh -T git@github.com
# Expected: "Hi kentonium3! You've successfully authenticated..."
```

**Important**: This is a **mandatory stop point**. The agent must present
these commands and wait for Kent to confirm completion before WP05 can
proceed. Do not attempt to run these commands via SSH as the claude user.

**Validation**:
- [ ] Kent confirms SSH key is generated and added to GitHub
- [ ] Kent confirms `ssh -T git@github.com` succeeds from office2

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- Git repo initialized on Mac with `notes/` gitignored
- GitHub remote created at kentonium3/second-brain (private)
- Initial commit pushed to origin
- Kent has been presented with office2 git setup commands
- Kent confirms office2 git credentials are working

## Risks

- GitHub repo name conflict: If `kentonium3/second-brain` already exists,
  use the existing repo or choose a different name
- Kent's email for .gitconfig: Agent should ask Kent for the correct email
  rather than guessing

## Activity Log

- 2026-04-01T18:37:52Z – claude-code – shell_pid=17035 – lane=doing – Assigned agent via workflow command
