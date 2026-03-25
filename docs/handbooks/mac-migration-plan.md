# Mac Development Environment Migration Plan

*Systematic migration from Windows (Office3) to MacBook Pro as primary development platform*

**Created**: 2025-11-30  
**Status**: In Progress  
**Primary Goal**: Achieve functional parity with Windows development environment while leveraging Mac-native capabilities

## Migration Context

### Problem Statement
- Experiencing path handling issues between Linux/Windows styles in tools
- Encoding problems affecting automation workflows
- Tooling incompatibilities on Windows platform
- Need for more stable development environment

### Current Environment
- **Source Platform**: Windows PC (Office3) - Windows 11
- **Target Platform**: MacBook Pro - macOS
- **Shared Tools**: VS Code, Git, Claude Code, Cursor, spec-kitty, Obsidian
- **Repository Location**: `/Users/kentgale/repos/kg-automation/`

## Phase 1: Assessment & Preparation

### 1.1 Current State Audit
- [ ] Mount Office3 via network share to access Windows configurations
- [ ] Document current VS Code extensions from Office3
- [ ] Export VS Code settings.json from Windows
- [ ] List active Git repositories and their remotes
- [ ] Document Obsidian vault configurations
- [ ] Check Claude Code and Cursor configurations
- [ ] Document spec-kitty usage patterns and configurations

#### Windows Configuration Locations to Check
```powershell
# VS Code
%APPDATA%\Code\User\settings.json
%USERPROFILE%\.vscode\extensions

# Git
%USERPROFILE%\.gitconfig

# Obsidian
%APPDATA%\obsidian\

# Project repositories
C:\Users\Kent\repos\
```

### 1.2 Mac Environment Check
- [ ] Verify Git is installed and configured
- [ ] Check VS Code installation status
- [ ] Confirm Dropbox sync is working properly
- [ ] Verify access to all repository locations
- [ ] Check Homebrew installation
- [ ] Verify Xcode Command Line Tools

## Phase 2: Core Development Tools Setup

### 2.1 VS Code Configuration
- [ ] Install VS Code (if not already installed)
  ```bash
  # Via Homebrew
  brew install --cask visual-studio-code
  ```
- [ ] Enable Settings Sync or manually import settings from Windows
- [ ] Install critical extensions:
  - [ ] Git integration extensions
  - [ ] Markdown extensions (Markdown All in One, Markdown Preview Enhanced)
  - [ ] Google Apps Script extensions
  - [ ] Project-specific extensions from Windows
- [ ] Configure workspace at `/Users/kentgale/repos/`
- [ ] Set up keyboard shortcuts matching Windows where possible
- [ ] Configure integrated terminal to use zsh

### 2.2 Git Configuration
- [ ] Configure global Git settings:
  ```bash
  git config --global user.name "Kent Gale"
  git config --global user.email "kentgale@gmail.com"
  git config --global core.autocrlf input
  git config --global core.editor "code --wait"
  ```
- [ ] Clone missing repositories if any
- [ ] Set up SSH keys for GitHub if not already done:
  ```bash
  ssh-keygen -t ed25519 -C "kentgale@gmail.com"
  eval "$(ssh-agent -s)"
  ssh-add ~/.ssh/id_ed25519
  # Add public key to GitHub
  ```
- [ ] Verify all repositories are up to date
- [ ] Configure Git credential manager

## Phase 3: Specialized Tools Migration

### 3.1 Claude Code Setup
- [ ] Install Claude Code on Mac
  ```bash
  # Installation method TBD based on availability
  ```
- [ ] Configure MCP servers (filesystem, etc.)
- [ ] Test connectivity with Claude extensions
- [ ] Document Mac-specific configurations
- [ ] Set up environment variables if needed

### 3.2 Cursor Installation
- [ ] Download and install Cursor from https://cursor.sh
- [ ] Import settings from Windows if possible
- [ ] Configure AI integrations
- [ ] Test with existing projects
- [ ] Document keyboard shortcuts differences

### 3.3 Spec-Kitty Setup
- [ ] Research Mac compatibility for spec-kitty
- [ ] Install if available or find Mac alternative
- [ ] Configure for workflow needs
- [ ] Document usage patterns
- [ ] Create compatibility layer if needed

## Phase 4: Obsidian Configuration

### 4.1 Vault Setup
- [ ] Install Obsidian on Mac
  ```bash
  brew install --cask obsidian
  ```
- [ ] Configure vault locations in each repo's docs directory:
  - [ ] kg-automation: `/Users/kentgale/repos/kg-automation/docs`
  - [ ] intentional: `/Users/kentgale/repos/intentional/docs`
  - [ ] Other project vaults as needed
- [ ] Install required plugins matching Windows setup:
  - [ ] Better Markdown Links (if used)
  - [ ] Git plugin for version control
  - [ ] Other productivity plugins
- [ ] Import settings from Windows Obsidian
- [ ] Test sync with Dropbox for cross-platform access
- [ ] Configure hotkeys for Mac (Cmd instead of Ctrl)

## Phase 5: Automation Scripts Migration

### 5.1 Platform-Specific Scripts
- [ ] Convert PowerShell scripts to bash/zsh equivalents:
  - [ ] Deployment scripts (`deploy-to-dropbox.ps1` → `deploy-to-dropbox.sh`)
  - [ ] Repository snapshot scripts
  - [ ] ECI worker scripts
- [ ] Update file paths from Windows to Mac format
- [ ] Test all automation workflows
- [ ] Create script templates for future automation

#### Script Conversion Examples
```bash
# Windows PowerShell
$DropboxRoot = "$env:USERPROFILE\Dropbox"

# Mac Bash/Zsh
DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox"
```

### 5.2 Cross-Platform Compatibility
- [ ] Create platform detection in scripts:
  ```bash
  if [[ "$OSTYPE" == "darwin"* ]]; then
      # Mac specific
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
      # Windows specific
  fi
  ```
- [ ] Maintain both PS1 and SH versions where needed
- [ ] Update documentation with Mac-specific commands
- [ ] Test cross-platform job queue processing

## Phase 6: VS Code Tasks & Shortcuts

### 6.1 Tasks Configuration
- [ ] Review `.vscode/tasks.json` in each project
- [ ] Update paths from Windows to Mac format
- [ ] Configure keyboard shortcuts (Cmd instead of Ctrl)
- [ ] Test deployment tasks to Dropbox
- [ ] Create Mac-specific task variants if needed

### 6.2 Keyboard Shortcuts Migration
- [ ] Document frequently used Windows shortcuts
- [ ] Map to Mac equivalents
- [ ] Update keybindings.json as needed
- [ ] Create cheat sheet for transition period

## Phase 7: Testing & Validation

### 7.1 Workflow Testing
- [ ] Test Git workflow: clone, commit, push, pull
- [ ] Test VS Code: editing, debugging, extensions
- [ ] Test automation: ECI workers, job queue
- [ ] Test AI tools: Claude Code, Cursor functionality
- [ ] Test Obsidian: vault access, plugin functionality
- [ ] Verify Dropbox deployment pipeline

### 7.2 Cross-Platform Verification
- [ ] Verify files created on Mac are accessible on Windows
- [ ] Test encoding compatibility (UTF-8)
- [ ] Verify line endings (LF vs CRLF)
- [ ] Test shared Dropbox queue operations
- [ ] Confirm Git commits work from both platforms

## Phase 8: Documentation & Cleanup

### 8.1 Update Documentation
- [ ] Create Mac development setup guide
- [ ] Document tool configurations
- [ ] Update platform-capability-matrix.md
- [ ] Add Mac-specific runbooks
- [ ] Document troubleshooting solutions

### 8.2 Optimize Workflow
- [ ] Remove Windows-specific workarounds
- [ ] Leverage Mac-native features:
  - [ ] Terminal/iTerm2 configurations
  - [ ] Homebrew package management
  - [ ] macOS automation (Shortcuts, Automator)
- [ ] Set up Mac-specific automations
- [ ] Configure development environment optimizations

## Issues Encountered & Resolutions

### Issue Log
*Document issues as they arise during migration*

#### Example Format:
```markdown
**Issue**: [Brief description]
**Date**: YYYY-MM-DD
**Symptoms**: What went wrong
**Root Cause**: Why it happened
**Resolution**: How it was fixed
**Prevention**: How to avoid in future
```

### Known Compatibility Issues
- Path separators: Windows `\` vs Mac `/`
- Line endings: CRLF vs LF
- Case sensitivity: macOS is case-insensitive by default
- Binary execution: .exe vs native binaries
- Environment variables: Different syntax and locations

## Tools & Resources

### Mac Development Tools
- **Homebrew**: Package manager for macOS
- **iTerm2**: Enhanced terminal emulator
- **Rectangle**: Window management
- **Alfred**: Productivity launcher
- **BetterTouchTool**: Automation and customization

### Documentation Resources
- Mac keyboard shortcuts: https://support.apple.com/en-us/HT201236
- Homebrew: https://brew.sh
- VS Code Mac guide: https://code.visualstudio.com/docs/setup/mac
- Git for Mac: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git

## Success Criteria

### Minimum Viable Migration
- [ ] Can edit and commit code in VS Code
- [ ] Git operations work correctly
- [ ] Can deploy to Dropbox
- [ ] Basic automation scripts functional
- [ ] Can access all project repositories

### Full Migration Success
- [ ] All Windows workflows replicated or improved
- [ ] Cross-platform compatibility maintained
- [ ] Automation enhanced with Mac capabilities
- [ ] Documentation complete and accurate
- [ ] Team handoff procedures updated

## Next Steps

1. **Immediate**: Mount Office3 network share for configuration access
2. **Priority 1**: Set up VS Code and Git (core development tools)
3. **Priority 2**: Migrate automation scripts and workflows
4. **Priority 3**: Optimize for Mac-native capabilities

## Notes & Observations

*Space for ongoing observations during migration*

---

**Migration Start Date**: 2025-11-30  
**Target Completion**: TBD based on complexity discovered  
**Last Updated**: 2025-11-30

*This is a living document. Update as migration progresses and issues are resolved.*
