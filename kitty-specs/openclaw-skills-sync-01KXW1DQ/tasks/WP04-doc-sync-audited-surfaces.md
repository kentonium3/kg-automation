---
work_package_id: WP04
title: Documentation synchronization + audited-surface globs
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- FR-013
tracker_refs: []
planning_base_branch: feat/openclaw-skills-sync
merge_target_branch: feat/openclaw-skills-sync
branch_strategy: Planning artifacts for this mission were generated on feat/openclaw-skills-sync. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/openclaw-skills-sync unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
agent: "claude"
shell_pid: "96426"
shell_pid_created_at: "1784431015.853065"
history:
- '2026-07-19: authored by /spec-kitty.tasks'
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/data/service-inventory.json
create_intent:
- docs/runbooks/agent-skill-sync-ops.md
execution_mode: code_change
owned_files:
- docs/design/architecture/data/audited-surfaces.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/service-dependencies.view.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/runbooks/agent-skill-sync-ops.md
- docs/runbooks/deployment.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
- docs/design/felix-capability-roadmap.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

## Objective

Synchronize the architecture docs with what WP01–WP03 built (DIR-014), extend the audited-surface
globs so C-002's rebaseline claim actually holds (Codex #1 MEDIUM-1), and ship the ops runbook. JSON
is authoritative; markdown views must match. Set `updated_by: 775` on JSON edits. Validators
(`validate_docs.py`, `validate_architecture_data.py`) must pass.

**Read before editing**: this mission's `plan.md` (IC-05, Documentation Synchronization list) +
`data-model.md` (health_check shape); `agent-prompt-sync-ops.md` (template for the new runbook); the
existing `audited-surfaces.json`, `service-inventory.json`, and `data-flows.json` entries for
agent-prompt-sync (mirror them).

### Subtask T014 — Extend `audited-surfaces.json` globs

**Purpose**: Make the new systemd unit + deploy script actually audited (they aren't matched today).

- The `systemd-user-units` surface matches `scripts/office2/*.{service,timer}` — **add**
  `scripts/openclaw/deploy/*.service` and `scripts/openclaw/deploy/*.timer` (this also retroactively
  covers agent-prompt-sync's units — note that in the change).
- The `deploy-pipeline` (or equivalent) surface matches `scripts/deploy/lib/**` + `deploys/*.yaml` —
  **add** `scripts/deploy/deploy-skills-sync.sh` (or the appropriate glob) so the entrypoint is audited.
- Set `updated_by: 775`; keep the JSON schema valid (`validate_architecture_data.py`).

### Subtask T015 — `service-inventory.json` + `.md` + health_check

- Add the skills-sync service (mirror the agent-prompt-sync entry): systemd unit, source, deployed
  target, purpose, and a `health_check` `{ endpoint: /data/services/openclaw/deploy/skills-last-tick.json,
  method: <tick-signal method used by prompt-sync>, max_age_seconds: 600 }`.
- Update `service-inventory.md` to match. `updated_by: 775`.

### Subtask T016 — `data-flows.*` + `service-dependencies.view.md`

- Add the new **repo → office2 skill-sync** data flow to `data-flows.json` (+ `.md` + `.view.md`
  mermaid), mirroring the agent-prompt-sync flow.
- Add the sync service relationship to `service-dependencies.view.md`.
- `updated_by: 775`; markdown views match JSON.

### Subtask T017 — Runbook + navigation + roadmap

- New `docs/runbooks/agent-skill-sync-ops.md` (mirror `agent-prompt-sync-ops.md`): what it is, the
  units, operator enable, validation, the drift-check probe, rollback. Use the mission `quickstart.md`
  as the source of the live-verify + rollback steps.
- Note the skills-sync alongside agent-prompt-sync in `docs/runbooks/deployment.md`.
- Add the runbook to `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`.
- Add a capability/status note to `docs/design/felix-capability-roadmap.md` if applicable (#775 closes
  the skills silent-drift gap).

## Branch Strategy

Planning on `feat/openclaw-skills-sync`; merge target `feat/openclaw-skills-sync`. Worktree per lane
from `lanes.json`. Depends on WP01–WP03 (documents their surfaces) — runs last.

## Definition of Done

- [ ] `audited-surfaces.json` globs extended to cover the new unit + deploy script (`updated_by: 775`).
- [ ] `service-inventory.json`/`.md` add the service + `skills-last-tick.json` health_check.
- [ ] `data-flows.*` + `service-dependencies.view.md` add the skill-sync flow.
- [ ] `agent-skill-sync-ops.md` created; `deployment.md`, `INDEX.md`, `DEVELOPER_PORTAL.md`, roadmap updated.
- [ ] `validate_docs.py` + `validate_architecture_data.py` pass; JSON authoritative, md views match.

## Risks / reviewer guidance

- **Load-bearing**: the audited-surfaces glob extension is what makes C-002 true — verify the new
  globs actually match `scripts/openclaw/deploy/agent-skill-sync.{service,timer}` and the deploy
  script (test the pattern, don't eyeball).
- Reviewer: confirm every JSON edit has `updated_by: 775` and the markdown views were regenerated to
  match (validators enforce this).

## Activity Log

- 2026-07-19T03:01:13Z – claude – shell_pid=91267 – Assigned agent via action command
- 2026-07-19T03:17:20Z – claude – shell_pid=91267 – Doc-sync + audited-surface globs; validators green
- 2026-07-19T03:17:32Z – claude – shell_pid=96426 – Started review via action command
- 2026-07-19T03:17:56Z – user – shell_pid=96426 – Audited-surface globs verified to match new units + deploy script; service entry wires independent drift check as canary probe; validators green. Post-merge Codex is the whole-diff backstop.
