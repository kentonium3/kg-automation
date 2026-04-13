# Data Model: Agent Workspace Reconciliation

**Mission**: 028-agent-workspace-reconciliation
**Date**: 2026-04-13

## Entity: Baseline Manifest

**File**: `scripts/openclaw/agents/baseline-manifest.json`
**Purpose**: Post-reconciliation record of all tracked workspace file hashes. Used by the enforcement script as the reference point for drift detection.

```json
{
  "generated_at": "2026-04-13T00:00:00Z",
  "generated_by": "mission-028",
  "agents": {
    "main": {
      "workspace_path": "/data/services/openclaw/data",
      "repo_path": "scripts/openclaw/agents/main",
      "files": {
        "AGENTS.md": {
          "sha256": "bbd2866d407f77aa...",
          "lines": 258,
          "tracked": true,
          "factory_default": false
        },
        "TOOLS.md": {
          "sha256": "78f3e26b8625ea28...",
          "lines": 40,
          "tracked": true,
          "factory_default": true
        }
      }
    }
  }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `generated_at` | ISO 8601 datetime | When the manifest was last generated |
| `generated_by` | string | Mission or script that generated the manifest |
| `agents` | object | Keyed by agent ID from `openclaw.json` |
| `agents.*.workspace_path` | string | Absolute path to workspace on office2 |
| `agents.*.repo_path` | string | Relative path to repo directory (from repo root) |
| `agents.*.files` | object | Keyed by filename (e.g., `AGENTS.md`) |
| `agents.*.files.*.sha256` | string | Full SHA256 hash of the reconciled file |
| `agents.*.files.*.lines` | integer | Line count at reconciliation time |
| `agents.*.files.*.tracked` | boolean | Whether this file is tracked in the repo |
| `agents.*.files.*.factory_default` | boolean | Whether this file currently matches a known factory baseline hash |

### Validation Rules

- Every agent in `openclaw.json` must have an entry in `agents`
- Every workspace file on office2 must have an entry in `files`
- `sha256` must match both the repo file and the office2 file at generation time (zero-drift invariant)
- `tracked: false` is only valid when `factory_default: true` (untracked customized files are a policy violation)

## Entity: Factory Baselines

**File**: `scripts/openclaw/agents/factory-baselines.json`
**Purpose**: Known SHA256 hashes of unmodified OpenClaw factory-default template files. Used to distinguish "never customized" from "customized and potentially drifted."

```json
{
  "openclaw_version": "2026.3.24",
  "baselines": {
    "BOOTSTRAP.md": "c6545993b6e07b97...",
    "TOOLS.md": "78f3e26b8625ea28...",
    "IDENTITY.md": {
      "template_v1": "1379f924cf4b4d6d...",
      "template_v2": "418094e6f9a6478c..."
    }
  }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `openclaw_version` | string | OpenClaw version these baselines were captured from |
| `baselines` | object | Keyed by filename |
| `baselines.*` | string or object | SHA256 hash (string) or version-keyed hashes (object) if multiple template versions exist |

### Notes

- Multiple template versions are possible (e.g., IDENTITY.md has different formats across agent types)
- When OpenClaw upgrades, factory baselines should be re-captured and the manifest version updated
- This file is maintained manually; automation could be added later to extract baselines from OpenClaw's template store

## Entity: Drift Check Config

**File**: `scripts/openclaw/enforcement/drift-check-config.json`
**Purpose**: Configuration for the enforcement script, including agent mapping and notification settings.

```json
{
  "enforcement_mode": "notify",
  "agents": {
    "main": {
      "workspace_path": "/data/services/openclaw/data",
      "repo_path": "scripts/openclaw/agents/main",
      "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
      "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
    }
  },
  "notification": {
    "channel": "whatsapp",
    "openclaw_agent": "main",
    "recipient": "<kent-e164-number>",
    "issue_repo": "kentonium3/kg-automation",
    "issue_labels": ["drift-alert", "area/felix-core"]
  },
  "factory_baselines_path": "../agents/factory-baselines.json",
  "baseline_manifest_path": "../agents/baseline-manifest.json",
  "repo_root": "/home/claude/kg-automation"
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `enforcement_mode` | enum: `self-heal`, `notify` | Controls whether drift triggers auto-remediation or notification only. Set based on R4 research outcome. |
| `agents` | object | Agent-to-workspace mapping (mirrors baseline manifest structure) |
| `notification.channel` | string | Delivery channel for alerts (`whatsapp`) |
| `notification.openclaw_agent` | string | Which OpenClaw agent sends the notification |
| `notification.recipient` | string | E.164 phone number for WhatsApp delivery |
| `notification.issue_repo` | string | GitHub repo for drift-alert issue creation |
| `notification.issue_labels` | array of string | Labels applied to drift-alert issues |
| `factory_baselines_path` | string | Relative path to factory baselines JSON |
| `baseline_manifest_path` | string | Relative path to baseline manifest JSON |
| `repo_root` | string | Absolute path to the repo on office2 |

### State Transitions

```
File lifecycle:
  factory-default (untracked) → customized (detected) → captured-to-repo (tracked) → monitored (enforcement)

Enforcement modes:
  R4 research pending → "notify" (safe default)
  R4 confirms read-only → "self-heal" (auto-deploy repo→office2)
  R4 finds runtime writes → stays "notify" (defer self-heal to follow-up)
```
