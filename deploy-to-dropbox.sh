#!/bin/bash
# Deploy committed files from git repository to Dropbox
# Deploy to project subdirectory, preserve global queue structure

# Source repository
REPO_DIR="$HOME/Vaults-repos/kg-automation"

# Canonical roots (macOS)
DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox"
AUTOMATION_ROOT="$DROPBOX_ROOT/Automation"
# Global (unchanged)
QUEUE_ROOT="${QUEUE_ROOT:-$AUTOMATION_ROOT/.queue}"
STATE_ROOT="${STATE_ROOT:-$AUTOMATION_ROOT/.state}"
# Project-scoped target
PROJECT_ROOT="$AUTOMATION_ROOT/kg-automation"

echo "🚀 Deploying kg-automation to Dropbox..."
echo "📁 Target: $PROJECT_ROOT"

# Ensure project directory exists
mkdir -p "$PROJECT_ROOT"

# Copy bootstrap file to BOTH locations (AI session compatibility)
echo "🎯 Syncing Bootstrap to Both Locations..."
mkdir -p "$AUTOMATION_ROOT/ai-agents"
cp "$REPO_DIR/ai-agents/ai-context-bootstrap.md" "$AUTOMATION_ROOT/ai-agents/ai-context-bootstrap.md"
mkdir -p "$PROJECT_ROOT/ai-agents"
rsync -av --delete "$REPO_DIR/ai-agents/" "$PROJECT_ROOT/ai-agents/"

# Copy documentation
echo "📚 Syncing Documentation..."
mkdir -p "$PROJECT_ROOT/docs"
rsync -av --delete "$REPO_DIR/docs/" "$PROJECT_ROOT/docs/"

# Copy scripts (when they exist)
if [ -d "$REPO_DIR/scripts" ]; then
    echo "📜 Syncing Scripts..."
    mkdir -p "$PROJECT_ROOT/scripts"
    rsync -av --delete "$REPO_DIR/scripts/" "$PROJECT_ROOT/scripts/"
fi

# Copy runbooks  
echo "📖 Syncing Runbooks..."
mkdir -p "$PROJECT_ROOT/runbooks"
rsync -av --delete "$REPO_DIR/runbooks/" "$PROJECT_ROOT/runbooks/"

# Copy workflows
echo "⚡ Syncing Workflows..."
mkdir -p "$PROJECT_ROOT/workflows"
rsync -av --delete "$REPO_DIR/workflows/" "$PROJECT_ROOT/workflows/"

# Copy systems
echo "🔧 Syncing Systems..."
mkdir -p "$PROJECT_ROOT/systems"
rsync -av --delete "$REPO_DIR/systems/" "$PROJECT_ROOT/systems/"

# Copy root files (README, etc.)
echo "📄 Syncing Root Files..."
cp "$REPO_DIR/README.md" "$PROJECT_ROOT/README.md"
if [ -f "$REPO_DIR/.gitignore" ]; then
    cp "$REPO_DIR/.gitignore" "$PROJECT_ROOT/.gitignore"
fi

echo "✅ Deployment complete!"
echo "📁 Project files: $PROJECT_ROOT"
echo "🔄 Global queue: $QUEUE_ROOT"
echo "💾 Global state: $STATE_ROOT"
