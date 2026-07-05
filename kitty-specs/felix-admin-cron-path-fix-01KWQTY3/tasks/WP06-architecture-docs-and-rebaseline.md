---
work_package_id: WP06
title: Architecture docs update + rebaseline determination record
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-004
- FR-006
- FR-012
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
- T021
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "89077"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/data-flows.json
role: implementer
tags: []
---

# Work Package Prompt: WP06 – Architecture docs + rebaseline record

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load curator-carla` (role: implementer) before anything else.

## Branch Strategy

- Planning/base + merge target: `fix/felix-admin-cron-path-fix`. Depends on WP01–WP05 (reflect final state).

## Objectives & Success Criteria

Keep the live architecture store truthful after this mission's changes, and record
the rebaseline determination. Done when the JSON+md name the new state/log locations
and the gateway drop-in, `validate_architecture_data.py` passes, and the rebaseline
note is captured for the merge commit.

## Context & Constraints

- Standing requirement (repo `CLAUDE.md`): any change to services/credentials/ports/
  data-flows updates `docs/design/architecture/data/*.json` + md counterparts.
- **Discovery aid**: consult `docs/design/architecture/data/signal-to-doc-map.json`
  filtering `match.source == "mission-architecture-impact"` for the change classes in
  play here: `service-added-or-modified` (gateway drop-in), `data-flow-added-or-modified`
  (state/log relocation), `systemd-unit-added-or-modified` (drop-in). Update every
  `doc_targets` entry those classes enumerate (INDEX.md / DEVELOPER_PORTAL.md are
  routinely missed — check them).
- `validate_architecture_data.py` is a BLOCKING Docs-CI gate — run it before finishing.

## Subtasks & Detailed Guidance

### Subtask T019 – service-inventory (json + md)
- **Files**: `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`
- **Steps**: record that inbox dedup state + calendar clarification state now live at
  `/data/services/openclaw/state/` (owner `claude:secondbrain`, 0750/0640); forensic
  logs now go to the Obsidian vault `/home/kgale/second-brain/agents/logs/`; and the
  `openclaw-gateway` service now carries a `PYTHONPATH` drop-in. Keep JSON authoritative;
  mirror in md.

### Subtask T020 – data-flows + signal-to-doc consult
- **File**: `docs/design/architecture/data/data-flows.json` (+ any doc_targets the map names)
- **Steps**: update the inbox/escalation data-flow entries whose state/log endpoints
  changed. Follow the `signal-to-doc-map.json` doc_targets for the change classes above;
  update navigation docs (INDEX.md, DEVELOPER_PORTAL.md) if listed.

### Subtask T021 – rebaseline determination (R6)
- **Steps**: record (in the mission's merge notes / this WP's activity log) the
  rebaseline determination: the **systemd drop-in IS a monitored audited surface**
  → the merge must carry `Rebaseline: completed at <ts>` (or the automated
  felix-deployer deferred-confirm equivalent). Note the **#621 gap**: agent-prompt
  `AGENTS.md` changes (WP04) are NOT hashed by `audit.sh`, so they require no rebaseline
  and none is claimed for them. State which applies explicitly.

## Test Strategy

- `python3 tooling/scripts/validate_docs.py` and the architecture-data validator must pass.

## Risks & Mitigations

- Missing a doc_target → use the signal-to-doc map, don't hand-guess.

## Integration Verification (before for_review)

- [ ] JSON + md agree; validators pass.
- [ ] signal-to-doc doc_targets for the change classes all addressed.
- [ ] Rebaseline determination recorded (drop-in = rebaseline; AGENTS.md = none, #621).

## Review Guidance

- Confirm the machine-readable JSON is authoritative and consistent with the md.

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T04:30:52Z – claude:sonnet:curator-carla:implementer – shell_pid=83710 – Assigned agent via action command
- 2026-07-05T04:39:08Z – claude:sonnet:curator-carla:implementer – shell_pid=83710 – Ready for review: arch docs updated (state dir + vault log relocation, gateway PYTHONPATH drop-in), validators green (validate_docs: OK, validate_architecture_data: OK 0 findings), rebaseline determination recorded in commit message and audited-surfaces.json. Signal-to-doc map targets for service-added-or-modified + data-flow-added-or-modified + systemd-unit-added-or-modified all addressed. audited-surfaces.json extended with openclaw/*.service.d/ pattern.
- 2026-07-05T04:39:50Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=87301 – Started review via action command
- 2026-07-05T04:43:33Z – user – shell_pid=87301 – Reset stuck codex review claim (codex hit usage limit mid-review); re-reviewing with independent opus per operator decision
- 2026-07-05T04:43:37Z – claude:opus:reviewer-renata:reviewer – shell_pid=89077 – Started review via action command
- 2026-07-05T04:50:40Z – user – shell_pid=89077 – Moved to planned
