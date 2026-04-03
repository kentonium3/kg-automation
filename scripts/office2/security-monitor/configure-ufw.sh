#!/bin/bash
# Configure UFW firewall on office2
# Protects SSH (port 22) from non-LAN, non-Tailscale access
#
# Why UFW is safe here despite Docker:
#   All Docker ports are bound to 100.92.197.90 (Tailscale IP only),
#   so Docker bypassing UFW's INPUT chain is not a concern —
#   there are no Docker ports exposed on non-Tailscale interfaces to protect.
#   UFW's sole job is controlling access to SSH on port 22.
#
# Run as kgale with sudo available

set -e

echo "=== Current UFW state ==="
ufw status

echo ""
echo "=== Configuring UFW rules ==="

# Defaults
ufw default deny incoming
ufw default allow outgoing

# SSH: allow from home LAN
ufw allow from 192.168.1.0/24 to any port 22 proto tcp comment 'SSH from home LAN'

# SSH: allow from Tailscale address range (100.64.0.0/10 per RFC 6598)
ufw allow from 100.64.0.0/10 to any port 22 proto tcp comment 'SSH from Tailscale'

echo ""
echo "=== Enabling UFW ==="
# --force skips the interactive "may disrupt existing connections" prompt
# Rules above ensure current SSH session stays alive
ufw --force enable

echo ""
echo "=== Final UFW state ==="
ufw status verbose
