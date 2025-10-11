# AI Context Bootstrap - READ FIRST

*Mandatory reading for all AI systems before engaging with Kent Gale automation project*

## File Location Strategy - CRITICAL

### **For Reading Context (All AIs)**
- **Global Location**: Dropbox Automation root (for bootstrap and shared resources)
- **Project Location**: Dropbox kg-automation subdirectory (for project documentation)
- **Status**: Deployed files, updated after Git commits

### **For Making Changes (Mac/Windows only)**
- **Location**: Git repository paths (e.g., `~/Vaults-repos/kg-automation/`)
- **Purpose**: Source files for editing and version control
- **Workflow**: Edit → Commit → Push → Deploy to Dropbox

### **Key Rules**
- ✅ **READ** from Dropbox for context and reference
- ✅ **EDIT** in Git repository when changes needed
- ❌ **NEVER** edit files directly in Dropbox
- ✅ **ALWAYS** commit changes and deploy to sync platforms

## Current Session Context Requirements

### User Must Provide
- Platform: [Mac/Windows/iPad/iPhone]
- Working Context: [Personal development/Business operations/Client work]
- Immediate Goal: [What we are trying to accomplish]

### AI Must Confirm
- Access to required tools/extensions for current platform
- Understanding of current working directory and file paths
- Capability to handle requested tasks on current platform

## Canonical Paths by Platform

### **Mac Platform:**
```bash
# Canonical roots
DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox"
AUTOMATION_ROOT="$DROPBOX_ROOT/Automation"
PROJECT_ROOT="$AUTOMATION_ROOT/kg-automation"

# Global resources (cross-project)
QUEUE_ROOT="$AUTOMATION_ROOT/.queue"
STATE_ROOT="$AUTOMATION_ROOT/.state"
BOOTSTRAP="$AUTOMATION_ROOT/ai-agents/ai-context-bootstrap.md"

# Project-specific documentation
PROJECT_DOCS="$PROJECT_ROOT/docs"
PROJECT_AI="$PROJECT_ROOT/ai-agents"
PROJECT_SYSTEMS="$PROJECT_ROOT/systems"
PROJECT_RUNBOOKS="$PROJECT_ROOT/runbooks"
PROJECT_WORKFLOWS="$PROJECT_ROOT/workflows"
```

### **Windows Platform:**
```powershell
# Canonical roots
$DropboxRoot = "$env:USERPROFILE\Dropbox"
$AutomationRoot = "$DropboxRoot\Automation"  
$ProjectRoot = "$AutomationRoot\kg-automation"

# Global resources (cross-project)
$QueueRoot = "$AutomationRoot\.queue"
$StateRoot = "$AutomationRoot\.state"
$Bootstrap = "$AutomationRoot\ai-agents\ai-context-bootstrap.md"

# Project-specific documentation
$ProjectDocs = "$ProjectRoot\docs"
$ProjectAI = "$ProjectRoot\ai-agents"  
$ProjectSystems = "$ProjectRoot\systems"
$ProjectRunbooks = "$ProjectRoot\runbooks"
$ProjectWorkflows = "$ProjectRoot\workflows"
```

## Mandatory Context Documents

**Read from Dropbox deployment locations:**

### **Mac Paths:**
1. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/systems/integration-architecture.md` — complete systems overview
2. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/ai-agents/ai-collaboration-standards.md` — AI behavior standards
3. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/ai-agents/platform-capability-matrix.md` — AI capabilities by device
4. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/runbooks/session-continuity.md` — recovery procedures if context is lost
5. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/docs/execution-context-identification.md` — ECI (local-only machine identity on each device)
6. `~/Library/CloudStorage/Dropbox/Automation/kg-automation/docs/diagrams/eci-sequence.mmd` — sequence diagram for ECI + job intake flow

### **Windows Paths:**
1. `C:\Users\Kent\Dropbox\Automation\kg-automation\systems\integration-architecture.md`
2. `C:\Users\Kent\Dropbox\Automation\kg-automation\ai-agents\ai-collaboration-standards.md`
3. `C:\Users\Kent\Dropbox\Automation\kg-automation\ai-agents\platform-capability-matrix.md`
4. `C:\Users\Kent\Dropbox\Automation\kg-automation\runbooks\session-continuity.md`
5. `C:\Users\Kent\Dropbox\Automation\kg-automation\docs\execution-context-identification.md`
6. `C:\Users\Kent\Dropbox\Automation\kg-automation\docs\diagrams\eci-sequence.mmd`

## Project State
- Phase: Setup/Documentation
- Repository: https://github.com/kentonium3/kg-automation.git
- Status: Active development

---
*Read this document first in every new AI session*
