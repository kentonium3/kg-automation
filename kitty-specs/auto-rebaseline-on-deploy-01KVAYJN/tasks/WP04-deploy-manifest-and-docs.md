---
work_package_id: WP04
title: Deploy manifest + documentation/charter amendment + integration canary
dependencies:
- WP03
requirement_refs:
- FR-006
- NFR-003
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
- T017
agent: "claude"
history: []
agent_profile: curator-carla
authoritative_surface: deploys/queued/
create_intent:
- deploys/queued/0005-felix-deployer-auto-rebaseline.yaml
execution_mode: code_change
owned_files:
- deploys/queued/0005-felix-deployer-auto-rebaseline.yaml
- CLAUDE.md
- docs/runbooks/security-baseline-ops.md
role: implementer
tags: []
shell_pid: "40349"
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load curator-carla` (role: implementer). Adopt its identity and
boundaries before reading further.

## Objective

Ship the auto-rebaseline change to office2 through the manifest pipeline, make
**automation the documented happy path** (manual reset = the out-of-band
exception), and **own the mission's explicit integration verification** (the
post-merge office2 canary). C-002 (manifest discipline), C-004 (doc/charter
amendment), the integration gate (T017).

Read first: `../research.md` (R6), `../spec.md` (C-002/C-004, NFR-003, SC-001…SC-004),
`../plan.md` (IC-04), `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`
(manifest shape), `deploys/schema/manifest-v1.schema.json`,
`docs/runbooks/deploy/discipline.md`.

## Context

felix-deployer self-updates by `git pull` each oneshot tick, so the new
`rebaseline.py` / `_tick.py` code goes live on the next tick after merge — no
restart needed. The manifest's role is a **Tier-3 verification** that the new
modules are present + importable, recorded in `deploys/applied/`. Because the
code only goes live post-merge, the true end-to-end verification is a post-merge
operator canary (T017), not a pre-merge test.

## Subtasks

### T013 — Deploy manifest `deploys/queued/0005-felix-deployer-auto-rebaseline.yaml`
Author per the v1 schema (validate against `deploys/schema/manifest-v1.schema.json`).
Tier 3. Entrypoint verifies the new modules exist and import cleanly (using the
repo's established `-m` invocation convention, e.g. `python3 -m` import of the
felix-deployer rebaseline module) and that the felix-deployer tick can load them.
No state mutation beyond verification. Mirror flag/field shapes from
`0002-bootstrap-felix-deployer-v2.yaml` — verify each field against the schema,
do not guess.

### T014 — CLAUDE.md "Rebaseline obligation" rewrite
Update the "Rebaseline obligation (#557)" paragraph: on the **happy path**
(an audited-surface change applied through the deploy pipeline), felix-deployer
rebaselines automatically and silently — operators are NOT the load-bearing
component. Manual `ssh office2-claude` rebaseline is now the **out-of-band
exception** (changes made directly on office2, bypassing the pipeline) plus the
break-glass fallback. Keep the canonical command reference. Cross-reference #618.

### T015 — `docs/runbooks/security-baseline-ops.md` update
Add an "Automatic rebaseline (felix-deployer)" section: the deferred-confirm
flow, the pending-token at `/data/services/felix-deployer/state/rebaseline-pending.json`,
the observability outcomes, the ntfy alerts (failed/unexpected/stale), and when a
human is still involved (out-of-band changes; unexpected drift). Add an explicit
**"Integration verification (post-merge canary)"** subsection capturing the T017
procedure. Keep the manual command as the documented fallback.

### T016 — Charter Rebaseline-Obligation amendment (via charter workflow)
The charter is workflow-managed (`.kittify`). Do **NOT** edit it directly. Use the
charter-sync workflow (load the `spec-kitty-charter-doctrine` / `spk-doctrine-charter`
skill) to amend the "Rebaseline Obligation (Audited Surfaces, #557)" section so it
matches the new automation-is-happy-path posture. If the charter workflow can't be
driven cleanly within this mission, record a one-line deferral note in the WP and
flag it to the operator rather than hand-editing `.kittify`.

### T017 — Post-merge integration verification (office2 canary)
This is the mission's **explicit integration verification** (charter Quality Gates
"WP05-equivalent" gate). A pre-merge live smoke is impossible — the auto-rebaseline
code only goes live on the felix-deployer tick *after* merge — so the integration
verification is a **post-merge operator canary** against real office2 service state,
matching this repo's established deferred-canary pattern (e.g. mission #185).
Document the canary procedure in `security-baseline-ops.md` (T015) and define it
here so it is recorded as a **merge acceptance criterion** (the merge commit /
closing-issue record carries the canary outcome alongside the Rebaseline note):
- **SC-001 / SC-003**: after the next real audited-surface deploy via felix-deployer,
  confirm the tick log records `pending_set` then `completed` (audited-surface change)
  or `not_required` (non-audited change), baselines healthy (count == `expected_baseline_count`),
  no operator action.
- **SC-002**: confirm the next scheduled security audit reports no drift attributable
  to the change (zero false-positive drift alert).
- **SC-004**: exercise (or simulate, per the documented canary steps) a rebaseline
  failure and confirm exactly one ntfy alert + a failure annotation on the deploy
  record, with the applied code left in place.
The canary is **operator-run post-deploy**; its result is the integration gate. Until
it passes, the mission's deployed behavior is unverified — record the outcome.

## Branch Strategy
Planning base `main`; merge target `main`; lane worktree at implement time.
Depends on WP03 (docs describe behavior built in WP02/WP03).

## Definition of Done
- Manifest validates against the v1 schema; Tier 3; verification-only entrypoint.
- CLAUDE.md + security-baseline-ops.md describe automation as the happy path and
  manual reset as the out-of-band exception.
- Charter amended via the charter workflow, or an explicit deferral recorded.
- Post-merge integration canary (T017) documented as an explicit "Integration
  verification" procedure in `security-baseline-ops.md` and defined as the
  mission's merge acceptance criterion; its outcome is recorded post-deploy.

## Risks / Reviewer guidance
- C-004 transition note: THIS mission's own merge touches `scripts/deploy/**` (an
  audited surface) and predates the automation being live — so its merge is
  rebaselined **manually** (the last manual one). Make that explicit in the docs.
- Do not hand-edit `.kittify`. Charter changes flow through the charter workflow.
- Reviewer: validate the manifest against the schema; confirm no state mutation in
  the entrypoint; confirm the canary procedure is concrete and operator-runnable.

## Activity Log

- 2026-06-17T16:13:10Z – claude – shell_pid=35424 – Started implementation via action command
- 2026-06-17T16:20:06Z – claude – shell_pid=35424 – Ready for review: deploy manifest (0005, Tier 3, verification-only, schema-validated), CLAUDE.md rebaseline-obligation rewrite, security-baseline-ops.md automatic-rebaseline + canary sections, T016 charter deferral noted
- 2026-06-17T16:22:37Z – claude – shell_pid=40349 – Started review via action command
- 2026-06-17T16:27:22Z – user – shell_pid=40349 – opus review PASSED first-pass (manifest schema-valid + verification-only entrypoint, docs accurate, charter deferred). --skip-review-artifact-check: review-cycle-1.md is a blocked-recovery byproduct, not a quality rejection. --force: lane-d kitty-specs verified byte-identical to main (history-only).
