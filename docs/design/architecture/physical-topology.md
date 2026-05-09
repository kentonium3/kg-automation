---
title: Physical Topology
doc_type: reference
status: approved
---

# Physical Topology

Authoritative data: [`data/hardware-inventory.json`](<./data/hardware-inventory.json>), [`data/network-topology.json`](<./data/network-topology.json>)

## Hosts

### office2 — Always-On Hub

| Attribute | Value |
|-----------|-------|
| Hardware | Dell XPS 8700 |
| CPU | Intel Core i7-4790 @ 3.60GHz |
| RAM | 32 GB |
| GPU | NVIDIA GeForce GTX 1060 6GB (Pascal GP106, compute 6.1) — driver 535.288.01, CUDA 12.2 |
| OS | Ubuntu 24.04 LTS (kernel 6.8.0-111-generic) |
| Local IP | 192.168.1.158 |
| Tailscale IP | 100.92.197.90 |
| Role | Always-on hub — runs all services |

**Storage:**

| Mount | Device | Size | Purpose |
|-------|--------|------|---------|
| `/` | LVM (SSD) | 98 GB | OS and home directories |
| `/data` | `/dev/sda1` (HDD) | 2.7 TB | Services, transcripts, application data |
| `/mnt/backups` | `/dev/sdg1` | 916 GB | Restic backup repository |

**BIOS / firmware:**

| Setting | Value | Notes |
|---------|-------|-------|
| BIOS version | A13 (2018-06-13) | Final firmware Dell shipped for the XPS 8700; no further updates expected |
| AC power restoration | Power on | Auto-recovers after power outages — important for "always-on hub" role (set 2026-05-08 after a Detroit outage took the server offline for two days) |
| Primary display | PCIe / discrete GPU | GTX 1060 drives the console |
| Secure boot | Enabled | Canonical-signed nvidia driver works without MOK enrollment |
| Console resolution | 800x600 (firmware ceiling) | UEFI hands the kernel a low-res framebuffer at POST and it cannot be overridden in OS — see issue #191 |

### MacBook Pro — Authoring Endpoint

| Attribute | Value |
|-----------|-------|
| Tailscale IP | 100.71.19.66 |
| Role | Authoring, interaction, SSH to office2 |

### iPhone 14 Pro Max — Mobile

| Attribute | Value |
|-----------|-------|
| Tailscale IP | 100.109.208.6 |
| Role | Mobile capture (Wispr Flow), task monitoring (Vikunja web UI) |

## Network

All inter-device communication uses **Tailscale**. No services are exposed to the public internet. No port forwarding or NAT traversal outside Tailscale.

**Tailscale Serve**: Port 443 on the `tailscale0` interface proxies to `100.92.197.90:3456` (Vikunja). TLS is terminated by Tailscale with auto-provisioned Let's Encrypt certificates. Access is tailnet-only (Funnel disabled).

**SSH access:**
- Agents: `ssh office2-claude` (claude user, no sudo)
- Kent: `ssh office2-kgale` (kgale user, sudo available)
- Host aliases defined in `~/.ssh/config` on Mac

## Service Dependencies

See [Service Dependencies Diagram](<./service-dependencies.view.md>) for a visual map of how services on office2 depend on each other. This diagram is derived from the `dependencies` field in `data/service-inventory.json` and is used during change control pre-flight assessment to determine blast radius.
