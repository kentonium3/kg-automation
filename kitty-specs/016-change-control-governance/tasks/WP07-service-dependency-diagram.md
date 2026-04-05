---
work_package_id: WP07
title: Service Dependency Diagram
dependencies:
- WP02
requirement_refs:
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP02
base_commit: f758ab83480cad22de0facb7565ec4298e890500
created_at: '2026-04-05T23:41:33.472814+00:00'
subtasks:
- T032
- T033
- T034
phase: Phase 2 - Documentation
assignee: ''
agent: "claude"
shell_pid: "62497"
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/service-dependencies.view.md
execution_mode: code_change
owned_files:
- docs/design/architecture/service-dependencies.view.md
---

# Work Package Prompt: WP07 — Service Dependency Diagram

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP02.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Create a Mermaid service dependency diagram showing all 11 office2 services, their inter-service dependencies, risk tiers, and the critical port 443 chain.

**Success criteria**:

- [ ] `docs/design/architecture/service-dependencies.view.md` exists with correct frontmatter.
- [ ] Mermaid diagram uses `graph LR` directive with subgraphs grouped by service category.
- [ ] All 11 office2 services present as nodes.
- [ ] Dependency edges drawn from enriched `service-inventory.json` data.
- [ ] Edges labeled with dependency type/port.
- [ ] Risk tiers annotated on each node.
- [ ] Critical chain port 443 -> tailscale-serve -> vikunja is prominently visible.

## Context & Constraints

This WP depends on WP02 (enriched service-inventory.json with dependency data). The diagram is a rendered view of machine-readable data, following the existing pattern of `.view.md` files in the architecture directory (e.g., `data-flows.view.md`, `physical-topology.view.md`).

**Constraints**:

- Diagram must be consistent with machine-readable sources (service-inventory.json).
- Follow existing `.view.md` frontmatter pattern.
- Mermaid syntax must render correctly in GitHub and Obsidian.
- Service categories for subgraph grouping should reflect logical function, not alphabetical order.

**Reference documents**:

- `docs/design/architecture/data/service-inventory.json` (source data, enriched by WP02)
- `docs/design/architecture/data-flows.view.md` (pattern for .view.md files)
- `docs/design/architecture/physical-topology.view.md` (pattern for .view.md files)
- `kitty-specs/016-change-control-governance/plan.md`
- `kitty-specs/016-change-control-governance/data-model.md`

## Subtasks & Detailed Guidance

### Subtask T032 — Create service-dependencies.view.md with frontmatter

- **Purpose**: Create the file skeleton matching existing .view.md pattern.
- **Steps**:
  1. Examine existing `.view.md` files for frontmatter pattern.
  2. Create `docs/design/architecture/service-dependencies.view.md` with frontmatter:

     ```yaml
     ---
     title: "Service Dependencies (Rendered)"
     doc_type: guide
     level: reference
     status: approved
     audience: agents_and_humans
     owners: [kgale]
     last_validated: 2026-04-05
     version: "1.0"
     ---
     ```

  3. Add H1 "Service Dependencies" and a brief intro explaining this is a rendered view of service-inventory.json dependency data.
- **Files**: `docs/design/architecture/service-dependencies.view.md` (new)
- **Parallel?**: No — blocks T033 and T034.
- **Notes**: Match frontmatter fields to existing .view.md files. If existing files use different fields, follow the established pattern.

### Subtask T033 — Write Mermaid dependency graph

- **Purpose**: Render all 11 services and their dependency relationships as a Mermaid diagram.
- **Steps**:
  1. Read enriched `service-inventory.json` for the full service list and dependency data.
  2. Write a Mermaid code block using `graph LR` directive.
  3. Create subgraphs to group services by category. Suggested groupings:
     - **Core Services**: vikunja, openclaw (primary application services)
     - **Agent Services**: felix-agent, inbox-processor, habits-agent, task-intelligence-agent, obsidian-sync (agent-operated services)
     - **Infrastructure**: tailscale, tailscale-serve, ufw, docker (platform/networking)
  4. Define each service as a node.
  5. Draw dependency edges from the JSON dependency data.
  6. Label each edge with the dependency type and/or port number.
- **Files**: `docs/design/architecture/service-dependencies.view.md`
- **Parallel?**: No — depends on T032.
- **Notes**: Adjust subgraph groupings if the actual service data suggests a different logical grouping. The goal is readability.

### Subtask T034 — Add risk tier annotations and highlight critical chain

- **Purpose**: Make risk tiers visible on the diagram and ensure the port 443 chain stands out.
- **Steps**:
  1. Annotate each node with its risk_tier (e.g., `vikunja\nTier 2` or use Mermaid styling/color coding).
  2. Ensure the critical chain `port 443 -> tailscale-serve -> vikunja` is prominently visible:
     - Use thick edges, different color, or explicit labeling to highlight this path.
     - Consider adding a comment or note in the Mermaid source marking it as the critical external access chain.
  3. Verify all 11 services have risk tier annotations.
  4. Verify the diagram renders correctly in a Mermaid preview.
- **Files**: `docs/design/architecture/service-dependencies.view.md`
- **Parallel?**: No — depends on T033.
- **Notes**: If Mermaid styling limitations prevent color-coding, use text annotations instead. Readability takes priority over visual complexity.

## Test Strategy

N/A — governance feature, no automated tests. Manual validation per quickstart.md.

**Manual validation**:

- Diagram renders in GitHub Markdown preview.
- All 11 services present as nodes.
- Port 443 chain visible and highlighted.
- Risk tiers shown on all nodes.
- Edges match service-inventory.json dependency data.

## Risks & Mitigations

- **Risk**: WP02 dependency data incomplete or not yet available. **Mitigation**: WP02 is a hard dependency; do not start until WP02 is complete.
- **Risk**: Mermaid rendering differences between GitHub and Obsidian. **Mitigation**: Use standard Mermaid syntax; avoid advanced features with inconsistent support.
- **Risk**: Diagram too complex to read with 11 nodes + edges + annotations. **Mitigation**: Use subgraphs for grouping; keep edge labels concise.

## Integration Verification

- [ ] `docs/design/architecture/service-dependencies.view.md` exists with valid frontmatter.
- [ ] Mermaid diagram uses `graph LR` with subgraphs.
- [ ] All 11 office2 services present as nodes.
- [ ] Dependency edges drawn with type/port labels.
- [ ] Risk tiers annotated on every node.
- [ ] Port 443 -> tailscale-serve -> vikunja chain prominently visible.
- [ ] Diagram renders correctly in GitHub preview.

## Review Guidance

- **Key checkpoints**: Diagram is readable. All 11 services present. Port 443 chain is visually prominent. Risk tiers are shown. Edges match JSON source data.
- **Before approving**: Render the Mermaid diagram in a preview tool. Verify all 11 services are visible and the critical chain stands out.

## Definition of Done

- `docs/design/architecture/service-dependencies.view.md` committed with complete Mermaid dependency diagram.
- All 11 services shown with risk tiers and dependency edges.
- Critical port 443 chain prominently visible.

## Activity Log

- 2026-04-05T23:46:50Z – unknown – shell_pid=61151 – Mermaid diagram created with all 11 services
- 2026-04-05T23:46:55Z – claude – shell_pid=62497 – Started review via workflow command
