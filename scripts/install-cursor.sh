#!/bin/bash

# Install Cursor IDE on Mac
# Created: 2025-11-30

echo "=== Installing Cursor IDE ==="
echo ""

# Check if Cursor is already installed
if [ -d "/Applications/Cursor.app" ]; then
    echo "✓ Cursor is already installed"
    echo "  Version: $(defaults read /Applications/Cursor.app/Contents/Info.plist CFBundleShortVersionString 2>/dev/null || echo 'unknown')"
    echo ""
    echo "To update Cursor, run: brew upgrade --cask cursor"
else
    echo "Installing Cursor via Homebrew Cask..."
    brew install --cask cursor
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Cursor installed successfully!"
        echo "Location: /Applications/Cursor.app"
    else
        echo ""
        echo "⚠️  Installation failed. Trying alternative method..."
        echo "Please download manually from: https://cursor.sh"
        open "https://cursor.sh"
    fi
fi

echo ""
echo "=== Verifying Claude Code Connection ==="

# Check if Claude Code is accessible
if command -v claude &> /dev/null; then
    echo "✓ Claude Code is installed and in PATH"
    claude --version 2>/dev/null || echo "  Version check not available"
else
    echo "⚠️  Claude Code not found in PATH"
    echo "  Expected at: /usr/local/bin/claude"
fi

echo ""
echo "=== Next Steps ==="
echo "1. Open Cursor from Applications or Launchpad"
echo "2. Sign in with your account"
echo "3. Configure AI settings (API keys, models)"
echo "4. Import settings from Windows if available"
echo ""
echo "To launch Cursor from terminal: cursor"
echo "To add Cursor to PATH (if needed):"
echo "  Open Cursor → Cmd+Shift+P → 'Install cursor command in PATH'"

# Check for bake-tracker CLAUDE.md
BAKE_TRACKER_DIR="$HOME/repos/bake-tracker"
if [ -f "$BAKE_TRACKER_DIR/CLAUDE.md" ]; then
    echo ""
    echo "=== Claude Code Project Detected ==="
    echo "✓ Found CLAUDE.md in bake-tracker repository"
    echo "  Location: $BAKE_TRACKER_DIR/CLAUDE.md"
    echo "  This project is configured for Claude Code integration"
fi

echo ""
echo "Done!"
