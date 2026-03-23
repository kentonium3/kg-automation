#!/bin/bash

# Configure pip to work without the externally-managed restriction
# This makes your Mac pip work like Windows pip

echo "=== Configuring pip to work normally ==="
echo ""

# Create pip config directory
mkdir -p ~/.config/pip

# Create pip.conf with settings
cat > ~/.config/pip/pip.conf << 'EOF'
[global]
break-system-packages = true

[install]
user = true
EOF

echo "✓ Created ~/.config/pip/pip.conf"
echo ""
echo "pip will now:"
echo "  - Install packages without the 'externally-managed' warning"
echo "  - Install to your user directory by default (--user)"
echo ""
echo "You can now use pip normally:"
echo "  pip install spec-kitty-cli"
echo "  pip install any-other-package"
echo ""
echo "This matches your Windows workflow."
