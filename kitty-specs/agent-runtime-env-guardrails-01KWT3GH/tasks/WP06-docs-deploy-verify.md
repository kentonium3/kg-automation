---
work_package_id: WP06
title: Docs (#167 + architecture) + deploy manifest 0010 + verify
dependencies:
- WP05
requirement_refs:
- FR-009
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T023
- T024
- T025
- T026
agent: "claude"
shell_pid: "16079"
history:
- 2026-07-05 authored from plan IC-05/IC-06 (docs + deploy + verify)
agent_profile: curator-carla
authoritative_surface: deploys/queued/0010-agent-runtime-env-guardrails.yaml
create_intent:
- deploys/queued/0010-agent-runtime-env-guardrails.yaml
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- deploys/queued/0010-agent-runtime-env-guardrails.yaml
- docs/design/architecture/data/audited-surfaces.json
- docs/runbooks/openclaw-agent-setup.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile
Run `/ad-hoc-profile-load curator-carla` (role: implementer). Then read this WP.

## Objective
Land the docs updates, the deploy manifest, and the verification plan. Read
`docs/runbooks/deploy/discipline.md` for the manifest pattern and
`docs/design/architecture/data/signal-to-doc-map.json` for the doc targets (change class
`agent-prompt-changed`). **Verify the actual #167 authoring-standard doc path before editing**
(the plan names `docs/runbooks/openclaw-agent-setup.md` as the authoring standard — confirm it
is the right surface for the guardrail reference; if the #587/#167 standard lives elsewhere,
own that file instead and update owned_files rationale).

## Subtasks
- **T023 — #167 authoring standard.** Add a short section referencing the env-assumption
  guardrail: newly-authored agents must use the canonical `cd "${PYTHONPATH:?}" && …` form and
  will be validated by `validate_workspace.py`'s `runtime_env_assumptions` check.
- **T024 — architecture reconcile.** Per the signal map: `service-inventory.json` / `network-topology.json`
  — no change expected (affirm). `audited-surfaces.json` — agent prompts are already audited;
  confirm the guard/validator additions need no new baseline entry (they are CI/validation logic,
  not a deployed audited artifact); set `updated_by` to 658 only if a deploy artifact is added.
  Review `docs/INDEX.md` / `DEVELOPER_PORTAL.md` for a new guard surface (likely no change).
- **T025 — deploy manifest** `deploys/queued/0010-agent-runtime-env-guardrails.yaml`: redeploy
  the converted prompts via `python3 -m scripts.openclaw.deploy.deploy_agent_prompts` (dry-run in
  a pre-check; apply step syncs repo→deployed). Tier 3. Include health-check verify steps:
  capture `prescan --self-check`→ok, habits/escalation/tasker cron green, **calendar's
  validate_calendar_event (stdin) + log_action shape resolve** (Codex MED-4), and the
  **non-repo-cwd smoke** (run a converted helper from `/tmp` with PYTHONPATH exported — Codex
  HIGH-3). felix-deployer auto-rebaselines the audited surface (agent prompts); the manifest/merge
  records `Rebaseline: completed`. Model 0010 on an existing `deploys/applied/000N-*.yaml`.
- **T026 — verification plan.** Document the post-deploy verification (the SC-004 checks) in the
  manifest `verify:`/notes and/or `../quickstart.md`. These run after felix-deployer applies on
  office2; capture the expected signals.

## Branch Strategy
Base/merge: `feat/agent-runtime-env-guardrails`. Lane worktree from `lanes.json`. Depends on
WP05 (the guard must be green and the #167 reference points at it).

## Definition of Done
- #167 standard references the guardrail; architecture docs reconciled/affirmed.
- `deploys/queued/0010-…yaml` valid (tier guard passes), invokes `deploy_agent_prompts`, and its
  verify steps cover capture/habits/escalation/tasker **and calendar** + the cwd smoke.
- No native OpenClaw element touched (SC-005) — the manifest deploys prompts only.

## Reviewer guidance
- Verify the manifest schema matches a recent applied manifest and the tier guard passes.
- Confirm calendar health checks + the non-repo-cwd smoke are present (Codex MED-4/HIGH-3).
- Confirm no edits under `~/.openclaw`, `openclaw.json`, or `openclaw-gateway.service` (SC-005).
- Confirm the #167 doc path is the real authoring standard (not a wrong surface).

## Activity Log

- 2026-07-05T22:51:41Z – claude – shell_pid=16079 – Assigned agent via action command
- 2026-07-05T23:03:14Z – claude – shell_pid=16079 – deploy manifest 0010 + entrypoint + doc; 45 tests green
- 2026-07-05T23:03:21Z – user – shell_pid=16079 – Reviewed: manifest schema-valid + tier-guard pass; self-bootstrapping entrypoint (dry-run from /tmp exits 0, cwd-independent); rebaseline corrected to 'not required' per canonical audited-surfaces.json (#621); #167 doc references guardrail.
