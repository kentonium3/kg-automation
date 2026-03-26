---
title: Change Control
doc_type: reference
status: approved
---

# Change Control

## Update Protocol

Every feature that changes the deployed system must update the relevant architecture documentation as part of its implementation work packages. This is a standing requirement, not a separate workflow.

### What Triggers an Update

| Change Type | JSON to Update | Markdown to Update |
|-------------|---------------|--------------------|
| New service deployed | `service-inventory.json` | `service-inventory.md` |
| Service version changed | `service-inventory.json` | `service-inventory.md` |
| New hardware or host | `hardware-inventory.json` | `physical-topology.md` |
| New credential added | `credential-manifest.json` | `credentials-and-secrets.md` |
| New input path or pipeline | `data-flows.json` | `data-flows.md` |
| Port or network change | `network-topology.json` | `physical-topology.md`, `security-posture.md` |
| Backup scope change | `service-inventory.json` | `backup-and-recovery.md` |
| Security baseline change | — | `security-posture.md` |
| New identity or routing rule | — | `identity-model.md` |

### How to Update

1. Edit the relevant JSON file in `docs/design/architecture/data/`
2. Set `last_updated` to today's date and `updated_by` to the feature ID
3. Update the corresponding markdown view to match
4. Update Mermaid diagrams if the topology or data flow changed
5. Commit alongside the feature's other deliverables

### JSON Schema Rules

Every JSON file includes:
- `schema_version` — for forward compatibility (currently `"1.0"`)
- `last_updated` — ISO date of last modification
- `updated_by` — feature ID that last modified it (e.g., `"F001"`)

### Where This Gets Enforced

- **Func-spec template**: Each func-spec should identify which architecture docs are affected
- **Agent instructions**: CLAUDE.md and agent instruction files include a standing directive to update architecture docs
- **Spec-kitty review**: Reviewers check that architecture docs were updated when infrastructure changes

## CI Validation

`validate_docs.py` runs on every push to main. All markdown files in `docs/design/architecture/` must have valid YAML frontmatter (title, doc_type, status).

## Git Workflow

Push directly to main for routine changes. Use feature branches for complex multi-step work. Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`.
