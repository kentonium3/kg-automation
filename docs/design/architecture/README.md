---
title: Architecture Documentation Index
doc_type: index
status: approved
---

# Architecture Documentation

Current-state documentation of the kg-automation system. Updated after every feature deployment.

**JSON files in `data/` are the authoritative record.** Markdown files are narrative views. When they conflict, JSON wins.

## Machine-Readable Artifact Home

`docs/design/architecture/data/` is the **canonical home** for all current-state operational machine-readable artifacts describing the kg-automation system: service inventory, hardware inventory, network topology, credential manifest, data flows, and their associated JSON schemas.

- **Authoritative record**: These JSON files are the source of truth. Narrative `.md` companions render the JSON as prose for human readers.
- **Exempt from moves**: Files in `data/` are not relocated by documentation-rationalization work (constraint enforced by F015).
- **Schema co-location**: Schema files (`*-schema.json`) live alongside the data files they describe within `data/`. Schemas that describe cross-cutting standards (e.g., frontmatter, validator policy) live in `docs/design/standards/` as the exception.

See [`docs/INDEX.md`](../../INDEX.md) for the complete listing of machine-readable artifacts across the repo.

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
| [Service Dependencies Diagram](service-dependencies.view.md) | Visual map of service dependency graph |
| [Pre-Flight Checklist](../runbooks/governance/pre-flight-checklist.md) | Change control pre-flight assessment |
| [Post-Change Verification](../runbooks/governance/post-change-verification.md) | Post-change service health verification |
| [Postmortems](../../issues/postmortems/) | Incident analysis records |
| [Glossary](glossary.md) | Canonical terms |

## Data Files

| File | Contents |
|------|----------|
| [hardware-inventory.json](data/hardware-inventory.json) | Hosts, IPs, specs, roles |
| [service-inventory.json](data/service-inventory.json) | Services, versions, ports, paths |
| [network-topology.json](data/network-topology.json) | Tailscale IPs, port assignments |
| [credential-manifest.json](data/credential-manifest.json) | Named credentials, scopes |
| [data-flows.json](data/data-flows.json) | Input paths, pipelines, storage targets |
| [change-risk-taxonomy.json](data/change-risk-taxonomy.json) | Five-tier risk taxonomy with guardrail protocols |

## Update Protocol

Every feature that changes deployed services, credentials, data flows, or network topology must update the relevant files here. See [Change Control](change-control.md) for the full protocol.
