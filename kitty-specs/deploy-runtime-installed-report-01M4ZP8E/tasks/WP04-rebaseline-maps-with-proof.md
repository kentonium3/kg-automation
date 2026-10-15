---
work_package_id: WP04
title: rebaseline maps reports with proof of installation; fold freshness
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-004
- FR-009
- C-001
- C-002
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-deploy-runtime-installed-report-01M4ZP8E
base_commit: 295a7c05a3e68a1b123e80b6351da8554799ec7a
created_at: '2026-10-15T12:17:59.916219+00:00'
subtasks:
- T011
- T012
- T013
- T014
- T015
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/
create_intent:
- tests/deploy/test_rebaseline_reported.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/deploy/felix-deployer/rebaseline.py
- docs/design/architecture/data/audited-surfaces.json
- tests/deploy/test_rebaseline_reported.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – rebaseline maps reports with proof of installation; fold freshness

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `fix/deploy-runtime-installed-report` · **Merge target branch**: `fix/deploy-runtime-installed-report`. Worktrees come from `lanes.json`.

## Context

Spec: `spec.md`, especially FR-001–FR-010 and C-001/C-002. Plan: `plan.md` (the IC named below). Contract: `contracts/installed-report.md`, which is authoritative for format, reader rules, mapper rules and result keys. Data model: `data-model.md`. Review dispositions: `research.md`.

## Objective (IC-04, plus the rebaseline half of IC-05)

`baselines_for_installed_report`; `host_paths` in the registry; `observe()` preserves fold fields; `fold_manifest_baselines` stamps `last_fold_utc` and persists names; `_within_grace` honors `last_fold_utc`.

## Subtasks

### T011 – Registry

Add `"host_paths": ["~/.config/systemd/user/"]` to the `systemd-user-units` surface in `audited-surfaces.json`, by text insertion with no reformatting. Update its description and the file's `last_updated` / `updated_by`. `validate_architecture_data.py` must pass.

### T012 – Mapper `baselines_for_installed_report(report, repo_root, home, registry=None)`

- A rejected or missing report returns `{"baselines": [], "rejected": report.rejected, ...}`.
- Set `root = Path(repo_root).resolve()`.
- Read the registry with the same non-exiting read `observe` uses. If it is unreadable, return nothing plus a warning.
- For each entry:
  - `src = Path(source).resolve()`, which must satisfy `is_relative_to(root)`;
  - make `src` repo-relative;
  - `match_surfaces([rel], registry)`;
  - the matched surfaces that declare `host_paths`: for each, expand `~` against `home`, then `.resolve()`;
  - `dest = Path(dest).resolve()` must be `is_relative_to` one of those roots.
- **Any** entry whose source is outside the repo, or that matches a surface with `host_paths` but whose destination lies outside all of them, rejects the **whole** report.
- A source matching no surface, or only surfaces without `host_paths`, contributes nothing and is not an error.
- Return `{"baselines": sorted union, "rejected": bool, "matched": [...], "warnings": [...]}`.
- It never raises.

### T013 – Fold freshness and names

- In `fold_manifest_baselines`, on a merge, set `token["last_fold_utc"] = now_iso` and persist `token["manifest_names"] = sorted(set(existing names) | set(names))`.
- In `observe()`'s merge (around `rebaseline.py:325–358`), preserve `last_fold_utc` and `manifest_names` from the existing token.
- In `_within_grace`, measure age from `max(pending_since_utc, last_fold_utc)`.
- Leave `_maybe_stale` unchanged.

### T014 – Mapper tests (`tests/deploy/test_rebaseline_reported.py`)

Use the real registry and a `tmp_path` repo root that contains `scripts/sync/systemd/x.timer`, with `home` set to a `tmp_path` home. Cases:

- the 0029 shape (source under the repo, destination under `home/.config/systemd/user`) gives the four systemd-user-units baselines;
- a scratch destination gives a rejected report with no baselines;
- a source outside the repo is rejected;
- one bad entry among good ones gives a whole-report rejection;
- an unmatched source gives no baselines and no rejection;
- a symlinked repo root and a symlinked home are both accepted;
- a destination symlink pointing outside the host path is rejected;
- an unreadable registry (inject a registry error) gives a warning and no baselines.

### T015 – Freshness tests

- Old token (`pending_since` 1 hour ago) → fold → clean reconcile within 330 s keeps the token (`pending_clean`).
- Old token → fold → `observe` with a matching change → `last_fold_utc` and `manifest_names` are retained.
- A stale alert still uses `pending_since_utc`.
- Existing `tests/deploy/test_rebaseline.py` stays green and unchanged.

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP04 --note "…"` · implement: `spec-kitty agent action implement WP04 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
