# Implementation Plan: Felix exec host=gateway directive

**Branch**: `fix/felix-exec-host-gateway-directive` (coordination branch `kitty/mission-felix-exec-host-gateway-directive-01KVBRVY`) | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/felix-exec-host-gateway-directive-01KVBRVY/spec.md`

## Summary

Add an identical, explicit hard-rule section to each of the four Felix sub-agent
`AGENTS.md` standing-orders files instructing the agent to always use
`host=gateway` for the OpenClaw `exec` tool and never `host=node`. This removes
the model's non-deterministic host selection that produces false-positive
cron-failure alerts (issue #603). The change is prompt content only; it deploys
to office2 automatically via the existing `agent-prompt-sync.service` and
auto-rebaselines the `openclaw-config.txt` security baseline via the #618
felix-deployer observe→reconcile path.

## Technical Context

**Language/Version**: Markdown — OpenClaw `AGENTS.md` standing-orders prompt files (no programming language; no build step)
**Primary Dependencies**: OpenClaw agent runtime (`exec` tool with `host=gateway`/`host=node`); `agent-prompt-sync.service` (#567) deploy path (`scripts/openclaw/deploy/deploy_agent_prompts.py`)
**Storage**: N/A (no data store touched)
**Testing**: Static verification (each of the 4 files contains the directive; identical wording) + post-deploy observational check (7-day `journalctl` window with zero `exec host=node requires a paired node` errors). No automated unit tests apply to prompt content.
**Target Platform**: office2 (Ubuntu 24.04 LTS) OpenClaw gateway; agents run as the `claude`/gateway user
**Project Type**: single (config/prompt edit — no source tree change)
**Performance Goals**: N/A
**Constraints**: Tier 3 (logic/workflow — agent prompts). `AGENTS.md` is an audited surface (`affected_baselines: openclaw-config.txt`) → rebaseline obligation per #557, satisfied automatically by #618 on merge.
**Scale/Scope**: 4 files (`felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`), one short added section each (~6–8 lines).

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Governance context (compact): software-dev-default; directives DIRECTIVE_001, DIRECTIVE_003, DIRECTIVE_010, DIRECTIVE_024.

- **Directive 6 (deterministic vs stochastic split)**: The fix itself is a static prompt directive (deterministic content). No helper-script extraction applies — there is no runtime computation, only a standing instruction that constrains the agent's tool-call choice. Verification (grep the 4 files; observe the journal) is deterministic and needs no new script. **Pass.**
- **Active-surface hygiene**: The change reduces noise (false-positive alerts) without adding surfaces. **Pass.**
- **Audited-surface / change-control**: Tier 3; `AGENTS.md` audited surface; rebaseline handled by automation (#618). Recorded as a constraint (C-001). **Pass.**
- No charter conflicts identified.

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-exec-host-gateway-directive-01KVBRVY/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (no data entities — documented)
├── quickstart.md        # Phase 1 output (verification recipe)
├── contracts/           # Phase 1 output (no API contracts — documented)
└── tasks.md             # /spec-kitty.tasks output (NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/
├── felix-admin-capture/AGENTS.md      # add exec-host hard-rule section
├── felix-admin-habits/AGENTS.md       # add exec-host hard-rule section
├── felix-admin-tasker/AGENTS.md       # add exec-host hard-rule section
└── felix-admin-escalation/AGENTS.md   # add exec-host hard-rule section

scripts/openclaw/deploy/deploy_agent_prompts.py   # existing auto-sync deployer (unchanged; not modified)
docs/design/architecture/data/audited-surfaces.json  # existing registry (unchanged; confirms deploy_path + affected_baselines)
```

**Structure Decision**: No new source structure. The change edits four existing
prompt files under `scripts/openclaw/agents/<agent>/AGENTS.md`. All four share a
consistent top structure (`## Governance` → `## Authority` → `## Message
identity` → `## Output discipline`); the new section is inserted at the same
anchor (immediately after `## Message identity`, before `## Output discipline`)
in each file so placement and wording are identical. No `deploys/queued/`
manifest is required because agent prompts deploy through the dedicated
`agent-prompt-sync.service`, not the felix-deployer manifest pipeline.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks` translates
> these into executable WPs.

### IC-01 — Add the exec-host directive to the four Felix sub-agent AGENTS.md files

- **Purpose**: Constrain every Felix sub-agent to `exec host=gateway` so the model never selects the unpaired `host=node`, eliminating false-positive cron-failure alerts.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-005, NFR-001.
- **Affected surfaces**: `scripts/openclaw/agents/{felix-admin-capture,felix-admin-habits,felix-admin-tasker,felix-admin-escalation}/AGENTS.md`.
- **Sequencing/depends-on**: none.
- **Risks**: Wording must be an unambiguous hard rule (not a soft preference) and identical across all four; placement at the shared anchor keeps the four consistent. Must not disturb existing content (FR-005). Low risk — additive, single-section edit.

### IC-02 — Deploy and rebaseline (operational follow-through, post-merge)

- **Purpose**: Get the edited prompts onto office2 and reset the affected security baseline so the change does not read as drift.
- **Relevant requirements**: FR-004, C-001, C-004, SC-002, SC-004.
- **Affected surfaces**: office2 `agent-prompt-sync.service` (auto, no code change); `openclaw-config.txt` baseline (auto-rebaseline via #618).
- **Sequencing/depends-on**: IC-01 merged.
- **Risks**: Deploy and rebaseline are both automated; the only residual risk is the automation not firing — covered by the 7-day observational window (NFR-002, SC-003) and the standard felix-deployer failure alert. This concern is verification/observation, not new code, so `/spec-kitty.tasks` may fold it into the same WP as a post-merge checklist rather than a separate executable WP.
