---
work_package_id: WP03
title: Docs & merge hygiene
dependencies:
- WP01
- WP02
requirement_refs:
- C-001
- C-005
tracker_refs: []
planning_base_branch: fix/felix-deployer-rebaseline-detection
merge_target_branch: fix/felix-deployer-rebaseline-detection
branch_strategy: Planning artifacts for this mission were generated on fix/felix-deployer-rebaseline-detection. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-deployer-rebaseline-detection unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: curator-carla
authoritative_surface: docs/runbooks/deployment.md
create_intent: []
execution_mode: code_change
owned_files:
- CLAUDE.md
- docs/runbooks/deployment.md
- docs/runbooks/security-baseline-ops.md
role: implementer
tags: []
shell_pid: "20715"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load curator-carla` (role: implementer/curator). Adopt its
documentation-fidelity discipline for this WP.

## Objective

Make the docs describe the shipped behavior from WP01/WP02: the `CLAUDE.md` "happy path"
guarantee is now true and robust to out-of-band HEAD advance; document the watermark-based
observe range and the manifest `expected_baselines` declaration. Confirm the signal-to-doc
map targets so no doc surface is missed.

Read before editing: `../spec.md` (Architecture Impact), `../plan.md` (IC-04), the merged
WP01/WP02 code so the docs match reality.

## Context

- `CLAUDE.md` (repo root) has a "Deploys to office2" / "Rebaseline obligation" section
  describing felix-deployer's "happy path" — *"felix-deployer rebaselines automatically and
  silently — no operator action needed"*. #685 made that false for out-of-band-pull and
  CLI-mutation deploys; WP01/WP02 restore it. Editing `CLAUDE.md` is Tier 4 (auto-commit).
- `docs/runbooks/deployment.md` — felix-deployer behavior/deployment reference.
- `docs/runbooks/security-baseline-ops.md` — the rebaseline procedure runbook.
- `docs/design/architecture/data/signal-to-doc-map.json` — enumerates doc targets per
  change class. Relevant classes here: `systemd-unit-added-or-modified`,
  `deploy-manifest-added`, `runbook-modified`.

---

### T015 — CLAUDE.md happy-path text

Update the felix-deployer "happy path" description to state that the deferred-confirm flow
is now driven by a **persisted last-observed-head watermark**, so it detects audited-surface
changes **regardless of which actor advanced the checkout HEAD** (out-of-band `git pull`
included) — closing #685. Keep the existing out-of-band-exception paragraph accurate (manual
resets are still for changes made directly on office2, not via the pipeline). Do not
overclaim: note that a deploy whose drift is not signaled by a repo-file change should
declare `expected_baselines` in its manifest.

### T016 — deployment.md (felix-deployer behavior)

Document: (a) the watermark file `rebaseline-observed-head.json` in
`/data/services/felix-deployer/state/` and that the observe range is
`last_observed_head..post_pull_head`; (b) the manifest `expected_baselines` field and when
to use it (CLI-mutation deploys with no repo-file signal); (c) the same-tick clear grace
rule (a token isn't cleared on empty drift until its drift has had a tick to appear).

### T017 — security-baseline-ops.md + signal-to-doc-map

Add a short note that CLI-mutation deploys declare their drifted baselines via the manifest
`expected_baselines` field so the auto-rebaseline covers them (no manual reset). Then run
the signal-to-doc-map lookup for the change classes above and confirm no additional doc
target (e.g. `docs/INDEX.md`, `DEVELOPER_PORTAL.md`, the felix-deployer behavior reference)
is required; if the map names one this WP doesn't own, record it in the WP history / flag it
for a follow-up rather than silently skipping.

## Branch Strategy

Planning base and final merge target are both `fix/felix-deployer-rebaseline-detection`.
Depends on WP01 + WP02 (docs describe their behavior). Execution worktrees per `lanes.json`.

## Definition of Done

- All 3 subtasks complete; `python tooling/scripts/validate_docs.py` passes for edited docs.
- The `CLAUDE.md` happy-path text is accurate to the shipped watermark behavior.
- The signal-to-doc-map lookup is done and any uncovered target is named (not silently
  skipped).

## Risks & Reviewer Guidance

- Reviewer: confirm the docs match the merged WP01/WP02 behavior (no aspirational claims);
  confirm the manifest `expected_baselines` guidance matches WP02's validation rules
  (known names only; requires `audited_surface: true`).

## Activity Log

- 2026-07-09T02:10:06Z – claude:opus:curator-carla:implementer – shell_pid=18477 – Assigned agent via action command
- 2026-07-09T02:14:56Z – claude:opus:curator-carla:implementer – shell_pid=18477 – WP03 complete: CLAUDE.md happy-path + deployment.md + security-baseline-ops.md updated; docs validate
- 2026-07-09T02:16:03Z – claude:opus:reviewer-renata:reviewer – shell_pid=20715 – Started review via action command
- 2026-07-09T02:18:41Z – user – shell_pid=20715 – Review passed: docs match shipped behavior; validate_docs OK
