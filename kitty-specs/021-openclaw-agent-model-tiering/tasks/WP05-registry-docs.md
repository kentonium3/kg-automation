---
work_package_id: WP05
title: Registry and Documentation Update
dependencies: [WP04]
requirement_refs:
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Branch from WP04 or main — depends on whether WP04 produced repo changes
subtasks: [T017, T018, T019, T020, T021]
history:
- date: '2026-04-09T17:18:21Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/constitution/agent-registry.json
- docs/constitution/AGENT-REGISTRY.md
- docs/design/architecture/service-inventory.md
- docs/runbooks/openclaw-agent-setup.md
---

# WP05: Registry and Documentation Update

## Objective

Update the agent registry, architecture documentation, and agent setup runbook to reflect the deployed model tier assignments. Calculate and document the monthly cost target based on actual validation data.

## Context

- Agent registry: `docs/constitution/agent-registry.json` (machine-readable) + `docs/constitution/AGENT-REGISTRY.md` (narrative)
- Service inventory: `docs/design/architecture/service-inventory.md`
- Agent setup runbook: `docs/runbooks/openclaw-agent-setup.md`
- Validation data: Token usage from WP02/WP03 validation runs
- Final model assignments: From WP04 deployment
- Per constitution Directive 5: JSON is authoritative; markdown is the narrative view

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP05 --base WP04`

---

## Subtask T017: Add Model Fields to agent-registry.json

**Purpose**: Add model assignment, policy, and rationale as new fields in the machine-readable agent registry.

**Steps**:
1. Read current `docs/constitution/agent-registry.json`
2. For each agent entry, add three new fields:
   - `model`: The assigned model string (e.g., `"anthropic/claude-haiku-4-5"` or `"anthropic/claude-sonnet-4-6"`)
   - `model_policy`: Either `"pinned"` (must not be changed without explicit justification) or `"optimizable"` (eligible for future cost optimization)
   - `model_rationale`: Brief explanation of why this model was assigned (e.g., "Routine classification task — validated on Haiku 2026-04-09" or "Complex trend reasoning — Haiku validation failed for weekly review")
3. Use the final model assignments from WP04 deployment
4. For the `main` agent: Note that it's not in the registry — it may need to be added, or document its model assignment in a comment/note

**Example entry update**:
```json
"felix-admin-capture": {
  "team": "SuperAdmin (B)",
  "scope": "Obsidian inbox processing...",
  "autonomy_level": "assisted",
  "model": "anthropic/claude-haiku-4-5",
  "model_policy": "optimizable",
  "model_rationale": "Routine classification — validated on Haiku 2026-04-09, equivalent routing accuracy",
  ...
}
```

5. Update the `version` and `updated` fields at the top of the JSON
6. Set `updated_by` to reference this feature (e.g., `"021-openclaw-agent-model-tiering"`)

**Validation**:
- [ ] Every agent has `model`, `model_policy`, `model_rationale` fields
- [ ] Values match the deployed configuration from WP04
- [ ] JSON is syntactically valid
- [ ] Version and updated fields current

---

## Subtask T018: Update AGENT-REGISTRY.md

**Purpose**: Update the narrative markdown to match the JSON — add model tier information visible to human readers.

**Steps**:
1. Read current `docs/constitution/AGENT-REGISTRY.md`
2. Add a "Model" column to the agent table showing:
   - Assigned model (short name: "Haiku" or "Sonnet")
   - Policy indicator: "(pinned)" or "(optimizable)"
3. Add a "Model Assignment Policy" section documenting:
   - Default for new agents: Haiku (cheapest viable)
   - When to use Sonnet: complex reasoning, trend analysis, orchestration
   - How to change a tier: requires validation on representative inputs
   - Where to find validation evidence: mission directory or issue comments
4. Ensure the markdown matches the JSON (Directive 5 compliance)

**Validation**:
- [ ] Model column added to agent table
- [ ] Model assignment policy section added
- [ ] Markdown matches JSON values
- [ ] No existing content lost

---

## Subtask T019: Update service-inventory.md

**Purpose**: Note the tiered model configuration in the OpenClaw service entry.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`
2. Find the OpenClaw entry
3. Add a note about tiered model configuration:
   - Global default: Haiku
   - Agents use per-agent model override
   - Reference the agent registry for per-agent assignments
4. Keep the update minimal — the registry has the detailed per-agent data

**Validation**:
- [ ] OpenClaw entry updated with tiered model note
- [ ] Reference to agent registry included

---

## Subtask T020: Update Agent Setup Runbook

**Purpose**: Add model tier selection as a required step in the agent registration process.

**Steps**:
1. Read `docs/runbooks/openclaw-agent-setup.md`
2. Add a "Model Tier Assignment" section to the registration checklist:
   - New agents default to Haiku unless explicitly justified
   - Document the model selection in the agent registry entry
   - Include `model`, `model_policy`, and `model_rationale` in registration
   - If Sonnet is needed: document why and mark as "pinned"
3. Add a note about validation requirements:
   - Before changing an existing agent's model tier, run validation with representative inputs
   - Document validation results in the issue or mission that drove the change
4. Reference the model assignment policy in AGENT-REGISTRY.md

**Validation**:
- [ ] Model tier selection added to registration checklist
- [ ] Default-to-Haiku policy documented
- [ ] Validation requirement for tier changes documented

---

## Subtask T021: Calculate and Document Monthly Cost Target

**Purpose**: Establish a documented monthly API spend target based on actual token usage data from validation runs.

**Steps**:
1. Collect token usage data from WP02/WP03 validation runs:
   - Input tokens and output tokens per Haiku run
   - Compare to equivalent Sonnet token counts (from session logs)
2. Calculate per-agent monthly cost:
   - For each agent: (tokens per run) × (runs per month) × (cost per token)
   - Haiku pricing: ~$0.25/M input, ~$1.25/M output (verify current pricing)
   - Sonnet pricing: ~$3/M input, ~$15/M output (verify current pricing)
3. Sum to get projected monthly total
4. Document in the mission directory or as a comment on #135:

   | Agent | Model | Runs/Month | Est. Tokens/Run | Est. Monthly Cost |
   |---|---|---|---|---|
   | main | Sonnet | varies | varies | $X |
   | felix-admin-capture | [result] | ~240 | [from validation] | $X |
   | felix-admin-habits | [result] | ~31 | [from validation] | $X |
   | felix-admin-escalation | [result] | ~30 | [from validation] | $X |
   | felix-admin-tasker | Sonnet | varies | varies | $X |
   | **Total** | | | | **$X/month** |

5. Compare to the baseline (~$115/month all-Sonnet)
6. Verify the target meets NFR-001 (at least 60% reduction)
7. Include headroom for planned fleet growth (#131 escalation delegation)

**Validation**:
- [ ] Cost projection based on actual validation token counts (not estimates)
- [ ] Per-agent breakdown documented
- [ ] Total meets 60% reduction target (NFR-001)
- [ ] Headroom for fleet growth noted

---

## Definition of Done

- [ ] agent-registry.json updated with model fields for all agents
- [ ] AGENT-REGISTRY.md matches JSON with model tier column
- [ ] service-inventory.md OpenClaw entry updated
- [ ] Agent setup runbook includes model tier registration requirement
- [ ] Monthly cost target calculated and documented
- [ ] All documentation committed to repo

## Risks

- **Token usage data unavailable from validation runs**: Use session log token counts from Sonnet runs as proxy, apply Haiku pricing; note this is an estimate
- **Pricing has changed**: Verify current Anthropic API pricing before calculating
- **`main` agent not in registry**: May need to add it or document separately

## Reviewer Guidance

- JSON must be valid — parse it to verify
- Markdown must match JSON (Directive 5)
- Cost projection should use real data from validation, not theoretical estimates
- Check that the runbook update is actionable — a new agent registration should clearly require model selection
