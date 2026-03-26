#!/usr/bin/env bash
# install.sh — Install OpenClaw on office2
# Run as claude user. Sudo commands are printed for Kent to execute manually.
set -euo pipefail

OPENCLAW_VERSION="v2026.3.24"
SECRETS_DIR="/data/services/openclaw/secrets"
DATA_DIR="/data/services/openclaw/data"

echo "=== OpenClaw Install ==="
echo ""

# Check Node.js
if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js is not installed." >&2
    exit 1
fi
NODE_VER=$(node --version)
echo "[OK] Node.js: $NODE_VER"

# Check npm
if ! command -v npm &>/dev/null; then
    echo "ERROR: npm is not installed." >&2
    exit 1
fi
echo "[OK] npm: $(npm --version)"

# Check if OpenClaw is already installed
if command -v openclaw &>/dev/null; then
    CURRENT_VER=$(openclaw --version 2>/dev/null || echo "unknown")
    echo "[INFO] OpenClaw already installed: $CURRENT_VER"
    echo "  To upgrade, Kent must run:"
    echo "  sudo npm install -g openclaw@${OPENCLAW_VERSION}"
else
    echo ""
    echo "============================================================"
    echo "MANUAL STEP: Kent must run the following sudo command:"
    echo "============================================================"
    echo ""
    echo "  sudo npm install -g openclaw@${OPENCLAW_VERSION}"
    echo ""
    echo "Then verify: openclaw --version"
fi

# Create directories
echo ""
echo "Creating directories..."
mkdir -p "$SECRETS_DIR"
mkdir -p "$DATA_DIR"
chmod 700 "$SECRETS_DIR"
echo "[OK] Secrets directory: $SECRETS_DIR (mode 700)"
echo "[OK] Data directory: $DATA_DIR"

# Verify ownership
OWNER=$(stat -c '%U' "$SECRETS_DIR" 2>/dev/null || stat -f '%Su' "$SECRETS_DIR" 2>/dev/null)
if [ "$OWNER" != "claude" ]; then
    echo "WARNING: Secrets directory owned by $OWNER, expected claude" >&2
fi

# Print credential placement instructions
echo ""
echo "============================================================"
echo "MANUAL STEPS: Kent must place credentials"
echo "============================================================"
echo ""
echo "1. Place Anthropic API key:"
echo "   echo '<API_KEY>' > $SECRETS_DIR/anthropic"
echo "   chmod 600 $SECRETS_DIR/anthropic"
echo ""
echo "2. Run onboarding (after placing API key):"
echo "   openclaw onboard --install-daemon"
echo ""
echo "3. Later (WP03): Place Vikunja API token:"
echo "   echo '<TOKEN>' > $SECRETS_DIR/vikunja-api"
echo "   chmod 600 $SECRETS_DIR/vikunja-api"
echo ""
echo "=== Install script complete ==="
