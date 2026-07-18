---
work_package_id: WP05
title: Agent prompt edits + deploy docs (capture)
dependencies:
- WP03
requirement_refs:
- FR-001
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
agent: "claude:sonnet:curator-carla:implementer"
shell_pid: "86970"
shell_pid_created_at: "1784414848.66806"
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md
- docs/runbooks/inbox-ops.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

Adopt its identity, governance scope, and boundaries before reading further.

## Objective

Wire the deployed capture agent to the new behavior: (1) at add-time, persist the
eligibility signal + resolved date into the pending record; (2) at tick-time, invoke
the new deterministic sweep-finalize path instead of the bare `sweep`. Document the
new command. Deploys via `agent-prompt-sync` (no manifest; no rebaseline — agent
AGENTS.md is not a hashed audited surface).

## Context (read `research.md` §4/§5, `spec.md` FR-001/C-003/C-007)

- **Read [[reference_felix_output_discipline_pattern]] and the openclaw-agent-setup
  runbook conventions before editing any AGENTS.md.** Preserve the agent's existing
  output-discipline rules and step structure.
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`:
  - **Step 3c** (~L147) — the calendar clarification flow — composes
    `handle_clarification_state add --note-filename <name> --partial-payload <json>`.
  - **Step 1a** (~L90) — runs `handle_clarification_state sweep` each tick.
- Deployed via `agent-prompt-sync` to `/data/services/openclaw/<deploy-dir>/`
  (verify the deploy dir via `find`, agent slug ≠ deploy dir —
  [[reference_office2_agent_deploy_paths]]).
- **Rebaseline: not required** — record in the merge commit:
  `Rebaseline: not required — agent AGENTS.md/TOOLS.md are not hashed audited surfaces`.

## Subtasks

### T014 — Step 3c: persist the signal + resolved date

Edit the Step 3c `--partial-payload` instruction so the JSON the agent records
carries, from `validate`'s output (WP01): the `missing_fields` list **and** the
resolved `start_date`. The agent should pass `fields_so_far` (which now includes
`start_date`) plus `missing_fields` verbatim — it must **not** compute or reformat the
date. Keep the WhatsApp-ask wording unchanged (the ask still fires; C-005).

### T015 — Step 1a: invoke sweep-finalize

Replace the bare `handle_clarification_state sweep` invocation with the new
deterministic sweep-finalize command
(`python3 -m scripts.inbox.clarification_sweep_finalize …`, exact form per WP03).
Keep the "continue regardless of outcome count" tick semantics. Make explicit in the
prompt that this path is deterministic and the agent does not itself create the event.

### T016 — Document the command + behavior

Update `felix-admin-capture/TOOLS.md` (the add/sweep/finalize command reference) and
`docs/runbooks/inbox-ops.md` to describe: the new sweep-finalize command, the 8h
window (C-006), the all-day fallback for unanswered start-time clarifications, and
the eligibility rule. Keep the narrative pointer to the WP06 process-flow doc as the
canonical explanation (avoid duplicating the full flow here — link it).

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree per computed lane in `lanes.json`. Deploy is post-merge via
`agent-prompt-sync`, not part of this WP.

## Definition of Done

- [ ] Step 3c records `missing_fields` + `start_date` (agent copies, does not compute).
- [ ] Step 1a invokes the sweep-finalize command; tick semantics preserved.
- [ ] TOOLS.md + inbox-ops.md document the command, the 8h window, and the fallback; link the WP06 flow doc.
- [ ] Output-discipline + step structure preserved; AGENTS.md still renders within the size cap.
- [ ] Merge commit records `Rebaseline: not required — …`.

## Risks / reviewer guidance

- Reviewer confirms the ask (Step 3c WhatsApp prompt) still fires first — the all-day path is timeout-only (C-005), never a first-response.
- Confirm the agent is instructed to **copy** `start_date`/`missing_fields`, never to compute a date (determinism lives in code, not the prompt).
- Confirm the exact command string matches WP03's `-m` entry point.
- AGENTS.md rawChars inflation (~26%) — confirm the edit stays within the deployed size cap ([[reference_openclaw_gotchas]]).

## Activity Log

- 2026-07-18T22:47:41Z – claude:sonnet:curator-carla:implementer – shell_pid=86970 – Assigned agent via action command
