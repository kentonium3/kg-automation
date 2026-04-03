#!/bin/bash
# Install and configure fail2ban on office2
# Protects SSH against brute-force attempts
# Run as kgale with sudo available

set -e

echo "=== Installing fail2ban ==="
apt-get update -qq
apt-get install -y fail2ban

echo "=== Writing jail.local ==="
cat > /etc/fail2ban/jail.local << 'EOF'
# Felix security hardening — fail2ban SSH jail
# Installed as part of Level 1 security hardening

[DEFAULT]
# Ban duration: 1 hour
bantime  = 3600
# Window to count failures in: 10 minutes
findtime = 600
# Max failures before ban
maxretry = 5
# Use systemd journal as log backend (Ubuntu 24.04)
backend  = systemd

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s
maxretry = 5
EOF

echo "=== Enabling and starting fail2ban ==="
systemctl enable fail2ban
systemctl start fail2ban

echo "=== Status ==="
systemctl is-active fail2ban
fail2ban-client status sshd
