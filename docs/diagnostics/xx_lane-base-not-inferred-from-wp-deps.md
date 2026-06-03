# Bug: lane base ignores WP-level dependencies; sibling-lane work not propagated to dependent lanes

## Summary

Spec-kitty does not propagate work between dependent lanes. When a work package declares `dependencies: [WP##]` in its frontmatter and the dependency has been approved on a sibling lane, the dependent WP's worktree is created from the bare mission branch instead of the approved lane's tip. The dependent WP cannot import from the prior WP's modules and tests cannot run. Spec-kitty's own implement/review skill documentation states *"implementation workspace base is inferred automatically from the approved dependency graph"* — this is not the observed behavior. Workaround requires manual `git reset --hard` per dependent lane, which the spec-kitty git-workflow skill explicitly forbids.

## Reproduction

### Prerequisites

- `spec-kitty-cli` 3.1.1+
- A mission with two or more WPs where downstream WPs import code from earlier WPs (any sequential-dependency mission)
- WP frontmatter contains `dependencies: [WP##]` in the format produced by `spec-kitty agent mission finalize-tasks`

### Steps

```bash
# Mission scaffolding (assumes WP02 declares dependencies: [WP01])
spec-kitty agent mission create "test-sequential" --json
# ... author tasks.md with two WPs, WP02 depending on WP01 ...
spec-kitty agent tasks map-requirements --batch '{...}' --mission test-sequential --json
spec-kitty agent mission finalize-tasks --mission test-sequential --json

# Implement + approve WP01 normally
spec-kitty agent action implement WP01 --mission test-sequential --agent <name>
# ... implement, commit, mark done, move to for_review, approve ...

# Claim WP02 and inspect lane-b's base
spec-kitty agent action implement WP02 --mission test-sequential --agent <name>
cd .worktrees/test-sequential-lane-b
git log --oneline -3
ls scripts/<wp01-module-directory>/      # empty — WP01 code not present
```

### Expected Behavior

Per the implement/review skill (Linear Dependency Chain section):

> *"THEN implement WP02, review, approve. The implementation workspace base is inferred automatically from the approved dependency graph."*

Lane-b's HEAD should be at lane-a's tip (or at least at a commit containing lane-a's approved work). WP02's implementer should be able to import from WP01's modules and run tests.

### Actual Behavior

Lane-b's HEAD is at the pre-implementation mission-branch tip. WP01's commits exist only on the lane-a branch and are not visible on lane-b.

```text
# lanes.json after finalize-tasks (excerpt)
"lanes": [
  {
    "lane_id": "lane-a",
    "wp_ids": ["WP01"],
    "depends_on_lanes": [],
    "parallel_group": 0
  },
  {
    "lane_id": "lane-b",
    "wp_ids": ["WP02"],
    "depends_on_lanes": [],
    "parallel_group": 0
  }
]
```

`depends_on_lanes` is empty for lane-b despite WP02's frontmatter declaring `dependencies: [WP01]`. Every lane is independently rooted at the mission branch.

Additionally, the `finalize-tasks --json` output includes `"dependencies_parsed": {}` (empty for all WPs), suggesting WP frontmatter dependencies may not be consumed by the lane resolver at all — even though `finalize-tasks` itself reads and writes those frontmatter entries.

## Root Cause

The lane resolver in `finalize-tasks` does not translate WP-level `dependencies: [WP##]` (declared in WP frontmatter) into lane-level `depends_on_lanes` (recorded in `lanes.json`). Consequently:

- `lanes.json` reports all lanes as `parallel_group: 0` with `depends_on_lanes: []`
- `agent action implement WP##` creates the worktree from the mission branch unconditionally
- No mechanism exists to consult dependency-graph state at lane-creation time

The `collapse_report` field in `lanes.json` (`{"events": [], "total_merges": 0, "independent_wps_collapsed": 0, "by_rule": {}}`) suggests the resolver only collapses *parallel* groups, not *dependency chains*.

## Workaround Applied

For each dependent lane after its predecessor is approved, manually reset the dependent worktree's HEAD to the predecessor lane's tip:

```bash
cd /path/to/repo/.worktrees/<mission>-lane-<n>
git reset --hard kitty/mission-<mission>-lane-<n-1>
```

Repeated per WP boundary in dependency order. After the final WP merges, `spec-kitty merge` runs cleanly with no stale-lane conflicts — the workaround is benign at the merge layer.

Alternative workaround: split sequential-dependency missions into separate missions, merging each to main before starting the next. More invasive — abandons existing mission planning artifacts and adds a full mission-creation/merge round-trip per dependency boundary.

## Environment

- OS: macOS Darwin 26.5
- Python: 3.13.13
- spec-kitty-cli: 3.1.8 (CLI binary; behavior originally observed against 3.1.1, persists through 3.1.8 with no changelog entry indicating a fix)
- Confirmed not addressed in: 3.2.0rc36 (latest pre-release, 2026-06-03) — see Related Upstream

## Related Upstream

Searched open + closed issues and PRs under `Priivacy-ai/spec-kitty` for terms covering "lane dependency", "depends_on_lanes", "lane base", "dependency chain", "WP01 WP02 base", "lane sequencing", "finalize-tasks dependencies", "sequential WP", and "WP propagation". No issue or PR found that matches this exact symptom (WP-level `dependencies: [WP##]` not translated into lane-level `depends_on_lanes` or worktree base resolution). Adjacent items:

- `#1236` (closed 2026-05-21): "Lane-collapse algorithm ignores owned_files disjointness; downstream-only WP collapses every upstream into one lane" — opposite-direction bug (collapses too aggressively rather than not at all). Confirms the lane resolver does some dependency reasoning but only via collapse, never via dependent-base inference.
- `#1619` (open Epic, 2026-06-02): "Unify mission execution context across coord/main/lane topology" — names "dependency checks reading stale state" as one of the broader failure class symptoms, and references `src/specify_cli/cli/commands/implement.py:747-753` reading dependency lanes from a main-checkout `feature_dir`. The lane-base-from-WP-dependency case is plausibly downstream of this Epic but not enumerated as a sub-issue.
- `#1666` (open, blocks #1619): "Execution-state & context domain-boundary redesign" — the parent architectural redesign for the broader area; design notes merged via #1671 but implementation has not landed.
- `#1672` (open, 2026-06-03): "Strangler step 1: e2e parity ratchet — next→implement→move-task→review→status from main and lane CWD" — gating test for the Strangler arc, but its acceptance criteria cover CWD-parity only, not dep-graph correctness.

CHANGELOG search for 3.2.0rc1..rc36 returns dependency-related fixes scoped to different surfaces (cycle detection #1589, dependency-parser trailing-prose bleed, finalize-tasks dependency-prose false positives, dependency-source precedence tweaks). None describe translating WP-level dependencies into lane-base resolution.

Net read: the broader execution-state area is under active redesign but this specific symptom is not enumerated and not fixed in 3.2.0rc36.
