---
work_package_id: WP04
title: Deploy manifest + architecture docs + rebaseline
dependencies:
- WP01
- WP03
requirement_refs:
- C-001
- C-002
- C-003
- C-005
- FR-012
- FR-013
- NFR-003
tracker_refs: []
planning_base_branch: feat/deterministic-monitoring-checks
merge_target_branch: feat/deterministic-monitoring-checks
branch_strategy: Planning artifacts for this mission were generated on feat/deterministic-monitoring-checks. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/deterministic-monitoring-checks unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
agent: claude
history: []
agent_profile: implementer-ivan
authoritative_surface: deploys/queued/deterministic-monitoring-checks.yaml
create_intent:
- deploys/queued/deterministic-monitoring-checks.yaml
execution_mode: code_change
owned_files:
- deploys/queued/deterministic-monitoring-checks.yaml
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/constitution/AGENT-REGISTRY.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load implementer-ivan` (role: implementer). Adopt its identity +
discipline before reading further.

## Objective

Author the office2 deploy manifest that installs WP03's systemd unit + wrapper and
removes the two `health-check-*` openclaw crons, then synchronize the architecture docs
and record the rebaseline obligation. This WP lands last (it deploys WP01 + WP03
outputs) but authors only manifests/docs — the deploy itself runs post-merge via
felix-deployer.

## Context (read these)

- Plan: `plan.md` IC-04 + Charter Check (DIR-004 manifest discipline, DIR-007 cron-CLI,
  #557 rebaseline). Quickstart: `quickstart.md` (strict deploy order, Codex #6).
- Deploy discipline: `docs/runbooks/deploy/discipline.md`, `scripts/deploy/lib/README.md`,
  `deploys/schema/manifest-v1.schema.json`. **Precedent**: an existing
  `deploys/applied/` entry + `scripts/office2/deploy/credential-health-check.sh`.
- Architecture: `docs/design/architecture/data/service-inventory.json` (+ its md view —
  confirm the actual view filename; `.view.md` assumed) and the validator
  `tooling/scripts/validate_architecture_data.py` (a blocking Docs-CI gate).
- Do NOT re-number the queued manifest defensively (repo lesson: pre-numbering caused a
  collision; felix-deployer sequences on apply). Use the unnumbered name in owned_files.

## Subtasks

### T016 — Deploy manifest `deploys/queued/deterministic-monitoring-checks.yaml`
- Conform to `deploys/schema/manifest-v1.schema.json`. Reference a deploy script that
  uses `scripts/deploy/lib/` primitives (tier guard, file-presence, etc.). It must:
  install `felix-health-check.{service,timer}` + the wrapper (WP03 outputs), run
  `daemon-reload`, enable+start the timer, and remove the two openclaw crons
  (`health-check-morning`, `health-check-evening`) via the `openclaw cron` CLI (DIR-007;
  system crontab never used).
- Encode the **strict order** (Codex #6): install units → smoke → enable timer → verify
  `list-timers` → remove crons → confirm none remain. Tier 3.

### T017 — Resolve the cron-removal path
- Determine (against `scripts/deploy/lib/` + the felix-deployer behavior) whether
  `openclaw cron remove` can ride the felix-deployer happy path or must be an
  out-of-band manual step (like prior openclaw.json edits). Encode the answer in the
  manifest (if pipeline-able) or document the out-of-band step in the manifest notes +
  ensure `quickstart.md` matches. State the decision explicitly in the WP history.

### T018 — Architecture data sync `[P]`
- `service-inventory.json`: reflect health-check execution moving off `main` to the
  `felix-health-check` systemd timer, and the heartbeat-gate losing its Haiku/model
  dependency. Set `updated_by` to `676`. Update the markdown view to match.
- Run `python3 tooling/scripts/validate_architecture_data.py` (or the documented
  invocation) and ensure it passes (it is a blocking Docs-CI gate).

### T019 — Agent registry review `[P]`
- Review `docs/constitution/AGENT-REGISTRY.md` for `main`'s scheduled workload: it loses
  two scheduled sessions/day (the health-check crons). Update if the registry documents
  main's scheduled jobs; otherwise record "reviewed, no change needed" in WP history.

### T020 — Rebaseline record
- Record the #557 rebaseline obligation: the change touches systemd user units + deploy
  scripts AND openclaw config (cron removal). Ensure the manifest/notes make clear the
  merge commit must carry `Rebaseline: completed at <ts>` (felix-deployer automated for
  the unit files if pipeline-applied; the cron-removal openclaw-config change per T017 —
  out-of-band manual per `docs/runbooks/security-baseline-ops.md` if not pipeline-able).

## Branch Strategy

Base + merge target `feat/deterministic-monitoring-checks`; worktrees per `lanes.json`.
Depends on WP01 + WP03 — reference their file paths (unit names, wrapper module path);
they must exist on your lane's base.

## Definition of Done

- [ ] `deploys/queued/deterministic-monitoring-checks.yaml` passes the manifest schema
      and encodes the strict deploy order + cron removal via CLI.
- [ ] Cron-removal path (pipeline vs out-of-band) resolved + documented consistently in
      manifest and quickstart.
- [ ] `service-inventory.json` + md view updated (`updated_by=676`);
      `validate_architecture_data.py` green.
- [ ] AGENT-REGISTRY reviewed/updated (or "no change" recorded).
- [ ] Rebaseline obligation recorded for the merge commit.

## Risks / reviewer guidance

- Reviewer: confirm cron ops go through `openclaw cron` CLI only (DIR-007), and the
  deploy order can't create a double-alert/missed-check window around 11:00/23:00.
- Confirm the manifest references WP03's real unit/wrapper paths (not invented ones).
- The architecture-data validator is a hard gate — do not merge red.
- NFR-003 (spend reduction) is verified post-deploy (quickstart #16), not in this WP.
