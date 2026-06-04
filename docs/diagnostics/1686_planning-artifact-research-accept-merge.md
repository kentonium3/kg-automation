# Bug: research-mission accept/merge fails for planning_artifact lanes — missing mission branch, acceptance-matrix.json, and path conventions

**Filed upstream**: [Priivacy-ai/spec-kitty#1686](https://github.com/Priivacy-ai/spec-kitty/issues/1686) (2026-06-04). Internal tracking: [kentonium3/kg-automation#521](https://github.com/kentonium3/kg-automation/issues/521).

## Summary

On spec-kitty 3.1.8, a `research` mission whose WPs all carry `execution_mode: planning_artifact` collapses to a single `lane-planning` lane (verified via `lanes.json` after `finalize-tasks`). All planning artifacts land directly on the target branch (e.g., `main`) via the implement-review loop — no `kitty/mission-<slug>` branch is ever created, no worktrees are allocated, and the `acceptance-matrix.json` artifact is never generated.

When all WPs reach `approved` and the workflow attempts to close the mission, both `spec-kitty merge` and `spec-kitty accept` fail with structural validation errors that demand artifacts the planning_artifact code path never produces.

## Reproduction

Any `research` mission where:

- `meta.json` has `mission_type: "research"` (set at create time via `--mission-type research`)
- All WPs are tagged `execution_mode: "planning_artifact"` (the natural choice for research deliverables that live in markdown + ADRs + filed GitHub sub-issues)
- `finalize-tasks` collapses all WPs into a single `lane-planning` lane
- The implement-review loop runs to completion with all WPs `approved`
- `spec-kitty merge` or `spec-kitty accept` is invoked

Will reproduce all three failures below.

### Observed merge failure

```text
$ spec-kitty merge --mission <slug>
Lane-based merge for <slug>
  Mission branch: kitty/mission-<slug>
  Lanes: lane-planning
  ✓ Gate evidence: All 3 WPs have review approval
  ✓ Gate risk: Risk score 0.00 within threshold
  ✓ Gate dependency: All dependencies complete
  Checking and merging lane-planning...
  ✗ lane-planning: Failed to create merge worktree: fatal: invalid reference: kitty/mission-<slug>
```

### Observed accept failure

```text
$ spec-kitty accept --mission <slug> --no-commit --json
{
  ...
  "all_done": true,
  "ok": false,
  "activity_issues": [
    "Acceptance must run on mission branch kitty/mission-<slug>, not main",
    "Acceptance matrix (acceptance-matrix.json) is required for lane-based features but was not found"
  ],
  "path_violations": [
    "Path Convention Errors:\n  - Deep Research Kitty expects workspace path: research/ (not found)\n  - Deep Research Kitty expects data path: data/ (not found)\n  - Deep Research Kitty expects deliverables path: findings/ (not found)\n  - Deep Research Kitty expects documentation path: reports/ (not found)\n\nRequired Actions:\n  - Create directories in one go: mkdir -p research/ data/ findings/ reports/"
  ],
  "warnings": [
    "Optional artifacts missing: quickstart.md, contracts",
    "Path conventions not satisfied."
  ]
}
```

## Three distinct gaps, one root cause

The validator does not know about `planning_artifact` execution mode.

1. **Mission branch never created.** `planning_artifact` lane execution skips `git branch kitty/mission-<slug>`, but `accept` and `merge` both assume it exists.

2. **`acceptance-matrix.json` never generated.** No prior step writes it, but the validator requires it for lane-based features.

3. **Path conventions checked at repo root, not at the mission's documented deliverables path.** The research-kitty `plan-template.md` line ~118 explicitly says:

   > **Deliverables Path**: `docs/research/[###-research-name]/`
   > *(Update this path during planning - e.g., `docs/research/001-cancer-cure/`, `research-outputs/market-analysis/`)*

   But the `spec-kitty accept` path validator looks for `research/`, `data/`, `findings/`, `reports/` **at the repo root**, ignoring the configured `deliverables_path` in `meta.json`. This is a direct contradiction between the documented research-kitty convention and the enforced validator behavior.

## Expected Behavior

For a `research` mission whose WPs are all `planning_artifact`:

- **Option A**: `accept` and `merge` recognize planning_artifact execution mode and either skip the branch/worktree/matrix checks entirely, or run a planning-mode equivalent that closes the mission without requiring artifacts that the execution path never creates.
- **Option B**: The implement-review loop for planning_artifact missions creates the `kitty/mission-<slug>` branch + `acceptance-matrix.json` as part of `finalize-tasks` or first `implement` invocation, so they exist when `accept`/`merge` runs.
- The path validator reads `deliverables_path` from `meta.json` (the configured value documented by `plan-template.md`) instead of looking for fixed top-level paths.

## Workaround Applied

`spec-kitty agent tasks move-task <WP> --to done --done-override-reason "<rationale>"` advances each approved WP individually. This succeeds via the documented `--done-override-reason` field (which already exists for "merge ancestry cannot be verified" cases). It bypasses the merge bookkeeping entirely.

This workaround is not destructive — it uses a documented CLI escape hatch — but it leaves the mission without the formal acceptance artifact (`acceptance-matrix.json`) and without the `kitty/mission-<slug>` branch in git history. For audit purposes, the actual research deliverables are present on `main` and the operator acceptance is recorded as a GitHub comment on the source issue.

## Environment

- spec-kitty-cli: 3.1.8
- Mission type: `research` (Deep Research Kitty)
- All 3 WPs `execution_mode: "planning_artifact"`
- Operator acceptance gate satisfied via GitHub comment on source issue (research-kitty convention: SC-007 via `kentonium3/kg-automation#508` comment, not via spec-kitty `accept`)
- macOS Darwin 26.5 / Python 3.13.13 / pipx install

## Related Upstream

Searched open + closed issues for "planning_artifact accept merge", "research mission accept path conventions", "Deep Research Kitty workspace path findings reports", "acceptance-matrix planning_artifact lane-planning" — no prior match found. Adjacent:

- `#960` (closed, fixed in v3.2.0a10) — `move-task` rejection from `in_review` lacks structured `ReviewResult` evidence. Different code path but same shape of bug: CLI surface contradicts internal validator. We hit `#960` mid-mission and worked around via direct Python API; tracked as separate internal issue [kentonium3/kg-automation#517](https://github.com/kentonium3/kg-automation/issues/517).
