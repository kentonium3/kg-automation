# F016 Phase 1 — Data Model: Schema Extensions

**Feature**: 016-change-control-governance
**Phase**: 1 (Design)

---

## 1. change-risk-taxonomy.json (NEW)

Path: `docs/design/architecture/data/change-risk-taxonomy.json`

```json
{
  "schema_version": "1.0",
  "last_updated": "2026-04-XX",
  "updated_by": "F016",
  "tiers": [
    {
      "tier": 0,
      "name": "Host / Foundational",
      "scope": "SSH, sudoers, UFW, iptables, kernel parameters, system file permissions",
      "guardrail_protocol": "hard_lock",
      "guardrail_description": "AI generates script only; human executes manually via ssh office2-kgale",
      "examples": ["ufw rules", "sshd_config", "sudoers", "chmod/chown on system files"],
      "overridable": false
    },
    {
      "tier": 1,
      "name": "Connectivity / Fabric",
      "scope": "Tailscale, Docker networks, proxy/DNS, API gateways",
      "guardrail_protocol": "verification_required",
      "guardrail_description": "AI must confirm connectivity before and after; surface dependent services",
      "examples": ["tailscale serve config", "Docker network changes", "port bindings"],
      "overridable": true
    },
    {
      "tier": 2,
      "name": "Application / State",
      "scope": "DB schemas, service env files, Docker Compose volumes",
      "guardrail_protocol": "snapshot_required",
      "guardrail_description": "AI must trigger backup/snapshot before modifying",
      "examples": ["Docker Compose env changes", "Vikunja config", "database schema"],
      "overridable": true
    },
    {
      "tier": 3,
      "name": "Logic / Workflow",
      "scope": "Python scripts, agent prompts, cron jobs, logic flows",
      "guardrail_protocol": "standard",
      "guardrail_description": "AI may modify and test via dry-run or sandbox",
      "examples": ["agent AGENTS.md", "cron schedule", "OpenClaw skill scripts"],
      "overridable": true
    },
    {
      "tier": 4,
      "name": "Schema / Metadata",
      "scope": "CLAUDE.md, READMEs, comments, logging verbosity, doc frontmatter",
      "guardrail_protocol": "auto_commit",
      "guardrail_description": "AI has full autonomy to update and sync",
      "examples": ["CLAUDE.md edits", "doc frontmatter", "README updates"],
      "overridable": true
    }
  ]
}
```

---

## 2. service-inventory.json Extension Fields

Schema version: 1.0 → 1.1. All new fields OPTIONAL on each service record.

### risk_tier (integer)

```json
"risk_tier": 2
```

Value 0-4 matching `change-risk-taxonomy.json` tier numbers. Reflects the tier of the SERVICE'S CONFIGURATION — not the host it runs on. Examples:

| Service | risk_tier | Rationale |
|---|---|---|
| vikunja | 2 | Application state — Docker Compose, env, data volume |
| openclaw-gateway | 2 | Application state — agent config, skills |
| restic-backup | 2 | Application state — backup config, excludes |
| security-monitor | 1 | Connectivity fabric — UFW rules, audit baselines |
| obsidian-sync | 3 | Logic/workflow — sync script, cron schedule |
| felix-core-digest | 3 | Logic/workflow — agent prompt, cron schedule |

### dependencies (array of objects)

```json
"dependencies": [
  {
    "target": "tailscale-serve:443",
    "type": "requires",
    "description": "HTTPS termination via Tailscale Serve on port 443"
  },
  {
    "target": "docker",
    "type": "requires",
    "description": "Runs as Docker container"
  }
]
```

Fields:
- `target` (string): service name, port, or interface identifier. Specific enough for pre-flight impact analysis.
- `type` (string): `"requires"` | `"provides"` | `"optional"`.
- `description` (string): human-readable explanation.

### health_check (object)

```json
"health_check": {
  "method": "http",
  "endpoint": "http://100.92.197.90:3456/api/v1/info",
  "expected": 200,
  "timeout_seconds": 5
}
```

Fields:
- `method` (string): `"http"` | `"tcp"` | `"systemd-status"` | `"shell"` | `"none"`.
- `endpoint` (string, optional): URL, address, or command.
- `expected` (integer or string, optional): expected HTTP status code or output.
- `timeout_seconds` (integer): max wait.

When `method: "none"`: service has no automated health check. Post-change verification flags as "manual check required."

### config_files (array of objects)

```json
"config_files": [
  {
    "path": "/etc/systemd/system/vikunja.service",
    "source_in_repo": "scripts/vikunja/vikunja.service",
    "format": "systemd-unit"
  },
  {
    "path": "/data/services/vikunja/vikunja.yml",
    "format": "yaml"
  }
]
```

Fields:
- `path` (string): absolute path on the host.
- `source_in_repo` (string, optional): repo path if version-controlled.
- `format` (string): file format identifier.

---

## 3. network-topology.json Extension

Add `tailscale_serve` object to port assignments where Tailscale serve terminates TLS:

```json
{
  "port": 443,
  "service": "tailscale-serve",
  "host": "office2",
  "bind_ip": "tailscale0",
  "protocol": "tcp",
  "public_exposure": "tailnet-only",
  "access": "tailscale-only",
  "tls_termination": "tailscale-serve",
  "public_url": "https://office2.tail0f5f56.ts.net",
  "tailscale_serve": {
    "backend": "https+insecure://100.92.197.90:3456",
    "backend_service": "vikunja",
    "ufw_rule": "allow in on tailscale0 to any port 443 proto tcp"
  }
}
```

---

## 4. Postmortem Template Schema

Template file: `docs/runbooks/governance/incident-postmortem-template.md`

Required sections:
1. **Incident Summary** — title, date, duration, severity
2. **Timeline** — chronological events from detection to resolution
3. **Root Cause Chain** — causal chain from trigger to impact
4. **Impact** — what was affected, for how long, who was impacted
5. **What Went Well** — effective responses or mitigations
6. **What Failed** — process/system gaps that allowed or prolonged the incident
7. **Follow-On Actions** — structured as:

```markdown
| ID | Action | Type | Owner | Vikunja Task | Status |
|---|---|---|---|---|---|
| A1 | Add port 443 dependency to service inventory | documentation | Kent | (placeholder) | pending |
| A2 | Create pre-flight checklist for firewall changes | process | Kent | (placeholder) | pending |
```

Action types: `immediate-fix`, `process-change`, `tooling-improvement`, `documentation`.

---

## 5. Pre-Flight Checklist Schema

Template file: `docs/runbooks/governance/pre-flight-checklist.md`

**Tier 0/1 checklist** (mandatory):
1. Identify affected ports/interfaces
2. Query service inventory for dependent services (by port/interface match)
3. For each dependent service: note health-check endpoint + expected behavior
4. Document rollback procedure (how to undo the change)
5. Confirm operator availability (solo-operator reality: can you respond to issues?)
6. Define post-change verification plan (which health checks to run, in what order)

**Tier 2 checklist** (lighter):
1. Confirm recent backup exists (Restic snapshot within last N hours)
2. Note affected service's health-check endpoint
3. Have rollback plan (restart service, restore backup)

---

## 6. Entity Relationships

```text
change-risk-taxonomy.json
  └── defines tiers 0-4 with guardrail protocols
        └── referenced by CLAUDE.md guardrail rules
        └── referenced by service-inventory.json risk_tier field

service-inventory.json
  ├── risk_tier → links to taxonomy tier number
  ├── dependencies → links to other services/ports
  ├── health_check → used by post-change verification protocol
  └── config_files → used by pre-flight checklist (what files are affected)

pre-flight-checklist.md
  └── queries service-inventory.json dependencies for impact analysis
  └── references change-risk-taxonomy.json for tier determination

post-change-verification.md
  └── queries service-inventory.json health_check for verification steps
  └── defines rollback trigger on verification failure

incident-postmortem-template.md
  └── follow-on actions reference Vikunja tasks (placeholder format)
  └── root cause chain references dependency data from inventory
```
