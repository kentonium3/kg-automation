---
work_package_id: WP06
title: Architecture + Runbook Updates
dependencies:
- WP04
requirement_refs:
- FR-007
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T026
- T027
- T028
- T029
- T030
- T031
- T032
- T033
history: []
authoritative_surface: docs/design/architecture/
execution_mode: planning_artifact
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/service-dependencies.view.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/credentials-and-secrets.md
- docs/runbooks/sync-driver-ops.md
- docs/INDEX.md
- docs/design/felix-capability-roadmap.md
tags: []
agent: "claude:sonnet:implementer:implementer"
shell_pid: "93285"
---

# WP06 — Architecture + Runbook Updates

## Objective

Update all architecture docs (machine-readable JSON + narrative markdown + view diagrams) and the sync-driver-ops runbook to reflect the full-poll model, project-layer audit semantics, deletion-cleanup algorithm, and URL config plumbing. Mark Epic #507 complete in the capability roadmap.

Per `signal-to-doc-map.json` for `service-added-or-modified`, `data-flow-added-or-modified`, and `runbook-modified` change classes, and the standing architecture-documentation directive in `CLAUDE.md`.

## Context

This is the polish + governance WP that closes the Epic #507 implementation arc. It depends on WP04 so the documentation reflects the actual delivered code, not aspirational behavior.

The architecture documentation has 3 layers (per CLAUDE.md):
- **Machine-readable JSON** is the authoritative record (`data/service-inventory.json`, `data/data-flows.json`)
- **Narrative markdown** provides context and rationale (`service-inventory.md`, `data-flows.md`, `credentials-and-secrets.md`)
- **Diagrams** (Mermaid `.view.md` files) communicate structure (`service-dependencies.view.md`, `data-flows.view.md`)

The runbook (`docs/runbooks/sync-driver-ops.md`) is the operator-facing operational guide. The signal-to-doc-map's `runbook-modified` change class triggers an `INDEX.md` entry update if the runbook's scope or title changed.

## Implementation guidance

### Subtask T026: Update `service-inventory.json`

**Purpose**: register the URL config file in the sync driver's metadata.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`.
2. Locate the entry for `felix-vikunja-sync-driver` (or similar — verify the actual key).
3. Add (or extend) a `config_files` array listing the new URL config file:
   ```json
   "config_files": [
     {
       "path": "/data/services/openclaw/config/vikunja-base-url.txt",
       "purpose": "Vikunja API base URL, single source of truth",
       "mode": "0644",
       "owner": "claude:claude"
     }
   ]
   ```
4. Add `VIKUNJA_BASE_URL` to the documented env vars list, if such a field exists.
5. Validate JSON parses: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"`

**Files**: `docs/design/architecture/data/service-inventory.json`

**Validation**:
- [ ] JSON parses cleanly
- [ ] URL config file is registered under the driver's config_files

### Subtask T027: Update `service-inventory.md` narrative

**Purpose**: describe the URL config dependency in operator-readable prose.

**Steps**:

1. Open `docs/design/architecture/service-inventory.md`.
2. Locate the sync driver section.
3. Add a sentence or short paragraph describing the URL config dependency: the driver and 8 runtime-path consumers (6 #519-migrated touchpoints + 2 retained write paths) read the Vikunja base URL from a shared config file at `/data/services/openclaw/config/vikunja-base-url.txt`, with `VIKUNJA_BASE_URL` env var as a convenience wrapper.

**Files**: `docs/design/architecture/service-inventory.md`

**Validation**:
- [ ] Narrative reflects URL config dependency
- [ ] `python3 tooling/scripts/validate_docs.py` passes

### Subtask T028: Update `service-dependencies.view.md` diagram

**Purpose**: add the new edge (URL config → driver + touchpoints) to the dependency diagram.

**Steps**:

1. Open `docs/design/architecture/service-dependencies.view.md`.
2. The file is a Mermaid diagram. Add a node for "vikunja-base-url.txt config" or similar.
3. Add edges from the config node to "felix-vikunja-sync-driver" and to the cluster of touchpoint consumers (if represented as a single node).
4. Render preview if possible: paste into a Mermaid renderer to verify the diagram is well-formed.

**Files**: `docs/design/architecture/service-dependencies.view.md`

**Validation**:
- [ ] Mermaid syntax valid
- [ ] New edges added without breaking existing layout

### Subtask T029: Update `data-flows.json`

**Purpose**: add the URL config data flow.

**Steps**:

1. Open `docs/design/architecture/data/data-flows.json`.
2. Add a new flow object:
   ```json
   {
     "name": "vikunja-base-url-config",
     "purpose": "Single source of truth for the Vikunja API base URL across the sync driver and runtime-path touchpoints",
     "source": "operator (manual edit)",
     "sink": [
       "felix-vikunja-sync-driver",
       "habits touchpoints (TP-02, TP-03, TP-04, TP-07)",
       "escalation touchpoint (TP-10)",
       "enrichment touchpoint (TP-12)"
     ],
     "format": "single-line UTF-8 text file",
     "location": "/data/services/openclaw/config/vikunja-base-url.txt",
     "added_by": "#520-mission-c",
     "added_at": "2026-06-05"
   }
   ```
3. Validate JSON parses.

**Files**: `docs/design/architecture/data/data-flows.json`

**Validation**:
- [ ] JSON parses cleanly
- [ ] New flow object registered

### Subtask T030: Update `data-flows.md` + `data-flows.view.md`

**Purpose**: narrative + diagram for the new flow.

**Steps**:

1. Open `docs/design/architecture/data-flows.md`. Add a section or paragraph describing the URL config flow, mirroring the JSON content.
2. Open `docs/design/architecture/data-flows.view.md`. Add diagram nodes + edges for the new flow.

**Files**: `docs/design/architecture/data-flows.md` + `docs/design/architecture/data-flows.view.md`

**Validation**:
- [ ] Narrative is operator-readable
- [ ] Diagram syntax valid

### Subtask T031: Update `credentials-and-secrets.md` storage inventory

**Purpose**: add the URL config file to the inventory of storage mechanisms even though it's not a secret.

**Steps**:

1. Open `docs/design/architecture/credentials-and-secrets.md`.
2. Locate the Storage Mechanisms section (heading like `## Storage Mechanisms`).
3. Add a row or paragraph for the URL config file. Note explicitly that it is NOT a secret — it lives in the same directory tree (`/data/services/openclaw/`) for convenience but has mode 0644 (world-readable on the host).
4. Link to `docs/runbooks/credential-rotation-ops.md` if the URL config file rotation procedure is co-documented there (it isn't per #522 — URL config rotation is operator-driven and not credential-rotation). Just note this in a single sentence.

**Files**: `docs/design/architecture/credentials-and-secrets.md`

**Validation**:
- [ ] URL config file appears in storage inventory
- [ ] Explicit note that it's not a secret
- [ ] `validate_docs.py` passes

### Subtask T032: Rewrite `docs/runbooks/sync-driver-ops.md`

**Purpose**: operator-facing rewrite reflecting the full-poll model + project-layer audit + deletion cleanup + URL config.

**Steps**:

1. Read the existing `docs/runbooks/sync-driver-ops.md` to understand its current structure.
2. Replace the "How the cycle works" section (or equivalent) with the full-poll description:
   - 6-phase pipeline (preamble → fetch → diff → classify → emit → update → complete) plus Phase 5b (deletion-cleanup) between Phase 5 and Phase 6
   - `GET /tasks/all` + `GET /projects` per cycle (no `updated_since`)
   - 3-way set diff for both layers
   - LayerSummary in last-tick.json (not layer_pointers)
3. Add a "Project layer" section describing the audit/discovery role (no downstream consumer changes — future missions may consume project state).
4. Add a "Deletion handling" section describing the three-action cleanup (history-log → schedule.yaml → cache via Phase 6).
5. Add a "URL config" section describing:
   - The canonical file at `/data/services/openclaw/config/vikunja-base-url.txt`
   - The `VIKUNJA_BASE_URL` env var
   - How to change the URL (edit the file; restart isn't required because each cycle re-reads at start)
   - Sample troubleshooting (the helper raises `VikunjaConfigError` if both sources are missing)
6. Update "Troubleshooting" section to include:
   - "Cycle aborts with `auth_failure`" → check vikunja-api token
   - "Cycle aborts with `empty_response_when_cache_nonzero`" → Vikunja may be filtering tasks (e.g., share grants revoked); investigate
   - "Cycle aborts with `vikunja_5xx`" → check Vikunja service health
7. Remove any reference to `updated_since`, incremental polling, `layer_pointers.before/after`, N=3 deletion confirmation, or just-in-time per-project fetching.

**Files**: `docs/runbooks/sync-driver-ops.md` (substantial rewrite)

**Validation**:
- [ ] All operator-facing content reflects the full-poll model
- [ ] No reference to incremental polling, N-cycle confirmation, or `updated_since` remains
- [ ] `validate_docs.py` passes

### Subtask T033: Update `INDEX.md` + `felix-capability-roadmap.md`

**Purpose**: register the runbook scope expansion in INDEX, mark Epic #507 complete in the roadmap.

**Steps**:

1. Open `docs/INDEX.md`. Locate the entry for `sync-driver-ops.md`. If the entry description doesn't already mention the full-poll model + project layer + deletion handling + URL config, update it to reflect the new scope. Keep the description concise (one line).
2. Open `docs/design/felix-capability-roadmap.md`. Locate the entry for Epic #507 (or the area of the roadmap covering Felix-Vikunja bi-directional sync). Mark the Epic as complete (per the roadmap's existing status convention — could be a checkmark, a "completed" tag, or a date stamp).
3. Do NOT reorganize the roadmap. Make the smallest possible targeted change.

**Files**: `docs/INDEX.md` + `docs/design/felix-capability-roadmap.md`

**Validation**:
- [ ] INDEX entry reflects updated scope of sync-driver-ops.md (if changed)
- [ ] Capability roadmap marks Epic #507 complete
- [ ] `validate_docs.py` passes

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json` (depends on WP04). The lane's base inherits WP04's changes.

## Test Strategy

`python3 tooling/scripts/validate_docs.py` is the structural validator. Manual narrative review by the reviewer covers operator-comprehensibility.

## Definition of Done

- [ ] All 10 owned files are updated
- [ ] JSON files parse cleanly (run `python3 -c "import json; json.load(...)"` on each)
- [ ] `validate_docs.py` passes
- [ ] Mermaid diagrams render correctly
- [ ] `sync-driver-ops.md` describes the full-poll model end-to-end (no incremental references)
- [ ] Epic #507 is marked complete in the capability roadmap
- [ ] No changes to files outside `owned_files`

## Risks

- **`validate_docs.py` drift**: if the validator checks portal/runbook-filter coherence, the runbook scope change may require running `python3 tooling/scripts/build_runbook_filter.py --write` (the same pattern as #518's WP06). Check this before committing.
- **Mermaid syntax**: edge additions can break the layout. Render locally to verify.
- **JSON schema validation**: `service-inventory.json` and `data-flows.json` have implicit schemas. Add fields conservatively and match existing patterns.
- **Roadmap edit scope**: don't reorganize. Make the smallest possible change to mark Epic #507 complete.

## Reviewer Guidance

The reviewer should validate:

1. **All 3 doc layers updated for each change class** — JSON + markdown + diagram for `service-inventory` and `data-flows`.
2. **`validate_docs.py` passes**.
3. **`sync-driver-ops.md` matches the actual delivered behavior** (cross-check against `contracts/cycle-pipeline.md`).
4. **No reference to incremental polling, updated_since, N-cycle confirmation, or LayerPointerSnapshot** remains in any doc.
5. **Capability roadmap edit is targeted** — no broader reorganization.
6. **`build_runbook_filter.py --write` was run** if the runbook frontmatter or audience changed.
7. **No leakage into files outside `owned_files`**.

## Implementation command

```bash
spec-kitty agent action implement WP06 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP06 approval

This is the final WP. After approval:
- `/spec-kitty.merge` (or the auto-drive equivalent) merges the mission to `main`.
- Post-merge deploy on office2: git pull + create the URL config file before the next cycle.
- File the FR-010 follow-up issue for one-off scripts migration.
- Run the downstream-leftovers sweep per Kent's 2026-06-05 request.
- Update the Epic #507 GitHub issue with the merge commit hash and close it.

## Activity Log

- 2026-06-05T19:57:58Z – claude:sonnet:implementer:implementer – shell_pid=93285 – Started implementation via action command
- 2026-06-05T20:43:37Z – claude:sonnet:implementer:implementer – shell_pid=93285 – Ready for review: T026-T033 complete. 10 doc files updated per signal-to-doc-map. sync-driver-ops.md rewritten to v2.0 (7-phase pipeline, project layer audit, Phase 5b deletion cleanup, URL config). INDEX + capability roadmap updated. Epic #507 marked complete. validate_docs.py OK.
