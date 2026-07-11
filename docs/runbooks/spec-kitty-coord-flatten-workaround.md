---
id: spec-kitty-coord-flatten-workaround
doc_type: runbook
title: "Spec-Kitty coord-topology flatten workaround"
status: active
level: howto
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-07-11
version: 1
---

# Spec-Kitty coord-topology flatten workaround

**When to use this**: a solo, PR-bound spec-kitty mission (our standard Felix mission shape,
created with `--start-branch <feat>`) was assigned the **`coord` topology**, which is redundant
for a single-agent feature-branch mission and causes recurring friction — dirty-tree gate
failures, stranded/empty coordination worktrees, and merge-time working-tree invariant errors.
This runbook flattens such a mission to the equivalent **`lanes` topology on the primary
checkout**, so all artifacts + status route to the feature branch and the friction disappears.

> **Cheapest path is prevention.** If you catch the redundant coord topology *before*
> `finalize-tasks`, flattening is a one-line `meta.json` edit (no seed-event or lane-base
> reconciliation needed). Post-finalize, use the full procedure below. Better still, when the
> upstream fix lands (see **Upstream status**), coord topology should stop being assigned to
> solo PR-bound missions at all.

## Upstream status (check before assuming this is still needed)

| Upstream | What | Our tracker |
|----------|------|-------------|
| [Priivacy-ai/spec-kitty#2533](https://github.com/Priivacy-ai/spec-kitty/issues/2533) | PR-bound `--start-branch` mission gets redundant coord topology; coord worktree stranded → `spec-commit` split-brain fallback | kentonium3/kg-automation#709 |
| [Priivacy-ai/spec-kitty#2549](https://github.com/Priivacy-ai/spec-kitty/issues/2549) | `move-task --force` from a lane commits `status.*` to the lane branch (self-rejected); `finalize-tasks --json` reports one `commit_hash` across a two-branch commit set | kentonium3/kg-automation#710 |

When both are released **and** we've upgraded to consume them, retest the solo PR-bound flow and
retire this runbook (advance the trackers to `upstream-released`).

## Background — why the friction happens

Spec-Kitty 3.2.6 partitions mission files (`mission_runtime/artifacts.py`):
- **`_PRIMARY_ARTIFACT_KINDS`** (spec/plan/tasks.md/`tasks/WP*`/lanes.json/meta) → commit to the
  `target_branch` (the feature branch).
- **`_PLACEMENT_ARTIFACT_KINDS`** (`status.events.jsonl`, `status.json`, `acceptance-matrix.json`,
  `issue-matrix.md`, `analysis-report.md`) → commit to the **coordination branch** under coord
  topology; their stale primary copies are "coordination residue".

For a solo PR-bound mission this split is pure overhead: the placement artifacts sit on a coord
branch the feature branch (the merge target) can't see, the primary checkout is left with
untracked residue that trips dirty-tree gates (`record-analysis`, `implement`), and the tool's
suggested fixes (`doctor sparse-checkout --fix`, blanket `git add -f && commit`) either no-op or
mis-place files.

## The flatten mechanism

`meta.json` carries `topology` and a separate `flattened` provenance flag. Routing is decided by
`routes_through_coordination(topology)` → true only for `COORD`/`LANES_WITH_COORD`.
`classify_topology(coordination_branch, has_lanes)` returns:
- coord + lanes → `LANES_WITH_COORD`; coord only → `COORD`; lanes only → **`LANES`**; neither → `SINGLE_BRANCH`.

So after `finalize-tasks` (when `lanes.json` exists), removing `coordination_branch` and setting
`topology: lanes` yields a **flattened LANES** mission that routes everything to the primary
(feature) branch. There is **no `spec-kitty` flatten command** — it is a manual `meta.json` edit
(the #2533 warning itself prescribes it).

## Procedure (post-`finalize-tasks`)

**Prereq: quit Obsidian** if `docs/` is your Obsidian vault (the Better-Markdown-Links plugin
rewrites link syntax in the working tree and races spec-kitty's working-tree checks — see
[obsidian-better-markdown-links memory] / step 6). Back up first:
`cp kitty-specs/<slug>/meta.json /tmp/meta.json.bak` and
`cp kitty-specs/<slug>/status.events.jsonl /tmp/status.events.jsonl.bak`.

**1. Flatten `meta.json`** (workflow-managed file — do this only as the sanctioned recovery):
- remove the `"coordination_branch": ...` key;
- set `"topology": "lanes"` (NOT left as `coord`, or routing stays coord);
- set `"flattened": true`.

**2. Commit the flattened meta + the COMPLETE event log + status to the feature branch**:
```
spec-kitty spec-commit --mission <slug> -m "flatten redundant coord topology to lanes+primary" \
  kitty-specs/<slug>/meta.json kitty-specs/<slug>/status.events.jsonl \
  kitty-specs/<slug>/status.json kitty-specs/<slug>/analysis-report.md
```
Now flattened, these placement kinds route to the feature branch.

**3. Reconcile the bootstrap seed events (the post-finalize gotcha).** `finalize-tasks` emits 7
(one per WP) `genesis → planned` "canonical bootstrap" events that are placement-partition, so
they were committed to the **coord branch**, not the primary event log. After de-linking coord,
`spec-kitty next` reports `blocked / "no actionable wp"` and all WPs read `genesis`/unseeded.
`move-task --to planned` does **not** re-seed (it's a rejection-return that demands review
feedback). **Fix: merge the coord branch's seed events into the primary `status.events.jsonl`**:
```
git show kitty/mission-<slug>:kitty-specs/<slug>/status.events.jsonl   # the 7 seed events
```
Concatenate them with the primary log, sort by the event `timestamp`/`at` field (the seeds come
right after `TasksCompleted`), write the merged file, and `spec-commit` it. They are real
finalize-authored events, just relocated. → WPs flip to `planned`, `next` → `implement`.

**4. Commit any regenerated `status.json`**, then confirm `spec-kitty agent action implement WP01`
passes the planning-state gate.

**5. Fix the lane base (the 2nd post-finalize gotcha).** `lanes.json` bases lane worktrees off
`mission_branch` (`kitty/mission-<slug>`), which stayed stale/diverged and lacks the
primary-partition planning artifacts — so a claimed WP's lane worktree is missing `tasks/WP*`,
`data-model.md`, `contracts/`. Flatten does **not** redirect it. Fix:
```
git worktree remove --force .worktrees/<slug>-coord        # remove the orphaned coord worktree
git worktree remove --force .worktrees/<slug>-lane-<X>     # remove any stale lane worktree(s)
git branch -f kitty/mission-<slug> feat/<branch>           # reset mission branch ref to feat HEAD
spec-kitty agent action implement WP01 --agent claude --mission <slug>   # re-cut the lane off feat
```
Verify the lane worktree now contains `tasks/WP*`, `data-model.md`, `contracts/`, and source
before dispatching an implementer.

**6. Merge with Obsidian quit.** The post-merge working-tree invariant check races the
Better-Markdown-Links plugin (it re-wraps `](path)` → `](<path>)` faster than the merge
completes, tripping "paths diverge from HEAD" and suggesting the wrong `doctor sparse-checkout
--fix`). **Quit Obsidian before `spec-kitty merge`**; then the merge's "record WPs done" step
passes. Re-running merge while the race persists just adds redundant squash-merge commits
(harmless history noise). Pre-wrapping links in `<>` in the source is an alternative but quitting
Obsidian is the reliable fix.

## Gotcha summary (why "just remove coordination_branch" is not enough post-finalize)

1. Must set `topology: lanes` too, not just remove `coordination_branch` (else routing stays coord).
2. The complete event log lives untracked in the primary checkout — commit it to feat.
3. The 7 `genesis→planned` seed events are stranded on the coord branch — merge them into the primary log.
4. `move-task --to planned` cannot re-seed (rejection-return semantics).
5. Lane worktrees base off the stale `mission_branch` — reset its ref to feat HEAD and re-claim.
6. Obsidian's link-wrap plugin races the merge invariant — quit Obsidian for the merge.

## Related

- [`docs/runbooks/spec-kitty-bug-reporting.md`](spec-kitty-bug-reporting.md) — dual-track bug filing.
- Obsidian Better-Markdown-Links transform is benign and repo-expected; do not fight it or file it as a spec-kitty bug.
- First applied end-to-end on mission `felix-canary-registry-01KX8T7B` (#327), 2026-07-11.
