---
work_package_id: WP02
title: Enrich Service Inventory + Network Topology
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP01
base_commit: 2fefc6d022e353f74e4d492223808e48a571a10c
created_at: '2026-04-05T23:37:19.825606+00:00'
subtasks:
- T005
- T006
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Data Enrichment
assignee: ''
agent: "claude"
shell_pid: "60801"
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/data/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/network-topology.json
---

# Work Package Prompt: WP02 — Enrich Service Inventory + Network Topology

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Extend all 11 service records in `service-inventory.json` with `risk_tier`, `dependencies`, `health_check`, and `config_files` fields. Add Tailscale serve entry to `network-topology.json`.

**Success criteria**:

- [ ] All 11 services have `risk_tier` (integer 0-4).
- [ ] All 11 services have `dependencies` array (may be empty for independent services).
- [ ] All 11 services have `health_check` object.
- [ ] All 11 services have `config_files` array.
- [ ] Vikunja has a dependency on `tailscale-serve:443` specifically.
- [ ] `network-topology.json` port 443 entry has a `tailscale_serve` object.
- [ ] `service-inventory.json` `schema_version` bumped to `"1.1"`, `updated_by` set to `"F016"`.
- [ ] No existing fields removed (backward-compatible schema extension per NFR-004).

## Context & Constraints

The service inventory and network topology are machine-readable architecture files that other WPs (WP03, WP05) depend on for dependency lookups and health-check references. The enrichment must be backward-compatible — extend the schema, never remove existing fields.

**Constraints**:

- NFR-004: Extend schema WITHOUT removing existing fields.
- Risk tier assignments must align with WP01 taxonomy definitions.
- Dependency entries must use specific target identifiers (not generic service names).

**Reference documents**:

- `docs/design/architecture/data/service-inventory.json` (current state)
- `docs/design/architecture/data/network-topology.json` (current state)
- `docs/design/architecture/data/change-risk-taxonomy.json` (created by WP01)
- `kitty-specs/016-change-control-governance/plan.md`

## Subtasks & Detailed Guidance

### Subtask T005 — Add risk_tier to each service

- **Purpose**: Classify each service by its risk tier from the taxonomy.
- **Steps**:
  1. Add `"risk_tier"` (integer) to each service record using these assignments:
     - vikunja: 2
     - openclaw-gateway: 2
     - restic-backup: 2
     - security-monitor: 1
     - obsidian-sync: 3
     - second-brain-sync: 3
     - transcribe-api: 2
     - inbox-processing: 3
     - habit-checkin: 3
     - task-detection: 3
     - felix-core-digest: 3
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: Yes — independent of T006, T007, T008.

### Subtask T006 — Add dependencies array

- **Purpose**: Document inter-service and infrastructure dependencies.
- **Steps**:
  1. Add `"dependencies"` array to each service. Each entry is an object with:
     - `"target"` (string — specific identifier, e.g., `"tailscale-serve:443"`)
     - `"type"` (string — one of: `"requires"`, `"provides"`, `"optional"`)
     - `"description"` (string)
  2. **Critical**: Vikunja MUST have a dependency entry with `"target": "tailscale-serve:443"`, `"type": "requires"`, and a description noting HTTPS access depends on Tailscale serve.
  3. Services with no external dependencies get an empty array `[]`.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: Yes — independent of T005, T007, T008.

### Subtask T007 — Add health_check object

- **Purpose**: Define how to verify each service is operational.
- **Steps**:
  1. Add `"health_check"` object to each service with fields:
     - `"method"` (string — one of: `"http"`, `"tcp"`, `"systemd-status"`, `"shell"`, `"none"`)
     - `"endpoint"` (string — URL, address, or unit name; empty string if method is `"none"`)
     - `"expected"` (string or integer — e.g., `200` for HTTP, `"active"` for systemd)
     - `"timeout_seconds"` (integer)
  2. For services without a reachable endpoint, use `"method": "none"`.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: Yes — independent of T005, T006, T008.

### Subtask T008 — Add config_files array

- **Purpose**: Document configuration file locations for each service.
- **Steps**:
  1. Add `"config_files"` array to each service. Each entry is an object with:
     - `"path"` (string — absolute path on office2)
     - `"source_in_repo"` (string, optional — relative path in kg-automation repo if the config is tracked)
     - `"format"` (string — e.g., `"yaml"`, `"env"`, `"json"`, `"toml"`, `"ini"`)
  2. Services with no tracked config files get an empty array `[]`.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: Yes — independent of T005, T006, T007.

### Subtask T009 — Verify Vikunja tailscale-serve:443 dependency

- **Purpose**: Explicitly verify the critical dependency that motivated this feature.
- **Steps**:
  1. Confirm Vikunja's `dependencies` array contains an entry with `"target": "tailscale-serve:443"`.
  2. This is the dependency that the origin UFW incident would have surfaced if the inventory had existed.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: After T006.

### Subtask T010 — Add tailscale_serve to network topology

- **Purpose**: Document the Tailscale serve configuration for port 443.
- **Steps**:
  1. In `network-topology.json`, locate the port 443 entry.
  2. Add a `"tailscale_serve"` object:
     ```json
     {
       "listen_port": 443,
       "backend": "https+insecure://100.92.197.90:3456",
       "backend_service": "vikunja",
       "interface": "tailscale0",
       "ufw_rule": "allow in on tailscale0 to any port 443 proto tcp"
     }
     ```
- **Files**: `docs/design/architecture/data/network-topology.json`
- **Parallel?**: Yes — independent of service-inventory subtasks.

### Subtask T011 — Bump schema version

- **Purpose**: Signal that the schema has been extended.
- **Steps**:
  1. In `service-inventory.json`, change `"schema_version"` from `"1.0"` to `"1.1"`.
  2. Set `"updated_by"` to `"F016"`.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: After T005-T008 are complete.

## Test Strategy

N/A — data enrichment, no automated tests.

**Manual validation**:

- Both JSON files parse correctly.
- All 11 services have the 4 new fields.
- Vikunja has `tailscale-serve:443` dependency.
- No existing fields have been removed.

## Integration Verification

- [ ] All 11 services have `risk_tier`, `dependencies`, `health_check`, `config_files`.
- [ ] Vikunja `dependencies` includes `tailscale-serve:443`.
- [ ] `network-topology.json` port 443 has `tailscale_serve` object.
- [ ] `schema_version` is `"1.1"` in `service-inventory.json`.
- [ ] Both files are valid JSON.
- [ ] No existing fields removed (diff shows only additions).

## Review Guidance

- **Key checkpoints**: All 11 services enriched with all 4 new fields. Vikunja's `tailscale-serve:443` dependency is present and correct. Schema is backward-compatible (no fields removed).
- **Before approving**: Diff against prior version to confirm only additions. Spot-check risk tier assignments against taxonomy definitions.

## Definition of Done

- Both JSON files committed to main with enriched data.
- All 11 services enriched.
- Vikunja dependency on tailscale-serve:443 documented.
- Schema backward-compatible.

## Activity Log
- 2026-04-05T23:40:41Z – unknown – shell_pid=60032 – 11 services enriched with risk_tier/deps/health/config. Vikunja tailscale-serve:443 dep confirmed. Schema v1.1.
- 2026-04-05T23:40:50Z – claude – shell_pid=60801 – Started review via workflow command
