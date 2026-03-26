---
title: Architecture Documentation Index
doc_type: index
status: approved
---

# Architecture Documentation

Current-state documentation of the kg-automation system. Updated after every feature deployment.

**JSON files in `data/` are the authoritative record.** Markdown files are narrative views. When they conflict, JSON wins.

## Documents

| Document | Purpose |
|----------|---------|
| [Physical Topology](physical-topology.md) | Hardware, network, Tailscale topology |
| [Service Inventory](service-inventory.md) | What runs where — versions, ports, paths |
| [Data Flows](data-flows.md) | Input paths, processing pipelines, storage |
| [Credentials and Secrets](credentials-and-secrets.md) | Secret store layout, access model |
| [Identity Model](identity-model.md) | Personal vs Intentional, label routing |
| [Backup and Recovery](backup-and-recovery.md) | Restic scope, retention, restore |
| [Security Posture](security-posture.md) | Tailscale-only, supply chain, privacy |
| [Change Control](change-control.md) | Update protocol after each feature |
| [Glossary](glossary.md) | Canonical terms |

## Data Files

| File | Contents |
|------|----------|
| [hardware-inventory.json](data/hardware-inventory.json) | Hosts, IPs, specs, roles |
| [service-inventory.json](data/service-inventory.json) | Services, versions, ports, paths |
| [network-topology.json](data/network-topology.json) | Tailscale IPs, port assignments |
| [credential-manifest.json](data/credential-manifest.json) | Named credentials, scopes |
| [data-flows.json](data/data-flows.json) | Input paths, pipelines, storage targets |

## Update Protocol

Every feature that changes deployed services, credentials, data flows, or network topology must update the relevant files here. See [Change Control](change-control.md) for the full protocol.
