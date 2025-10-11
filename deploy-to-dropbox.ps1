# Deploy committed files from git repository to Dropbox
# Deploy to project subdirectory, preserve global queue structure
# PowerShell version for Windows

# Source repository
$RepoDir = "$env:USERPROFILE\Vaults-repos\kg-automation"

# Canonical roots (Windows)
$DropboxRoot = "$env:USERPROFILE\Dropbox"
$AutomationRoot = "$DropboxRoot\Automation"
# Global (unchanged)
$QueueRoot = if ($env:QUEUE_ROOT) { $env:QUEUE_ROOT } else { "$AutomationRoot\.queue" }
$StateRoot = if ($env:STATE_ROOT) { $env:STATE_ROOT } else { "$AutomationRoot\.state" }
# Project-scoped target
$ProjectRoot = "$AutomationRoot\kg-automation"

Write-Host "?? Deploying kg-automation to Dropbox..." -ForegroundColor Green
Write-Host "?? Target: $ProjectRoot" -ForegroundColor Cyan

# Ensure project directory exists
if (-not (Test-Path $ProjectRoot)) {
    New-Item -ItemType Directory -Path $ProjectRoot -Force | Out-Null
}

# Copy bootstrap file to BOTH locations (AI session compatibility)
Write-Host "?? Syncing Bootstrap to Both Locations..." -ForegroundColor Yellow
if (-not (Test-Path "$AutomationRoot\ai-agents")) {
    New-Item -ItemType Directory -Path "$AutomationRoot\ai-agents" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\ai-agents\ai-context-bootstrap.md" -Destination "$AutomationRoot\ai-agents\ai-context-bootstrap.md" -Force

if (Test-Path "$ProjectRoot\ai-agents") {
    Remove-Item -Path "$ProjectRoot\ai-agents\*" -Recurse -Force
}
if (-not (Test-Path "$ProjectRoot\ai-agents")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\ai-agents" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\ai-agents\*" -Destination "$ProjectRoot\ai-agents\" -Recurse -Force

# Copy documentation
Write-Host "?? Syncing Documentation..." -ForegroundColor Yellow
if (Test-Path "$ProjectRoot\docs") {
    Remove-Item -Path "$ProjectRoot\docs\*" -Recurse -Force
}
if (-not (Test-Path "$ProjectRoot\docs")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\docs" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\docs\*" -Destination "$ProjectRoot\docs\" -Recurse -Force

# Copy scripts (when they exist)
if (Test-Path "$RepoDir\scripts") {
    Write-Host "?? Syncing Scripts..." -ForegroundColor Yellow
    if (Test-Path "$ProjectRoot\scripts") {
        Remove-Item -Path "$ProjectRoot\scripts\*" -Recurse -Force
    }
    if (-not (Test-Path "$ProjectRoot\scripts")) {
        New-Item -ItemType Directory -Path "$ProjectRoot\scripts" -Force | Out-Null
    }
    Copy-Item -Path "$RepoDir\scripts\*" -Destination "$ProjectRoot\scripts\" -Recurse -Force
}

# Copy runbooks
Write-Host "?? Syncing Runbooks..." -ForegroundColor Yellow
if (Test-Path "$ProjectRoot\runbooks") {
    Remove-Item -Path "$ProjectRoot\runbooks\*" -Recurse -Force
}
if (-not (Test-Path "$ProjectRoot\runbooks")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\runbooks" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\runbooks\*" -Destination "$ProjectRoot\runbooks\" -Recurse -Force

# Copy workflows
Write-Host "? Syncing Workflows..." -ForegroundColor Yellow
if (Test-Path "$ProjectRoot\workflows") {
    Remove-Item -Path "$ProjectRoot\workflows\*" -Recurse -Force
}
if (-not (Test-Path "$ProjectRoot\workflows")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\workflows" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\workflows\*" -Destination "$ProjectRoot\workflows\" -Recurse -Force

# Copy systems
Write-Host "?? Syncing Systems..." -ForegroundColor Yellow
if (Test-Path "$ProjectRoot\systems") {
    Remove-Item -Path "$ProjectRoot\systems\*" -Recurse -Force
}
if (-not (Test-Path "$ProjectRoot\systems")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\systems" -Force | Out-Null
}
Copy-Item -Path "$RepoDir\systems\*" -Destination "$ProjectRoot\systems\" -Recurse -Force

# Copy root files (README, etc.)
Write-Host "?? Syncing Root Files..." -ForegroundColor Yellow
Copy-Item -Path "$RepoDir\README.md" -Destination "$ProjectRoot\README.md" -Force
if (Test-Path "$RepoDir\.gitignore") {
    Copy-Item -Path "$RepoDir\.gitignore" -Destination "$ProjectRoot\.gitignore" -Force
}

Write-Host "? Deployment complete!" -ForegroundColor Green
Write-Host "?? Project files: $ProjectRoot" -ForegroundColor Cyan
Write-Host "?? Global queue: $QueueRoot" -ForegroundColor Cyan
Write-Host "?? Global state: $StateRoot" -ForegroundColor Cyan
