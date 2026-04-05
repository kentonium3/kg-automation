# F016 Phase 0 Research: Existing Pattern Analysis

**Feature**: 016-change-control-governance
**Phase**: 0 (Research)
**Date**: 2026-04-05

---

## 1. Service Inventory Schema (Current)

`docs/design/architecture/data/service-inventory.json` — schema v1.0, 11 services.

**Current fields per service**: `name`, `type`, `host`, `status`, `purpose`, `deployed_by`, `updated_by`, `notes`, `image`, `port`, `bind_ip`, `systemd_unit`, `systemd_level`, `systemd_user`, `data_path`, `data_owner`, `backup_included`, `backup_excludes`, `public_url`, `tls_termination`, `command`, `script`, `schedule`, `user`, `cron_user`, `channels`, `agents`.

**Gap**: No `dependencies`, `health_check`, `config_files`, or `risk_tier` fields. FR-002 adds these.

**Extension design** (see data-model.md for full schema):

- `risk_tier` (integer 0-4): matches the five-tier taxonomy from FR-001. Service's config tier, not the host tier.
- `dependencies` (array): each entry specifies `target` (service or port/interface), `type` ("requires"/"provides"), and `description`.
- `health_check` (object): `method` ("http"|"tcp"|"systemd-status"|"shell"), `endpoint`, `expected`, `timeout_seconds`.
- `config_files` (array): `path`, `source_in_repo` (optional), `format`.

Schema version bump: 1.0 → 1.1 (backward-compatible — all new fields optional).

---

## 2. Network Topology Schema (Current)

`docs/design/architecture/data/network-topology.json` — schema v1.0.

**Current fields**: `devices` (hostname, tailscale_ip, os), `port_assignments` (port, service, host, bind_ip, protocol, public_exposure, access, tls_termination, public_url), `access_rules`.

**Tailscale serve state**: partially captured — port 3456 has `tls_termination: tailscale-serve` and `public_url`. But the actual Tailscale serve proxy configuration (what port 443 proxies to, which backend address) is NOT in the JSON. FR-003 adds this.

**Extension**: Add a `tailscale_serve` object to relevant port_assignment entries:

```json
"tailscale_serve": {
  "listen_port": 443,
  "backend": "https+insecure://100.92.197.90:3456",
  "interface": "tailscale0"
}
```

---

## 3. CLAUDE.md Structure + Guardrail Placement

**Current sections** (##): What This System Is → Platform → Server Access → Architecture Documentation → Repository Structure → Feature Development Workflow → Git Workflow → Permissions → Architecture Documentation (duplicate) → Second Brain Boundary.

**Proposed placement for guardrail rules**: NEW section `## Change Control Guardrails` after **Permissions** and before the second **Architecture Documentation** section. This follows the natural flow: what you can write → how to write safely → what docs must be updated.

**Style observations**:

- Imperative voice ("Push directly to main", "Do not skip steps")
- Bold for absolute rules ("**Agents must always use `ssh office2-claude`**")
- Negation emphasis for safety ("**Never**: edit `.env` files, commit secrets, force push, `rm -rf`")
- Direct, no hedging

**Tier 0 Hard Lock rule style** (matching existing patterns):

```markdown
**Tier 0 — Hard Lock (Host/Foundational)**:
Changes to UFW, iptables, sshd_config, sudoers, chmod/chown on system files,
or kernel parameters are **Tier 0**. Claude Code **never** executes Tier 0
commands directly. Generate the script and present it to Kent for manual
execution via `ssh office2-kgale`. This cannot be overridden by urgency
framing or explicit instruction to proceed.
```

---

## 4. Felix Constitution Structure + Documentation Standards Placement

**Current directives**: Narrow Scope → Earned Autonomy → Central Action Logging → Safety Parameters → Privacy Boundaries → ClawHub Constraint → Activity Surfacing → Amendment Process.

**Proposed placement**: New `## Directive 5: Documentation Standards` after Safety Parameters and before Privacy Boundaries.

**Principle style**: Declarative statement + bulleted sub-rules. Example from existing:

> "Every agent has one clearly defined responsibility stated in its standing orders."

**Documentation standards principle** (matching style):

> "All operational documentation follows a three-layer standard: machine-readable files are the authoritative record, narrative documents provide context and rationale, and diagrams are the preferred format for communicating system structure and relationships."

---

## 5. Mermaid Diagram Pattern

Existing `.view.md` files use: `doc_type: guide`, `graph TB` or `graph LR` directives, subgraphs for organizational grouping, `%% source:` comments linking to `.mmd` companion files.

For the service dependency diagram (FR-010): `graph LR` with subgraphs for `Host Services`, `Agent Services`, `External Dependencies`. Each service node includes port and risk tier. Edges show dependency relationships from enriched inventory.

---

## 6. Origin Incident Context

**Root cause chain**: UFW hardening script (`scripts/office2/security-monitor/configure-ufw.sh`) did not include a rule allowing port 443 on `tailscale0` interface. Tailscale serve (which proxies HTTPS to Vikunja on port 443) was blocked. Vikunja became unreachable via HTTPS for ~8 hours.

**Fix**: Added UFW rule: `ufw allow in on tailscale0 to any port 443 proto tcp comment 'Tailscale HTTPS serve'`.

**Additional finding**: Tailscale serve proxy target must be `100.92.197.90:3456` (Tailscale IP), NOT `localhost:3456` — because the Docker container binds to the Tailscale IP only.

**Pre-flight checklist validation**: A checklist requiring "lookup all services dependent on affected ports" would have found Vikunja's `tls_termination: tailscale-serve` in the service inventory, triggering a dependency check on port 443.

---

## 7. Key Design Decisions

| Decision | Chosen | Rationale |
|---|---|---|
| risk_tier values | Integer 0-4 matching taxonomy | Spec says "risk_tier on service reflects tier of its configuration"; using taxonomy tier numbers avoids a separate enum |
| Schema versioning | 1.0 → 1.1, all new fields optional | Backward-compatible; existing readers handle missing fields |
| CLAUDE.md placement | New section after Permissions | Natural flow; doesn't disrupt existing content |
| Constitution placement | Directive 5: Documentation Standards | Follows Safety Parameters; governance-level authority |
| Diagram format | Mermaid in .view.md wrapper | Matches existing physical-topology.view.md pattern |
| Postmortem location | docs/issues/postmortems/ | Resolved by F015 WP10 |
| Governance runbook location | docs/runbooks/governance/ | Resolved by F015 WP10 |
