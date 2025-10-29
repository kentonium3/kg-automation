---
id: eci-path-resolution
title: ECI Path Resolution
doc_type: handbook
level: reference
status: approved
owners:
  - "@kent@intentional.biz"
last_updated: "2025-10-15"
revision: v1.0
audience: agents_and_humans
---

# ECI Path Resolution

**Goal:** Make path handling deterministic for humans and agents across Windows, macOS, and containers. Read from Dropbox for context; edit in Git; use GitHub as system of record.

## Golden Rules
- **Read context** (reference-only) from Dropbox deployment.
- **Edit & generate** only in the Git repo working copy (feature branches).
- **Never** hand-edit generated artifacts; use their generators.
- **In containers/agents without host FS**, operate **GitHub-only** (no host paths).

## Canonical Roots

### Windows
```
$DropboxRoot = "C:\\Users\\Kent\\Dropbox"
$AutomationRoot = "$DropboxRoot\\Automation"
$ProjectRoot = "$AutomationRoot\\kg-automation"
```
Examples:
```
$ProjectDocs        = "$ProjectRoot\\docs"
$ProjectAI          = "$ProjectRoot\\ai-agents"
$ProjectSystems     = "$ProjectRoot\\systems"
$ProjectRunbooks    = "$ProjectRoot\\runbooks"
$ProjectWorkflows   = "$ProjectRoot\\workflows"
```

### macOS
```
DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox"
AUTOMATION_ROOT="$DROPBOX_ROOT/Automation"
PROJECT_ROOT="$AUTOMATION_ROOT/kg-automation"
```

### Containers / CI / Codespaces
- Treat **Git checkout** as the only filesystem.
- Do not attempt to access host-specific paths.
- Use handoffs and PRs to move data.

## Path Strategy by Task
- **Bootstrap reading:** read required context from Dropbox (if running on a host with Dropbox installed) using the canonical paths above.
- **Edits & generation:** work in your Git working copy (e.g., `C:/Users/Kent/Vaults-repos/kg-automation` or the dev container checkout).
- **CI/Container:** operate only on repo paths; assume no Dropbox.

## Common Failure Modes & Fixes
- **Dropbox appears under `C:\\Users\\Kent\\Dropbox` in Explorer but is virtualized** → rely on the canonical env-var paths above; avoid hardcoding.
- **Agent tries to `cd` into Windows path inside container** → switch to **GitHub-only mode**; fetch files via PR/files instead of host FS.
- **Link errors in Docs CI** → add temporary stub files or update links; replace stubs in follow-up PRs.

## See Also
- Agent Handbook (Pre-PR Checklist): `./agent-handbook.md`
- Runner Policies: `./runner-policies.md`