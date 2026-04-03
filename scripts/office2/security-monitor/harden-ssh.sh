#!/bin/bash
# SSH hardening for office2
# Adds explicit security settings via sshd_config.d drop-in
# Does not modify /etc/ssh/sshd_config directly
# Run as kgale with sudo available

set -e

DROPIN="/etc/ssh/sshd_config.d/10-felix-hardening.conf"
OLD_DROPIN="/etc/ssh/sshd_config.d/60-felix-hardening.conf"

echo "=== Writing SSH hardening drop-in ==="
cat > "$DROPIN" << 'EOF'
# Felix security hardening — explicit SSH settings
# Installed as part of Level 1 security hardening
# Overrides commented-out defaults in /etc/ssh/sshd_config

# Disable password authentication — key-based auth only
PasswordAuthentication no

# Disable root login entirely (default is prohibit-password; this is explicit)
PermitRootLogin no
EOF

echo "Written: $DROPIN"
cat "$DROPIN"

# Remove old 60- file if it exists
[ -f "$OLD_DROPIN" ] && rm "$OLD_DROPIN" && echo "Removed old: $OLD_DROPIN"

echo ""
echo "=== Validating sshd config ==="
sshd -t && echo "Config valid"

echo ""
echo "=== Reloading sshd ==="
systemctl reload ssh

echo ""
echo "=== Effective settings ==="
sshd -T 2>/dev/null | grep -E "^passwordauthentication|^permitrootlogin|^pubkeyauthentication"
