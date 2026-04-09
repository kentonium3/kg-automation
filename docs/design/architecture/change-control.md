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
| Doc added, moved, archived, or deprecated under `docs/` | — | `docs/INDEX.md` |
| New directory created under `docs/` | — | `docs/INDEX.md` |

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

## INDEX.md Maintenance (mandatory)

When a feature adds, moves, archives, or deletes any document or directory under `docs/`, the same feature branch MUST update `docs/INDEX.md` to reflect the change. Failure to update INDEX.md is a protocol violation and blocks feature acceptance.

**Applies to**:

- Adding a new doc or directory under `docs/`
- Moving or renaming a doc or directory
- Archiving a doc (moving to `docs/archive/`)
- Deprecating a doc (setting `status: deprecated`)
- Adding a new machine-readable artifact under `docs/design/architecture/data/`

**Does not apply to**:

- Editing an existing doc's body content without changing its path
- Updating frontmatter metadata alone (e.g., `last_validated`)
- Touching files under `docs/archive/` (frozen historical artifacts)

## Risk-Tiered Change Control

All changes to the deployed system are classified by a five-tier risk taxonomy defined in `docs/design/architecture/data/change-risk-taxonomy.json`:

| Tier | Label | Guardrail |
|------|-------|-----------|
| 0 | Hard Lock | AI generates scripts, human executes — host/foundational changes (UFW, iptables, SSH) |
| 1 | Human-Gated | AI prepares, human approves before execution |
| 2 | Supervised | AI executes with post-change verification |
| 3 | Notify | AI executes autonomously, human notified |
| 4 | Auto-Commit | Routine changes committed without notification |

**Pre-flight assessment**: Tier 0 and Tier 1 changes require a mandatory pre-flight checklist before execution. See `docs/runbooks/governance/pre-flight-checklist.md`.

**Post-change verification**: Tier 0, 1, and 2 changes require post-change service health verification. See `docs/runbooks/governance/post-change-verification.md`.

**Dependency awareness**: The service dependency graph (`docs/design/architecture/data/service-inventory.json` — `dependencies` field) is consulted during pre-flight to identify blast radius. See `docs/design/architecture/service-dependencies.view.md` for a visual map.

**Postmortems**: When a change causes an incident, a postmortem is filed as a GitHub issue or archived to `docs/archive/`.

## CI Validation

`validate_docs.py` runs on every push to main. All markdown files in `docs/design/architecture/` must have valid YAML frontmatter (title, doc_type, status).

## Git Workflow

Push directly to main for routine changes. Use feature branches for complex multi-step work. Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`.
