# kg_automation Development & Deployment Workflow

*Complete setup and workflow documentation for the Kent Gale automation project*

**Created:** September 2025  
**Status:** Active, Working Configuration  
**Platforms:** Mac (completed), Windows (ready for setup)

## Overview

This document captures the complete development and deployment workflow established for the kg_automation project, including repository setup, VS Code automation, and cross-machine file synchronization.

## Architecture Summary

### **Three-Layer System:**
1. **Git Repository** (`~/Documents/Code/kg_automation/`) - Version control and development
2. **VS Code Automation** - Automated deployment workflows  
3. **Dropbox Sync** (`~/Dropbox/Automation/`) - Cross-machine file access

### **Core Principle:**
- **Develop** in git repository with full version control
- **Deploy** committed changes to Dropbox for cross-machine access
- **Never** put git repositories in Dropbox (avoids sync conflicts)

## Directory Structure

### Mac Setup (Completed)
```
~/Vaults-repos/kg_automation/          ← Git repository (work here)
├── .git/                               ← Git version control
├── .vscode/                            ← VS Code automation config
│   ├── tasks.json                      ← Deployment tasks
│   ├── keybindings.json               ← Keyboard shortcuts
│   ├── settings.json                  ← Workspace settings
│   └── launch.json                    ← Debug config
├── deploy-to-dropbox.sh               ← Deployment script
├── docs/                              ← Project docs
├── ai-agents/                         ← AI configurations
├── systems/                           ← System integration docs
├── runbooks/                          ← Operational procedures
└── workflows/                         ← Process documentation

~/Library/CloudStorage/Dropbox/Automation/  ← Shared access (deployed files)
├── docs/                              ← Current docs (from git)
├── ai-agents/                         ← Current AI configs (from git)
├── systems/                           ← Current system docs (from git)
├── runbooks/                          ← Current runbooks (from git)
├── workflows/                         ← Current workflows (from git)
├── Scripts/                           ← Live automation scripts
├── .queue/                            ← AI job coordination
└── .state/                            ← Runtime state files
```

### Windows Setup (To Be Configured)
```
C:\Users\Kent\Vaults-repos\kg_automation\     ← Git repository
C:\Users\Kent\Dropbox\Automation\               ← Shared access (deployed files)
```

## VS Code Automation Features

### **Keyboard Shortcuts:**
- **`Cmd+Shift+D`** (Mac) / **`Ctrl+Shift+D`** (Windows) - Quick Deploy (sync to Dropbox, skip git)
- **`Cmd+Shift+P`** (Mac) / **`Ctrl+Shift+P`** (Windows) - Complete Workflow (commit → push → deploy)

### **Available Tasks** (Command Palette → "Tasks: Run Task"):
1. **"Deploy to Dropbox"** - Sync current files to Dropbox
2. **"Complete Deployment Workflow"** - Full git commit, push, and deploy sequence
3. **"Quick Deploy (Skip Git)"** - Fast Dropbox sync without git operations
4. **"Git: Commit with Message"** - Commit with custom message prompt
5. **"Git: Push to Origin"** - Push changes to GitHub

### **Task Dependencies:**
- Complete Workflow runs: Git Add → Git Commit → Git Push → Deploy to Dropbox
- Each step shows progress in VS Code integrated terminal
- Commit messages are prompted interactively

## Development Workflows

### **Quick Changes (No Git Tracking):**
1. Edit files in VS Code
2. Press `Cmd+Shift+D` to deploy immediately to Dropbox
3. Files available on all machines within seconds

### **Committed Changes (Full Version Control):**
1. Edit files in VS Code
2. Press `Cmd+Shift+P` to run complete workflow
3. Enter commit message when prompted
4. Automatic sequence: commit → push to GitHub → deploy to Dropbox

### **Manual Git Operations:**
```bash
cd ~/Vaults-repos/kg_automation
git add .
git commit -m "Your commit message"
git push origin main
./deploy-to-dropbox.sh
```

## Deployment Script Details

### **File: `deploy-to-dropbox.sh`**
- Uses `rsync` for efficient file synchronization
- Preserves file permissions and timestamps
- Deletes files in Dropbox that no longer exist in git repo
- Syncs all major project directories: docs, ai-agents, systems, runbooks, workflows
- Provides verbose output with progress indicators

### **Deployment Targets:**
- All markdown documentation files
- AI agent configurations
- System integration documentation
- Runbooks and procedures
- Workflow documentation
- Future: Scripts directory for automation tools

## Cross-Platform Setup Instructions

### **Mac (Completed):**
1. ✅ Repository cloned to `~/Vaults-repos/kg_automation/`
2. ✅ VS Code configured with automation tasks
3. ✅ Deployment script created and tested
4. ✅ Dropbox sync verified working

### **Windows (Next Steps):**
1. **Clone Repository:**
   ```bash
   cd C:\Users\Kent\Vaults-repos
   git clone https://github.com/kentonium3/kg_automation.git
   ```

2. **Test Deployment Script:**
   ```bash
   cd C:\Users\Kent\Vaults-repos\kg_automation
   ./deploy-to-dropbox.sh
   ```

3. **Configure VS Code:**
   - VS Code settings should sync automatically
   - Keyboard shortcuts will use Ctrl instead of Cmd
   - All tasks will work identically

4. **Verify Dropbox Paths:**
   - Ensure Dropbox path in script matches Windows installation
   - Update script if necessary for Windows Dropbox location

## Git Repository Information

### **GitHub Repository:** https://github.com/kentonium3/kg_automation.git
### **Branch:** `main`
### **Recent Commits:**
- Documentation patch: ECI (Execution Context Identification) implementation
- VS Code automation workflows configuration
- Deployment script creation and testing

### **Related Repositories:**
- `bug-driven-development` - Learning project
- `google-apps-script-libraries` - Reusable automation libraries  
- `multi-habit-tracker` - Habit tracking web app

## File Organization Principles

### **What Goes Where:**

**Git Repository (Version Control):**
- Source documentation files
- AI agent configurations
- System architecture documentation
- Development scripts and tools
- VS Code workspace configuration

**Dropbox (Shared Access):**
- Current/deployed versions of documentation
- Live automation scripts for execution
- AI job queue files (`.queue/`)
- Runtime state files (`.state/`)
- Cross-machine configuration files

### **What NOT to Put in Dropbox:**
- `.git` directories (causes sync conflicts)
- Development work-in-progress files
- Local machine configuration files
- Personal access tokens or secrets

## Troubleshooting

### **Common Issues:**

1. **Deployment Script Permission Error:**
   ```bash
   chmod +x deploy-to-dropbox.sh
   ```

2. **Git Push Fails:**
   - Check network connection
   - Verify GitHub authentication
   - Run `git status` to check repository state

3. **Dropbox Sync Not Working:**
   - Verify Dropbox is running and synced
   - Check path in deployment script matches local Dropbox installation
   - Confirm Dropbox has sufficient storage space

4. **VS Code Tasks Not Appearing:**
   - Reload VS Code window: `Cmd+Shift+P` → "Developer: Reload Window"
   - Check `.vscode/tasks.json` file exists and is valid JSON

## Session Continuity

### **For New AI Sessions:**
1. **Read this document first** for complete context
2. **Platform confirmation:** Specify whether on Mac or Windows
3. **Repository location:** Use appropriate paths for platform
4. **Current capabilities:** Reference `ai-agents/platform-capability-matrix.md`

### **Key Context Files:**
- `ai-agents/ai-context-bootstrap.md` - Always read first
- `ai-agents/platform-capability-matrix.md` - AI capabilities by device
- `systems/integration-architecture.md` - Complete systems overview
- This document - Complete workflow reference

## Next Development Priorities

### **Immediate (Current Session):**
1. ✅ Apply documentation patch (ECI implementation)
2. ✅ Set up Mac development environment
3. ✅ Configure VS Code automation
4. ✅ Test complete workflow

### **Next Session:**
1. **Windows Setup:** Configure identical workflow on Windows machine
2. **Cross-Platform Testing:** Verify workflow works between machines
3. **Script Development:** Begin building automation tools in Scripts/ directory
4. **AI Agent Implementation:** Start building the job queue and worker systems

### **Future Development:**
1. **ECI Implementation:** Create machine ID beacon files
2. **Job Queue System:** Implement AI job coordination
3. **Automation Scripts:** Build productivity and business automation tools
4. **Integration Testing:** Verify cross-AI, cross-platform coordination

## Success Metrics

The workflow is successful when:
- ✅ Changes committed on one machine appear on others within minutes
- ✅ VS Code keyboard shortcuts work reliably
- ✅ No manual file copying required between machines
- ✅ Full version history maintained in GitHub
- ✅ No git repositories in Dropbox
- ✅ Clean separation between development and deployment

---

**This workflow is now operational and ready for continued development.**

*Last Updated: September 2025 - Mac setup complete, Windows setup pending*
