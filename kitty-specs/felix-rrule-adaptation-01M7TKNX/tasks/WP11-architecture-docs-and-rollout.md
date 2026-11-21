---
work_package_id: WP11
title: Architecture docs, runbooks, rollout
dependencies:
- WP08
- WP09
- WP10
- WP12
requirement_refs:
- FR-023
- FR-024
- C-002
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
subtasks:
- T051
- T052
- T053
- T054
- T055
phase: Phase 4 - Documentation
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: planning_artifact
model: claude-opus-5-5
owned_files:
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/data/mutation-surfaces.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/credentials-and-secrets.md
- docs/design/process-flows/habits.md
- docs/runbooks/habits-ops.md
- docs/runbooks/escalation-ops.md
- docs/runbooks/deploy/office2-deploy-paths.md
- docs/runbooks/agent-prompt-sync-ops.md
- docs/runbooks/openclaw-agent-setup.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP11 – Architecture docs, runbooks, rollout

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

kg-automation's standing requirement is that a change to data flows, credentials or deployed components updates `docs/design/architecture/data/*.json` and its narrative views **in the same merge**. Do that for this mission (FR-023). Also **write the documentation** for the operator steps Kent gates (FR-024, C-002). This WP only documents them; it executes none of them, and it is reviewed on its diff:

- the token re-issue;
- the rollout window (pause `N done`, check synced copies and a fresh session);
- the canary check procedure from `quickstart.md`;
- inventory and repair;
- the sweeper re-enable plus verifying the next tick.

Done when:
- `python3 tooling/scripts/validate_architecture_data.py --strict` passes.
- `python3 tooling/scripts/validate_docs.py` passes.
- `make test` passes, since the broken-link gate lives in pytest (memory: "Docs CI green ≠ CI green").
- Every `doc_targets` entry for the applicable change classes in `signal-to-doc-map.json` is either updated or noted as reviewed-unchanged in the WP history.

## Context & Constraints

- **The JSON is authoritative.** When the JSON and the markdown conflict, the JSON wins (Directive 5).
- **Applicable change classes** (research.md R-011; signal-to-doc-map `mission-architecture-impact`):
  - `data-flow-added-or-modified` (:195)
  - `credential-added-or-modified` (:181)
  - `service-added-or-modified` (:166)
  - `agent-prompt-changed` (:281)
  - `habits-flow-changed` (:424)
  - `runbook-added` and `runbook-modified` (:241)
  - `office2-service-deployment` (:331), reviewed only, since nothing was deployed by manifest
- **What changed, factually:**
  - Writes now use `PATCH /api/v2/tasks/{id}`. Reads use v1 lists plus v2 `GET /api/v2/tasks/{id}`. New reads are `GET /api/v2/tasks/{id}/occurrences` and `POST /api/v2/tasks/occurrences/preview`. Create uses `POST /api/v2/projects/{id}/tasks`.
  - The base URL config is unchanged (still `/api/v1`), and v2 is derived from it.
  - Credential `vikunja-api-kent` needs `tasks.occurrences` and `tasks.occurrences_preview`. Record the re-issue date once Kent does it; until then, record "pending Kent re-issue" with a pointer to #1111.
  - `scripts/habits/migrate_schedule.py` is retired. Remove `service-inventory.json:1110-1117` and the `used_by` mention at `credential-manifest.json:411`.
  - New helpers: `scripts.vikunja.rule_inventory`, `rule_repair` and `preview_rule`, and `schedule_loader --check-live`. New state: `/data/services/openclaw/state/vikunja-repair/` and the sync's `seed-ledger.jsonl`.
  - `set_due_dates --reconcile-schedule` is retired. `habits-ops.md:617-635` must be updated, and `habits-ops.md:417` mentions `repeat_after`.
  - The escalation agent no longer writes Vikunja directly.
- `mutation-surfaces.json:177`: the `vikunja-api-mutate` pattern must include `PATCH` and `/api/v2/`.
- No `@mentions`. Copy here is Kent's own documentation, so no external copy gate applies.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP11 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T051 – Architecture data JSON

- `data-flows.json`:
  - update the habits and escalation write legs (:542-552), the reconcile reads (:601-616), and the other `/tasks/<id>` legs (:186, :230, :259, :294, :425) to the v2 paths;
  - add flows for occurrences, preview, the inventory/repair helpers and the seed ledger;
  - keep each schema valid, checking the validator for required keys.
- `service-inventory.json`: remove the `migrate_schedule` artifact; add the new helpers and state paths; update the fork notes to v2.8.0-rrule.4 with v2 use.
- `credential-manifest.json`: for `vikunja-api-kent`, record the required permissions including the two new keys, the re-issue status, and the `used_by` edit.
- `mutation-surfaces.json:177`: the pattern.

### Subtask T052 – Narrative views

- Update `data-flows.md:110` and `data-flows.view.md` (Mermaid), `service-inventory.md`, and `credentials-and-secrets.md:244` to match the JSON. Keep each diagram readable, and add only the new edges.

### Subtask T053 – Runbooks

- **`habits-ops.md`**:
  - remove the `--reconcile-schedule` section, or replace it with "retired — the sweeper advances day-specific habits by rule";
  - fix L417;
  - add **"Re-enabling the sweeper"**: Kent's go, then `ssh office2-claude 'systemctl --user enable --now felix-habit-sweeper.timer'`, then `list-timers`. The timer is `Persistent=true`, so it catches up one missed run. Verify the next tick in the sweeper ledger (0 errors) and run `schedule_loader --check-live`.
  - add **"Schedule drift check"**.
- **`escalation-ops.md`**: the agent no longer writes Vikunja; `N done` goes through the helper; the outcome values (`advanced`, `series_ended`, `done_one_off`, `unexpected`) and what each means.
- **`deploy/office2-deploy-paths.md`** + **`agent-prompt-sync-ops.md`**: add a "helper/doc skew" note and the rollout-window procedure from quickstart.md. Helpers ride the pull, and docs ride the sync and session-init cache.
- **`openclaw-agent-setup.md`**: only if the agent-prompt-changed class requires it; otherwise note it as reviewed-unchanged.

### Subtask T054 – Process flow and navigation

- `docs/design/process-flows/habits.md`: the completion and auto-skip flow, now rule-driven.
- `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`: add `docs/runbooks/vikunja-task-repair.md` (created by WP10) with its Divio type.

### Subtask T055 – Validators

```bash
python3 tooling/scripts/validate_architecture_data.py --strict
```

```bash
python3 tooling/scripts/validate_docs.py
```

```bash
make test
```

Record the results with `add-history`. Run nothing in GitHub Actions.

## Risks & Mitigations

- **Missing a navigation doc** (#492 precedent). Walk the signal-to-doc-map list explicitly.
- **Recording the token as re-issued before it is.** Write "pending" unless #1111 shows it done.

## Review Guidance

- Does the JSON match the shipped code (spot-check 3 flows against WP02's client methods)?
- Are the sweeper re-enable and rollout-window steps present and accurate?
- Are the validators green?

## Progress & Status

Use `spec-kitty agent tasks add-history WP11 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
