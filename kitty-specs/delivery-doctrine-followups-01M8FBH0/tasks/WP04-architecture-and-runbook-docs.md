---
work_package_id: WP04
title: Architecture and runbook docs
dependencies:
- WP03
requirement_refs:
- FR-007
planning_base_branch: fix/1146-delivery-doctrine-followups
merge_target_branch: fix/1146-delivery-doctrine-followups
branch_strategy: Planning artifacts for this mission were generated on fix/1146-delivery-doctrine-followups. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/1146-delivery-doctrine-followups unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
phase: Phase 3 - Documentation
history:
- at: '2026-11-27T20:57:33Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/
create_intent: []
execution_mode: planning_artifact
model: claude-sonnet-5-5
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/runbooks/openclaw-agent-setup.md
- docs/runbooks/deploy/discipline.md
- docs/design/architecture/security-posture.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Architecture and runbook docs

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete. Feedback items are your implementation TODO list.
- **Report progress**: As you address each feedback item, record what you changed with `spec-kitty agent tasks add-history <WPID> --note "..."` (stored in the status event log).

---

## Review Feedback

*[If this WP was returned from review, the reviewer feedback reference appears in the status event log.]*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks: `` `<div>` ``, `` `<script>` ``
Use language identifiers in code blocks: ````python`,````bash`

---

## Objectives & Success Criteria

The docs that `docs/design/architecture/data/signal-to-doc-map.json` names for **agent-prompt-changed** and **deploy-manifest-added** must describe the post-mission state:

- the announce agents' tool deny;
- the manifest-driven `openclaw.json` edit pattern;
- scoped rollback.

The JSON stays authoritative where it and the Markdown overlap. All three doc validators pass.

## Context & Constraints

- **Read**:
  - `plan.md` ("Architecture Impact", IC-04, the "Post-plan review" table);
  - `data-model.md`;
  - the WP03 entrypoint and manifest, once merged into this lane's base;
  - `CLAUDE.md` ("Architecture Documentation", "Documentation Standards": machine-readable wins).
- **Depends on WP03**: use the real entrypoint, manifest, receipt path and rollback flag names it shipped.
- Frontmatter rules apply (`validate_docs.py`). Bump `last_updated` where the doc carries it.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T016 – Service inventory

- In `docs/design/architecture/data/service-inventory.json`, record the tool deny on the OpenClaw entry for the three announce agents (felix-admin-capture, -escalation, -habits), following the file's existing schema. Do not invent new top-level keys; if no field fits, add it within an existing per-service notes or config field. Mirror the change in `service-inventory.md`.
- Run `validate_architecture_data.py --strict`.

### Subtask T017 – openclaw-agent-setup.md

- Add an "Announce agents: tool policy" note. An agent whose cron delivers by `announce` delivers only through its final reply (the delivery doctrine, #1143). Its `agents.entries.<id>.tools.deny` holds the four groups, and it is set through the deploy pipeline, never by hand. A new announce agent needs both the doctrine block and the deny.

### Subtask T018 – deploy/discipline.md

- Add a short section, "Editing openclaw.json through a manifest", covering:
  - the Gateway-owned `config patch` with dry-run;
  - the write-once recovery receipt;
  - the non-target hash check;
  - reload confirmation (acknowledgement plus unchanged PID);
  - the `expected_baselines: [openclaw-config.txt]` requirement, and why (no signal in the commit range);
  - scoped rollback: dequeue if unapplied, otherwise use the entrypoint's rollback; whole-file backup as the last resort.
- Point to `scripts/deploy/deploy-announce-agent-tool-deny.py` as the reference implementation.

### Subtask T019 – Security posture and review

- In `docs/design/architecture/security-posture.md`, note the capability deny for announce agents as defence in depth behind the prompt doctrine, and cite openclaw/openclaw#206884.
- Review `docs/runbooks/agent-prompt-sync-ops.md`, `docs/runbooks/deploy/office2-deploy-paths.md` and `docs/design/architecture/data/audited-surfaces.json`. Change them only if they are now wrong. If a change is needed outside `owned_files`, stop and report it to the lead rather than editing; the lead extends ownership.
- Run:

```bash
.venv/bin/python tooling/scripts/validate_docs.py
.venv/bin/python tooling/scripts/validate_architecture_data.py --strict
.venv/bin/python tooling/scripts/generate_doc_standards.py --check
```

(Use the repo's actual paths for these scripts if they differ.)

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| The JSON and Markdown disagree | Edit the JSON first; mirror it in the Markdown |
| The docs name non-existent flags or paths | Take the names from WP03's merged code |

## Review Guidance

- Cross-check every flag, path and field name against WP03's code and manifest.
- Confirm that the validators pass and that no doc outside `owned_files` changed.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`) — never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history <WPID> --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task <WPID> --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
