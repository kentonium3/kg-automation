---
work_package_id: WP08
title: Architecture data updates
dependencies: []
requirement_refs:
- FR-013
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T037
- T038
- T039
- T040
- T041
agent: claude
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: docs/design/architecture/data/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/audited-surfaces.json
- docs/design/architecture/data/signal-to-doc-map.json
- docs/design/architecture/data/mutation-surfaces.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Update the canonical machine-readable architecture data so the deploy pipeline is discoverable by automated tooling and so the signal-to-doc map can route deploy-related change classes to the right docs.

## Context

`docs/design/architecture/data/*.json` are authoritative for operational state per the Felix Constitution Directive 5. Markdown narrative documents (where present) follow the JSON. Per `kg-automation/CLAUDE.md` standing requirement: any feature that deploys, modifies, or registers a service MUST update these files as part of the same PR.

**Critical for the doctrine layer**: `signal-to-doc-map.json` currently has **zero** deploy-related entries. That's why a future agent's specify/plan can't automatically discover the deploy discipline when consulting the map. WP08 adds the missing entries.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T037 — `service-inventory.json`

Add a `felix-deployer` entry. Use the existing `felix-doc-auditor` entry as the canonical shape (per memory `reference_felix_doc_auditor_ops`). Fields to set:

- `name`: `felix-deployer`
- `description`: `"Pull-based deploy applier — reads deploys/queued/, applies via scripts/deploy/lib/, dispatches WhatsApp DM on failure. systemd --user Type=oneshot, 5-min timer."`
- `host`: `office2`
- `systemd_unit`: `felix-deployer.timer`
- `account`: `claude`
- `schedule`: `every 5 minutes`
- `state_root`: `/data/services/felix-deployer/`
- `log_root`: `/data/services/felix-deployer/logs/`
- `health_signal`: `/data/services/felix-deployer/state/last-tick.json`
- `dependent_services`: `["openclaw"]`
- `runbook`: `docs/runbooks/deploy/discipline.md`
- `last_updated_by`: `136`

If the JSON has a top-level `updated_by` / `last_updated`, update those too.

### T038 — `data-flows.json`

Add a flow:

- `name`: `github-to-office2-deploy-pull`
- `source`: `github.com/kentonium3/kg-automation (main branch)`
- `destination`: `office2 (claude user, /home/claude/kg-automation)`
- `transport`: `git pull (HTTPS via Tailscale exit node OR public internet)`
- `frequency`: `every 5 minutes (driven by felix-deployer.timer)`
- `payload`: `manifests under deploys/queued/, deploy scripts under scripts/deploy/, library under scripts/deploy/lib/`
- `triggers`: `automatic (systemd timer)`
- `description`: `"The applier pulls from main on every tick, scans deploys/queued/ for new manifests, and applies them through lib.apply.dry_run_then_apply_gate."`
- `last_updated_by`: `136`

Mirror the existing flow entries' shape.

### T039 — `audited-surfaces.json`

Add two paths to the audited surfaces list:

- `deploys/` (new manifest queue + applied + failed dirs)
- `scripts/deploy/lib/` (Python deploy library)

The bootstrap wrapper at `scripts/deploy/deploy-felix-deployer-bootstrap.sh` and the applier at `scripts/deploy/felix-deployer/` may already be covered by an existing `scripts/deploy/` entry — check first; only add if not.

If a `rationale` field exists per entry, set: `"Deploy script and manifest changes can affect every deployed service; rebaseline required on every change."`

### T040 — `signal-to-doc-map.json`

This is the most consequential subtask for agentic visibility. Add 3 new mapping entries. The structure (per session research) uses a `mappings` array with `id`, `match`, `doc_targets`, `rationale`. Existing entries use `match.source: audit.sh` with `baseline_name`. The new entries use `match.source: mission-architecture-impact` per the discovery aid noted in CLAUDE.md.

```json
{
  "id": "deploy-manifest-added",
  "match": {
    "source": "mission-architecture-impact",
    "change_class": "deploy-manifest-added"
  },
  "doc_targets": [
    "docs/runbooks/deploy/discipline.md",
    "scripts/deploy/lib/README.md"
  ],
  "rationale": "New deploys/queued/<name>.yaml requires familiarity with the manifest schema and library API. Surfaced during specify/plan when the mission needs an office2 deploy.",
  "issue_labels": ["P3-candidate", "spec: brief", "area/infrastructure"]
}
```

```json
{
  "id": "office2-service-deployment",
  "match": {
    "source": "mission-architecture-impact",
    "change_class": "office2-service-deployment"
  },
  "doc_targets": [
    "docs/runbooks/deploy/discipline.md",
    "docs/design/architecture/data/service-inventory.json"
  ],
  "rationale": "Any new or modified office2 service should be planned against the discipline runbook and recorded in service-inventory.json.",
  "issue_labels": ["P3-candidate", "spec: brief", "area/infrastructure"]
}
```

```json
{
  "id": "deploy-library-modified",
  "match": {
    "source": "mission-architecture-impact",
    "change_class": "deploy-library-modified"
  },
  "doc_targets": [
    "scripts/deploy/lib/README.md",
    "docs/runbooks/deploy/discipline.md"
  ],
  "rationale": "Changes to scripts/deploy/lib/ affect every downstream deploy. Library API contract (kitty-specs/<slug>/contracts/deploy-library-api.md) should be reviewed.",
  "issue_labels": ["P3-candidate", "spec: brief", "area/infrastructure"]
}
```

Append to the existing `mappings` array. Update top-level `last_updated`, `updated_by`.

### T041 — `mutation-surfaces.json`

Add an entry for the deployer's mutation surfaces:

- `actor`: `felix-deployer`
- `mutates`: list of paths the applier writes — `deploys/queued/` (moves out), `deploys/applied/` (writes in), `deploys/failed/` (writes), `/data/services/felix-deployer/logs/`, `/data/services/felix-deployer/state/last-tick.json`
- `frequency`: `5 minutes (per tick)`
- `last_updated_by`: `136`

Mirror the shape of existing entries.

## Test strategy

- All 5 JSON files parse: `python3 -c "import json; [json.load(open(f)) for f in 'docs/design/architecture/data/service-inventory.json docs/design/architecture/data/data-flows.json docs/design/architecture/data/audited-surfaces.json docs/design/architecture/data/signal-to-doc-map.json docs/design/architecture/data/mutation-surfaces.json'.split()]"`
- Manual cross-check: each entry's fields match the existing schema shape for that file
- signal-to-doc-map: 3 new entries with `match.source = mission-architecture-impact` exist; doc_targets resolve

## Definition of Done

- All 5 files modified
- All JSON well-formed
- `felix-deployer` entry in service-inventory mirrors `felix-doc-auditor` shape
- 3 new signal-to-doc-map entries cover the agreed change-classes
- `audited-surfaces.json` includes `deploys/` and `scripts/deploy/lib/` (or confirmed already covered)
- All entries set `last_updated_by: 136` (or the file-wide equivalent)
- Markdown views, if present, match the JSON

## Risks

- **JSON schema drift**: each file has its own implicit schema (no formal JSON Schema for these). Read 2-3 existing entries before adding new ones to match the shape exactly.
- **signal-to-doc-map mapping shape**: the existing entries are all `match.source: audit.sh` driven by drift detection. The new entries use `match.source: mission-architecture-impact` per CLAUDE.md's discovery-aid guidance. This is a NEW source value; confirm there's no schema-validation step that would reject it.
- **Concurrent JSON edits**: these files are edited by many missions. If a parallel mission also modifies them, expect merge conflicts. Resolve at merge time per standard practice.
- **`updated_by` field naming**: some files use `updated_by`, some `last_updated_by`, some `last_updated`. Read each file's existing top-level fields first.

## Reviewer guidance

1. Parse each JSON file: `for f in <5 files>; do python3 -c "import json; json.load(open('$f'))" || echo "$f INVALID"; done`
2. Confirm `felix-deployer` service entry mirrors `felix-doc-auditor`'s field set.
3. Confirm the 3 signal-to-doc-map entries are unique IDs (no `id` collision with existing entries).
4. Confirm each new signal-to-doc-map `doc_targets` path exists in the repo (will be enforced by WP06's cross-link test for the discipline runbook target).
5. Spot-check `updated_by` field is consistently set to `136`.
