---
affected_files: []
cycle_number: 1
mission_slug: portable-dotfiles-01M18D57
reproduction_command:
reviewed_at: '2026-08-30T05:28:20Z'
reviewer_agent: claude
wp_id: WP01
---

**Issue**: Released unstarted — blocked on a structural question the operator must answer.

WP01's deliverables (`dotfiles/README.md`, `secrets.example`, `.gitignore`, and the `core/`, `machines/`, `bin/` tree) belong to the private `kentonium3/dotfiles` repo. But the lane worktree is a **kg-automation** worktree, so anything created at those paths is committed to `kitty/mission-portable-dotfiles-01M18D57-lane-a` and eventually merged to kg-automation `main` — which is **public**.

C-004 forbids exactly that: *"kg-automation is public and must not gain shell config."* That constraint came from an explicit operator decision, so proceeding would override it.

No work was started. Lane worktree created by the claim; tree otherwise clean.

**Options for the operator** — all preserve C-004:

1. **Kittify `~/repos/dotfiles`** and run the mission there. Cleanest end state: `owned_files` become natural, content stays private, review reads real code. Cost: specify/plan/tasks must be re-run in that repo; tracking splits from kg-automation#911.
2. **Keep the mission in kg-automation, make each WP's artifact an implementation *record*** under `kitty-specs/`, with the code landing in the private repo and referenced by SHA. Cost: review inspects records plus out-of-tree files rather than an in-tree diff.
3. **Relax C-004** and let the shell config live in public kg-automation. Cost: publishes PATH layout, aliases and repo topology — none of it secret, and CLAUDE.md already describes the account split publicly, but it reverses a deliberate decision.

Not decided autonomously per the autopilot contract: *"Surface genuine judgment calls; do not decide the operator's decisions."*
